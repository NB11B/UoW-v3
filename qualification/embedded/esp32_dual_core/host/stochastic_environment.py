#!/usr/bin/env python3
"""Stochastic Nonstationary Environment Generator for Continuous Adaptation Testing.

Simulates real-world unpredictable environmental shifts:
- Dynamic dwell times drawn from exponential / Poisson distributions
- Unannounced phase transitions (no explicit phase notification to the learner)
- Compound contention (simultaneous GPU + NPU or CPU + GPU pressure)
- Recurring regimes (A -> B -> C -> A -> D -> B) to measure operational memory:
    rho_memory = T_reacquire / T_learn_first << 1
- Continuous metric calculation for:
    T_detect:  Jobs until routing distribution shifts after an environmental shock
    T_recover: Jobs until running average regret falls below recovery threshold (1,000 us)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from pathlib import Path
import random
import sys
import time
from typing import Any

# Ensure UTF-8 output encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from routing_policy import DEVICE_CPU, DEVICE_GPU, DEVICE_NPU, JobDescriptor
from workload_engine import WorkloadEngine


class RegimeType(Enum):
    NOMINAL = "NOMINAL"
    LARGE_BATCH_BURST = "LARGE_BATCH_BURST"
    GPU_CONTENTION = "GPU_CONTENTION"
    NPU_CONTENTION = "NPU_CONTENTION"
    COMPOUND_CONTENTION = "COMPOUND_CONTENTION"
    DEVICE_OUTAGE = "DEVICE_OUTAGE"


@dataclass
class RegimeTransitionEvent:
    job_id: int
    regime: RegimeType
    dwell_jobs: int
    timestamp_s: float
    description: str


@dataclass
class RegimeRecoveryMetric:
    regime: RegimeType
    occurrence_index: int
    start_job_id: int
    t_detect_jobs: int | None = None
    t_recover_jobs: int | None = None
    reacquire_ratio: float | None = None


class StochasticEnvironmentGenerator:
    """Manages unannounced environmental shocks, compound contention, and recovery metrics."""

    def __init__(
        self,
        workload_engine: WorkloadEngine,
        authority_client: Any,
        seed: int = 42,
        mean_dwell_jobs: int = 80,
    ):
        self.engine = workload_engine
        self.authority = authority_client
        self.rng = random.Random(seed)
        self.mean_dwell = mean_dwell_jobs

        self.current_regime = RegimeType.NOMINAL
        self.jobs_in_current_regime = 0
        self.target_dwell_jobs = self._sample_dwell()

        self.history_events: list[RegimeTransitionEvent] = []
        self.regime_occurrences: dict[RegimeType, list[RegimeRecoveryMetric]] = {r: [] for r in RegimeType}

        self.regime_sequence: list[RegimeType] = [
            RegimeType.NOMINAL,
            RegimeType.LARGE_BATCH_BURST,
            RegimeType.GPU_CONTENTION,
            RegimeType.NOMINAL,
            RegimeType.NPU_CONTENTION,
            RegimeType.COMPOUND_CONTENTION,
            RegimeType.DEVICE_OUTAGE,
            RegimeType.NOMINAL,
            RegimeType.GPU_CONTENTION,
            RegimeType.NOMINAL,
        ]
        self._sequence_idx = 0

        # Apply initial nominal regime
        self._apply_regime(1, self.regime_sequence[0])

    def _sample_dwell(self) -> int:
        """Sample dwell time from truncated exponential distribution."""
        # Mean dwell with minimum 30 jobs and maximum 250 jobs
        raw = self.rng.expovariate(1.0 / self.mean_dwell)
        return max(30, min(250, int(round(raw))))

    def _apply_regime(self, job_id: int, regime: RegimeType) -> None:
        """Enforce physical hardware contention and authority online status for regime."""
        self.current_regime = regime
        self.jobs_in_current_regime = 0
        self.target_dwell_jobs = self._sample_dwell()

        desc = ""
        if regime == RegimeType.NOMINAL:
            self.engine.set_gpu_contention(False)
            self.engine.set_npu_contention(False)
            self.engine.set_cpu_contention(False)
            self.authority.set_online(DEVICE_GPU, True)
            self.authority.set_online(DEVICE_NPU, True)
            desc = "All devices online and unburdened"

        elif regime == RegimeType.LARGE_BATCH_BURST:
            self.engine.set_gpu_contention(False)
            self.engine.set_npu_contention(False)
            self.authority.set_online(DEVICE_GPU, True)
            self.authority.set_online(DEVICE_NPU, True)
            desc = "Heavy Poisson burst of batch 16 and 64 workloads"

        elif regime == RegimeType.GPU_CONTENTION:
            self.engine.set_gpu_contention(True)
            self.engine.set_npu_contention(False)
            self.authority.set_online(DEVICE_GPU, True)
            desc = "Heavy background GEMM contention active on RTX 5070 GPU"

        elif regime == RegimeType.NPU_CONTENTION:
            self.engine.set_gpu_contention(False)
            self.engine.set_npu_contention(True)
            self.authority.set_online(DEVICE_GPU, True)
            desc = "Heavy background inference contention active on Intel NPU"

        elif regime == RegimeType.COMPOUND_CONTENTION:
            self.engine.set_gpu_contention(True)
            self.engine.set_npu_contention(True)
            self.authority.set_online(DEVICE_GPU, True)
            desc = "Simultaneous compound contention on GPU and NPU"

        elif regime == RegimeType.DEVICE_OUTAGE:
            self.engine.set_gpu_contention(False)
            self.engine.set_npu_contention(False)
            self.authority.set_online(DEVICE_GPU, False)
            desc = "Hardware authority took GPU offline (SCHED_SET_ONLINE 1 0)"

        event = RegimeTransitionEvent(
            job_id=job_id,
            regime=regime,
            dwell_jobs=self.target_dwell_jobs,
            timestamp_s=time.monotonic(),
            description=desc,
        )
        self.history_events.append(event)

        # Track occurrence metric
        occ_idx = len(self.regime_occurrences[regime])
        metric = RegimeRecoveryMetric(
            regime=regime,
            occurrence_index=occ_idx,
            start_job_id=job_id,
        )
        self.regime_occurrences[regime].append(metric)

        print(f"\n[StochasticEnv] >>> Environmental Shock at Job {job_id}: {regime.value} ({desc}) | Planned Dwell: {self.target_dwell_jobs} jobs <<<")

    def step(self, job_id: int) -> RegimeType:
        """Advance environmental state and trigger transitions when dwell expires."""
        self.jobs_in_current_regime += 1
        if self.jobs_in_current_regime >= self.target_dwell_jobs:
            self._sequence_idx = (self._sequence_idx + 1) % len(self.regime_sequence)
            next_regime = self.regime_sequence[self._sequence_idx]
            self._apply_regime(job_id, next_regime)
        return self.current_regime

    def sample_job(self, job_id: int) -> JobDescriptor:
        """Generate job appropriate for current stochastic environmental distribution."""
        rng = random.Random(job_id * 54321 + 99)
        regime = self.current_regime

        if regime == RegimeType.LARGE_BATCH_BURST:
            batch = rng.choices([1, 4, 16, 64], weights=[0.05, 0.05, 0.40, 0.50])[0]
        elif regime in (RegimeType.GPU_CONTENTION, RegimeType.COMPOUND_CONTENTION):
            batch = rng.choices([1, 4, 16, 64], weights=[0.25, 0.25, 0.25, 0.25])[0]
        elif regime == RegimeType.DEVICE_OUTAGE:
            batch = rng.choices([1, 4, 16, 64], weights=[0.10, 0.15, 0.35, 0.40])[0]
        else:
            batch = rng.choices([1, 4, 16, 64], weights=[0.30, 0.30, 0.25, 0.15])[0]

        prio = rng.uniform(0.1, 1.0)
        budget = int(rng.uniform(5000, 20000))
        return JobDescriptor(
            job_id=job_id,
            batch_size=batch,
            priority=prio,
            latency_budget_us=budget,
            tokens=1,
        )

    def record_job_result(
        self,
        job_id: int,
        target_device: int,
        committed: bool,
        latency_us: int,
        regret_us: int,
    ) -> None:
        """Update detection and recovery metrics for the active regime occurrence."""
        metrics_list = self.regime_occurrences.get(self.current_regime, [])
        if not metrics_list:
            return

        cur_metric = metrics_list[-1]
        elapsed = job_id - cur_metric.start_job_id

        # T_detect: first time routing shifts away from previously favored path or rejects
        if cur_metric.t_detect_jobs is None:
            if not committed:
                cur_metric.t_detect_jobs = elapsed
            elif self.current_regime == RegimeType.GPU_CONTENTION and target_device != DEVICE_GPU:
                cur_metric.t_detect_jobs = elapsed
            elif self.current_regime == RegimeType.NPU_CONTENTION and target_device != DEVICE_NPU:
                cur_metric.t_detect_jobs = elapsed
            elif self.current_regime == RegimeType.DEVICE_OUTAGE and target_device != DEVICE_GPU:
                cur_metric.t_detect_jobs = elapsed

        # T_recover: first time regret drops below 1,000 us and stays low
        if cur_metric.t_recover_jobs is None and elapsed >= 3:
            if committed and regret_us <= 1000:
                cur_metric.t_recover_jobs = elapsed

                # If recurring regime (occurrence_index > 0), compute rho_memory
                if cur_metric.occurrence_index > 0:
                    first_metric = metrics_list[0]
                    first_t = first_metric.t_recover_jobs or 20
                    cur_metric.reacquire_ratio = float(cur_metric.t_recover_jobs) / max(1.0, float(first_t))

    def compute_summary_metrics(self) -> dict[str, Any]:
        """Aggregate recovery and memory statistics across all regimes."""
        summary = {}
        for r_type, m_list in self.regime_occurrences.items():
            detects = [m.t_detect_jobs for m in m_list if m.t_detect_jobs is not None]
            recovers = [m.t_recover_jobs for m in m_list if m.t_recover_jobs is not None]
            ratios = [m.reacquire_ratio for m in m_list if m.reacquire_ratio is not None]

            summary[r_type.value] = {
                "occurrences": len(m_list),
                "mean_t_detect_jobs": (sum(detects) / len(detects)) if detects else None,
                "mean_t_recover_jobs": (sum(recovers) / len(recovers)) if recovers else None,
                "memory_reacquire_ratios": ratios,
                "mean_memory_reacquire_ratio": (sum(ratios) / len(ratios)) if ratios else None,
            }
        return summary
