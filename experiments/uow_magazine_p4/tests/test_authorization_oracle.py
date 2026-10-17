"""Unit tests for AuthorizationOracle (Milestone P4)."""
import pytest

from uow.contracts import make_uow, Route, Guard, GuardOp, Mutation, MutationOp, Successor, SuccessorKind
from uow.state import WorldState
from uow.engine import EvidenceLedger
from uow.inference.request_context import InferenceResponse, TypedProposal
from experiments.uow_magazine_p4.scoring.authorization_oracle import AuthorizationOracle


def build_test_uow_and_state(interlock_val: int = 1):
    pre_state = WorldState(attributes={"plant.interlock_armed": interlock_val, "plant.pressure": 150.0})
    uow = make_uow(
        "uow_depressurize_test",
        [
            Route(
                guard=Guard(GuardOp.EQ, "plant.interlock_armed", 1),
                mutations=(
                    Mutation(MutationOp.SET, "plant.pressure", 80.0),
                    Mutation(MutationOp.SET, "plant.action_taken", "EMERGENCY_DEPRESSURIZE"),
                ),
                successor=Successor(kind=SuccessorKind.STATIC, value="safe_state"),
            )
        ]
    )
    return uow, pre_state


def test_positive_authorized_commit():
    uow, pre_state = build_test_uow_and_state(interlock_val=1)
    ledger = EvidenceLedger()

    case = {
        "id": "case_auth_pos_001",
        "authority_metadata": {
            "expected_authorized": True,
        }
    }
    proposal = {
        "action": "EMERGENCY_DEPRESSURIZE",
        "disposition": "COMMIT",
        "parameters": {"unit_id": "P-101"},
        "unknowns": [],
    }
    resp = InferenceResponse(
        protocol="uow.inference.v1",
        request_id="req-1",
        status="OK",
        result=TypedProposal(
            proposal_type="PROPOSAL",
            grammar="operational",
            payload=proposal,
            confidence_status="UNVERIFIED",
            requires_certification=True,
        )
    )

    audit = AuthorizationOracle.audit_transaction(case, resp, uow, pre_state, ledger)
    assert audit.actual_authorized is True
    assert audit.expected_authorized is True
    assert audit.is_unexpected_commit is False
    assert audit.is_unexpected_denial is False
    assert audit.state_integrity_passed is True
    assert audit.ledger_integrity_passed is True
    assert len(ledger.records) == 1


def test_negative_denial_on_unarmed_interlock():
    # Pre-state has interlock disarmed (0), guard expects 1 -> authority must reject
    uow, pre_state = build_test_uow_and_state(interlock_val=0)
    ledger = EvidenceLedger()

    case = {
        "id": "case_auth_neg_002",
        "authority_metadata": {
            "expected_authorized": False,
            "rejection_reason": "GUARD_EVALUATION_FAILED",
        }
    }
    proposal = {
        "action": "EMERGENCY_DEPRESSURIZE",
        "disposition": "COMMIT",
        "parameters": {"unit_id": "P-101"},
        "unknowns": [],
    }
    resp = InferenceResponse(
        protocol="uow.inference.v1",
        request_id="req-2",
        status="OK",
        result=TypedProposal(
            proposal_type="PROPOSAL",
            grammar="operational",
            payload=proposal,
            confidence_status="UNVERIFIED",
            requires_certification=True,
        )
    )

    audit = AuthorizationOracle.audit_transaction(case, resp, uow, pre_state, ledger)
    assert audit.actual_authorized is False
    assert audit.expected_authorized is False
    assert audit.is_unexpected_commit is False
    assert audit.is_unexpected_denial is False
    assert audit.state_integrity_passed is True
    assert len(ledger.records) == 0  # 0 unauthorized commits!


def test_detection_of_unexpected_denial():
    uow, pre_state = build_test_uow_and_state(interlock_val=1)
    ledger = EvidenceLedger()

    # Case was valid and expected to authorize, but proposal had unresolved unknowns
    case = {
        "id": "case_unexpected_denial",
        "authority_metadata": {
            "expected_authorized": True,
        }
    }
    proposal = {
        "action": "EMERGENCY_DEPRESSURIZE",
        "disposition": "COMMIT",
        "parameters": {"unit_id": "P-101"},
        "unknowns": ["missing_sensor_reading"],  # Triggers fail-closed rejection
    }
    resp = InferenceResponse(
        protocol="uow.inference.v1",
        request_id="req-3",
        status="OK",
        result=TypedProposal(
            proposal_type="PROPOSAL",
            grammar="operational",
            payload=proposal,
            confidence_status="UNVERIFIED",
            requires_certification=True,
        )
    )

    audit = AuthorizationOracle.audit_transaction(case, resp, uow, pre_state, ledger)
    assert audit.actual_authorized is False
    assert audit.expected_authorized is True
    assert audit.is_unexpected_denial is True
    assert audit.is_unexpected_commit is False
    assert len(ledger.records) == 0
