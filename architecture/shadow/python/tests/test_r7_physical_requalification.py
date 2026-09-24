from pathlib import Path


REPO = Path(__file__).resolve().parents[4]


def test_r7_physical_requalification_map_does_not_upgrade_portable_evidence():
    text = (REPO / "architecture" / "PHYSICAL_REQUALIFICATION_MAP.yaml").read_text(encoding="utf-8")

    assert "portable/shadow parity never upgrades to PHYSICAL" in text
    assert "fresh_physical_run_required_now: false" in text
    assert "NO_PHYSICAL_RERUN_REQUIRED_FOR_ADDITIVE_R7_WORK" in text


def test_r7_physical_map_includes_all_current_physical_claim_ids():
    claim_text = (REPO / "qualification" / "claim_registry.py").read_text(encoding="utf-8")
    mapping = (REPO / "architecture" / "PHYSICAL_REQUALIFICATION_MAP.yaml").read_text(encoding="utf-8")

    physical_ids = []
    current_id = None
    for line in claim_text.splitlines():
        stripped = line.strip()
        if stripped.startswith('"') and '": ClaimSpec(' in stripped:
            current_id = stripped.split('"', 2)[1]
        elif current_id and "EvidenceLevel.PHYSICAL" in stripped:
            physical_ids.append(current_id)
            current_id = None

    assert physical_ids
    for claim_id in physical_ids:
        assert claim_id in mapping, claim_id


def test_r7_policy_oracle_keeps_a3_physical_evidence_inherited_not_double_counted():
    text = (REPO / "architecture" / "PHYSICAL_REQUALIFICATION_MAP.yaml").read_text(encoding="utf-8")
    assert "downstream of A3" in text
    assert "not double-counted" in text
