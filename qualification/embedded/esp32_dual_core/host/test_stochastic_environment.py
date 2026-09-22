#!/usr/bin/env python3
"""Unit and integration tests for stochastic endurance harness and adversarial canary rollback."""
from __future__ import annotations

from pathlib import Path
import tempfile
import pytest

from stochastic_environment import (
    RegimeType,
    StochasticEnvironmentGenerator,
)
from routing_policy import (
    AdaptiveRoutingPolicy,
    DEVICE_CPU,
    DEVICE_GPU,
    DEVICE_NPU,
    JobDescriptor,
    RouterNet,
)
from workload_engine import WorkloadEngine
from router_campaign import (
    MockAuthorityClient,
    RouterCampaignRunner,
)


def test_stochastic_environment_generator_transitions():
    engine = WorkloadEngine()
    auth = MockAuthorityClient()
    try:
        env = StochasticEnvironmentGenerator(
            workload_engine=engine,
            authority_client=auth,
            seed=123,
            mean_dwell_jobs=10,
        )
        initial_regime = env.current_regime
        assert initial_regime == RegimeType.NOMINAL

        # Advance jobs until a regime transition occurs
        regimes_visited = {initial_regime}
        for j in range(2, 60):
            r = env.step(j)
            regimes_visited.add(r)
            job = env.sample_job(j)
            assert job.batch_size in (1, 4, 16, 64)

        assert len(regimes_visited) >= 2
    finally:
        engine.shutdown()


def test_stochastic_recovery_and_memory_metrics():
    engine = WorkloadEngine()
    auth = MockAuthorityClient()
    try:
        env = StochasticEnvironmentGenerator(
            workload_engine=engine,
            authority_client=auth,
            seed=42,
            mean_dwell_jobs=15,
        )
        # Simulate an environmental shift and subsequent recovery
        for j in range(1, 30):
            env.step(j)
            # Record simulated adaptation feedback
            committed = True
            regret = 2500 if j < 5 else 400
            env.record_job_result(j, target_device=DEVICE_GPU, committed=committed, latency_us=1200, regret_us=regret)

        metrics = env.compute_summary_metrics()
        assert RegimeType.NOMINAL.value in metrics
        assert metrics[RegimeType.NOMINAL.value]["occurrences"] >= 1
    finally:
        engine.shutdown()


def test_adversarial_canary_injection_and_rollback():
    engine = WorkloadEngine()
    try:
        policy = AdaptiveRoutingPolicy()
        policy.bootstrap_calibration(engine)
        active_before = policy.deployer.active_compiled_model
        initial_promotions = policy.deployer.promotions_count
        initial_rollbacks = policy.deployer.rollbacks_count

        # Inject an adversarial candidate into the canary window
        injected = policy.inject_adversarial_test("inverted")
        assert injected is True
        assert policy.deployer.canary_window_remaining > 0

        # Feed degraded/high-latency & high-rejection canary observations
        snap = {"inflight": [0, 0, 0], "max_inflight": [16, 16, 16], "resource_tokens": 1000}
        load = {"cpu": 0.05, "gpu": 0.05, "npu": 0.05}
        job = JobDescriptor(job_id=999, batch_size=4, priority=0.5, latency_budget_us=10000)
        feats = policy.featurize(job, snap, load)

        for _ in range(8):
            policy.record_feedback(feats, action=DEVICE_CPU, latency_us=15000, rejected=True, phase="CanaryTest")

        # Verify rollback was triggered
        assert policy.deployer.rollbacks_count == initial_rollbacks + 1
        assert policy.deployer.canary_window_remaining == 0
        assert policy.deployer.candidate_compiled_model is None
        # Verify active policy was preserved
        assert policy.deployer.active_compiled_model is not None
    finally:
        engine.shutdown()


def test_occ_retry_handling():
    auth = MockAuthorityClient()
    snap = auth.reset(online_mask=7)
    curr_hash = snap["state_hash"]

    # Invalidate hash by proposing an external reservation
    _ = auth.propose(pre_state_hash=curr_hash, job_id=1, target=DEVICE_CPU, tokens=1)

    # Now attempt propose_with_occ_retry using the stale hash
    # Should automatically detect STALE_STATE_HASH, refresh state hash, and commit
    retry_res = auth.propose_with_occ_retry(pre_state_hash=curr_hash, job_id=2, target=DEVICE_GPU, tokens=1)
    assert retry_res["committed"] is True
    assert retry_res["reason"] == "NONE"
    assert retry_res["reservation_id"] == 2


def test_stochastic_campaign_with_adversarial_injection_mock():
    with tempfile.TemporaryDirectory() as tmp_dir:
        artifacts_path = Path(tmp_dir)
        engine = WorkloadEngine()
        policy = AdaptiveRoutingPolicy()
        policy.bootstrap_calibration(engine)
        auth = MockAuthorityClient()

        runner = RouterCampaignRunner(
            authority_client=auth,
            workload_engine=engine,
            routing_policy=policy,
            artifacts_dir=artifacts_path,
            total_jobs=40,
            stochastic_mode=True,
            adversarial_injection_job=15,
        )
        summary = runner.run()

        assert summary["wrong_authoritative_commits"] == 0
        assert summary["gates"]["G0_zero_wrong_commits"]["passed"] is True
        assert summary["gates"]["G8_adversarial_rollback"]["passed"] is True
        assert len(summary["golden_benchmarks"]) >= 1
