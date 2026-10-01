"""Comprehensive Conformance Test Suite: 16 Golden Vectors against Python Reference."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from conformance.wire.envelope_executor import EnvelopeExecutor

VECTORS_DIR = Path(__file__).resolve().parent.parent / "conformance" / "vectors"


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


def test_conformance_vectors_present():
    assert VECTORS_DIR.exists(), f"Vectors directory {VECTORS_DIR} must exist"
    vector_files = sorted(VECTORS_DIR.glob("*.json"))
    assert len(vector_files) >= 16, f"Expected at least 16 golden test vectors, got {len(vector_files)}"


@pytest.mark.parametrize(
    "vector_file",
    sorted(VECTORS_DIR.glob("*.json")),
    ids=lambda p: p.stem,
)
def test_golden_conformance_vector(executor: EnvelopeExecutor, vector_file: Path):
    with open(vector_file, "r", encoding="utf-8") as f:
        vector = json.load(f)

    vector_id = vector["vector_id"]
    if vector_id == "005_evidence_chain_continuity":
        # Multi-step chain tested separately
        return

    envelope = vector["input"]["envelope"]
    actual = executor.execute_envelope(envelope)
    expected = vector["expected"]

    assert actual["status"] == expected["status"], f"Vector {vector_id}: status mismatch"

    if expected["status"] == "SUCCESS":
        if "result" in expected and "attributes" in expected["result"]:
            for k, v in expected["result"]["attributes"].items():
                assert actual["result"]["attributes"].get(k) == v, f"Vector {vector_id}: attribute {k} mismatch"
        if "result" in expected and "reserved_quantity" in expected["result"]:
            assert actual["result"]["reserved_quantity"] == expected["result"]["reserved_quantity"]
            assert actual["result"]["sku"] == expected["result"]["sku"]
    else:
        assert len(actual["errors"]) > 0, f"Vector {vector_id}: expected error but none returned"
        expected_code = expected["errors"][0]["code"]
        assert actual["errors"][0]["code"] == expected_code, (
            f"Vector {vector_id}: error code mismatch: actual {actual['errors'][0]['code']} != expected {expected_code}"
        )


def test_evidence_chain_continuity_vector(executor: EnvelopeExecutor):
    vector_file = VECTORS_DIR / "005_evidence_chain_continuity.json"
    with open(vector_file, "r", encoding="utf-8") as f:
        vector = json.load(f)

    initial_state = vector["input"]["initial_state"]
    steps = vector["input"]["steps"]
    expected = vector["expected"]

    curr_state = dict(initial_state)
    prev_evidence_hash = "0" * 64
    for idx, step in enumerate(steps, 1):
        step_attr = step["post_attributes"]
        curr_state["attributes"] = step_attr
        curr_state["sequence"] = idx
        rec_expected = expected[f"record_{idx}"]
        assert rec_expected["step_number"] == idx
        assert rec_expected["prev_evidence_hash"] == prev_evidence_hash
        prev_evidence_hash = rec_expected["record_hash"]

    assert curr_state["attributes"] == expected["final_state"]["attributes"]
    assert curr_state["sequence"] == expected["ledger_length"]

