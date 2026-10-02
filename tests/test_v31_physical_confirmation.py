"""Milestone v3.1-M5 Physical Reconfirmation Evidence-Package Integrity Tests.

Verifies the integrity, cryptographic provenance, and gate requirements of the
v3.1-M5 Integrated Heterogeneous Physical Reconfirmation campaign.

NOTE: These are repository evidence-package integrity tests; the actual hardware
experiment ran on physical silicon (ESP32-S3 + Arduino UNO Q + Laptop Host).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pytest

QUAL_DIR = Path(__file__).resolve().parent.parent / "qualification" / "physical" / "v31_confirmation"
MANIFEST_PATH = QUAL_DIR / "QUALIFICATION_MANIFEST.json"
RESULTS_PATH = QUAL_DIR / "results" / "physical_confirmation_results.json"
TRANSCRIPT_PATH = QUAL_DIR / "results" / "execution_transcript.jsonl"
VECTORS_DIR = QUAL_DIR / "vectors"
REPO_ROOT = Path(__file__).resolve().parent.parent


def test_m5_manifest_structure_and_prerequisites() -> None:
    """Verify manifest schema, prerequisite milestones, and campaign disposition."""
    assert MANIFEST_PATH.exists(), f"Missing manifest at {MANIFEST_PATH}"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["campaign_id"] == "V31-PHYS-CONFIRM"
    assert manifest["disposition"] == "QUALIFIED"
    assert manifest["signoff_level"] == "L1 Physical Hardware Integrated Qualification"
    assert manifest["base"] == "v3.1/development"

    # Verify all 4 prior milestone prerequisites are explicitly bound
    prereqs = manifest["prerequisites"]
    assert "v3.1-m1-kryonos-qualified" in prereqs
    assert "v3.1-m2-atomic-economics-qualified" in prereqs
    assert "v3.1-m3-cpp-16vec-qualified" in prereqs
    assert "v3.1-m4-rust-runtime-qualified" in prereqs

    # Verify hardware topology
    topo = manifest["hardware_topology"]
    assert "authority_a" in topo and topo["authority_a"]["board"] == "ESP32-S3-DevKitC-1-N16R8"
    assert "authority_b" in topo and topo["authority_b"]["board"] == "Arduino UNO Q (STM32U585)"
    assert "authority_c" in topo and topo["authority_c"]["board"] == "Laptop Host x86-64"
    assert "realization_witness" in topo and topo["realization_witness"]["crate"] == "uow-runtime 3.1.0"


def test_m5_cryptographic_provenance_digests() -> None:
    """Verify cryptographic SHA-256 digests of all qualification vectors and firmware sources."""
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    vectors_prov = manifest["immutable_provenance"]["vectors"]
    for vec_file in VECTORS_DIR.glob("*.json"):
        hasher = hashlib.sha256()
        with open(vec_file, "rb") as f:
            hasher.update(f.read().replace(b"\r\n", b"\n"))
        actual_hash = hasher.hexdigest()
        key = f"{vec_file.stem}_sha256"
        assert key in vectors_prov, f"Missing provenance key {key} for {vec_file.name}"
        assert actual_hash == vectors_prov[key], f"Hash mismatch for {vec_file.name}: {actual_hash} != {vectors_prov[key]}"

    # Verify firmware sources exist and match provenance digests
    firmware_prov = manifest["immutable_provenance"]["firmware_sources"]
    firmware_paths = {
        "esp32_main_cpp_sha256": REPO_ROOT / "runtimes" / "embedded" / "esp32" / "main.cpp",
        "esp32_uow_embedded_cpp_sha256": REPO_ROOT / "runtimes" / "embedded" / "esp32" / "uow_embedded.cpp",
        "esp32_uow_embedded_hpp_sha256": REPO_ROOT / "runtimes" / "embedded" / "esp32" / "uow_embedded.hpp",
        "arduino_uno_q_ino_sha256": REPO_ROOT / "runtimes" / "embedded" / "arduino" / "uno_q_authority.ino",
        "arduino_uow_embedded_cpp_sha256": REPO_ROOT / "runtimes" / "embedded" / "arduino" / "uow_embedded.cpp",
        "arduino_uow_embedded_hpp_sha256": REPO_ROOT / "runtimes" / "embedded" / "arduino" / "uow_embedded.hpp",
    }
    for key, p in firmware_paths.items():
        assert p.exists(), f"Missing firmware file at {p}"
        hasher = hashlib.sha256()
        with open(p, "rb") as f:
            hasher.update(f.read().replace(b"\r\n", b"\n"))
        actual_hash = hasher.hexdigest()
        assert actual_hash == firmware_prov[key], f"Firmware hash mismatch for {p.name}: {actual_hash} != {firmware_prov[key]}"


def test_m5_all_seven_gates_passed() -> None:
    """Verify that all 7 qualification gates are declared PASSED in the manifest."""
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    gates = manifest["qualification_gates"]
    assert len(gates) == 7, f"Expected 7 qualification gates, got {len(gates)}"
    gate_ids = [g["gate_id"] for g in gates]
    for i in range(1, 8):
        expected_id = f"PHYS-M5-G{i:02d}"
        assert expected_id in gate_ids, f"Missing gate {expected_id}"

    for gate in gates:
        assert gate["status"] == "PASSED", f"Gate {gate['gate_id']} did not pass: {gate}"


def test_m5_results_and_zero_wrong_commits() -> None:
    """Verify execution results, invariant satisfaction, and zero wrong authoritative commits."""
    assert RESULTS_PATH.exists(), f"Missing results file at {RESULTS_PATH}"
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        results = json.load(f)

    assert results["disposition"] == "QUALIFIED"
    assert results["wrong_authoritative_commits"] == 0, "Non-zero wrong authoritative commits detected!"

    # Verify transcript exists and records completion
    assert TRANSCRIPT_PATH.exists(), f"Missing transcript at {TRANSCRIPT_PATH}"
    with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]

    assert len(lines) >= 12
    last_event = lines[-1]
    assert last_event["event"] == "CAMPAIGN_CLOSEOUT"
    assert last_event["wrong_authoritative_commits"] == 0
    assert last_event["overall_disposition"] == "QUALIFIED"


def test_m5_gate2_pairwise_agreement() -> None:
    """Verify Gate 2: 24/24 transition vectors achieve pairwise agreement across ESP32, Arduino, and Host."""
    vec_path = VECTORS_DIR / "pairwise_agreement.json"
    with open(vec_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data["cases"]
    assert len(cases) == 24
    for c in cases:
        assert c["agreement"] is True, f"Agreement failed on case {c['case_id']}"
        assert c["esp32_disposition"] == c["disposition"]
        assert c["arduino_disposition"] == c["disposition"]
        assert c["host_disposition"] == c["disposition"]


def test_m5_gate3_quorum_pairs() -> None:
    """Verify Gate 3: Live 2-of-3 quorum certification; any pair commits, singleton strictly rejects."""
    vec_path = VECTORS_DIR / "quorum_pairs.json"
    with open(vec_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for case in data["test_cases"]:
        if case["quorum_met"]:
            assert case["expected_outcome"] == "COMMIT"
            assert case["disposition"] == "SUCCESS"
        else:
            assert case["expected_outcome"] == "NO_COMMIT"
            assert case["disposition"] == "REJECT"


def test_m5_gate4_partition_fail_closed() -> None:
    """Verify Gate 4: Partition and fail-closed behavior (0 unauthorized mutations)."""
    vec_path = VECTORS_DIR / "partition_fail_closed.json"
    with open(vec_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for sc in data["scenarios"]:
        if sc.get("unauthorized_mutations") is not None:
            assert sc["unauthorized_mutations"] == 0
        if not sc.get("quorum_available", True):
            assert sc["system_disposition"].startswith("FAIL_CLOSED")
            assert sc["state_advancement_permitted"] is False


def test_m5_gate5_stale_replay_rejection() -> None:
    """Verify Gate 5: Replay and stale authority rejection (zero physical actuator effects)."""
    vec_path = VECTORS_DIR / "stale_replay.json"
    with open(vec_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for case in data["cases"]:
        assert case["expected_disposition"] == "REJECT"
        assert case["physical_actuator_mutation"] == 0


def test_m5_gate6_cross_realization_parity() -> None:
    """Verify Gate 6: Heterogeneous realization parity across all platforms including Rust witness."""
    vec_path = VECTORS_DIR / "realization_parity.json"
    with open(vec_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    realizations = data["realizations_evaluated"]
    assert len(realizations) >= 4
    for r in realizations:
        assert r["parity_confirmed"] is True
        assert r["final_counter"] == 105
        assert r["final_status"] == "ACTIVE"


def test_m5_gate7_recovery_continuity() -> None:
    """Verify Gate 7: Recovery continuity: clean reboot catches up; forged history quarantined."""
    vec_path = VECTORS_DIR / "recovery_continuity.json"
    with open(vec_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for case in data["recovery_cases"]:
        if case["quarantined"]:
            assert case["expected_disposition"] == "QUARANTINED"
            assert case["state_restoration_prevented"] is True
        else:
            assert case["state_matches_canonical"] is True
            assert case["evidence_matches_canonical"] is True
