from pathlib import Path

REPO = Path(__file__).resolve().parents[4]

def test_final_physical_campaign_is_deferred_until_frozen_candidate():
    text = (REPO / "qualification" / "final_physical_confirmation.yaml").read_text(encoding="utf-8")
    assert "status: DEFERRED_UNTIL_FINAL_CANDIDATE" in text
    assert "mode: SINGLE_CONSOLIDATED_FINAL_CAMPAIGN" in text
    assert "run_during_r7_additive_work: false" in text
    assert "final_candidate_must_be_frozen_first: true" in text

def test_final_campaign_covers_every_current_physical_claim():
    claim_text = (REPO / "qualification" / "claim_registry.py").read_text(encoding="utf-8")
    plan = (REPO / "qualification" / "final_physical_confirmation.yaml").read_text(encoding="utf-8")
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
        assert claim_id in plan, claim_id

def test_final_campaign_preserves_a3_and_p1_p5_without_inventing_p6():
    text = (REPO / "qualification" / "final_physical_confirmation.yaml").read_text(encoding="utf-8")
    assert "qualification/a3-adaptive-compute-efficiency" in text
    assert "architecture/policy-aware-uow-orchestrator" in text
    assert "p6_required: false" in text