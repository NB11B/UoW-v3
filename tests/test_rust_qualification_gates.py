"""Milestone v3.1-M4 Qualification Gate Test Suite: Independent Rust Runtime.

Validates the 6 qualification gates of M4:
  - Gate 1 (RUST-M4-G01): 16/16 canonical semantic vectors
  - Gate 2 (RUST-M4-G02): OCC conflict equivalence
  - Gate 3 (RUST-M4-G03): Deterministic commit sequencing
  - Gate 4 (RUST-M4-G04): WAL crash/replay equivalence
  - Gate 5 (RUST-M4-G05): Deterministic DAG orchestration
  - Gate 6 (RUST-M4-G06): Proposer/authority non-escalation
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest
from conformance.rust.vector_bridge import RustVectorBridge

QUAL_DIR = Path(__file__).resolve().parent.parent / "qualification" / "rust" / "native_runtime"
VECTORS_DIR = QUAL_DIR / "vectors"
MANIFEST_PATH = QUAL_DIR / "QUALIFICATION_MANIFEST.json"
CANONICAL_VECTORS_DIR = Path(__file__).resolve().parent.parent / "conformance" / "vectors"


@pytest.fixture(scope="session")
def bridge() -> RustVectorBridge:
    return RustVectorBridge()


def test_m4_manifest_structure_and_gates() -> None:
    """Verify manifest schema, 6 qualification gates, and vector cryptographic hashes."""
    assert MANIFEST_PATH.exists(), f"Missing manifest at {MANIFEST_PATH}"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["campaign_id"] == "V31-RUST-RUNTIME"
    assert manifest["disposition"] == "QUALIFIED"
    assert manifest["signoff_level"] == "L3 Runtime Qualified"

    gates = manifest["qualification_gates"]
    assert len(gates) == 6, f"Expected 6 qualification gates, found {len(gates)}"
    for gate in gates:
        assert gate["status"] == "PASSED", f"Gate {gate['gate_id']} did not pass: {gate}"

    # Verify cryptographic digests for vector files
    vectors_prov = manifest["immutable_provenance"]["vectors"]
    for vec_file in VECTORS_DIR.glob("*.json"):
        hasher = hashlib.sha256()
        with open(vec_file, "rb") as f:
            hasher.update(f.read().replace(b"\r\n", b"\n"))
        actual_hash = hasher.hexdigest()
        key = f"{vec_file.stem}_sha256"
        assert key in vectors_prov, f"Missing provenance key {key}"
        assert actual_hash == vectors_prov[key], f"Hash mismatch for {vec_file.name}: {actual_hash} != {vectors_prov[key]}"


def test_gate1_rust_canonical_16_vectors(bridge: RustVectorBridge) -> None:
    """RUST-M4-G01: 16/16 canonical semantic vectors."""
    passed, total, output = bridge.execute_all(CANONICAL_VECTORS_DIR)
    assert total >= 16, f"Expected at least 16 vectors, got {total}"
    assert passed == 16, f"Expected 16 passed vectors, got {passed}/{total}\nOutput:\n{output}"


def test_gate2_occ_conflict_vectors() -> None:
    """RUST-M4-G02: OCC conflict equivalence."""
    vec_path = VECTORS_DIR / "occ_vectors.json"
    assert vec_path.exists()
    with open(vec_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data["cases"]
    assert len(cases) == 5
    case_ids = [c["case_id"] for c in cases]
    assert "OCC_01_DISJOINT_WRITES" in case_ids
    assert "OCC_02_WRITE_WRITE_COLLISION" in case_ids
    assert "OCC_03_READ_WRITE_HAZARD" in case_ids
    assert "OCC_04_WRITE_READ_COLLISION" in case_ids
    assert "OCC_05_STALE_BASE_SEQUENCE" in case_ids


def test_gate3_deterministic_sequencing() -> None:
    """RUST-M4-G03: Deterministic commit sequencing."""
    vec_path = VECTORS_DIR / "sequencing_vectors.json"
    assert vec_path.exists()
    with open(vec_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    txs = data["transactions"]
    assert len(txs) == 4
    assert txs[0]["expected_disposition"] == "COMMITTED"
    assert txs[1]["expected_disposition"] == "COMMITTED"
    assert txs[2]["expected_disposition"] == "REJECTED_WriteWriteConflict"
    assert txs[3]["expected_disposition"] == "COMMITTED"
    assert data["expected_final_state"]["sequence"] == 3


def test_gate4_wal_crash_replay() -> None:
    """RUST-M4-G04: WAL crash/replay equivalence."""
    vec_path = VECTORS_DIR / "wal_replay_vectors.json"
    assert vec_path.exists()
    with open(vec_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = data["wal_records"]
    assert len(records) == 4
    outcome = data["expected_replay_outcome"]
    assert outcome["expected_sequence"] == 4
    assert outcome["expected_ledger_length"] == 4
    assert outcome["expected_ledger_integrity"] is True
    assert outcome["idempotent_duplicate_replay_applied_count"] == 0


def test_gate5_orchestration_dag() -> None:
    """RUST-M4-G05: Deterministic DAG orchestration."""
    vec_path = VECTORS_DIR / "orchestration_vectors.json"
    assert vec_path.exists()
    with open(vec_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    steps = data["execution_steps"]
    assert len(steps) == 5
    assert steps[0]["expected_eligible"] == ["A", "B"]
    assert steps[1]["expected_eligible"] == ["B"]
    assert steps[2]["expected_eligible"] == ["C"]
    assert steps[3]["expected_eligible"] == ["D"]
    assert steps[4]["expected_eligible"] == []
    assert steps[4]["expected_halted"] is True

    negatives = data["negative_controls"]
    assert len(negatives) == 4


def test_gate6_proposer_zero_authority(bridge: RustVectorBridge) -> None:
    """RUST-M4-G06: Proposer non-escalation & zero authority boundary."""
    vec_path = VECTORS_DIR / "proposer_boundary_vectors.json"
    assert vec_path.exists()
    with open(vec_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    vectors = data["vectors"]
    assert len(vectors) == 4
    for vec in vectors:
        expected_status = vec["expected_status"]
        expected_err = vec["expected_error_code"]
        assert expected_status == "REJECTED"
        assert expected_err.startswith("ERR_")
