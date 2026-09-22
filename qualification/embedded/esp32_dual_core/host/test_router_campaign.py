#!/usr/bin/env python3
"""Unit and integration tests for heterogeneous adaptive workload router."""
from __future__ import annotations

from pathlib import Path
import tempfile
import pytest

from workload_engine import (
    WorkloadEngine,
    DEVICE_CPU,
    DEVICE_GPU,
    DEVICE_NPU,
    BenchmarkVisionModel,
)
from routing_policy import (
    AdaptiveRoutingPolicy,
    JobDescriptor,
    RouterNet,
    DualReplayBuffer,
    RoutingExperience,
)
from router_campaign import (
    MockAuthorityClient,
    RouterCampaignRunner,
)


def test_workload_engine_cpu():
    engine = WorkloadEngine()
    try:
        r = engine.execute(job_id=1, target_device=DEVICE_CPU, batch_size=4)
        assert r.error is None
        assert r.latency_us > 0
        assert len(r.output_digest) == 64
        assert r.target_device == DEVICE_CPU
    finally:
        engine.shutdown()


def test_mock_authority_lifecycle():
    auth = MockAuthorityClient()
    snap = auth.reset(online_mask=7, max_cpu=16, max_gpu=16, max_npu=16, tokens=100)
    assert snap["online_mask"] == 7
    assert snap["resource_tokens"] == 100
    state_hash_0 = snap["state_hash"]

    # Propose valid reservation
    prop = auth.propose(pre_state_hash=state_hash_0, job_id=101, target=DEVICE_GPU, tokens=1)
    assert prop["committed"] is True
    assert prop["reservation_id"] == 1
    assert prop["post_state_hash"] != state_hash_0

    # Receipt valid completion
    rec = auth.receipt(reservation_id=1, status=0, latency_us=1200, output_digest="a" * 64)
    assert rec["committed"] is True
    assert rec["completion_seq"] == 1


def test_mock_authority_offline_rejection():
    auth = MockAuthorityClient()
    snap = auth.reset(online_mask=7)
    # Take GPU offline
    snap = auth.set_online(DEVICE_GPU, False)
    assert (snap["online_mask"] & (1 << DEVICE_GPU)) == 0

    # Propose GPU -> should be rejected with DEVICE_OFFLINE
    prop = auth.propose(pre_state_hash=snap["state_hash"], job_id=102, target=DEVICE_GPU, tokens=1)
    assert prop["committed"] is False
    assert prop["reason"] == "DEVICE_OFFLINE"


def test_dual_replay_buffer():
    buf = DualReplayBuffer(recent_capacity=10, retention_capacity=5)
    for i in range(20):
        exp = RoutingExperience(
            features=[0.1] * 12,
            action=i % 3,
            observed_latency_ms=1.5,
            rejected=0.0,
            phase="test",
        )
        buf.add(exp)

    sample = buf.sample(8)
    assert len(sample) <= 8
    assert len(buf.retention_buffer) > 0


def test_mock_router_campaign_short_run():
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
            total_jobs=30,
        )
        summary = runner.run()
        assert summary["wrong_authoritative_commits"] == 0
        g0 = summary["gates"]["G0_zero_wrong_commits"]
        assert g0["observed_pass"] is True
        assert g0["qualified"] is False
        assert g0["passed"] is False
        assert (artifacts_path / "router_campaign_report.json").exists()
