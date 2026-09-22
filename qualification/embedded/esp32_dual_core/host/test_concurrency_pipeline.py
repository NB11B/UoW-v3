#!/usr/bin/env python3
"""Unit and integration tests for Asynchronous Multi-Threaded Worker Pool & OCC Concurrency Pipeline."""
from __future__ import annotations

import concurrent.futures
from pathlib import Path
import tempfile
import time
import pytest

from routing_policy import (
    AdaptiveRoutingPolicy,
    DEVICE_CPU,
    DEVICE_GPU,
    DEVICE_NPU,
    JobDescriptor,
)
from workload_engine import WorkloadEngine
from router_campaign import (
    MockAuthorityClient,
    RouterCampaignRunner,
)


def test_thread_safe_authority_concurrent_snapshots():
    """Verify thread-safe locking under concurrent access to authority."""
    auth = MockAuthorityClient()
    auth.reset()

    def _worker(thread_id: int):
        for _ in range(50):
            snap = auth.get_snapshot()
            assert "state_hash" in snap
            assert "online_mask" in snap

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(_worker, i) for i in range(8)]
        for fut in concurrent.futures.as_completed(futures):
            fut.result()


def test_concurrent_occ_conflict_resolution():
    """Verify that asynchronous completions advance state hash and proposals retry successfully."""
    auth = MockAuthorityClient()
    snap = auth.reset(online_mask=7)
    initial_hash = snap["state_hash"]

    # Reserve job 1
    res1 = auth.propose(pre_state_hash=initial_hash, job_id=1, target=DEVICE_CPU, tokens=1)
    assert res1["committed"] is True
    res1_id = res1["reservation_id"]
    post_res1_hash = res1["post_state_hash"]

    # Now, simulate a background completion committing on the authority
    rec_res = auth.receipt(reservation_id=res1_id, status=0, latency_us=1000, output_digest="0" * 64)
    assert rec_res["committed"] is True
    advanced_hash = rec_res["post_state_hash"]
    assert advanced_hash != post_res1_hash

    # A concurrent proposal prepared with post_res1_hash will hit STALE_STATE_HASH
    stale_prop = auth.propose(pre_state_hash=post_res1_hash, job_id=2, target=DEVICE_GPU, tokens=1)
    assert stale_prop["committed"] is False
    assert stale_prop["reason"] == "STALE_STATE_HASH"

    # Now propose_with_occ_retry using the stale hash: should detect and retry
    retry_prop = auth.propose_with_occ_retry(pre_state_hash=post_res1_hash, job_id=2, target=DEVICE_GPU, tokens=1)
    assert retry_prop["committed"] is True
    assert retry_prop["reason"] == "NONE"
    assert retry_prop.get("occ_attempts", 1) >= 2


def test_async_router_campaign_mock_run():
    """Verify end-to-end async concurrency pipeline execution with K=4 concurrent workers."""
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
            concurrency=4,
            stochastic_mode=True,
            adversarial_injection_job=15,
        )
        summary = runner.run()

        assert summary["wrong_authoritative_commits"] == 0
        assert summary["total_jobs"] == 40
        assert summary["records_count"] == 40
        assert summary["gates"]["G0_zero_wrong_commits"]["passed"] is True
        assert summary["gates"]["G8_adversarial_rollback"]["passed"] is True
        assert summary["gates"]["G11_occ_concurrency"]["passed"] is True
        assert summary["gates"]["G11_occ_concurrency"]["concurrency"] == 4
