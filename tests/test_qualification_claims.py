from qualification.claim_lint import lint_claim_registry
from qualification.claim_registry import CLAIMS
from qualification.evidence import (
    ClaimRequirement,
    EvidenceContext,
    EvidenceLevel,
    evaluate_claim,
)


def test_claim_registry_lints_clean():
    assert lint_claim_registry() == []


def test_all_physical_claims_name_actual_components():
    physical = [c for c in CLAIMS.values() if c.required_level is EvidenceLevel.PHYSICAL]
    assert physical
    assert all(c.required_components for c in physical)


def test_simulated_observation_cannot_satisfy_registered_physical_claim():
    spec = CLAIMS["ESP32.AUTHORITY"]
    result = evaluate_claim(
        True,
        EvidenceContext(
            EvidenceLevel.SIMULATED,
            "test",
            {},
            {"authority": "mock"},
        ),
        ClaimRequirement(spec.required_level, spec.required_components),
    )
    assert result["observed_pass"] is True
    assert result["qualified"] is False
    assert result["passed"] is False


def test_registered_physical_claim_passes_only_with_actual_components():
    spec = CLAIMS["HETERO.EXECUTION"]
    actual = {name: f"actual:{name}" for name in spec.required_components}
    result = evaluate_claim(
        True,
        EvidenceContext(EvidenceLevel.PHYSICAL, "test", actual, {}),
        ClaimRequirement(spec.required_level, spec.required_components),
    )
    assert result["qualified"] is True
    assert result["passed"] is True
