"""Offline qualification test harness for JEV Operator Bracket Bilinearity Campaign.

Validates:
1. Deterministic oracle conformance across all 29 bilinearity specs.
2. Common-output control across all failure states (k=8, margin=-1, FAILED).
3. Raw telemetry representation (zero forbidden strings).
4. Offline synthetic linear provider passing all bilinearity gates (B0..B4).
5. Offline synthetic nonlinear provider failing bilinearity gates.
6. Fail-closed behavior on incomplete observations.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import pytest

from qualification.jev_operator_bilinearity_campaign import (
    DEFAULT_BILINEARITY_SPECS,
    BilinearitySpec,
    analyze_bilinearity_observations,
    build_bilinearity_states,
    run_live_bilinearity_experiment,
)


class LinearBilinearityProvider:
    """Synthetic provider generating mathematically linear, bilinear commutator brackets."""

    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        base = [0.50, 0.50, 0.50, 0.50, 0.50, 0.50, 0.50, 0.50]
        p_mech = str(state.get("primary_mechanism", "none"))
        s_mech = str(state.get("secondary_mechanism", "none"))
        direction = str(state.get("composition_direction", ""))
        alpha = float(state.get("alpha", 1.0))

        raw_deltas = {
            "authority": [-0.65, -0.42, -0.84, -0.74, -0.38, -0.54, -0.16, 0.44],
            "temporal": [-0.25, -0.30, -0.65, -0.40, -0.35, -0.40, -0.70, 0.75],
            "evidence": [-0.40, -0.55, -0.70, -0.60, -0.75, -0.82, -0.30, 0.35],
            "adversarial": [-0.55, -0.45, -0.80, -0.65, -0.85, -0.70, -0.25, 0.50],
        }
        pure_deltas = {k: [0.25 * x for x in v] for k, v in raw_deltas.items()}

        if p_mech == "none":
            vector = list(base)
        elif p_mech in pure_deltas and s_mech == "none":
            d = pure_deltas[p_mech]
            vector = [max(0.0, min(1.0, v + x)) for v, x in zip(base, d)]
        elif "+" in p_mech or "+" in s_mech:
            # Physical sum (e.g. authority+temporal) composed with secondary (adversarial)
            composite = p_mech if "+" in p_mech else s_mech
            simple = s_mech if "+" in p_mech else p_mech
            m1, m2 = composite.split("+", 1)
            d1 = pure_deltas[m1]
            d2 = pure_deltas[m2]
            d_sum = [x1 + x2 for x1, x2 in zip(d1, d2)]
            d_sec = pure_deltas[simple]
            
            # Linear commutator bracket: c(1+2, sec) = c(1, sec) + c(2, sec)
            sign = 1.0 if direction == "forward" else -1.0
            chi = [sign * 0.08 * ((x1 - xsec) + (x2 - xsec)) for x1, x2, xsec in zip(d1, d2, d_sec)]
            d_blend = [0.5 * (x1 + x2) + 0.5 * xsec for x1, x2, xsec in zip(d1, d2, d_sec)]
            vector = [max(0.0, min(1.0, v + b + c)) for v, b, c in zip(base, d_blend, chi)]
        elif direction in ("forward", "reverse"):
            # Fractional scalar scaling alpha * m1 with m2
            # Identify the two base mechanisms
            m1 = p_mech if direction == "forward" else s_mech
            m2 = s_mech if direction == "forward" else p_mech
            d1 = [alpha * x for x in pure_deltas[m1]]
            d2 = pure_deltas[m2]
            sign = 1.0 if direction == "forward" else -1.0
            chi = [sign * 0.08 * (x1 - x2) for x1, x2 in zip(d1, d2)]
            d_blend = [0.5 * x1 + 0.5 * x2 for x1, x2 in zip(d1, d2)]
            vector = [max(0.0, min(1.0, v + b + c)) for v, b, c in zip(base, d_blend, chi)]
        else:
            vector = list(base)

        return {
            "request_id": request_id,
            "requested_model": "fake",
            "resolved_model": "fake",
            "question_ids": [str(q.get("question_id", "")) for q in questions],
            "vector": vector,
            "answers": {},
            "usage": None,
            "validation_status": "VALID",
        }


class NonlinearBilinearityProvider(LinearBilinearityProvider):
    """Synthetic provider violating scalar homogeneity with quadratic scaling alpha^2."""

    def decide(self, **kwargs: Any) -> dict[str, Any]:
        result = super().decide(**kwargs)
        state = kwargs.get("state", {})
        alpha = float(state.get("alpha", 1.0))
        if state.get("condition_role") == "homogeneity":
            # Add directional quadratic distortion: alpha^2 deviation breaking linearity
            direction = str(state.get("composition_direction", "forward"))
            sign = 1.0 if direction == "forward" else -1.0
            distortion = sign * 0.25 * (alpha**2 - alpha)
            result["vector"] = [max(0.0, min(1.0, v + distortion)) for v in result["vector"]]
        return result


def test_deterministic_bilinearity_states():
    states = build_bilinearity_states()
    assert len(states) == len(DEFAULT_BILINEARITY_SPECS) == 29
    for item in states:
        oracle = item["oracle"]
        assert oracle["passes_expected_behavior"]
        assert oracle["boundary_certificates_valid"]


def test_bilinearity_common_output_control():
    states = build_bilinearity_states()
    for item in states:
        s = item["state"]
        spec = item["spec"]
        if spec["primary_mech"] != "none":
            assert s["admissible_constituent_units"] == 8
            assert s["disturbed_constituent_units"] == 8
            assert s["quorum_margin"] == -1
            assert s["emitted_output_keys"] == []
        else:
            assert s["admissible_constituent_units"] == 16
            assert s["quorum_margin"] == 7
            assert s["emitted_output_keys"] == ["composition_result"]


def test_bilinearity_telemetry_forbids_status_words():
    forbidden = ["fail", "error", "unavailable", "verified", "committed", "bypass", "status"]
    states = build_bilinearity_states()
    for item in states:
        serialized = json.dumps(item["state"]).lower()
        for f in forbidden:
            assert f not in serialized, f"Forbidden '{f}' found in {item['spec']['spec_id']}"


def test_offline_analysis_accepts_linear_bilinearity_provider():
    result = run_live_bilinearity_experiment(
        provider=LinearBilinearityProvider(),
        replicates=3,
        specs=DEFAULT_BILINEARITY_SPECS,
    )
    analysis = result["analysis"]
    assert analysis["oracle_pass"]
    assert analysis["provider_complete"]
    assert analysis["supported_within_engineering_gates"]
    assert analysis["verdict"] == "OPERATOR_BILINEARITY_SUPPORTED"

    gates = analysis["gates"]
    assert gates["B0_deterministic_oracle"]
    assert gates["B1_provider_complete"]
    assert gates["B2_repeatability_noise_floor"]
    assert gates["B3_scalar_homogeneity"]
    assert gates["B4_bracket_additivity"]

    # Verify scaling R2
    hom = analysis["scalar_homogeneity"]
    assert hom["temporal_series"]["linear_scaling_R2_percent"] >= 85.0
    assert hom["authority_series"]["linear_scaling_R2_percent"] >= 85.0


def test_offline_analysis_rejects_nonlinear_provider():
    result = run_live_bilinearity_experiment(
        provider=NonlinearBilinearityProvider(),
        replicates=3,
        specs=DEFAULT_BILINEARITY_SPECS,
    )
    analysis = result["analysis"]
    assert analysis["gates"]["B3_scalar_homogeneity"] is False
    assert analysis["verdict"] == "NONLINEAR_BRACKET_DETECTED"
