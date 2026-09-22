#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qualification.evidence import (
    ClaimRequirement,
    EvidenceContext,
    EvidenceLevel,
    evaluate_claim,
)
from router_campaign import MockAuthorityClient
from workload_engine import DEVICE_NPU, WorkloadEngine


def test_simulated_observation_cannot_pass_physical_claim():
    context = EvidenceContext(
        EvidenceLevel.SIMULATED,
        "unit-test",
        {},
        {"authority": "mock"},
    )
    result = evaluate_claim(
        True,
        context,
        ClaimRequirement(EvidenceLevel.PHYSICAL, ("authority",)),
    )
    assert result["observed_pass"] is True
    assert result["qualified"] is False
    assert result["passed"] is False


def test_substituted_component_blocks_physical_claim():
    context = EvidenceContext(
        EvidenceLevel.PHYSICAL,
        "unit-test",
        {"authority": "ESP32", "npu": "logical NPU"},
        {"npu": "CPU substitute"},
    )
    result = evaluate_claim(
        True,
        context,
        ClaimRequirement(EvidenceLevel.PHYSICAL, ("authority", "npu")),
    )
    assert result["qualified"] is False
    assert result["passed"] is False


def test_actual_components_can_qualify_physical_claim():
    context = EvidenceContext(
        EvidenceLevel.PHYSICAL,
        "unit-test",
        {"authority": "ESP32", "npu": "Intel AI Boost"},
        {},
    )
    result = evaluate_claim(
        True,
        context,
        ClaimRequirement(EvidenceLevel.PHYSICAL, ("authority", "npu")),
    )
    assert result["qualified"] is True
    assert result["passed"] is True


def test_mock_authority_is_explicitly_simulated():
    context = MockAuthorityClient().evidence_context()
    assert context.level is EvidenceLevel.SIMULATED
    assert "authority" in context.substitutions
    assert "authority" not in context.actual_components


def test_npu_request_never_silently_falls_back_to_cpu():
    engine = WorkloadEngine()
    try:
        receipt = engine.execute(job_id=123, target_device=DEVICE_NPU, batch_size=1)
        if engine.has_npu:
            assert receipt.error is None
            assert receipt.actual_backend == "OPENVINO_NPU"
        else:
            assert receipt.error is not None
            assert receipt.actual_backend == "UNAVAILABLE"
            assert "NPU requested" in receipt.error
    finally:
        engine.shutdown()
