from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def test_v3_preseal_release_metadata_has_no_current_v1_or_v2_binding():
    confirmation = (REPO / "qualification" / "final_physical_confirmation.yaml").read_text(encoding="utf-8")
    inputs = (REPO / "qualification" / "final_physical_candidate_inputs.yaml").read_text(encoding="utf-8")
    driver = (REPO / "qualification" / "final_physical_campaign.py").read_text(encoding="utf-8")
    assert "candidate_v3:" in confirmation
    assert "planned_ref: archive/uow-reduction-software-candidate-v3" in confirmation
    assert "candidate_ref: UNBOUND_PRESEAL" in inputs
    assert "candidate_commit: UNBOUND_PRESEAL" in inputs
    assert 'CANDIDATE_REF = "UNBOUND_PRESEAL"' in driver
    assert 'CANDIDATE_COMMIT = "UNBOUND_PRESEAL"' in driver


def test_v3_preseal_counts_and_oracles_are_consistent():
    confirmation = (REPO / "qualification" / "final_physical_confirmation.yaml").read_text(encoding="utf-8")
    freeze = (REPO / "architecture" / "software_candidate_freeze.yaml").read_text(encoding="utf-8")
    assert "final_candidate_exact_shadow_tests: 279" in confirmation
    assert "policy_suite_tests: 44" in confirmation
    assert "expected_shadow_tests: 279" in freeze
    assert "expected_policy_tests: 44" in freeze
    assert "aa886329298f87e8b006501d47dd89eb8f0d4a3b" in confirmation
