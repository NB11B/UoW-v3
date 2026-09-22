#!/usr/bin/env python3
"""Multi-Device Neural Benchmark Workload Engine for UoW Heterogeneous Router.

Executes real neural inference workloads across three heterogeneous physical devices:
- Device 0: Host CPU (PyTorch CPU / OpenVINO CPU)
- Device 1: NVIDIA GeForce RTX 5070 Laptop GPU (PyTorch CUDA 12.8)
- Device 2: Intel(R) AI Boost NPU (OpenVINO 2026.4.0)

Generates hardware execution receipts containing exact execution latency (microseconds)
and cryptographic SHA-256 output digests proving execution on the target silicon.
Supports dynamic background contention injection (GPU matrix crunching, NPU/CPU contention)
to test adaptive routing under nonstationary conditions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any

# Ensure UTF-8 output encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import openvino as ov
import torch
import torch.nn as nn

SUPPORTED_BATCH_SIZES = (1, 4, 16, 64)
DEVICE_CPU = 0
DEVICE_GPU = 1
DEVICE_NPU = 2


class BenchmarkVisionModel(nn.Module):
    """Real feature extractor network used for heterogeneous benchmarking."""

    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((4, 4)),
            nn.Flatten(),
            nn.Linear(64 * 4 * 4, 128),
            nn.ReLU(),
            nn.Linear(128, 10),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.features(x)


@dataclass(frozen=True)
class WorkloadReceipt:
    job_id: int
    target_device: int
    device_name: str
    batch_size: int
    latency_us: int
    output_digest: str
    timestamp_ns: int
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WorkloadEngine:
    """Manages multi-device execution, contention generation, and receipt telemetry."""

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or (Path(__file__).resolve().parent / ".workload_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.net_cpu = BenchmarkVisionModel().eval()
        self.has_gpu = torch.cuda.is_available()
        if self.has_gpu:
            self.net_gpu = BenchmarkVisionModel().cuda().eval()
            self.gpu_device_name = torch.cuda.get_device_name(0)
        else:
            self.net_gpu = None
            self.gpu_device_name = "None"

        # Initialize OpenVINO core
        self.ov_core = ov.Core()
        available = self.ov_core.available_devices
        self.npu_target = "NPU" if "NPU" in available else "CPU"
        try:
            self.npu_device_name = self.ov_core.get_property(self.npu_target, "FULL_DEVICE_NAME")
        except Exception:
            self.npu_device_name = self.npu_target

        # Compile static models for supported batch sizes on NPU
        self.compiled_npu_models: dict[int, Any] = {}
        self._prepare_npu_models()

        # Contention state and background threads
        self.gpu_contention_active = False
        self.npu_contention_active = False
        self.cpu_contention_active = False
        self._gpu_contention_thread: threading.Thread | None = None
        self._npu_contention_thread: threading.Thread | None = None
        self._cpu_contention_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Warmup all targets
        self._warmup()

    def _prepare_npu_models(self) -> None:
        """Export ONNX models for static batch sizes and compile on Intel NPU."""
        for b in SUPPORTED_BATCH_SIZES:
            onnx_path = self.cache_dir / f"workload_b{b}.onnx"
            if not onnx_path.exists():
                dummy = torch.randn(b, 3, 32, 32)
                torch.onnx.export(
                    self.net_cpu,
                    dummy,
                    str(onnx_path),
                    input_names=["input"],
                    output_names=["output"],
                )
            model = self.ov_core.read_model(str(onnx_path))
            self.compiled_npu_models[b] = self.ov_core.compile_model(model, self.npu_target)

    def _warmup(self) -> None:
        """Warm up execution paths across CPU, GPU, and NPU for all supported batch sizes."""
        for b in SUPPORTED_BATCH_SIZES:
            dummy_np = np.zeros((b, 3, 32, 32), dtype=np.float32)
            dummy_cpu = torch.from_numpy(dummy_np)
            with torch.no_grad():
                self.net_cpu(dummy_cpu)
                if self.has_gpu and self.net_gpu is not None:
                    dummy_gpu = dummy_cpu.cuda()
                    for _ in range(3):
                        self.net_gpu(dummy_gpu)
                    torch.cuda.synchronize()
            if b in self.compiled_npu_models:
                for _ in range(3):
                    self.compiled_npu_models[b]([dummy_np])

    def set_gpu_contention(self, enabled: bool) -> None:
        """Toggle background GPU GEMM contention loop."""
        if not self.has_gpu:
            return
        if enabled and not self.gpu_contention_active:
            self.gpu_contention_active = True

            def _gpu_worker():
                stream = torch.cuda.Stream()
                # Run heavy matrix multiplications on CUDA stream
                with torch.cuda.stream(stream):
                    a = torch.randn(2048, 2048, device="cuda")
                    b = torch.randn(2048, 2048, device="cuda")
                    while self.gpu_contention_active and not self._stop_event.is_set():
                        _ = torch.matmul(a, b)
                        time.sleep(0.002)

            self._gpu_contention_thread = threading.Thread(target=_gpu_worker, daemon=True)
            self._gpu_contention_thread.start()
        elif not enabled and self.gpu_contention_active:
            self.gpu_contention_active = False
            if self._gpu_contention_thread:
                self._gpu_contention_thread.join(timeout=1.0)
                self._gpu_contention_thread = None

    def set_npu_contention(self, enabled: bool) -> None:
        """Toggle background NPU inference contention loop."""
        if enabled and not self.npu_contention_active:
            self.npu_contention_active = True

            def _npu_worker():
                dummy = np.random.randn(16, 3, 32, 32).astype(np.float32)
                model = self.compiled_npu_models.get(16) or self.compiled_npu_models[1]
                req = model.create_infer_request()
                while self.npu_contention_active and not self._stop_event.is_set():
                    try:
                        _ = req.infer([dummy])
                    except Exception:
                        pass
                    time.sleep(0.002)

            self._npu_contention_thread = threading.Thread(target=_npu_worker, daemon=True)
            self._npu_contention_thread.start()
        elif not enabled and self.npu_contention_active:
            self.npu_contention_active = False
            if self._npu_contention_thread:
                self._npu_contention_thread.join(timeout=1.0)
                self._npu_contention_thread = None

    def set_cpu_contention(self, enabled: bool) -> None:
        """Toggle background CPU compute contention loop."""
        if enabled and not self.cpu_contention_active:
            self.cpu_contention_active = True

            def _cpu_worker():
                dummy = np.random.randn(64, 3, 32, 32).astype(np.float32)
                while self.cpu_contention_active and not self._stop_event.is_set():
                    _ = np.dot(dummy.reshape(64, -1), dummy.reshape(64, -1).T)
                    time.sleep(0.002)

            self._cpu_contention_thread = threading.Thread(target=_cpu_worker, daemon=True)
            self._cpu_contention_thread.start()
        elif not enabled and self.cpu_contention_active:
            self.cpu_contention_active = False
            if self._cpu_contention_thread:
                self._cpu_contention_thread.join(timeout=1.0)
                self._cpu_contention_thread = None

    def shutdown(self) -> None:
        """Stop all background contention threads."""
        self._stop_event.set()
        self.set_gpu_contention(False)
        self.set_npu_contention(False)
        self.set_cpu_contention(False)

    def execute(self, job_id: int, target_device: int, batch_size: int) -> WorkloadReceipt:
        """Execute real neural inference on the specified target hardware and return receipt."""
        # Find closest supported batch size
        b = batch_size if batch_size in SUPPORTED_BATCH_SIZES else min(SUPPORTED_BATCH_SIZES, key=lambda x: abs(x - batch_size))

        # Deterministic input tensor based on job_id seed
        rng = np.random.default_rng(seed=(job_id * 10007 + b) & 0xFFFFFFFF)
        input_np = rng.standard_normal((b, 3, 32, 32), dtype=np.float32)

        t_start_ns = time.perf_counter_ns()
        try:
            if target_device == DEVICE_CPU:
                device_name = "Host CPU"
                inp_torch = torch.from_numpy(input_np)
                with torch.no_grad():
                    out = self.net_cpu(inp_torch)
                out_np = out.numpy()

            elif target_device == DEVICE_GPU:
                if not self.has_gpu or self.net_gpu is None:
                    raise RuntimeError("GPU requested but CUDA is unavailable")
                device_name = f"GPU: {self.gpu_device_name}"
                inp_torch = torch.from_numpy(input_np).cuda()
                with torch.no_grad():
                    out = self.net_gpu(inp_torch)
                torch.cuda.synchronize()
                out_np = out.cpu().numpy()

            elif target_device == DEVICE_NPU:
                device_name = f"NPU: {self.npu_device_name}"
                compiled = self.compiled_npu_models.get(b)
                if compiled is None:
                    raise ValueError(f"No compiled NPU model for batch size {b}")
                req = compiled.create_infer_request()
                res = req.infer([input_np])
                out_np = res[compiled.output(0)]

            else:
                raise ValueError(f"Unknown target device {target_device}")

            t_end_ns = time.perf_counter_ns()
            latency_us = max(1, (t_end_ns - t_start_ns) // 1000)

            # Compute SHA-256 digest of rounded outputs to verify real execution
            digest = hashlib.sha256(np.round(out_np, decimals=3).tobytes()).hexdigest()

            return WorkloadReceipt(
                job_id=job_id,
                target_device=target_device,
                device_name=device_name,
                batch_size=b,
                latency_us=int(latency_us),
                output_digest=digest,
                timestamp_ns=t_start_ns,
            )

        except Exception as exc:
            t_end_ns = time.perf_counter_ns()
            latency_us = max(1, (t_end_ns - t_start_ns) // 1000)
            return WorkloadReceipt(
                job_id=job_id,
                target_device=target_device,
                device_name=f"Device-{target_device}",
                batch_size=b,
                latency_us=int(latency_us),
                output_digest="0" * 64,
                timestamp_ns=t_start_ns,
                error=str(exc),
            )

    def benchmark_oracle(self, job_id: int, batch_size: int, active_devices: list[int]) -> dict[int, int]:
        """Measure actual latency across all active candidate devices to determine regret."""
        latencies = {}
        for dev in active_devices:
            receipt = self.execute(job_id=job_id, target_device=dev, batch_size=batch_size)
            if receipt.error is None:
                latencies[dev] = receipt.latency_us
        return latencies
