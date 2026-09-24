from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
FINAL_REF = "archive/uow-reduction-software-candidate-v4"
FINAL_COMMIT = "9d95c11f4b09c34769e1f3a1e6d7b915291d43c8"


def test_v4_physical_campaign_is_closed_and_promotable():
    text = (REPO / "qualification" / "final_physical_confirmation.yaml").read_text(encoding="utf-8")
    assert "status: PHYSICALLY_QUALIFIED" in text
    assert f"ref: {FINAL_REF}" in text
    assert f"commit: {FINAL_COMMIT}" in text
    assert "passed: true" in text
    assert "physical_claims_promotable: true" in text
    assert "candidate_shadow_tests_passed: 279" in text
    assert "policy_tests_passed: 44" in text
    assert "mandatory_invariants_passed: 13" in text
    assert "release_state: CLOSED" in text


def test_final_campaign_covers_every_current_physical_claim():
    claim_text = (REPO / "qualification" / "claim_registry.py").read_text(encoding="utf-8")
    plan = (REPO / "qualification" / "final_physical_confirmation.yaml").read_text(encoding="utf-8")
    physical_ids = []
    current_id = None
    for line in claim_text.splitlines():
        stripped = line.strip()
        if stripped.startswith('"') and '\": ClaimSpec(' in stripped:
            current_id = stripped.split('"', 2)[1]
        elif current_id and "EvidenceLevel.PHYSICAL" in stripped:
            physical_ids.append(current_id)
            current_id = None
    assert physical_ids
    for claim_id in physical_ids:
        assert claim_id in plan, claim_id


def test_final_campaign_preserves_a3_and_post_a3_p1_p5_without_inventing_p6():
    text = (REPO / "qualification" / "final_physical_confirmation.yaml").read_text(encoding="utf-8")
    assert "qualification/a3-adaptive-compute-efficiency" in text
    assert "05c8094ac5c8572f7da6d00e781ce673754c5c59" in text
    assert "architecture/policy-aware-uow-orchestrator" in text
    assert "aa886329298f87e8b006501d47dd89eb8f0d4a3b" in text
    assert "final_candidate_exact_shadow_tests: 279" in text
    assert "policy_suite_tests: 44" in text
    assert "mandatory_invariants: 13" in text
    assert "p6_required: false" in text
