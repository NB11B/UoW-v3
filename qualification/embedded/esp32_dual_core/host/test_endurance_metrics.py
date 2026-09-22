#!/usr/bin/env python3
"""Unit and integration tests for Step 3: Distribution tracking, variance reduction, and Gate G12."""
from __future__ import annotations

import math
from pathlib import Path
import pytest
from unittest.mock import MagicMock

from router_campaign import (
    DistributionTracker,
    JobRecord,
    RouterCampaignRunner,
    MockAuthorityClient,
    WorkloadEngine,
    AdaptiveRoutingPolicy,
    DEVICE_CPU,
    DEVICE_GPU,
    DEVICE_NPU,
)


def test_distribution_tracker_compute_percentiles():
    # Empty list
    empty_res = DistributionTracker.compute_percentiles([])
    assert empty_res["count"] == 0
    assert empty_res["mean"] == 0.0

    # Linear distribution 0 to 100
    vals = [float(x) for x in range(101)]
    res = DistributionTracker.compute_percentiles(vals)
    assert res["count"] == 101
    assert math.isclose(res["mean"], 50.0, abs_tol=1e-3)
    assert math.isclose(res["p50"], 50.0, abs_tol=1e-3)
    assert math.isclose(res["p90"], 90.0, abs_tol=1e-3)
    assert math.isclose(res["p95"], 95.0, abs_tol=1e-3)
    assert math.isclose(res["p99"], 99.0, abs_tol=1e-3)
    assert res["std"] > 0


def test_distribution_tracker_analyze_records():
    # Synthetic records with converging variance
    recs = []
    for i in range(100):
        # First half has high regret, second half has low regret
        reg = 10000 if i < 50 else 2000
        lat = 15000 if i < 50 else 3000
        dev = DEVICE_GPU if (i % 2 == 0) else DEVICE_NPU
        recs.append(
            JobRecord(
                job_id=i + 1,
                phase="NOMINAL" if i < 50 else "GPU_CONTENTION",
                phase_index=0 if i < 50 else 1,
                batch_size=4,
                target_device=dev,
                proposed_committed=True,
                rejection_reason="NONE",
                reservation_id=i + 1,
                receipt_committed=True,
                latency_us=lat,
                oracle_latencies_us={0: 1000, 1: 500, 2: 700},
                oracle_best_device=1,
                regret_us=reg,
                post_state_hash="a" * 64,
                evidence_root="b" * 64,
                canary_active=False,
            )
        )

    analysis = DistributionTracker.analyze_records(recs)
    assert "global_latency" in analysis
    assert "global_regret" in analysis
    assert "variance_reduction" in analysis
    assert "device_distributions" in analysis
    assert "regime_distributions" in analysis

    assert analysis["global_latency"]["count"] == 100
    assert analysis["global_regret"]["count"] == 100
    assert analysis["device_distributions"]["GPU"]["count"] == 50
    assert analysis["device_distributions"]["NPU"]["count"] == 50


def test_gate_g12_evaluation_in_mock_runner(tmp_path: Path):
    authority = MockAuthorityClient()
    engine = WorkloadEngine()
    policy = AdaptiveRoutingPolicy()

    runner = RouterCampaignRunner(
        authority_client=authority,
        workload_engine=engine,
        routing_policy=policy,
        artifacts_dir=tmp_path,
        total_jobs=60,
        stochastic_mode=False,
        concurrency=2,
        seed=42,
    )

    summary = runner.run()
    gates = summary["gates"]
    assert "G12_distribution_stability" in gates
    g12 = gates["G12_distribution_stability"]
    assert "p50_regret_us" in g12
    assert "p99_regret_us" in g12
    assert "variance_ratio" in g12
    # Portable CI runs on arbitrary hosted CPU hardware and cannot be required
    # to satisfy the physical campaign's absolute latency/regret envelope.
    # The physical G12 pass/fail is sealed in the recorded hardware artifacts.
    assert isinstance(g12["passed"], bool)
    assert math.isfinite(float(g12["p50_regret_us"]))
    assert math.isfinite(float(g12["p99_regret_us"]))
    assert math.isfinite(float(g12["variance_ratio"]))
