"""Qualification evidence-package integrity tests for KryonOS ESP32-S3 Phase E4E.

NOTE: This test suite verifies the qualification artifacts, evidence-package integrity,
manifest schemas, and conformance vectors in the host Python environment. It does NOT
serve as an independent physical silicon runner.
"""
from __future__ import annotations

import json
from pathlib import Path

E4E_DIR = Path(__file__).resolve().parent.parent / "qualification" / "kryonos" / "esp32_e4e"
VECTORS_DIR = E4E_DIR / "vectors"
MANIFEST_PATH = E4E_DIR / "QUALIFICATION_MANIFEST.json"


def test_e4e_manifest_structure_and_gates() -> None:
    """Verify that the Phase E4E qualification manifest is valid and records 10 passed gates."""
    assert MANIFEST_PATH.exists(), f"Missing manifest at {MANIFEST_PATH}"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["campaign_id"] == "KRYONOS-ESP32-E4E"
    assert manifest["disposition"] == "QUALIFIED"
    assert manifest["signoff_level"] == "L1 Physical Hardware"

    # Verify immutable provenance block
    prov = manifest.get("immutable_provenance", {})
    assert prov["kryonos_commit_sha"] == "452b7f5245166ca1bed8538850e90dafd4365b89"
    assert prov["uow_native_source_commit_sha"] == "53f31d98af22c3ed030129070722ecaa120f9223"
    assert prov["uow_e4e_runner_cpp_sha256"] == "068f7943eb048fc1293e61a837cd725bf85c1ef7afbbeb7ec3e0133e09c05ad5"
    assert prov["uow_native_cpp_sha256"] == "755cbf680373a2c4bcd249f784821373bb4041e5637f0a7cf2abe9ea4241bb91"
    assert prov["uow_duktape_binding_cpp_sha256"] == "875dcc6084fabcbeabf3a7ef3022e8972b366d39ca809132f6dfe916413277a9"
    assert prov["uow_persistence_cpp_sha256"] == "49ed18dc2c1b6289d4a1b0e8f44ca59620b0f68b460e57abc4fa2ac24c373a89"
    assert prov["compiled_firmware_bin_sha256"] == "a4a86783bafc4d0be5f42e25ae5c7dd1fcf29bde3e460b267479f0482fad9c81"
    assert prov["qualification_report_sha256"] == "7c4eb3ebfb0489cb910e1dced4a56fc58926bd49eb54e34ec930846273bc0d1e"
    assert prov["platformio_version"] == "6.1.19"
    assert prov["board_environment"] == "esp32-s3-devkitc-1-n16r8"

    gates = manifest["qualification_gates"]
    assert len(gates) == 10, f"Expected 10 qualification gates, found {len(gates)}"
    for gate in gates:
        assert gate["status"] == "PASSED", f"Gate {gate['gate_id']} did not pass: {gate}"

    # Verify gate E4E-T10 name and criteria
    e10_gate = next(g for g in gates if g["gate_id"] == "E4E-T10")
    assert e10_gate["name"] == "Cumulative Heterogeneous Realization Parity"

    # Verify 10,000-op endurance gate metrics
    e9_gate = next(g for g in gates if g["gate_id"] == "E4E-T09")
    metrics = e9_gate["metrics"]
    assert metrics["total_operations"] == 10000
    assert metrics["unauthorized_mutations"] == 0
    assert metrics["stale_executions"] == 0
    assert metrics["duplicate_effects"] == 0
    assert metrics["authority_escalations"] == 0


def test_vector_01_fencing_matrix() -> None:
    """Verify 4-quadrant 2D fencing matrix vector invariants."""
    path = VECTORS_DIR / "vector_e4e_01_fencing_matrix.json"
    assert path.exists()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    quadrants = data["quadrants"]
    assert len(quadrants) == 4

    # Q1, Q2, Q3 must forbid mutation and retain pin at 0
    for q in quadrants[:3]:
        assert q["mutation_permitted"] is False
        assert q["expected_pin_state"] == 0
        assert q["expected_status"] in (13, 14)  # STALE_FENCE or STALE_AUTHORITY_EPOCH

    # Q4 (current epoch, current generation) must permit mutation
    q4 = quadrants[3]
    assert q4["quadrant"] == "Q4"
    assert q4["mutation_permitted"] is True
    assert q4["expected_pin_state"] == 1
    assert q4["expected_status"] == 0  # UOW_STATUS_OK


def test_vector_02_quorum_certificates() -> None:
    """Verify native quorum certificate verification vector test cases."""
    path = VECTORS_DIR / "vector_e4e_02_quorum_certificates.json"
    assert path.exists()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data["cases"]
    assert len(cases) == 6

    # Valid case accepted
    assert cases[0]["case_id"] == "A"
    assert cases[0]["outcome"] == "ACCEPTED"
    assert cases[0]["expected_status"] == 0

    # 5 adversarial cases strictly rejected
    for case in cases[1:]:
        assert case["outcome"] == "REJECTED"
        assert case["expected_status"] != 0


def test_vector_03_delayed_packet_rejection() -> None:
    """Verify delayed packet delivery invariants."""
    path = VECTORS_DIR / "vector_e4e_03_delayed_packet_rejection.json"
    assert path.exists()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["invariants"]["stale_command_executed"] is False
    assert data["invariants"]["physical_leakage_on_stale_packet"] == 0


def test_vector_04_app_replacement_isolation() -> None:
    """Verify application replacement isolation invariant."""
    path = VECTORS_DIR / "vector_e4e_04_app_replacement_isolation.json"
    assert path.exists()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["invariant"] == "Application Replacement != Authority Replacement"
    stage2 = data["test_stages"][1]
    assert stage2["mutation_prevented"] is True
    assert stage2["authority_breached"] is False


def test_vector_05_endurance_profile() -> None:
    """Verify 10,000-operation endurance stress run results."""
    path = VECTORS_DIR / "vector_e4e_05_endurance_profile.json"
    assert path.exists()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = data["empirical_results"]
    assert results["total_operations_executed"] == 10000
    assert results["unauthorized_mutations"] == 0
    assert results["stale_executions"] == 0
    assert results["duplicate_effects"] == 0
    assert results["authority_escalations"] == 0
