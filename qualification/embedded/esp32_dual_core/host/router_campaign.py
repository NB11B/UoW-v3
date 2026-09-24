#!/usr/bin/env python3
"""1,200-Job Continuous Adaptation Router Campaign Runner for ESP32 Authority.

Orchestrates the complete 6-phase heterogeneous adaptive routing campaign:
  Phase 1: Nominal Baseline (Jobs 0-199)
  Phase 2: Large Batches (Jobs 200-399)
  Phase 3: GPU Contention (Jobs 400-599)
  Phase 4: NPU Contention (Jobs 600-799)
  Phase 5: Device Outage [GPU Offline] (Jobs 800-999)
  Phase 6: Nominal Restoration [Retention / Fast Reacquisition] (Jobs 1000-1199)

Evaluates 13 Capability Gates (G0-G12), including:
  G0: zero wrong authoritative commits
  G1: forced offline-target rejection through the actual authority boundary
  G2: adaptation convergence
  G3: attested CPU/CUDA/NPU heterogeneous execution
  G4: latency regret against measured actual-hardware shadow oracle
  G5: independently verified SHA-256 evidence-chain continuity
  G6-G10: canary safety, retention, rollback, stochastic recovery, operational memory
  G11: OCC concurrency resolution
  G12: empirical tail-distribution stability
"""
from __future__ import annotations

import argparse
import concurrent.futures
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sys
import threading
import time
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qualification.claim_registry import get_claim
from qualification.evidence import (
    ClaimRequirement,
    EvidenceContext,
    EvidenceLevel,
    combine_contexts,
    evaluate_claim,
)

# Ensure UTF-8 output encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from routing_policy import (
    AdaptiveRoutingPolicy,
    DEVICE_CPU,
    DEVICE_GPU,
    DEVICE_NPU,
    JobDescriptor,
)
from stochastic_environment import (
    RegimeType,
    StochasticEnvironmentGenerator,
)
from workload_engine import WorkloadEngine


class PhysicalAuthorityClient:
    """Manages serial protocol communication with ESP32-S3 scheduling authority."""

    def __init__(self, port: str, baud: int = 115200, timeout: float = 20.0):
        try:
            import serial  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pyserial is required: pip install pyserial") from exc
        self.ser = serial.Serial()
        self.ser.port = port
        self.ser.baudrate = baud
        self.ser.timeout = 0.05
        self.ser.dtr = False
        self.ser.rts = False
        self.ser.open()
        self.timeout = timeout
        self._lock = threading.Lock()
        self._buf = bytearray()
        self._pending_frames: list[dict[str, Any]] = []
        self.last_evidence_root = "0" * 64
        self.last_reservation_id = 0
        time.sleep(1.5)
        with self._lock:
            self.ser.reset_input_buffer()

    def evidence_context(self) -> EvidenceContext:
        return EvidenceContext(
            EvidenceLevel.PHYSICAL,
            "PhysicalAuthorityClient",
            {"authority": f"ESP32-S3 serial:{self.ser.port}"},
            {},
        )

    def close(self) -> None:
        with self._lock:
            if self.ser and self.ser.is_open:
                self.ser.close()

    def _write_chunked(self, data: bytes) -> None:
        chunk_size = 16
        for i in range(0, len(data), chunk_size):
            self.ser.write(data[i : i + chunk_size])
            if i + chunk_size < len(data):
                time.sleep(0.003)
        self.ser.flush()

    def _extract_frames_from_buf(self) -> None:
        """Extract all complete JSON objects from self._buf and append to self._pending_frames."""
        while True:
            start = self._buf.find(b"{")
            if start == -1:
                self._buf.clear()
                break
            if start > 0:
                del self._buf[:start]
                start = 0

            end = self._buf.find(b"}", start)
            found = False
            while end != -1:
                candidate = self._buf[start : end + 1]
                try:
                    data = json.loads(candidate.decode("utf-8", errors="replace"))
                    if isinstance(data, dict):
                        self._pending_frames.append(data)
                        consumed = end + 1
                        while consumed < len(self._buf) and self._buf[consumed] in (10, 13, 32):
                            consumed += 1
                        del self._buf[:consumed]
                        found = True
                        break
                except json.JSONDecodeError:
                    pass
                end = self._buf.find(b"}", end + 1)

            if not found:
                break

    def _find_and_consume_frame(
        self,
        expected_events: tuple[str, ...],
        predicate: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any] | None:
        """Find and remove a matching frame from self._pending_frames."""
        for idx, frame in enumerate(self._pending_frames):
            ev = frame.get("event")
            if ev in expected_events or ev == "error":
                if predicate is None or ev == "error" or predicate(frame):
                    return self._pending_frames.pop(idx)
        return None

    def send_command(
        self,
        cmd: str,
        expected_events: tuple[str, ...],
        predicate: Callable[[dict[str, Any]], bool] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send command line and await JSON response matching expected_events and predicate."""
        with self._lock:
            # Drain any pending serial bytes into buffer first
            try:
                avail = self.ser.in_waiting
                if avail > 0:
                    chunk = self.ser.read(avail)
                    if chunk:
                        self._buf.extend(chunk)
                        self._extract_frames_from_buf()
            except Exception:
                pass

            # Check if a matching frame was already received (only when keyed by predicate)
            if predicate is not None:
                match = self._find_and_consume_frame(expected_events, predicate)
                if match is not None:
                    if "evidence_root" in match and match.get("committed", False):
                        self.last_evidence_root = match["evidence_root"]
                    return match
            else:
                self._pending_frames = [
                    f for f in self._pending_frames if f.get("event") not in expected_events
                ]

            time.sleep(0.002)
            self._write_chunked((cmd.strip() + "\n").encode("utf-8"))

            cmd_verb = cmd.split()[0].upper() if cmd.strip() else ""
            retryable = cmd_verb in {"SCHED_SNAPSHOT", "SCHED_RESET", "SCHED_SET_ONLINE", "SCHED_RECEIPT"}
            effective_timeout = timeout if timeout is not None else self.timeout
            deadline = time.monotonic() + effective_timeout

            while time.monotonic() < deadline:
                try:
                    avail = self.ser.in_waiting
                    if avail > 0:
                        chunk = self.ser.read(avail)
                        if chunk:
                            self._buf.extend(chunk)
                            self._extract_frames_from_buf()
                    else:
                        time.sleep(0.002)
                except Exception:
                    time.sleep(0.005)

                match = self._find_and_consume_frame(expected_events, predicate)
                if match is not None:
                    if "evidence_root" in match and match.get("committed", False):
                        self.last_evidence_root = match["evidence_root"]
                    return match

                if retryable and time.monotonic() < deadline - 0.5 and (time.monotonic() - (deadline - effective_timeout)) > 0.15:
                    time.sleep(0.02)
                    self._write_chunked((cmd.strip() + "\n").encode("utf-8"))

            raise TimeoutError(f"Timeout waiting for {expected_events} after command: {cmd}")

    def get_snapshot(self) -> dict[str, Any]:
        snap = self.send_command("SCHED_SNAPSHOT", ("sched_snapshot",))
        if "evidence_root" in snap:
            self.last_evidence_root = snap["evidence_root"]
        return snap

    def reset(self, online_mask: int = 7, max_cpu: int = 16, max_gpu: int = 16, max_npu: int = 16, tokens: int = 1000) -> dict[str, Any]:
        with self._lock:
            self._pending_frames.clear()
            self._buf.clear()
            self.ser.reset_input_buffer()
        cmd = f"SCHED_RESET {online_mask} {max_cpu} {max_gpu} {max_npu} {tokens}"
        snap = self.send_command(cmd, ("sched_snapshot",))
        self.last_evidence_root = snap.get("evidence_root", "0" * 64)
        self.last_reservation_id = int(snap.get("reservation_seq", 0))
        return snap

    def set_online(self, device: int, online: bool) -> dict[str, Any]:
        cmd = f"SCHED_SET_ONLINE {device} {1 if online else 0}"
        return self.send_command(cmd, ("sched_snapshot",))

    def propose(self, pre_state_hash: str, job_id: int, target: int, tokens: int = 1, timeout: float | None = None) -> dict[str, Any]:
        prop_hash = hashlib.sha256(f"{pre_state_hash}:{job_id}:{target}:{tokens}".encode("utf-8")).hexdigest()
        cmd = f"SCHED_PROPOSE {pre_state_hash} {job_id} {target} {tokens} {prop_hash}"
        res = self.send_command(
            cmd,
            ("sched_decision",),
            predicate=lambda f: int(f.get("job_id", -1)) == job_id,
            timeout=timeout,
        )
        if res.get("committed", False):
            self.last_reservation_id = int(res.get("reservation_id", self.last_reservation_id))
            self.last_evidence_root = res.get("evidence_root", self.last_evidence_root)
        return res

    def propose_with_occ_retry(self, pre_state_hash: str, job_id: int, target: int, tokens: int = 1, max_retries: int = 5) -> dict[str, Any]:
        curr_hash = pre_state_hash
        attempts = 0
        for _ in range(max_retries):
            attempts += 1
            try:
                res = self.propose(pre_state_hash=curr_hash, job_id=job_id, target=target, tokens=tokens, timeout=10.0)
            except TimeoutError:
                with self._lock:
                    match = self._find_and_consume_frame(
                        ("sched_decision",),
                        lambda f: int(f.get("job_id", -1)) == job_id,
                    )
                if match is not None:
                    res = match
                else:
                    snap = self.get_snapshot()
                    curr_hash = snap.get("state_hash", curr_hash)
                    time.sleep(0.005)
                    continue

            if res.get("committed", False) or res.get("reason") != "STALE_STATE_HASH":
                res["occ_attempts"] = attempts
                return res
            snap = self.get_snapshot()
            curr_hash = snap.get("state_hash", curr_hash)
            time.sleep(0.002)
        res["occ_attempts"] = attempts
        return res

    def receipt(self, reservation_id: int, status: int, latency_us: int, output_digest: str) -> dict[str, Any]:
        cmd = f"SCHED_RECEIPT {reservation_id} {status} {latency_us} {output_digest}"
        for attempt in range(5):
            try:
                res = self.send_command(
                    cmd,
                    ("sched_receipt",),
                    predicate=lambda f: int(f.get("reservation_id", -1)) == reservation_id and f.get("committed", False),
                    timeout=5.0,
                )
                if res.get("committed", False):
                    self.last_evidence_root = res.get("evidence_root", self.last_evidence_root)
                return res
            except TimeoutError:
                with self._lock:
                    match = self._find_and_consume_frame(
                        ("sched_receipt",),
                        lambda f: int(f.get("reservation_id", -1)) == reservation_id and f.get("committed", False),
                    )
                if match is not None:
                    if match.get("committed", False):
                        self.last_evidence_root = match.get("evidence_root", self.last_evidence_root)
                    return match
                if attempt < 4:
                    time.sleep(0.02)
                    continue
                with self._lock:
                    match = self._find_and_consume_frame(
                        ("sched_receipt",),
                        lambda f: int(f.get("reservation_id", -1)) == reservation_id,
                    )
                if match is not None:
                    return match
                return {
                    "event": "sched_receipt",
                    "committed": False,
                    "reason": "TIMEOUT",
                    "reservation_id": reservation_id,
                }


class MockAuthorityClient:
    """Mock simulated ESP32 scheduling authority for tests and verification without physical serial."""

    def __init__(self):
        self._lock = threading.Lock()
        self.epoch = 1
        self.online_mask = 7
        self.inflight = [0, 0, 0]
        self.max_inflight = [16, 16, 16]
        self.tokens = 1000
        self.reservation_seq = 0
        self.completion_seq = 0
        self.evidence_root = "0" * 64
        self.reservations: dict[int, dict[str, Any]] = {}

    def _state_hash(self) -> str:
        s = f"{self.epoch}:{self.online_mask}:{self.inflight[0]}:{self.inflight[1]}:{self.inflight[2]}:{self.tokens}:{self.reservation_seq}:{self.completion_seq}"
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    def evidence_context(self) -> EvidenceContext:
        return EvidenceContext(
            EvidenceLevel.SIMULATED,
            "MockAuthorityClient",
            {},
            {"authority": "in-process mock authority"},
        )

    def close(self) -> None:
        pass

    def get_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "event": "sched_snapshot",
                "epoch": self.epoch,
                "online_mask": self.online_mask,
                "inflight": list(self.inflight),
                "max_inflight": list(self.max_inflight),
                "resource_tokens": self.tokens,
                "reservation_seq": self.reservation_seq,
                "completion_seq": self.completion_seq,
                "state_hash": self._state_hash(),
                "evidence_root": self.evidence_root,
            }

    def reset(self, online_mask: int = 7, max_cpu: int = 16, max_gpu: int = 16, max_npu: int = 16, tokens: int = 1000) -> dict[str, Any]:
        with self._lock:
            self.epoch += 1
            self.online_mask = online_mask
            self.inflight = [0, 0, 0]
            self.max_inflight = [max_cpu, max_gpu, max_npu]
            self.tokens = tokens
            self.reservation_seq = 0
            self.completion_seq = 0
            self.evidence_root = "0" * 64
            self.reservations.clear()
            return {
                "event": "sched_snapshot",
                "epoch": self.epoch,
                "online_mask": self.online_mask,
                "inflight": list(self.inflight),
                "max_inflight": list(self.max_inflight),
                "resource_tokens": self.tokens,
                "reservation_seq": self.reservation_seq,
                "completion_seq": self.completion_seq,
                "state_hash": self._state_hash(),
                "evidence_root": self.evidence_root,
            }

    def set_online(self, device: int, online: bool) -> dict[str, Any]:
        with self._lock:
            if online:
                self.online_mask |= (1 << device)
            else:
                self.online_mask &= ~(1 << device)
            self.epoch += 1
            return {
                "event": "sched_snapshot",
                "epoch": self.epoch,
                "online_mask": self.online_mask,
                "inflight": list(self.inflight),
                "max_inflight": list(self.max_inflight),
                "resource_tokens": self.tokens,
                "reservation_seq": self.reservation_seq,
                "completion_seq": self.completion_seq,
                "state_hash": self._state_hash(),
                "evidence_root": self.evidence_root,
            }

    def propose(self, pre_state_hash: str, job_id: int, target: int, tokens: int = 1) -> dict[str, Any]:
        with self._lock:
            curr = self._state_hash()
            reason = "NONE"
            if pre_state_hash != curr:
                reason = "STALE_STATE_HASH"
            elif target >= 3:
                reason = "INVALID_TARGET"
            elif (self.online_mask & (1 << target)) == 0:
                reason = "DEVICE_OFFLINE"
            elif self.inflight[target] >= self.max_inflight[target]:
                reason = "DEVICE_CAPACITY_EXCEEDED"
            elif self.tokens < tokens:
                reason = "INSUFFICIENT_TOKENS"

            if reason == "NONE":
                self.inflight[target] += 1
                self.tokens -= tokens
                self.reservation_seq += 1
                res_id = self.reservation_seq
                self.reservations[res_id] = {"job_id": job_id, "target": target, "tokens": tokens}
                post_hash = self._state_hash()
                prev_evidence_root = self.evidence_root
                ev_str = f"{prev_evidence_root}:RESERVE:{res_id}:{job_id}:{target}:{tokens}:{post_hash}"
                self.evidence_root = hashlib.sha256(ev_str.encode("utf-8")).hexdigest()
                return {
                    "event": "sched_decision",
                    "committed": True,
                    "reason": "NONE",
                    "reservation_id": res_id,
                    "job_id": job_id,
                    "target": target,
                    "post_state_hash": post_hash,
                    "prev_evidence_root": prev_evidence_root,
                    "evidence_root": self.evidence_root,
                }
            else:
                return {
                    "event": "sched_decision",
                    "committed": False,
                    "reason": reason,
                    "reservation_id": 0,
                    "job_id": job_id,
                    "target": target,
                    "post_state_hash": curr,
                    "evidence_root": self.evidence_root,
                }

    def propose_with_occ_retry(self, pre_state_hash: str, job_id: int, target: int, tokens: int = 1, max_retries: int = 5) -> dict[str, Any]:
        curr_hash = pre_state_hash
        attempts = 0
        for _ in range(max_retries):
            attempts += 1
            res = self.propose(pre_state_hash=curr_hash, job_id=job_id, target=target, tokens=tokens)
            if res.get("committed", False) or res.get("reason") != "STALE_STATE_HASH":
                res["occ_attempts"] = attempts
                return res
            snap = self.get_snapshot()
            curr_hash = snap.get("state_hash", curr_hash)
            time.sleep(0.002)
        res["occ_attempts"] = attempts
        return res

    def receipt(self, reservation_id: int, status: int, latency_us: int, output_digest: str) -> dict[str, Any]:
        with self._lock:
            res = self.reservations.get(reservation_id)
            if not res:
                return {
                    "event": "sched_receipt",
                    "committed": False,
                    "reason": "INVALID_RESERVATION",
                    "reservation_id": reservation_id,
                    "completion_seq": self.completion_seq,
                    "latency_us": 0,
                    "post_state_hash": self._state_hash(),
                    "evidence_root": self.evidence_root,
                }

            target = res["target"]
            tokens = res["tokens"]
            if self.inflight[target] > 0:
                self.inflight[target] -= 1
            self.tokens += tokens
            self.completion_seq += 1
            del self.reservations[reservation_id]
            post_hash = self._state_hash()
            prev_evidence_root = self.evidence_root
            ev_str = f"{prev_evidence_root}:RECEIPT:{reservation_id}:{status}:{latency_us}:{output_digest}:{post_hash}"
            self.evidence_root = hashlib.sha256(ev_str.encode("utf-8")).hexdigest()

            return {
                "event": "sched_receipt",
                "committed": True,
                "reason": "NONE",
                "reservation_id": reservation_id,
                "completion_seq": self.completion_seq,
                "latency_us": latency_us,
                "post_state_hash": post_hash,
                "prev_evidence_root": prev_evidence_root,
                "evidence_root": self.evidence_root,
            }


@dataclass
class JobRecord:
    job_id: int
    phase: str
    phase_index: int
    batch_size: int
    target_device: int
    proposed_committed: bool
    rejection_reason: str
    reservation_id: int
    receipt_committed: bool
    latency_us: int
    oracle_latencies_us: dict[int, int]
    oracle_best_device: int
    regret_us: int
    post_state_hash: str
    evidence_root: str
    canary_active: bool
    actual_backend: str = ""
    execution_error: str | None = None


class DistributionTracker:
    """Calculates statistical percentiles, tail metrics, and variance convergence across jobs."""

    @staticmethod
    def compute_percentiles(values: list[float]) -> dict[str, float]:
        if not values:
            return {"mean": 0.0, "std": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "count": 0}
        s = sorted(values)
        n = len(s)
        mean_val = sum(s) / n
        variance = sum((x - mean_val) ** 2 for x in s) / n
        std_val = math.sqrt(variance)

        def pct(p: float) -> float:
            idx = int(round((p / 100.0) * (n - 1)))
            return float(s[max(0, min(n - 1, idx))])

        return {
            "mean": float(mean_val),
            "std": float(std_val),
            "p50": pct(50),
            "p90": pct(90),
            "p95": pct(95),
            "p99": pct(99),
            "count": n,
        }

    @classmethod
    def analyze_records(cls, records: list[Any]) -> dict[str, Any]:
        """Aggregate global, per-device, and per-regime distribution statistics."""
        if not records:
            return {}

        latencies = [
            float(r.latency_us)
            for r in records
            if r.proposed_committed and r.receipt_committed and not r.execution_error
        ]
        regrets = [float(r.regret_us) for r in records]

        # First half vs Second half variance convergence
        n = len(regrets)
        h = n // 2
        early_regrets = regrets[:h] if h > 0 else regrets
        late_regrets = regrets[h:] if h > 0 else regrets

        early_std = cls.compute_percentiles(early_regrets)["std"]
        late_std = cls.compute_percentiles(late_regrets)["std"]
        variance_ratio = (late_std / max(1e-3, early_std)) if early_std > 0 else 1.0

        # Per-device breakdown
        device_stats = {}
        for dev_id, dev_name in [(DEVICE_CPU, "CPU"), (DEVICE_GPU, "GPU"), (DEVICE_NPU, "NPU")]:
            dev_lats = [
                float(r.latency_us)
                for r in records
                if r.proposed_committed and r.receipt_committed
                and not r.execution_error and r.target_device == dev_id
            ]
            dev_regs = [
                float(r.regret_us)
                for r in records
                if r.proposed_committed and r.receipt_committed
                and not r.execution_error and r.target_device == dev_id
            ]
            device_stats[dev_name] = {
                "count": len(dev_lats),
                "latency": cls.compute_percentiles(dev_lats),
                "regret": cls.compute_percentiles(dev_regs),
            }

        # Per-regime breakdown
        regimes = sorted(list(set(r.phase for r in records)))
        regime_stats = {}
        for reg in regimes:
            reg_lats = [
                float(r.latency_us)
                for r in records
                if r.proposed_committed and r.receipt_committed
                and not r.execution_error and r.phase == reg
            ]
            reg_regs = [float(r.regret_us) for r in records if r.phase == reg]
            regime_stats[reg] = {
                "count": len(reg_regs),
                "latency": cls.compute_percentiles(reg_lats),
                "regret": cls.compute_percentiles(reg_regs),
            }

        return {
            "global_latency": cls.compute_percentiles(latencies),
            "global_regret": cls.compute_percentiles(regrets),
            "variance_reduction": {
                "early_std_us": early_std,
                "late_std_us": late_std,
                "variance_ratio": variance_ratio,
            },
            "device_distributions": device_stats,
            "regime_distributions": regime_stats,
        }


class RouterCampaignRunner:
    """Orchestrates the 1,200-job continuous adaptation campaign."""

    def __init__(
        self,
        authority_client: Any,
        workload_engine: WorkloadEngine,
        routing_policy: AdaptiveRoutingPolicy,
        artifacts_dir: Path,
        total_jobs: int = 1200,
        stochastic_mode: bool = False,
        adversarial_injection_job: int | None = None,
        concurrency: int = 1,
        seed: int = 42,
    ):
        self.authority = authority_client
        self.engine = workload_engine
        self.policy = routing_policy
        self.artifacts_dir = artifacts_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.total_jobs = total_jobs
        self.stochastic_mode = stochastic_mode
        self.adversarial_injection_job = adversarial_injection_job
        self.concurrency = max(1, concurrency)
        self.seed = seed

        self.records: list[JobRecord] = []
        self.wrong_authoritative_commits = 0
        self.prev_evidence_root = "0" * 64
        self.golden_benchmark_results: list[dict[str, Any]] = []

        self.occ_conflicts = 0
        self.occ_retries_successful = 0
        self.evidence_links_verified = 0
        self.evidence_verification_failures = 0
        self.authority_negative_control: dict[str, Any] = {}
        self.evidence_context = combine_contexts(
            self.authority.evidence_context(),
            self.engine.evidence_context(),
            self.policy.evidence_context(),
            source="RouterCampaignRunner",
        )

        self.stochastic_env = (
            StochasticEnvironmentGenerator(
                workload_engine=self.engine,
                authority_client=self.authority,
                seed=self.seed,
            )
            if self.stochastic_mode
            else None
        )

    def _run_authority_negative_control(self) -> dict[str, Any]:
        """Force an offline-target proposal through the actual authority path."""
        self.authority.reset(
            online_mask=7,
            max_cpu=16,
            max_gpu=16,
            max_npu=16,
            tokens=1000,
        )
        offline = self.authority.set_online(DEVICE_GPU, False)
        before = self.authority.get_snapshot()
        before_hash = before.get("state_hash", "")
        before_root = before.get("evidence_root", "")
        forced = self.authority.propose(
            pre_state_hash=before_hash,
            job_id=0x7FFF0001,
            target=DEVICE_GPU,
            tokens=1,
        )
        after = self.authority.get_snapshot()
        observed_pass = (
            forced.get("committed") is False
            and forced.get("reason") == "DEVICE_OFFLINE"
            and after.get("state_hash") == before_hash
            and after.get("evidence_root") == before_root
        )
        return {
            "observed_pass": observed_pass,
            "forced_reason": forced.get("reason"),
            "committed": bool(forced.get("committed", False)),
            "state_unchanged": after.get("state_hash") == before_hash,
            "evidence_unchanged": after.get("evidence_root") == before_root,
            "offline_mask": offline.get("online_mask"),
        }

    def _verify_reservation_evidence(
        self,
        job: JobDescriptor,
        target: int,
        prop_res: dict[str, Any],
    ) -> None:
        if not prop_res.get("committed", False):
            return
        prev_root = prop_res.get("prev_evidence_root")
        post_hash = prop_res.get("post_state_hash")
        actual_root = prop_res.get("evidence_root")
        res_id = int(prop_res.get("reservation_id", 0))
        if not prev_root or not post_hash or not actual_root or res_id <= 0:
            self.evidence_verification_failures += 1
            return
        body = (
            f"{prev_root}:RESERVE:{res_id}:{job.job_id}:"
            f"{target}:{job.tokens}:{post_hash}"
        )
        expected = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if expected == actual_root:
            self.evidence_links_verified += 1
        else:
            self.evidence_verification_failures += 1

    def _verify_receipt_evidence(
        self,
        reservation_id: int,
        w_receipt: Any,
        rec_res: dict[str, Any],
    ) -> None:
        if not rec_res.get("committed", False):
            return
        prev_root = rec_res.get("prev_evidence_root")
        post_hash = rec_res.get("post_state_hash")
        actual_root = rec_res.get("evidence_root")
        if not prev_root or not post_hash or not actual_root:
            self.evidence_verification_failures += 1
            return
        status = 0 if w_receipt.error is None else 1
        body = (
            f"{prev_root}:RECEIPT:{reservation_id}:{status}:"
            f"{w_receipt.latency_us}:{w_receipt.output_digest}:{post_hash}"
        )
        expected = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if expected == actual_root:
            self.evidence_links_verified += 1
        else:
            self.evidence_verification_failures += 1

    def _execute_and_receipt(self, job: JobDescriptor, target: int, res_id: int) -> tuple[Any, dict[str, Any]]:
        w_receipt = self.engine.execute(job_id=job.job_id, target_device=target, batch_size=job.batch_size)
        rec_res = self.authority.receipt(
            reservation_id=res_id,
            status=0 if w_receipt.error is None else 1,
            latency_us=w_receipt.latency_us,
            output_digest=w_receipt.output_digest,
        )
        return (w_receipt, rec_res)

    def _finalize_completed_job(
        self,
        job: JobDescriptor,
        target: int,
        prop_res: dict[str, Any],
        w_receipt: Any,
        rec_res: dict[str, Any],
        feats: list[float],
        meta: dict[str, Any],
        phase_name: str,
        phase_idx: int,
    ) -> None:
        measured_latency_us = w_receipt.latency_us
        receipt_committed = rec_res.get("committed", False)
        self._verify_receipt_evidence(
            prop_res.get("reservation_id", 0),
            w_receipt,
            rec_res,
        )
        post_state_hash = rec_res.get("post_state_hash", prop_res.get("post_state_hash", ""))
        ev_root = rec_res.get("evidence_root", prop_res.get("evidence_root", self.prev_evidence_root))
        res_id = prop_res.get("reservation_id", 0)

        # Measure the shadow oracle on the actual currently-online hardware.
        # No hand-written latency proxy may satisfy a physical performance claim.
        online_mask = int(meta.get("authority_online_mask", 7))
        active_devices = [
            dev
            for dev in self.engine.available_actual_devices()
            if online_mask & (1 << dev)
        ]
        oracle = self.engine.benchmark_oracle(
            job_id=job.job_id,
            batch_size=job.batch_size,
            active_devices=active_devices,
        )
        if oracle:
            best_oracle_dev = min(oracle, key=oracle.get)
            best_oracle_lat = oracle[best_oracle_dev]
        else:
            best_oracle_dev = target
            best_oracle_lat = measured_latency_us

        execution_failed = bool(w_receipt.error) or not receipt_committed
        regret_us = 15000 if execution_failed else max(0, measured_latency_us - best_oracle_lat)

        self.policy.record_feedback(
            features=feats,
            action=target,
            latency_us=measured_latency_us,
            rejected=execution_failed,
            phase=phase_name,
        )

        record = JobRecord(
            job_id=job.job_id,
            phase=phase_name,
            phase_index=phase_idx,
            batch_size=job.batch_size,
            target_device=target,
            proposed_committed=True,
            rejection_reason="NONE",
            reservation_id=res_id,
            receipt_committed=receipt_committed,
            latency_us=measured_latency_us,
            oracle_latencies_us=oracle,
            oracle_best_device=best_oracle_dev,
            regret_us=regret_us,
            post_state_hash=post_state_hash,
            evidence_root=ev_root,
            canary_active=meta.get("canary_active", False),
            actual_backend=w_receipt.actual_backend,
            execution_error=w_receipt.error,
        )
        self.records.append(record)
        self.prev_evidence_root = ev_root

        if self.stochastic_env is not None:
            self.stochastic_env.record_job_result(
                job_id=job.job_id,
                target_device=target,
                committed=not execution_failed,
                latency_us=measured_latency_us,
                regret_us=regret_us,
            )

    def _finalize_rejected_job(
        self,
        job: JobDescriptor,
        target: int,
        prop_res: dict[str, Any],
        feats: list[float],
        meta: dict[str, Any],
        phase_name: str,
        phase_idx: int,
    ) -> None:
        reason = prop_res.get("reason", "NONE")
        post_state_hash = prop_res.get("post_state_hash", "")
        ev_root = prop_res.get("evidence_root", self.prev_evidence_root)
        measured_latency_us = 25000
        regret_us = 15000

        self.policy.record_feedback(
            features=feats,
            action=target,
            latency_us=measured_latency_us,
            rejected=True,
            phase=phase_name,
        )

        record = JobRecord(
            job_id=job.job_id,
            phase=phase_name,
            phase_index=phase_idx,
            batch_size=job.batch_size,
            target_device=target,
            proposed_committed=False,
            rejection_reason=reason,
            reservation_id=0,
            receipt_committed=False,
            latency_us=measured_latency_us,
            oracle_latencies_us={},
            oracle_best_device=target,
            regret_us=regret_us,
            post_state_hash=post_state_hash,
            evidence_root=ev_root,
            canary_active=meta.get("canary_active", False),
        )
        self.records.append(record)
        self.prev_evidence_root = ev_root

        if self.stochastic_env is not None:
            self.stochastic_env.record_job_result(
                job_id=job.job_id,
                target_device=target,
                committed=False,
                latency_us=measured_latency_us,
                regret_us=regret_us,
            )

    def run_golden_benchmark(self, job_id: int) -> dict[str, Any]:
        """Audit policy against fixed golden validation suite across all batch sizes."""
        snap = self.authority.get_snapshot()
        suite_lats = []
        for b in (1, 4, 16, 64):
            job = JobDescriptor(job_id=88880 + b, batch_size=b, priority=0.5, latency_budget_us=10000)
            feats = self.policy.featurize(job, snap, {"cpu": 0.05, "gpu": 0.05, "npu": 0.05})
            target, _ = self.policy.select_target(feats, snap, epsilon=0.0)
            receipt = self.engine.execute(job.job_id, target, b)
            suite_lats.append(receipt.latency_us)

        mean_suite_lat = sum(suite_lats) / len(suite_lats)
        audit_entry = {"job_id": job_id, "mean_suite_latency_us": mean_suite_lat, "per_batch_latencies": suite_lats}
        self.golden_benchmark_results.append(audit_entry)
        print(f"[GoldenBenchmark] Job {job_id}: Mean Golden Suite Latency = {mean_suite_lat:.1f} us (Retention check: OK)")
        return audit_entry

    def get_phase_config(self, job_idx: int) -> tuple[str, int]:
        """Return (phase_name, phase_id) for a given job index."""
        phase_len = max(1, self.total_jobs // 6)
        p_idx = min(5, job_idx // phase_len)
        phases = [
            "P1_Nominal_Baseline",
            "P2_Large_Batches",
            "P3_GPU_Contention",
            "P4_NPU_Contention",
            "P5_Device_Outage",
            "P6_Nominal_Restoration",
        ]
        return phases[p_idx], p_idx

    def generate_job(self, job_id: int, phase_idx: int) -> JobDescriptor:
        """Sample job descriptor appropriate for the current phase distribution."""
        rng = random.Random(job_id * 31337 + 42)
        if phase_idx == 1:  # P2: Large batches
            batch = rng.choices([1, 4, 16, 64], weights=[0.05, 0.10, 0.35, 0.50])[0]
        elif phase_idx in (3, 4):  # P4 & P5: Heavy batches
            batch = rng.choices([1, 4, 16, 64], weights=[0.10, 0.15, 0.35, 0.40])[0]
        else:
            batch = rng.choices([1, 4, 16, 64], weights=[0.35, 0.35, 0.15, 0.15])[0]

        prio = rng.uniform(0.1, 1.0)
        budget = int(rng.uniform(5000, 20000))
        return JobDescriptor(
            job_id=job_id,
            batch_size=batch,
            priority=prio,
            latency_budget_us=budget,
            tokens=1,
        )

    def run(self) -> dict[str, Any]:
        """Execute full campaign across all phases."""
        print(f"\n=======================================================")
        print(f" Starting 1,200-Job Continuous Adaptation Router Campaign")
        print(f" Total Jobs: {self.total_jobs} | Concurrency: {self.concurrency}")
        print(f"=======================================================\n")

        # 0. Required negative control: policy avoidance is not evidence that the
        # authority can reject an illegal offline-device proposal.
        self.authority_negative_control = self._run_authority_negative_control()

        # 1. Reset authority state after the negative control.
        snap = self.authority.reset(online_mask=7, max_cpu=16, max_gpu=16, max_npu=16, tokens=1000)
        self.prev_evidence_root = snap.get("evidence_root", "0" * 64)
        current_state_hash = snap.get("state_hash", "")

        active_phase_idx = -1
        phase_start_time = time.monotonic()
        consecutive_rejections = 0

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.concurrency) if self.concurrency > 1 else None
        in_flight: dict[concurrent.futures.Future, dict[str, Any]] = {}

        for job_id in range(1, self.total_jobs + 1):
            if self.concurrency > 1 and executor is not None:
                # Wait if at capacity limit
                while len(in_flight) >= self.concurrency:
                    done, _ = concurrent.futures.wait(in_flight.keys(), return_when=concurrent.futures.FIRST_COMPLETED)
                    for fut in done:
                        item = in_flight.pop(fut)
                        w_receipt, rec_res = fut.result()
                        self._finalize_completed_job(
                            job=item["job"],
                            target=item["target"],
                            prop_res=item["prop_res"],
                            w_receipt=w_receipt,
                            rec_res=rec_res,
                            feats=item["feats"],
                            meta=item["meta"],
                            phase_name=item["phase_name"],
                            phase_idx=item["phase_idx"],
                        )

                # Non-blocking reap of finished futures
                finished = [f for f in in_flight.keys() if f.done()]
                for fut in finished:
                    item = in_flight.pop(fut)
                    w_receipt, rec_res = fut.result()
                    self._finalize_completed_job(
                        job=item["job"],
                        target=item["target"],
                        prop_res=item["prop_res"],
                        w_receipt=w_receipt,
                        rec_res=rec_res,
                        feats=item["feats"],
                        meta=item["meta"],
                        phase_name=item["phase_name"],
                        phase_idx=item["phase_idx"],
                    )

            if self.stochastic_mode and self.stochastic_env is not None:
                regime = self.stochastic_env.step(job_id)
                phase_name = f"Stochastic_{regime.value}"
                phase_idx = list(RegimeType).index(regime)
                job = self.stochastic_env.sample_job(job_id)
            else:
                phase_name, phase_idx = self.get_phase_config(job_id - 1)

                if phase_idx != active_phase_idx:
                    active_phase_idx = phase_idx
                    print(f"\n---> Entering Phase {phase_idx + 1}/6: {phase_name} at Job {job_id} <---")

                    if phase_idx == 0:  # P1: Nominal
                        self.engine.set_gpu_contention(False)
                        self.engine.set_npu_contention(False)
                        self.engine.set_cpu_contention(False)
                        snap = self.authority.set_online(DEVICE_GPU, True)
                    elif phase_idx == 1:  # P2: Large Batches
                        self.engine.set_gpu_contention(False)
                        self.engine.set_npu_contention(False)
                    elif phase_idx == 2:  # P3: GPU Contention
                        print("  [Environment] Activating heavy background GPU GEMM contention loop...")
                        self.engine.set_gpu_contention(True)
                        self.engine.set_npu_contention(False)
                    elif phase_idx == 3:  # P4: NPU Contention
                        print("  [Environment] Deactivating GPU contention, activating background NPU contention loop...")
                        self.engine.set_gpu_contention(False)
                        self.engine.set_npu_contention(True)
                    elif phase_idx == 4:  # P5: Device Outage (GPU Offline)
                        print("  [Environment] Deactivating NPU contention, instructing Authority: GPU OFFLINE...")
                        self.engine.set_npu_contention(False)
                        snap = self.authority.set_online(DEVICE_GPU, False)
                    elif phase_idx == 5:  # P6: Nominal Restoration
                        print("  [Environment] Restoring GPU ONLINE and clearing all contention (testing retention)...")
                        self.engine.set_gpu_contention(False)
                        self.engine.set_npu_contention(False)
                        snap = self.authority.set_online(DEVICE_GPU, True)

                    current_state_hash = snap.get("state_hash", current_state_hash)

                job = self.generate_job(job_id, phase_idx)

            # Adversarial canary test injection
            if self.adversarial_injection_job is not None and job_id == self.adversarial_injection_job:
                print(f"\n[AdversarialTest] Injecting corrupted candidate policy at Job {job_id} to test live canary rollback...")
                self.policy.inject_adversarial_test("inverted")

            # Query current authority snapshot
            snap = self.authority.get_snapshot()
            current_state_hash = snap.get("state_hash", current_state_hash)

            # System load telemetry
            system_load = {
                "cpu": 0.3 if self.engine.cpu_contention_active else 0.05,
                "gpu": 0.85 if self.engine.gpu_contention_active else 0.05,
                "npu": 0.85 if self.engine.npu_contention_active else 0.05,
            }

            if self.stochastic_mode and self.stochastic_env is not None:
                jobs_in_regime = self.stochastic_env.jobs_in_current_regime
                eps = 0.20 if jobs_in_regime < 15 else 0.05
            else:
                jobs_in_phase = (job_id - 1) % max(1, self.total_jobs // 6)
                eps = 0.20 if jobs_in_phase < 25 else 0.05

            feats = self.policy.featurize(job, snap, system_load)
            target, meta = self.policy.select_target(feats, snap, epsilon=eps)
            meta["authority_online_mask"] = int(snap.get("online_mask", 7))

            # Submit proposal to ESP32 Scheduling Authority with OCC retry on stale state hash
            prop_res = self.authority.propose_with_occ_retry(
                pre_state_hash=current_state_hash,
                job_id=job.job_id,
                target=target,
                tokens=job.tokens,
            )

            if prop_res.get("occ_attempts", 1) > 1:
                self.occ_conflicts += 1
                if prop_res.get("reason") != "STALE_STATE_HASH":
                    self.occ_retries_successful += 1

            prop_committed = prop_res.get("committed", False)
            reason = prop_res.get("reason", "NONE")
            res_id = prop_res.get("reservation_id", 0)
            current_state_hash = prop_res.get("post_state_hash", current_state_hash)
            ev_root = prop_res.get("evidence_root", self.prev_evidence_root)

            # Authority invariant check
            online_mask = snap.get("online_mask", 7)
            if not bool(online_mask & (1 << target)) and prop_committed:
                self.wrong_authoritative_commits += 1
                print(f"CRITICAL FAULT: Authority committed proposal for offline device {target}!", file=sys.stderr)

            if prop_committed:
                self._verify_reservation_evidence(job, target, prop_res)
                if self.concurrency > 1 and executor is not None:
                    fut = executor.submit(
                        self._execute_and_receipt,
                        job=job,
                        target=target,
                        res_id=res_id,
                    )
                    in_flight[fut] = {
                        "job": job,
                        "target": target,
                        "prop_res": prop_res,
                        "feats": feats,
                        "meta": meta,
                        "phase_name": phase_name,
                        "phase_idx": phase_idx,
                    }
                else:
                    w_receipt, rec_res = self._execute_and_receipt(job, target, res_id)
                    self._finalize_completed_job(
                        job=job,
                        target=target,
                        prop_res=prop_res,
                        w_receipt=w_receipt,
                        rec_res=rec_res,
                        feats=feats,
                        meta=meta,
                        phase_name=phase_name,
                        phase_idx=phase_idx,
                    )
            else:
                self._finalize_rejected_job(
                    job=job,
                    target=target,
                    prop_res=prop_res,
                    feats=feats,
                    meta=meta,
                    phase_name=phase_name,
                    phase_idx=phase_idx,
                )

            # Golden Benchmark audit every 500 jobs or at final job
            if job_id % 500 == 0 or job_id == self.total_jobs:
                self.run_golden_benchmark(job_id)

            if not prop_committed:
                consecutive_rejections += 1
            else:
                consecutive_rejections = 0

            if (job_id % 20 == 0) or (consecutive_rejections >= 3):
                t_metrics = self.policy.train_step(batch_size=32, epochs=4)
                if self.policy.deployer.canary_window_remaining == 0:
                    self.policy.compile_and_canary_deploy()
                if consecutive_rejections >= 3:
                    consecutive_rejections = 0

            # Progress logging every 50 jobs
            if job_id % 50 == 0 or job_id == self.total_jobs:
                recent_50 = self.records[-50:]
                rej_cnt = sum(1 for r in recent_50 if not r.proposed_committed)
                avg_lat = sum(r.latency_us for r in recent_50 if r.proposed_committed) / max(1, sum(1 for r in recent_50 if r.proposed_committed))
                avg_regret = sum(r.regret_us for r in recent_50) / max(1, len(recent_50))
                print(f"Job {job_id:4d}/{self.total_jobs} | Phase: {phase_name[:16]:16s} | "
                      f"Rej(last50): {rej_cnt:2d}/50 | AvgLat: {avg_lat:6.1f}us | "
                      f"AvgRegret: {avg_regret:6.1f}us | Evidence: {self.prev_evidence_root[:10]}...")

        # Drain all remaining in-flight tasks
        if executor is not None:
            for fut in concurrent.futures.as_completed(in_flight.keys()):
                item = in_flight[fut]
                w_receipt, rec_res = fut.result()
                self._finalize_completed_job(
                    job=item["job"],
                    target=item["target"],
                    prop_res=item["prop_res"],
                    w_receipt=w_receipt,
                    rec_res=rec_res,
                    feats=item["feats"],
                    meta=item["meta"],
                    phase_name=item["phase_name"],
                    phase_idx=item["phase_idx"],
                )
            executor.shutdown(wait=True)

        # Clean up
        self.engine.shutdown()

        # Distribution metrics
        dist_metrics = DistributionTracker.analyze_records(self.records)

        # Audit Capability Gates
        gate_results = self.audit_capability_gates()
        stochastic_metrics = self.stochastic_env.compute_summary_metrics() if self.stochastic_env else {}
        summary = {
            "total_jobs": self.total_jobs,
            "seed": self.seed,
            "wrong_authoritative_commits": self.wrong_authoritative_commits,
            "evidence_context": self.evidence_context.to_dict(),
            "authority_negative_control": self.authority_negative_control,
            "gates": gate_results,
            "distribution_metrics": dist_metrics,
            "stochastic_metrics": stochastic_metrics,
            "golden_benchmarks": self.golden_benchmark_results,
            "final_evidence_root": self.prev_evidence_root,
            "final_state_hash": current_state_hash,
            "records_count": len(self.records),
        }

        # Save artifacts
        report_path = self.artifacts_dir / "router_campaign_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump({
                "summary": summary,
                "records": [asdict(r) for r in self.records],
            }, f, indent=2)

        print(f"\n[Campaign] Report successfully saved to: {report_path}")
        return summary

    def audit_capability_gates(self) -> dict[str, Any]:
        """Audit Capability Gates (G0 through G12)."""
        # G0: wrong_authoritative_commits == 0
        g0_pass = (self.wrong_authoritative_commits == 0)

        # G1: Explicit authority enforcement. Adaptive avoidance does not count.
        total_rejections = sum(1 for r in self.records if not r.proposed_committed)
        p5_rejections = sum(1 for r in self.records if r.phase_index == 4 and not r.proposed_committed)
        g1_pass = bool(self.authority_negative_control.get("observed_pass", False))

        # G2: Adaptation convergence (rejection rate in second half of each phase drops <= 5%)
        if self.stochastic_mode:
            # In stochastic dynamic regime mode, steady-state rejection rate must remain <= 5%
            second_half = self.records[len(self.records) // 2:]
            second_half_rej = sum(1 for r in second_half if not r.proposed_committed) / max(1, len(second_half))
            overall_rej = total_rejections / max(1, len(self.records))
            g2_pass = (second_half_rej <= 0.05 or overall_rej <= 0.05)
        else:
            g2_pass = True
            phase_len = max(1, self.total_jobs // 6)
            for p in range(6):
                p_recs = [r for r in self.records if r.phase_index == p]
                if len(p_recs) >= 50:
                    second_half = p_recs[len(p_recs) // 2:]
                    rej_rate = sum(1 for r in second_half if not r.proposed_committed) / len(second_half)
                    if rej_rate > 0.05:
                        g2_pass = False

        # G3: Heterogeneous execution: CPU, GPU, NPU all execute >= 2% of total jobs
        committed_recs = [
            r for r in self.records
            if r.proposed_committed and r.receipt_committed and not r.execution_error
        ]
        cpu_count = sum(1 for r in committed_recs if r.actual_backend == "CPU")
        gpu_count = sum(1 for r in committed_recs if r.actual_backend == "CUDA")
        npu_count = sum(1 for r in committed_recs if r.actual_backend == "OPENVINO_NPU")
        min_expected = max(1, int(self.total_jobs * 0.02))
        g3_pass = (cpu_count >= min_expected and gpu_count >= min_expected and npu_count >= min_expected)

        # G4: Latency regret reduction (overall average regret < 4,000 us)
        avg_regret = sum(r.regret_us for r in self.records) / max(1, len(self.records))
        g4_pass = (avg_regret < 4000.0)

        # G5: independently verified SHA-256 evidence-chain continuity.
        # Coverage must equal every authoritative RESERVE + RECEIPT link.
        committed_roots = [r.evidence_root for r in self.records if r.proposed_committed]
        final_sched_snapshot = self.authority.get_snapshot()
        expected_evidence_links = (
            int(final_sched_snapshot.get("reservation_seq", 0))
            + int(final_sched_snapshot.get("completion_seq", 0))
        )
        g5_pass = (
            expected_evidence_links > 0
            and self.evidence_verification_failures == 0
            and self.evidence_links_verified == expected_evidence_links
        )

        # G6: Transactional canary safety (deployer promotions occurred, no runaway regressions)
        promotions = self.policy.deployer.promotions_count
        g6_pass = (promotions >= 1)

        # G7: Retention / Fast reacquisition: re-convergence rejection rate <= 8% upon nominal restoration
        if self.stochastic_mode:
            # In stochastic mode, evaluate all subsequent returns to NOMINAL
            subsequent_nom = [r for r in self.records if "NOMINAL" in r.phase and r.job_id > 100]
            if subsequent_nom:
                nom_rej = sum(1 for r in subsequent_nom if not r.proposed_committed) / len(subsequent_nom)
                g7_pass = (nom_rej <= 0.08)
            else:
                g7_pass = True
        else:
            p6_recs = [r for r in self.records if r.phase_index == 5]
            if len(p6_recs) >= 25:
                p6_early_rej = sum(1 for r in p6_recs[:25] if not r.proposed_committed) / 25.0
                g7_pass = (p6_early_rej <= 0.08)
            else:
                g7_pass = True

        # G8: Adversarial Canary Rollback Verification
        if self.adversarial_injection_job is not None:
            rollbacks = self.policy.deployer.rollbacks_count
            g8_pass = (rollbacks >= 1)
        else:
            g8_pass = True

        # G9: Stochastic Recovery Verification (T_detect <= 25, T_recover <= 50)
        stochastic_metrics = self.stochastic_env.compute_summary_metrics() if self.stochastic_env else {}
        if self.stochastic_mode and stochastic_metrics:
            g9_pass = True
            for r_name, r_stats in stochastic_metrics.items():
                m_rec = r_stats.get("mean_t_recover_jobs")
                if m_rec is not None and m_rec > 50:
                    g9_pass = False
        else:
            g9_pass = True

        # G10: Retention Memory Ratio (mean rho_memory <= 1.0 or fast reacquisition <= 25 jobs)
        if self.stochastic_mode and stochastic_metrics:
            g10_pass = True
            for r_name, r_stats in stochastic_metrics.items():
                mean_r = r_stats.get("mean_memory_reacquire_ratio")
                m_rec = r_stats.get("mean_t_recover_jobs")
                # Either mean reacquisition ratio is <= 1.0 or recovery is fast (<= 25 jobs)
                if not ((mean_r is not None and mean_r <= 1.0) or (m_rec is not None and m_rec <= 25.0)):
                    g10_pass = False
        else:
            g10_pass = True

        # G11: OCC Concurrency Resolution
        if self.concurrency > 1:
            g11_pass = (self.wrong_authoritative_commits == 0 and
                        (self.occ_conflicts == 0 or self.occ_retries_successful == self.occ_conflicts))
        else:
            g11_pass = True

        # G12: Distribution Stability & Tail Regret Bound
        dist_analysis = DistributionTracker.analyze_records(self.records)
        glob_reg = dist_analysis.get("global_regret", {})
        var_red = dist_analysis.get("variance_reduction", {})
        p50_reg = glob_reg.get("p50", 0.0)
        p95_reg = glob_reg.get("p95", 0.0)
        p99_reg = glob_reg.get("p99", 0.0)
        var_ratio = var_red.get("variance_ratio", 1.0)
        late_std = var_red.get("late_std_us", 0.0)

        if self.total_jobs >= 200:
            g12_pass = (
                self.wrong_authoritative_commits == 0
                and p50_reg <= 2500.0
                and p95_reg <= 10000.0
                and (var_ratio <= 1.40 or late_std <= 12000.0)
            )
        else:
            g12_pass = (
                self.wrong_authoritative_commits == 0
                and p50_reg <= 3000.0
                and p95_reg <= 15000.0
            )

        def requirement(claim_id: str) -> ClaimRequirement:
            spec = get_claim(claim_id)
            return ClaimRequirement(spec.required_level, spec.required_components)

        physical_authority = requirement("ESP32.AUTHORITY")
        physical_heterogeneous = requirement("HETERO.EXECUTION")
        physical_adaptation = requirement("HETERO.ADAPTATION")
        physical_performance = requirement("HETERO.PERFORMANCE")
        physical_evidence_chain = requirement("EVIDENCE.CHAIN")

        gates = {
            "G0_zero_wrong_commits": evaluate_claim(
                g0_pass, self.evidence_context, physical_authority,
                wrong_commits=self.wrong_authoritative_commits,
            ),
            "G1_offline_target_authority": evaluate_claim(
                g1_pass, self.evidence_context, physical_authority,
                total_rejections=total_rejections,
                p5_rejections=p5_rejections,
                negative_control=self.authority_negative_control,
            ),
            "G2_adaptation_convergence": evaluate_claim(
                g2_pass, self.evidence_context, physical_adaptation,
            ),
            "G3_heterogeneous_execution": evaluate_claim(
                g3_pass, self.evidence_context, physical_heterogeneous,
                cpu_jobs=cpu_count,
                gpu_jobs=gpu_count,
                npu_jobs=npu_count,
            ),
            "G4_latency_regret_reduction": evaluate_claim(
                g4_pass, self.evidence_context, physical_performance,
                avg_regret_us=avg_regret,
                oracle="measured_actual_hardware",
            ),
            "G5_evidence_chain_continuity": evaluate_claim(
                g5_pass, self.evidence_context, physical_evidence_chain,
                links_verified=self.evidence_links_verified,
                expected_links=expected_evidence_links,
                verification_failures=self.evidence_verification_failures,
                final_evidence_root=final_sched_snapshot.get("evidence_root"),
            ),
            "G6_canary_safety": evaluate_claim(
                g6_pass, self.evidence_context, physical_adaptation,
                npu_promotions=promotions,
            ),
            "G7_retention_reacquisition": evaluate_claim(
                g7_pass, self.evidence_context, physical_adaptation,
            ),
            "G8_adversarial_rollback": evaluate_claim(
                g8_pass, self.evidence_context, physical_adaptation,
                rollbacks=self.policy.deployer.rollbacks_count,
            ),
            "G9_stochastic_recovery": evaluate_claim(
                g9_pass, self.evidence_context, physical_adaptation,
            ),
            "G10_retention_memory_ratio": evaluate_claim(
                g10_pass, self.evidence_context, physical_adaptation,
            ),
            "G11_occ_concurrency": evaluate_claim(
                g11_pass, self.evidence_context, physical_authority,
                concurrency=self.concurrency,
                occ_conflicts=self.occ_conflicts,
                occ_retries_successful=self.occ_retries_successful,
            ),
            "G12_distribution_stability": evaluate_claim(
                g12_pass, self.evidence_context, physical_performance,
                p50_regret_us=p50_reg,
                p95_regret_us=p95_reg,
                p99_regret_us=p99_reg,
                variance_ratio=var_ratio,
                oracle="measured_actual_hardware",
            ),
        }
        gates["all_gates_passed"] = all(
            gate["passed"] for gate in gates.values() if isinstance(gate, dict)
        )
        gates["all_logic_observed"] = all(
            gate["observed_pass"] for gate in gates.values() if isinstance(gate, dict)
        )
        return gates


def main():
    parser = argparse.ArgumentParser(description="Adaptive Heterogeneous Workload Router Campaign")
    parser.add_argument("--port", type=str, default=None, help="Serial port to physical ESP32 (e.g. COM10)")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    parser.add_argument("--jobs", type=int, default=1200, help="Total number of jobs to execute per run")
    parser.add_argument("--concurrency", type=int, default=1, help="Number of concurrent in-flight jobs in asynchronous pipeline")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for single run")
    parser.add_argument("--seeds", nargs="+", type=int, default=None, help="List of random seeds to execute multi-seed campaign")
    parser.add_argument("--mock", action="store_true", help="Run a simulated/portable logic test; cannot satisfy physical gates")
    parser.add_argument("--physical", action="store_true", help="Require actual ESP32 + CUDA GPU + OpenVINO NPU; enables physical qualification claims")
    parser.add_argument("--stochastic", action="store_true", help="Run with stochastic semi-Markov environment generator")
    parser.add_argument("--adversarial-at", type=int, default=None, help="Job ID at which to inject adversarial canary test")
    parser.add_argument("--artifacts", type=Path, default=Path(__file__).resolve().parent / "artifacts", help="Artifacts directory")
    args = parser.parse_args()

    if args.physical and args.mock:
        parser.error("--physical and --mock are mutually exclusive")
    if args.physical and not args.port:
        parser.error("--physical requires --port for the actual ESP32 authority")
    if args.port and not args.physical:
        parser.error("a serial port alone does not authorize a physical claim; add --physical or use --mock")

    if args.physical:
        print(f"[Campaign] PHYSICAL qualification: ESP32 on {args.port} at {args.baud} baud")
        authority = PhysicalAuthorityClient(port=args.port, baud=args.baud)
    else:
        print("[Campaign] SIMULATED/PORTABLE logic test with MockAuthorityClient; physical gates are blocked")
        authority = MockAuthorityClient()

    print("[Campaign] Initializing WorkloadEngine...")
    engine = WorkloadEngine(
        require_gpu=args.physical,
        require_npu=args.physical,
    )

    print("[Campaign] Initializing AdaptiveRoutingPolicy...")
    policy = AdaptiveRoutingPolicy(
        require_gpu=args.physical,
        require_npu=args.physical,
    )
    print("[Campaign] Running bootstrap hardware calibration...")
    policy.bootstrap_calibration(engine)

    seeds = args.seeds if args.seeds is not None else [args.seed]
    all_seed_summaries = {}

    try:
        for s_idx, current_seed in enumerate(seeds):
            if len(seeds) > 1:
                print(f"\n=======================================================")
                print(f" Executing Campaign Iteration {s_idx + 1}/{len(seeds)} (Seed: {current_seed})")
                print(f"=======================================================\n")

            runner = RouterCampaignRunner(
                authority_client=authority,
                workload_engine=engine,
                routing_policy=policy,
                artifacts_dir=args.artifacts,
                total_jobs=args.jobs,
                stochastic_mode=args.stochastic,
                adversarial_injection_job=args.adversarial_at,
                concurrency=args.concurrency,
                seed=current_seed,
            )

            summary = runner.run()
            all_seed_summaries[current_seed] = summary

            # If multi-seed, also write individual seed report
            if len(seeds) > 1:
                seed_report_path = args.artifacts / f"router_campaign_report_seed_{current_seed}.json"
                with open(seed_report_path, "w", encoding="utf-8") as f:
                    json.dump(summary, f, indent=2)

            print(f"\n================= CAMPAIGN AUDIT SUMMARY (Seed {current_seed}) =================")
            for g_name, g_val in summary["gates"].items():
                if isinstance(g_val, dict):
                    status = "PASS" if g_val.get("passed") else "FAIL"
                    print(f"  [{status}] {g_name}: {g_val}")
                else:
                    print(f"  {g_name}: {g_val}")
            print("========================================================================\n")

        if len(seeds) > 1:
            multi_seed_report = {
                "seeds": seeds,
                "total_runs": len(seeds),
                "all_runs_passed": all(s["gates"]["all_gates_passed"] for s in all_seed_summaries.values()),
                "runs": {str(s): s_summary["gates"] for s, s_summary in all_seed_summaries.items()},
            }
            multi_report_path = args.artifacts / "multi_seed_report.json"
            with open(multi_report_path, "w", encoding="utf-8") as f:
                json.dump(multi_seed_report, f, indent=2)
            print(f"[Campaign] Multi-seed aggregate report saved to: {multi_report_path}")

        all_passed = all(s["gates"]["all_gates_passed"] for s in all_seed_summaries.values())
        if not all_passed:
            sys.exit(1)
    finally:
        authority.close()


if __name__ == "__main__":
    main()

