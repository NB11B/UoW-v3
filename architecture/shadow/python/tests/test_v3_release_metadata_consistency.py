from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
FINAL_REF = "archive/uow-reduction-software-candidate-v3"
FINAL_COMMIT = "3e28e4bba1023810aada953e25d3e3c46a58f113"


def test_postfreeze_release_metadata_binds_only_v3_as_current():
    confirmation = (REPO / "qualification" / "final_physical_confirmation.yaml").read_text(encoding="utf-8")
    inputs = (REPO / "qualification" / "final_physical_candidate_inputs.yaml").read_text(encoding="utf-8")
    driver = (REPO / "qualification" / "final_physical_campaign.py").read_text(encoding="utf-8")
    assert f"ref: {FINAL_REF}" in confirmation
    assert f"commit: {FINAL_COMMIT}" in confirmation
    assert f"candidate_ref: {FINAL_REF}" in inputs
    assert f"candidate_commit: {FINAL_COMMIT}" in inputs
    assert f'CANDIDATE_REF = "{FINAL_REF}"' in driver
    assert f'CANDIDATE_COMMIT = "{FINAL_COMMIT}"' in driver


def test_v3_counts_and_oracles_are_consistent():
    confirmation = (REPO / "qualification" / "final_physical_confirmation.yaml").read_text(encoding="utf-8")
    freeze = (REPO / "architecture" / "software_candidate_freeze.yaml").read_text(encoding="utf-8")
    assert "final_candidate_exact_shadow_tests: 279" in confirmation
    assert "policy_suite_tests: 44" in confirmation
    assert "shadow_tests_passed: 279" in freeze
    assert "policy_tests_passed: 44" in freeze
    assert "aa886329298f87e8b006501d47dd89eb8f0d4a3b" in confirmation
