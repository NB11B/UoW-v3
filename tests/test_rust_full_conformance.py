"""Native Rust 16/16 Semantic Conformance Test Suite (Milestone v3.1-M4).

Verifies that the independent native Rust runtime achieves 16/16 semantic conformance
against the canonical golden test vectors.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from conformance.rust.vector_bridge import RustVectorBridge

VECTORS_DIR = Path(__file__).resolve().parent.parent / "conformance" / "vectors"


@pytest.fixture(scope="session")
def bridge() -> RustVectorBridge:
    return RustVectorBridge()


def test_rust_batch_all_16_vectors(bridge: RustVectorBridge) -> None:
    """Execute all 16 canonical vectors via native Rust batch runner."""
    passed, total, output = bridge.execute_all(VECTORS_DIR)
    print("\n" + output)
    assert total >= 16, f"Expected 16 vectors, got {total}"
    assert passed == 16, f"Expected 16 passed vectors, got {passed}/{total}\nOutput:\n{output}"


@pytest.mark.parametrize(
    "vector_file",
    sorted(VECTORS_DIR.glob("*.json")),
    ids=lambda p: p.stem,
)
def test_rust_individual_vector_semantic_parity(bridge: RustVectorBridge, vector_file: Path) -> None:
    """Execute each canonical vector through the Rust bridge and verify semantic parity."""
    with open(vector_file, "r", encoding="utf-8") as f:
        vector = json.load(f)

    vector_id = vector["vector_id"]
    expected = vector["expected"]
    actual = bridge.execute_vector(vector_file)

    assert actual["status"] == expected["status"], f"Vector {vector_id}: status mismatch ({actual['status']} != {expected['status']})"

    if expected["status"] == "SUCCESS":
        if vector_id == "005_evidence_chain_continuity":
            assert actual["ledger_length"] == expected["ledger_length"]
            assert actual["ledger_integrity"] == expected["ledger_integrity"]
            assert actual["record_1"]["record_hash"] == expected["record_1"]["record_hash"]
            assert actual["record_2"]["record_hash"] == expected["record_2"]["record_hash"]
            assert actual["record_2"]["prev_evidence_hash"] == expected["record_2"]["prev_evidence_hash"]
            assert actual["final_state"]["attributes"] == expected["final_state"]["attributes"]
            assert actual["final_state"]["state_hash"] == expected["final_state"]["state_hash"]
            return

        exp_res = expected.get("result", {})
        act_res = actual.get("result", {})

        if "attributes" in exp_res:
            for k, v in exp_res["attributes"].items():
                assert act_res["attributes"].get(k) == v, f"Vector {vector_id}: attribute '{k}' mismatch"

        if "reserved_quantity" in exp_res:
            assert act_res["reserved_quantity"] == exp_res["reserved_quantity"]
            assert act_res["sku"] == exp_res["sku"]
            assert act_res["status"] == exp_res["status"]

        # Vector 014: Multilingual UTF-8 preservation
        if vector_id == "014_unicode_and_special_characters":
            assert act_res["attributes"]["greeting"] == "Hola señora"
            assert act_res["attributes"]["city"] == "München"
            assert act_res["attributes"]["message"] == "café / こんにちは / 🚀"
            assert act_res["state_hash"] == expected["result"]["state_hash"]

        # Vector 015: Exact 64-bit integer boundary
        if vector_id == "015_integer_boundary_cases":
            assert act_res["attributes"]["big_int"] == 9007199254740991
            assert act_res["attributes"]["zero_val"] == -10
            assert act_res["state_hash"] == expected["result"]["state_hash"]

    else:
        assert len(actual.get("errors", [])) > 0, f"Vector {vector_id}: expected error in output"
        expected_code = expected["errors"][0]["code"]
        actual_code = actual["errors"][0]["code"]
        assert actual_code == expected_code, f"Vector {vector_id}: error code mismatch ({actual_code} != {expected_code})"
