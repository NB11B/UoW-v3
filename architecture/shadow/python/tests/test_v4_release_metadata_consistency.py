from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
FINAL_REF = "archive/uow-reduction-software-candidate-v4"
FINAL_COMMIT = "9d95c11f4b09c34769e1f3a1e6d7b915291d43c8"


def test_release_metadata_binds_only_v4_as_current():
    confirmation = (REPO / "qualification" / "final_physical_confirmation.yaml").read_text(encoding="utf-8")
    inputs = (REPO / "qualification" / "final_physical_candidate_inputs.yaml").read_text(encoding="utf-8")
    driver = (REPO / "qualification" / "final_physical_campaign.py").read_text(encoding="utf-8")
    assert f"ref: {FINAL_REF}" in confirmation
    assert f"commit: {FINAL_COMMIT}" in confirmation
    assert f"candidate_ref: {FINAL_REF}" in inputs
    assert f"candidate_commit: {FINAL_COMMIT}" in inputs
    assert f'CANDIDATE_REF = "{FINAL_REF}"' in driver
    assert f'CANDIDATE_COMMIT = "{FINAL_COMMIT}"' in driver


def test_v4_physical_closeout_is_promotable_and_consistent():
    confirmation = (REPO / "qualification" / "final_physical_confirmation.yaml").read_text(encoding="utf-8")
    freeze = (REPO / "architecture" / "software_candidate_freeze.yaml").read_text(encoding="utf-8")
    assert "status: PHYSICALLY_QUALIFIED" in confirmation
    assert "physical_claims_promotable: true" in confirmation
    assert "candidate_shadow_tests_passed: 279" in confirmation
    assert "policy_tests_passed: 44" in confirmation
    assert "mandatory_invariants_passed: 13" in confirmation
    assert "FROZEN_V4_PHYSICAL_QUALIFICATION_PASS" in freeze
