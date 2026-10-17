"""Unit tests for FullRecordOracle (Milestone P4)."""
import pytest
from experiments.uow_magazine_p4.scoring.full_record_oracle import FullRecordOracle


def test_positive_operational_full_match():
    proposal = {
        "domain": "industrial",
        "action": "EMERGENCY_DEPRESSURIZE",
        "disposition": "COMMIT",
        "parameters": {"unit_id": "P-101", "target_psi": 90.0},
        "guard_conditions": ["interlock_verified"],
        "unknowns": [],
    }
    ground_truth = {
        "domain": "industrial",
        "action": "EMERGENCY_DEPRESSURIZE",
        "disposition": "COMMIT",
        "parameters": {"unit_id": "P-101", "target_psi": 90.0},
        "guard_conditions": ["interlock_verified"],
        "unknowns": [],
    }
    context = {"allowed_entities": ["P-101", "T-202"]}

    res = FullRecordOracle.evaluate(proposal, ground_truth, context, grammar="operational")
    assert res.schema_valid is True
    assert res.grammar_classification is True
    assert res.complete_semantic_match is True
    assert res.grounding_valid is True
    assert res.uncertainty_valid is True
    assert res.numeric_precision is True
    assert res.is_fully_qualified is True


def test_negative_ungrounded_entity_detection():
    proposal = {
        "domain": "industrial",
        "action": "EMERGENCY_DEPRESSURIZE",
        "disposition": "COMMIT",
        "parameters": {"unit_id": "HALLUCINATED_TURBINE_999"},
        "guard_conditions": [],
        "unknowns": [],
    }
    ground_truth = {
        "domain": "industrial",
        "action": "EMERGENCY_DEPRESSURIZE",
        "disposition": "COMMIT",
        "parameters": {"unit_id": "P-101"},
        "guard_conditions": [],
        "unknowns": [],
    }
    context = {"allowed_entities": ["P-101", "T-202"]}

    res = FullRecordOracle.evaluate(proposal, ground_truth, context, grammar="operational")
    assert res.grounding_valid is False
    assert len(res.grounding_violations) > 0
    assert "HALLUCINATED_TURBINE_999" in res.grounding_violations[0]
    assert res.complete_semantic_match is False
    assert res.is_fully_qualified is False


def test_negative_missing_uncertainty_flag():
    # Ground truth requires acknowledging missing calibration telemetry
    proposal = {
        "domain": "cybersecurity",
        "action": "ISOLATE_HOST",
        "disposition": "COMMIT",
        "parameters": {"endpoint_id": "EP-01"},
        "unknowns": [],  # Failed to flag missing CVE risk
    }
    ground_truth = {
        "domain": "cybersecurity",
        "action": "ISOLATE_HOST",
        "disposition": "COMMIT",
        "parameters": {"endpoint_id": "EP-01"},
        "unknowns": ["missing_cve_severity"],
    }
    context = {"allowed_entities": ["EP-01"]}

    res = FullRecordOracle.evaluate(proposal, ground_truth, context, grammar="operational")
    assert res.uncertainty_valid is False
    assert res.complete_semantic_match is False


def test_negative_numeric_precision_mismatch():
    proposal = {
        "domain": "industrial",
        "action": "THROTTLE_FEED",
        "disposition": "COMMIT",
        "parameters": {"flow_rate_gpm": 12.5},  # Mismatched from expected 45.0
    }
    ground_truth = {
        "domain": "industrial",
        "action": "THROTTLE_FEED",
        "disposition": "COMMIT",
        "parameters": {"flow_rate_gpm": 45.0},
    }

    res = FullRecordOracle.evaluate(proposal, ground_truth, grammar="operational")
    assert res.numeric_precision is False
    assert res.complete_semantic_match is False
    assert any("Numeric mismatch" in r for r in res.failure_reasons)


def test_positive_temporal_match():
    proposal = {
        "domain": "logistics",
        "target_action": "DISPATCH_FREIGHT",
        "relation": "BEFORE",
        "time_window": "04:00-06:00",
        "dependencies": ["CUSTOMS_CLEARANCE"],
    }
    ground_truth = {
        "domain": "logistics",
        "target_action": "DISPATCH_FREIGHT",
        "relation": "BEFORE",
        "time_window": "04:00-06:00",
        "dependencies": ["CUSTOMS_CLEARANCE"],
    }

    res = FullRecordOracle.evaluate(proposal, ground_truth, grammar="temporal")
    assert res.schema_valid is True
    assert res.temporal_correctness is True
    assert res.complete_semantic_match is True


def test_positive_recovery_match():
    proposal = {
        "domain": "industrial",
        "strategy": "CIRCUIT_BREAK",
        "failure_mode": "OVERPRESSURE_TRIP",
        "max_retries": 0,
    }
    ground_truth = {
        "domain": "industrial",
        "strategy": "CIRCUIT_BREAK",
        "failure_mode": "OVERPRESSURE_TRIP",
        "max_retries": 0,
    }

    res = FullRecordOracle.evaluate(proposal, ground_truth, grammar="recovery")
    assert res.schema_valid is True
    assert res.recovery_correctness is True
    assert res.complete_semantic_match is True
