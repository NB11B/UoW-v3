from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
DRIVER = REPO / "qualification" / "final_physical_campaign.py"
CANDIDATE = "728988f93a1ec0f634f450dc4d187fbd5e0e95c9"


def test_final_physical_driver_is_syntax_valid_and_candidate_pinned():
    source = DRIVER.read_text(encoding="utf-8")
    compile(source, str(DRIVER), "exec")
    assert f'CANDIDATE_COMMIT = "{CANDIDATE}"' in source
    assert 'CANDIDATE_RELEASE_STATUS = "FINAL"' in source
    assert 'CANDIDATE_REF = "archive/uow-reduction-software-candidate-v2"' in source
    assert 'CANDIDATE_REF = "archive/uow-reduction-software-candidate"' in source
    assert '"candidate_commit": CANDIDATE_COMMIT' in source
    assert '"harness_commit": harness_commit()' in source


def test_final_physical_driver_covers_f0_f8_and_fail_closed_substrates():
    source = DRIVER.read_text(encoding="utf-8")
    for phase in ("F0", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8"):
        assert f'"{phase}"' in source
    assert '"--physical"' in source
    assert '"--device", "NPU"' in source
    assert "--allow-cpu-fallback" not in source
    assert "cpu_fallback_allowed_for_npu_claims" in source
    assert "FROZEN_CANDIDATE" not in source


def test_final_physical_driver_preserves_reference_oracles_and_thirteen_invariants():
    source = DRIVER.read_text(encoding="utf-8")
    assert 'A3_COMMIT = "05c8094ac5c8572f7da6d00e781ce673754c5c59"' in source
    assert 'P1_P5_COMMIT = "aa886329298f87e8b006501d47dd89eb8f0d4a3b"' in source
    assert "P1_P5_POLICY_SUITE_TESTS = 44" in source
    assert "P1_P5_FULL_REPOSITORY_TESTS = 324" in source
    assert "CANDIDATE_SHADOW_TESTS = 277" in source
    assert "f8_candidate_exact_seal_shadow" in source
    assert "f8_post_a3_p1_p5_frozen_oracle" in source
    assert "require_pytest_pass_count(oracle, P1_P5_POLICY_SUITE_TESTS)" in source
    start = source.index("P1_P5_INVARIANTS = (")
    end = source.index(")", start)
    block = source[start:end]
    assert block.count('    "') == 13
    assert '"p6_required": False' in source
