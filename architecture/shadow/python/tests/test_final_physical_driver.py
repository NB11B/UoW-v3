from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
DRIVER = REPO / "qualification" / "final_physical_campaign.py"
FINAL_REF = "archive/uow-reduction-software-candidate-v3"
FINAL_COMMIT = "3e28e4bba1023810aada953e25d3e3c46a58f113"


def test_postfreeze_harness_is_pinned_to_v3():
    source = DRIVER.read_text(encoding="utf-8")
    compile(source, str(DRIVER), "exec")
    assert f'CANDIDATE_REF = "{FINAL_REF}"' in source
    assert f'CANDIDATE_COMMIT = "{FINAL_COMMIT}"' in source
    assert 'CANDIDATE_RELEASE_STATUS = "FINAL"' in source


def test_final_physical_driver_covers_f0_f8_and_fail_closed_substrates():
    source = DRIVER.read_text(encoding="utf-8")
    for phase in ("F0", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8"):
        assert f'"{phase}"' in source
    assert '"--physical"' in source
    assert '"--device", "NPU"' in source
    assert "--allow-cpu-fallback" not in source
    assert "cpu_fallback_allowed_for_npu_claims" in source


def test_final_physical_driver_preserves_reference_oracles_and_thirteen_invariants():
    source = DRIVER.read_text(encoding="utf-8")
    assert 'A3_COMMIT = "05c8094ac5c8572f7da6d00e781ce673754c5c59"' in source
    assert 'P1_P5_COMMIT = "aa886329298f87e8b006501d47dd89eb8f0d4a3b"' in source
    assert "P1_P5_POLICY_SUITE_TESTS = 44" in source
    assert "P1_P5_FULL_REPOSITORY_TESTS = 324" in source
    assert "CANDIDATE_SHADOW_TESTS = 279" in source
    start = source.index("P1_P5_INVARIANTS = (")
    end = source.index(")", start)
    assert source[start:end].count('    "') == 13
