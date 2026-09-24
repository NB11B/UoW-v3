from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
FINAL_REF = "archive/uow-reduction-software-candidate-v3"
FINAL_COMMIT = "3e28e4bba1023810aada953e25d3e3c46a58f113"


def test_v3_is_bound_but_physical_execution_waits_for_harness_shadow():
    text = (REPO / "qualification" / "final_physical_confirmation.yaml").read_text(encoding="utf-8")
    assert "status: DEFERRED_PENDING_V3_HARNESS_SHADOW" in text
    assert f"ref: {FINAL_REF}" in text
    assert f"commit: {FINAL_COMMIT}" in text
    assert "exact_seal_run: 167" in text
    assert "exact_seal_shadow_tests_passed: 279" in text
    assert "exact_seal_policy_tests_passed: 44" in text
    assert "status: REPINNED_TO_V3_AWAITING_HARNESS_SHADOW" in text


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
    assert "architecture/policy-aware-uow-orchestrator" in text
    assert "aa886329298f87e8b006501d47dd89eb8f0d4a3b" in text
    assert "final_candidate_exact_shadow_tests: 279" in text
    assert "p6_required: false" in text
