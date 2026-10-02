"""Tests for UoW v3.2 Deficit-Driven Development Governance & Intake Validator."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import pytest
import yaml

from qualification.v32_intake import (
    validate_witness_dict,
    validate_witness_file,
    validate_all_witnesses,
    PERMITTED_CATEGORIES,
    PERMITTED_STATUSES,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = REPO_ROOT / "governance" / "v32" / "WITNESS_TEMPLATE.yaml"


def make_valid_witness() -> Dict[str, Any]:
    """Generate a syntactically and semantically valid v3.2 intake witness record."""
    return {
        "schema_version": "uow.v32.witness.v1",
        "witness": {
            "id": "V32-W0001",
            "title": "Simulated state transition deficit under ultra-low latency",
            "observed_at": "2026-10-02T12:00:00Z",
            "reporter": "UoW Test Harness",
        },
        "baseline": {
            "release_tag": "v3.1.0",
            "release_commit": "65acfc0177a3037433b09e2fde582f23368dfb8b",
            "development_commit": "",
        },
        "classification": {
            "category": "MISSING_ARCHITECTURAL_PRIMITIVE",
        },
        "requirement": {
            "description": "Express sub-microsecond atomic fencing boundary",
            "current_expression_attempt": "Attempted using existing Boundary and GuardOp",
            "expected_invariant": "Deterministic fence resolution within 100ns",
        },
        "observation": {
            "observed_behavior": "Evaluation exceeded boundary envelope by 250ns",
            "expected_behavior": "Strict zero-allocation fence completion",
            "difference": "150ns tail latency violation",
        },
        "reproduction": {
            "environment": "x86-64 host Windows 11 with GCC 13.2",
            "commands": ["python -m pytest tests/test_sample_deficit.py"],
            "artifacts": ["repro_log.txt"],
            "deterministic_reproduction": True,
        },
        "falsification": {
            "null_hypothesis": "The current qualified UoW architecture is sufficient.",
            "minimal_campaign": "Run 1000 simulated clock-cycle transitions",
            "negative_controls": ["unfenced_baseline", "tampered_clock"],
            "acceptance_criteria": ["All 1000 transitions satisfy H_0 sufficiency bounds"],
            "rejection_criteria": ["Any transition demonstrates unresolvable primitive deficit"],
        },
        "disposition": {
            "status": "INTAKE",
            "result": "PENDING",
        },
        "change_authorization": {
            "architectural_change_allowed": False,
            "authorized_campaign": None,
        },
    }


def test_valid_intake_record() -> None:
    """A fully populated intake witness with architectural change disabled passes."""
    data = make_valid_witness()
    errors = validate_witness_dict(data)
    assert errors == [], f"Unexpected validation errors: {errors}"


def test_missing_baseline_sha() -> None:
    """Witness without a valid 40-hex commit SHA fails validation."""
    data = make_valid_witness()
    data["baseline"]["release_commit"] = ""
    data["baseline"]["development_commit"] = "not-a-sha"
    errors = validate_witness_dict(data)
    assert any("baseline commit SHA" in e for e in errors)


def test_unknown_deficit_category() -> None:
    """Witness with an unapproved deficit category fails validation."""
    data = make_valid_witness()
    data["classification"]["category"] = "NEW_COOL_FEATURE"
    errors = validate_witness_dict(data)
    assert any("Invalid classification category" in e for e in errors)


def test_no_reproduction() -> None:
    """Witness lacking reproduction commands fails validation."""
    data = make_valid_witness()
    data["reproduction"]["commands"] = []
    errors = validate_witness_dict(data)
    assert any("reproduction instructions" in e for e in errors)


def test_no_null_hypothesis() -> None:
    """Witness without explicit falsification null hypothesis fails validation."""
    data = make_valid_witness()
    data["falsification"]["null_hypothesis"] = ""
    errors = validate_witness_dict(data)
    assert any("null_hypothesis" in e for e in errors)


def test_architectural_change_enabled_at_intake() -> None:
    """Enabling architectural change at INTAKE status is strictly prohibited."""
    data = make_valid_witness()
    data["disposition"]["status"] = "INTAKE"
    data["change_authorization"]["architectural_change_allowed"] = True
    errors = validate_witness_dict(data)
    assert any("cannot be True when status is 'INTAKE'" in e for e in errors)


def test_architectural_change_enabled_at_reproduced() -> None:
    """Enabling architectural change at REPRODUCED status is strictly prohibited."""
    data = make_valid_witness()
    data["disposition"]["status"] = "REPRODUCED"
    data["change_authorization"]["architectural_change_allowed"] = True
    errors = validate_witness_dict(data)
    assert any("cannot be True when status is 'REPRODUCED'" in e for e in errors)


def test_qualifies_with_no_deficit() -> None:
    """A status of QUALIFIES cannot be paired with NO_DEFICIT result."""
    data = make_valid_witness()
    data["disposition"]["status"] = "QUALIFIES"
    data["disposition"]["result"] = "NO_DEFICIT"
    data["change_authorization"]["architectural_change_allowed"] = True
    errors = validate_witness_dict(data)
    assert any("status 'QUALIFIES' requires disposition.result" in e or "cannot be 'QUALIFIES'" in e for e in errors)


def test_qualifies_with_valid_deficit() -> None:
    """A qualified deficit with matching result and authorized campaign passes."""
    data = make_valid_witness()
    data["classification"]["category"] = "BOUNDARY_FAILURE_NEW_CONDITION"
    data["disposition"]["status"] = "QUALIFIES"
    data["disposition"]["result"] = "BOUNDARY_FAILURE_NEW_CONDITION"
    data["change_authorization"]["architectural_change_allowed"] = True
    data["change_authorization"]["authorized_campaign"] = "v3.2/fencing-under-partition"
    errors = validate_witness_dict(data)
    assert errors == [], f"Unexpected errors on valid qualification: {errors}"


def test_closed_with_existing_architecture_sufficient() -> None:
    """Witness closed because existing architecture is sufficient passes cleanly."""
    data = make_valid_witness()
    data["disposition"]["status"] = "CLOSED"
    data["disposition"]["result"] = "EXISTING_ARCHITECTURE_SUFFICIENT"
    data["change_authorization"]["architectural_change_allowed"] = False
    errors = validate_witness_dict(data)
    assert errors == [], f"Unexpected errors on valid closure: {errors}"


def test_witness_template_yaml_parses_cleanly() -> None:
    """Verify that WITNESS_TEMPLATE.yaml exists, loads as valid YAML, and matches expected schema version."""
    assert TEMPLATE_PATH.exists(), f"Missing template at {TEMPLATE_PATH}"
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert data["schema_version"] == "uow.v32.witness.v1"
    assert data["baseline"]["release_tag"] == "v3.1.0"
    assert data["baseline"]["release_commit"] == "65acfc0177a3037433b09e2fde582f23368dfb8b"
    assert data["change_authorization"]["architectural_change_allowed"] is False
