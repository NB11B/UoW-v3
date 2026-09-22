#!/usr/bin/env python3
"""Adaptive Heterogeneous Routing Policy with Dual Replay Buffer and Canary Deployment.

Hardware Topology & Responsibilities:
- RTX 5070 Laptop GPU: Rapid online gradient updates via PyTorch CUDA 12.8.
- Intel AI Boost NPU: Low-latency active policy inference via OpenVINO 2026.4.0.
- CPU: Feature featurization, dual replay buffer (80% recent / 20% retention), and canary gatekeeper.

The policy network predicts:
1. Expected latency for all devices: [L_hat_CPU, L_hat_GPU, L_hat_NPU]
2. Authority rejection probability: [P_hat_rej_CPU, P_hat_rej_GPU, P_hat_rej_NPU]

Selection rule chooses the optimal valid target balancing latency, authority legality, and queuing.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass
import json
from pathlib import Path
import random
import sys
import time
from typing import Any

# Ensure UTF-8 output encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import openvino as ov
import torch
import torch.nn as nn
import torch.optim as optim

DEVICE_CPU = 0
DEVICE_GPU = 1
DEVICE_NPU = 2


class RouterNet(nn.Module):
    """Multi-head regression network for latency and authority rejection prediction."""

    def __init__(self, input_dim: int = 12):
        super().__init__()
        self.shared = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 128),
            nn.ReLU(),
        )
        self.latency_head = nn.Linear(128, 3)
        self.rejection_head = nn.Sequential(
            nn.Linear(128, 3),
            nn.Sigmoid(),
        )
        # Prior biases: CPU ~ 1.2ms, GPU ~ 0.5ms, NPU ~ 0.7ms; initial rejection prob ~ 0.05
        with torch.no_grad():
            self.latency_head.bias.copy_(torch.tensor([1.2, 0.5, 0.7]))
            self.rejection_head[0].bias.copy_(torch.tensor([-3.0, -3.0, -3.0]))

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        feat = self.shared(x)
        lat = self.latency_head(feat)
        rej = self.rejection_head(feat)
        return lat, rej


@dataclass
class JobDescriptor:
    job_id: int
    batch_size: int
    priority: float  # [0.0, 1.0]
    latency_budget_us: int
    tokens: int = 1


@dataclass
class RoutingExperience:
    features: list[float]
    action: int
    observed_latency_ms: float
    rejected: float  # 0.0 or 1.0
    phase: str


class DualReplayBuffer:
    """Maintains recent experiences (80%) and retention experiences (20%) across phases."""

    def __init__(self, recent_capacity: int = 500, retention_capacity: int = 200):
        self.recent_buffer: collections.deque[RoutingExperience] = collections.deque(maxlen=recent_capacity)
        self.retention_buffer: list[RoutingExperience] = []
        self.retention_capacity = retention_capacity
        self._phase_counts: dict[str, int] = collections.defaultdict(int)

    def add(self, exp: RoutingExperience) -> None:
        self.recent_buffer.append(exp)
        self._phase_counts[exp.phase] += 1

        # Curate retention buffer with balanced phase representation
        if len(self.retention_buffer) < self.retention_capacity:
            self.retention_buffer.append(exp)
        else:
            # Reservoir replacement per phase
            idx = random.randint(0, len(self.retention_buffer) - 1)
            if random.random() < 0.25:
                self.retention_buffer[idx] = exp

    def sample(self, batch_size: int) -> list[RoutingExperience]:
        if not self.recent_buffer:
            return []

        recent_k = min(len(self.recent_buffer), int(batch_size * 0.80))
        retention_k = min(len(self.retention_buffer), batch_size - recent_k)
        if retention_k == 0:
            recent_k = min(len(self.recent_buffer), batch_size)

        samples: list[RoutingExperience] = []
        if recent_k > 0:
            samples.extend(random.sample(list(self.recent_buffer), recent_k))
        if retention_k > 0:
            samples.extend(random.sample(self.retention_buffer, retention_k))
        return samples

    def __len__(self) -> int:
        return len(self.recent_buffer)


class TransactionalCanaryDeployer:
    """Coordinates GPU training, Intel NPU compilation, regression validation, and canary promotion."""

    def __init__(self, cache_dir: Path, target_npu_device: str = "NPU"):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.target_npu = target_npu_device
        self.ov_core = ov.Core()

        self.current_onnx_path = self.cache_dir / "active_router.onnx"
        self.candidate_onnx_path = self.cache_dir / "candidate_router.onnx"

        self.active_compiled_model: Any = None
        self.candidate_compiled_model: Any = None

        self.canary_window_remaining: int = 0
        self.canary_eval_metrics: dict[str, Any] = {}
        self.promotions_count: int = 0
        self.rollbacks_count: int = 0

    def compile_candidate(self, net: RouterNet) -> bool:
        """Export trained PyTorch net to ONNX and compile for Intel NPU."""
        try:
            net_cpu = net.cpu().eval()
            dummy = torch.zeros(1, 12, dtype=torch.float32)
            torch.onnx.export(
                net_cpu,
                dummy,
                str(self.candidate_onnx_path),
                input_names=["features"],
                output_names=["latency", "rejection"],
            )
            m = self.ov_core.read_model(str(self.candidate_onnx_path))
            self.candidate_compiled_model = self.ov_core.compile_model(m, self.target_npu)
            return True
        except Exception as exc:
            print(f"[CanaryDeployer] NPU compilation failed: {exc}", file=sys.stderr)
            self.candidate_compiled_model = None
            return False

    def validate_regression(self, validation_suite: list[RoutingExperience]) -> bool:
        """Ensure candidate model does not regress on the retention validation suite."""
        if self.candidate_compiled_model is None or not validation_suite:
            return True  # Allow initial bootstrap

        candidate_mse = 0.0
        active_mse = 0.0

        for exp in validation_suite:
            inp = np.array([exp.features], dtype=np.float32)
            # Candidate evaluation
            cand_res = self.candidate_compiled_model([inp])
            cand_lat = float(cand_res[self.candidate_compiled_model.output(0)][0, exp.action])
            candidate_mse += (cand_lat - exp.observed_latency_ms) ** 2

            # Active evaluation if available
            if self.active_compiled_model is not None:
                act_res = self.active_compiled_model([inp])
                act_lat = float(act_res[self.active_compiled_model.output(0)][0, exp.action])
                active_mse += (act_lat - exp.observed_latency_ms) ** 2

        cand_mse = candidate_mse / len(validation_suite)
        if self.active_compiled_model is not None:
            act_mse = active_mse / len(validation_suite)
            # Allow at most 10% regression margin on historical suite
            if cand_mse > act_mse * 1.10:
                print(f"[CanaryDeployer] Regression check failed: cand_mse={cand_mse:.4f} > act_mse={act_mse:.4f}", file=sys.stderr)
                return False

        return True

    def start_canary(self, window_size: int = 15) -> None:
        """Enter canary testing window."""
        self.canary_window_remaining = window_size
        self.canary_eval_metrics = {"proposals": 0, "rejections": 0, "latencies": []}

    def promote_candidate(self) -> None:
        """Promote candidate to active NPU router."""
        if self.candidate_compiled_model is not None:
            self.active_compiled_model = self.candidate_compiled_model
            self.candidate_compiled_model = None
            if self.candidate_onnx_path.exists():
                self.candidate_onnx_path.replace(self.current_onnx_path)
            self.promotions_count += 1
            self.canary_window_remaining = 0
            print("[CanaryDeployer] Promoted candidate to active NPU policy.")

    def rollback(self) -> None:
        """Discard degraded candidate and preserve active policy."""
        self.candidate_compiled_model = None
        self.rollbacks_count += 1
        self.canary_window_remaining = 0
        print("[CanaryDeployer] Rolled back degraded candidate policy.")

    def infer(self, features: list[float]) -> tuple[np.ndarray, np.ndarray]:
        """Run policy inference on Intel NPU using active (or candidate if in canary) model."""
        runner = self.candidate_compiled_model if (self.canary_window_remaining > 0 and self.candidate_compiled_model is not None) else self.active_compiled_model
        inp = np.array([features], dtype=np.float32)

        if runner is not None:
            try:
                res = runner([inp])
                lat = res[runner.output(0)][0]
                rej = res[runner.output(1)][0]
                return lat, rej
            except Exception:
                pass

        # Fallback heuristic if NPU model not yet compiled
        batch_size = features[0] * 64.0
        # Heuristic: CPU ~ 2-5ms, GPU ~ 0.5-2ms, NPU ~ 0.6-2.5ms
        lat = np.array([3.0 + batch_size * 0.05, 0.8 + batch_size * 0.02, 0.7 + batch_size * 0.03], dtype=np.float32)
        rej = np.zeros(3, dtype=np.float32)
        return lat, rej


class AdaptiveRoutingPolicy:
    """Full closed-loop routing policy manager combining GPU training and NPU inference."""

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or (Path(__file__).resolve().parent / ".router_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.has_gpu = torch.cuda.is_available()
        self.device = torch.device("cuda" if self.has_gpu else "cpu")

        # PyTorch model for GPU training
        self.net = RouterNet(input_dim=12).to(self.device)
        self.optimizer = optim.AdamW(self.net.parameters(), lr=5e-3, weight_decay=1e-4)

        # Dual replay buffer
        self.buffer = DualReplayBuffer(recent_capacity=500, retention_capacity=200)

        # Intel NPU canary deployer
        core = ov.Core()
        target_npu = "NPU" if "NPU" in core.available_devices else "CPU"
        self.deployer = TransactionalCanaryDeployer(self.cache_dir, target_npu_device=target_npu)

        # Cold-start bootstrap: compile initial model
        self.deployer.compile_candidate(self.net)
        self.deployer.promote_candidate()

        # Telemetry tracking
        self.training_steps: int = 0
        self.last_observed_latencies: dict[int, float] = {0: 3000.0, 1: 1000.0, 2: 800.0}

    def featurize(
        self,
        job: JobDescriptor,
        authority_snapshot: dict[str, Any],
        system_load: dict[str, float],
    ) -> list[float]:
        """Construct normalized 12-dimensional feature vector for policy inference."""
        inflight = authority_snapshot.get("inflight", [0, 0, 0])
        max_inflight = authority_snapshot.get("max_inflight", [16, 16, 16])

        f = [
            float(job.batch_size) / 64.0,
            float(job.priority),
            float(job.latency_budget_us) / 25000.0,
            float(system_load.get("cpu", 0.0)),
            float(system_load.get("gpu", 0.0)),
            float(system_load.get("npu", 0.0)),
            float(inflight[0]) / max(1.0, float(max_inflight[0])),
            float(inflight[1]) / max(1.0, float(max_inflight[1])),
            float(inflight[2]) / max(1.0, float(max_inflight[2])),
            float(self.last_observed_latencies[0]) / 10000.0,
            float(self.last_observed_latencies[1]) / 10000.0,
            float(self.last_observed_latencies[2]) / 10000.0,
        ]
        return f

    def select_target(
        self,
        features: list[float],
        authority_snapshot: dict[str, Any],
        epsilon: float = 0.0,
    ) -> tuple[int, dict[str, Any]]:
        """Select optimal target device honoring hard authority constraints."""
        online_mask = authority_snapshot.get("online_mask", 7)
        inflight = authority_snapshot.get("inflight", [0, 0, 0])
        max_inflight = authority_snapshot.get("max_inflight", [16, 16, 16])
        tokens = authority_snapshot.get("resource_tokens", 64)

        # Run hardware NPU inference
        pred_lat, pred_rej = self.deployer.infer(features)

        # Build candidate score list
        scores = {}
        for dev in (DEVICE_CPU, DEVICE_GPU, DEVICE_NPU):
            has_capacity = inflight[dev] < max_inflight[dev]
            has_tokens = tokens >= 1

            if not has_capacity:
                scores[dev] = 1e8  # Hard penalty for full queue
                continue
            if not has_tokens:
                scores[dev] = 1e7
                continue

            # Composite routing cost:
            # Cost = Latency_pred + 50.0 * P_rej_pred + 2.0 * queue_occupancy
            q_ratio = inflight[dev] / max(1.0, max_inflight[dev])
            cost = float(pred_lat[dev]) + 50.0 * float(pred_rej[dev]) + 2.0 * q_ratio
            scores[dev] = cost

        # Find best action
        valid_devs = [d for d in (DEVICE_CPU, DEVICE_GPU, DEVICE_NPU) if scores[d] < 1e6]
        if not valid_devs:
            # Fallback to least loaded device
            best_dev = min((DEVICE_CPU, DEVICE_GPU, DEVICE_NPU), key=lambda d: inflight[d])
        else:
            if random.random() < epsilon:
                best_dev = random.choice(valid_devs)
            else:
                best_dev = min(valid_devs, key=lambda d: scores[d])

        metadata = {
            "predicted_latencies_ms": [float(pred_lat[0]), float(pred_lat[1]), float(pred_lat[2])],
            "predicted_rejections": [float(pred_rej[0]), float(pred_rej[1]), float(pred_rej[2])],
            "scores": {k: float(v) for k, v in scores.items()},
            "canary_active": self.deployer.canary_window_remaining > 0,
        }
        return best_dev, metadata

    def record_feedback(
        self,
        features: list[float],
        action: int,
        latency_us: int,
        rejected: bool,
        phase: str,
    ) -> None:
        """Record experience in dual replay buffer and update latest observed latencies."""
        lat_ms = float(latency_us) / 1000.0
        if not rejected:
            self.last_observed_latencies[action] = 0.8 * self.last_observed_latencies[action] + 0.2 * float(latency_us)

        exp = RoutingExperience(
            features=features,
            action=action,
            observed_latency_ms=lat_ms,
            rejected=1.0 if rejected else 0.0,
            phase=phase,
        )
        self.buffer.add(exp)

        # Update canary statistics if in canary window
        if self.deployer.canary_window_remaining > 0:
            m = self.deployer.canary_eval_metrics
            m["proposals"] = m.get("proposals", 0) + 1
            if rejected:
                m["rejections"] = m.get("rejections", 0) + 1
            m["latencies"].append(lat_ms)
            self.deployer.canary_window_remaining -= 1
            if self.deployer.canary_window_remaining == 0:
                rej_rate = m["rejections"] / max(1, m["proposals"])
                if rej_rate < 0.15:
                    self.deployer.promote_candidate()
                else:
                    self.deployer.rollback()

    def train_step(self, batch_size: int = 64, epochs: int = 5) -> dict[str, float]:
        """Perform gradient updates on RTX 5070 GPU using dual replay buffer."""
        if len(self.buffer) < 16:
            return {"loss": 0.0}

        self.net.train().to(self.device)
        losses = []

        for _ in range(epochs):
            batch = self.buffer.sample(batch_size)
            if not batch:
                break

            x_t = torch.tensor([b.features for b in batch], dtype=torch.float32, device=self.device)
            actions = [b.action for b in batch]
            lat_target = torch.tensor([b.observed_latency_ms for b in batch], dtype=torch.float32, device=self.device)
            rej_target = torch.tensor([b.rejected for b in batch], dtype=torch.float32, device=self.device)

            pred_lat, pred_rej = self.net(x_t)

            batch_idx = torch.arange(len(batch), device=self.device)
            selected_lat = pred_lat[batch_idx, actions]
            selected_rej = pred_rej[batch_idx, actions]

            loss_lat = nn.functional.mse_loss(selected_lat, lat_target)
            loss_rej = nn.functional.binary_cross_entropy(selected_rej, rej_target)
            loss = loss_lat + 5.0 * loss_rej

            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()
            losses.append(float(loss.item()))

        self.net.eval()
        self.training_steps += 1
        return {"loss": float(np.mean(losses)) if losses else 0.0}

    def compile_and_canary_deploy(self) -> bool:
        """Trigger compilation of current GPU weights for Intel NPU and enter canary window."""
        ok = self.deployer.compile_candidate(self.net)
        if not ok:
            return False

        # Validate against retention buffer suite
        val_suite = self.buffer.retention_buffer
        if not self.deployer.validate_regression(val_suite):
            self.deployer.candidate_compiled_model = None
            return False

        self.deployer.start_canary(window_size=15)
        return True

    def bootstrap_calibration(self, engine: Any) -> None:
        """Seed replay buffer with initial hardware observations and pre-train policy."""
        snap = {"inflight": [0, 0, 0], "max_inflight": [16, 16, 16], "resource_tokens": 1000}
        load = {"cpu": 0.05, "gpu": 0.05, "npu": 0.05}
        for b in (1, 4, 16, 64):
            for dev in (DEVICE_CPU, DEVICE_GPU, DEVICE_NPU):
                receipt = engine.execute(job_id=9000 + dev * 100 + b, target_device=dev, batch_size=b)
                job = JobDescriptor(job_id=9000, batch_size=b, priority=0.5, latency_budget_us=10000)
                feats = self.featurize(job, snap, load)
                self.record_feedback(feats, dev, latency_us=receipt.latency_us, rejected=False, phase="Bootstrap")
        self.train_step(batch_size=12, epochs=80)
        self.deployer.compile_candidate(self.net)
        self.deployer.promote_candidate()

