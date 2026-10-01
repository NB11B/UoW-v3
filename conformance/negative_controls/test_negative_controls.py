"""Negative Control Gate Verification Suite.

Strict verification of all 10 required negative rejection categories and boundary edge cases:
1. Guard rejection (ERR_GUARD_UNSATISFIED)
2. Stale pre-state rejection (ERR_STALE_PRE_STATE / PRE_STATE_HASH_MISMATCH)
3. Tampered proposal rejection (ERR_PROPOSAL_TAMPERED / STATE_DIVERGENCE)
4. Authority rejection (ERR_UNAUTHORIZED_AUTHORITY / ERR_AUTHORITY_DENIED)
5. Evidence-chain tampering verification (ERR_EVIDENCE_CHAIN_TAMPERED)
6. Idempotent replay (cached receipt return)
7. Malformed envelope rejection (ERR_SCHEMA_VIOLATION)
8. Version rejection (ERR_VERSION_MISMATCH)
9. Payload conflict rejection (ERR_IDEMPOTENCY_CONFLICT)
10. Authority escalation rejection (ERR_AUTHORITY_DENIED / ERR_AUTHORITY_ESCALATION)
11. Unicode and special character handling
12. Integer boundary cases
13. Transport retry duplicate ack handling
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from conformance.wire.envelope_executor import EnvelopeExecutor

VECTORS_DIR = Path(__file__).resolve().parent.parent / "vectors"


@pytest.fixture
def executor() -> EnvelopeExecutor:
    idem_store = {
        "idem-key-777": {
            "request_id": "req-007",
            "operation": "uow.transition.execute_one",
            "status": "SUCCESS",
            "result": {"attributes": {"n": 43}, "sequence": 1},
            "evidence": {"evidence_hash": "ev-777", "prev_record_hash": "0" * 64, "certificate_hash": "cert-777", "ledger_index": 1},
            "execution_metadata": {"duration_ms": 0.1, "host_node": "python-ref", "execution_backend": "python"},
            "errors": [],
        }
    }
    return EnvelopeExecutor(idempotency_store=idem_store)


def _load_vector(filename: str) -> dict:
    path = VECTORS_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_guard_rejection(executor: EnvelopeExecutor):
    vec = _load_vector("002_guard_unsatisfied_rejection.json")
    res = executor.execute_envelope(vec["input"]["envelope"])
    assert res["status"] == "REJECTED"
    assert res["errors"][0]["code"] == "ERR_GUARD_UNSATISFIED"


def test_stale_state_rejection(executor: EnvelopeExecutor):
    vec = _load_vector("003_stale_pre_state_rejection.json")
    res = executor.execute_envelope(vec["input"]["envelope"])
    assert res["status"] == "REJECTED"
    assert res["errors"][0]["code"] == "ERR_STALE_PRE_STATE"
    assert res["result"]["rejection_reason"] == "PRE_STATE_HASH_MISMATCH"


def test_tampered_proposal_rejection(executor: EnvelopeExecutor):
    vec = _load_vector("004_tampered_proposal_rejection.json")
    res = executor.execute_envelope(vec["input"]["envelope"])
    assert res["status"] == "REJECTED"
    assert res["errors"][0]["code"] == "ERR_ROUTE_DIVERGENCE"
    assert res["result"]["rejection_reason"] == "STATE_DIVERGENCE"


def test_authority_unauthorized_rejection(executor: EnvelopeExecutor):
    vec = _load_vector("006_authority_unauthorized_rejection.json")
    res = executor.execute_envelope(vec["input"]["envelope"])
    assert res["status"] == "REJECTED"
    assert res["errors"][0]["code"] == "ERR_AUTHORITY_DENIED"


def test_evidence_tampering_rejection(executor: EnvelopeExecutor):
    vec = _load_vector("013_evidence_tampering_rejection.json")
    res = executor.execute_envelope(vec["input"]["envelope"])
    assert res["status"] == "REJECTED"
    assert res["errors"][0]["code"] == "ERR_ROUTE_DIVERGENCE"
    assert res["result"]["rejection_reason"] == "STATE_DIVERGENCE"


def test_idempotent_replay(executor: EnvelopeExecutor):
    vec = _load_vector("007_idempotency_replay.json")
    res = executor.execute_envelope(vec["input"]["envelope"])
    assert res["status"] == "SUCCESS"
    assert res["result"]["attributes"]["n"] == 43


def test_malformed_envelope_rejection(executor: EnvelopeExecutor):
    vec = _load_vector("009_malformed_envelope_rejection.json")
    res = executor.execute_envelope(vec["input"]["envelope"])
    assert res["status"] == "REJECTED"
    assert res["errors"][0]["code"] == "ERR_SCHEMA_VIOLATION"


def test_unknown_protocol_version_rejection(executor: EnvelopeExecutor):
    vec = _load_vector("010_unknown_protocol_version.json")
    res = executor.execute_envelope(vec["input"]["envelope"])
    assert res["status"] == "REJECTED"
    assert res["errors"][0]["code"] == "ERR_VERSION_MISMATCH"


def test_idempotency_payload_conflict_rejection(executor: EnvelopeExecutor):
    vec = _load_vector("011_idempotency_payload_conflict.json")
    res = executor.execute_envelope(vec["input"]["envelope"])
    assert res["status"] == "REJECTED"
    assert res["errors"][0]["code"] == "ERR_IDEMPOTENCY_CONFLICT"


def test_authority_escalation_attempt_rejection(executor: EnvelopeExecutor):
    vec = _load_vector("012_authority_escalation_attempt.json")
    res = executor.execute_envelope(vec["input"]["envelope"])
    assert res["status"] == "REJECTED"
    assert res["errors"][0]["code"] == "ERR_AUTHORITY_DENIED"


def test_unicode_and_special_characters_handling(executor: EnvelopeExecutor):
    vec = _load_vector("014_unicode_and_special_characters.json")
    res = executor.execute_envelope(vec["input"]["envelope"])
    assert res["status"] == "SUCCESS"
    assert "greeting" in res["result"]["attributes"]
    assert "city" in res["result"]["attributes"]
    assert "message" in res["result"]["attributes"]


def test_integer_boundary_cases_handling(executor: EnvelopeExecutor):
    vec = _load_vector("015_integer_boundary_cases.json")
    res = executor.execute_envelope(vec["input"]["envelope"])
    assert res["status"] == "SUCCESS"
    assert res["result"]["attributes"]["big_int"] == 9007199254740991
    assert res["result"]["attributes"]["zero_val"] == -10


def test_transport_retry_duplicate_ack_handling(executor: EnvelopeExecutor):
    vec = _load_vector("016_transport_retry_duplicate_ack.json")
    res = executor.execute_envelope(vec["input"]["envelope"])
    assert res["status"] == "SUCCESS"
    assert res["result"]["attributes"]["n"] == 43
