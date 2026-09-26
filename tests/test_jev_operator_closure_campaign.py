"""Offline qualification test harness for JEV Operator Algebraic Closure Campaign.

Validates:
1. Deterministic oracle conformance across all 37 specs (1 base, 6 pure, 30 composed).
2. Common-output control: identical macro-outcome across all 36 failure states.
3. Strict raw telemetry representation (zero forbidden outcome/error strings).
4. Offline synthetic positive control provider passing all gates (U0, J0..J4).
5. Offline synthetic negative control rejecting high noise floor.
6. Fail-closed behavior on incomplete observations.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import pytest

from qualification.jev_operator_closure_campaign import (
    DEFAULT_CLOSURE_SPECS,
    ClosureSpec,
    ClosureThresholds,
    analyze_closure_observations,
    build_closure_states,
    run_live_closure_experiment,
)


class StableClosureProvider:
    """Synthetic provider modeling closed algebraic interaction in the 3D-5D residual subspace."""

    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        base = [0.85, 0.90, 0.88, 0.84, 0.89, 0.91, 0.86, 0.12]
        mech = str(state.get("mechanism", "none"))

        pure_deltas = {
            "authority": [-0.65, -0.42, -0.84, -0.74, -0.38, -0.54, -0.16, 0.44],
            "evidence": [-0.40, -0.55, -0.70, -0.60, -0.75, -0.82, -0.30, 0.35],
            "causal": [-0.50, -0.60, -0.88, -0.80, -0.45, -0.60, -0.20, 0.40],
            "temporal": [-0.25, -0.30, -0.65, -0.40, -0.35, -0.40, -0.70, 0.75],
            "resource": [-0.30, -0.35, -0.70, -0.50, -0.40, -0.45, -0.75, 0.65],
            "adversarial": [-0.55, -0.45, -0.80, -0.65, -0.85, -0.70, -0.25, 0.50],
        }

        if mech == "none":
            vector = list(base)
        elif mech in pure_deltas:
            d = pure_deltas[mech]
            vector = [max(0.0, min(1.0, v + x)) for v, x in zip(base, d)]
        elif "_" in mech:
            # Composed state: linear combination + small deterministic ordering interaction
            m1, m2 = mech.split("_", 1)
            d1 = pure_deltas[m1]
            d2 = pure_deltas[m2]
            # Dominant blend
            d_blend = [0.55 * x1 + 0.45 * x2 for x1, x2 in zip(d1, d2)]
            # Directional interaction term living inside pure delta subspace:
            # chi_12 = 0.08 * (d1 - d2)
            d_inter = [0.08 * (x1 - x2) for x1, x2 in zip(d1, d2)]
            vector = [max(0.0, min(1.0, v + b + i)) for v, b, i in zip(base, d_blend, d_inter)]
        else:
            vector = list(base)

        return {
            "request_id": request_id,
            "requested_model": "fake",
            "resolved_model": "fake",
            "question_ids": [str(q["question_id"]) for q in questions],
            "vector": vector,
            "answers": {},
            "usage": None,
            "validation_status": "VALID",
        }


class HighNoiseClosureProvider(StableClosureProvider):
    """Synthetic provider with noisy replicate fluctuations exceeding the 0.05 threshold."""

    def decide(self, **kwargs: Any) -> dict[str, Any]:
        result = super().decide(**kwargs)
        req_id = kwargs.get("request_id", "")
        rep_noise = 0.08 if "r1" in req_id else (-0.08 if "r2" in req_id else 0.0)
        result["vector"] = [max(0.0, min(1.0, v + rep_noise)) for v in result["vector"]]
        return result


def test_deterministic_closure_states_and_oracles():
    """Verify oracle behavior across all 37 closure specifications."""
    states = build_closure_states()
    assert len(states) == len(DEFAULT_CLOSURE_SPECS) == 37

    for item in states:
        oracle = item["oracle"]
        spec = item["spec"]
        sid = spec["spec_id"]

        assert oracle["boundary_certificates_valid"]
        assert oracle["passes_expected_behavior"]

        if sid == "op_base":
            assert oracle["disturbed_count"] == 0
            assert oracle["admissible_count"] == 16
            assert oracle["quorum_achieved"] is True
            assert oracle["root_status"] == "SUCCESS"
            assert len(item["state"]["emitted_output_keys"]) == 1
            assert item["state"]["quorum_margin"] == 7
        else:
            assert oracle["disturbed_count"] == 8
            assert oracle["admissible_count"] == 8
            assert oracle["quorum_achieved"] is False
            assert oracle["root_status"] == "FAILED"
            assert len(item["state"]["emitted_output_keys"]) == 0
            assert item["state"]["quorum_margin"] == -1


def test_common_output_control():
    """Verify that all 36 failure states produce the identical macroscopic failure outcome."""
    states = build_closure_states()
    failure_states = [s for s in states if s["spec"]["spec_id"] != "op_base"]
    assert len(failure_states) == 36

    for item in failure_states:
        state = item["state"]
        oracle = item["oracle"]
        assert state["emitted_output_keys"] == []
        assert state["admissible_constituent_units"] == 8
        assert state["quorum_margin"] == -1
        assert oracle["root_status"] == "FAILED"
        assert oracle["quorum_achieved"] is False


def test_raw_telemetry_state_forbids_status_and_outcome_labels():
    """Ensure state representation contains zero forbidden words."""
    forbidden = ("fail", "error", "unavailable", "verified", "committed", "bypass", "status")
    states = build_closure_states()

    for item in states:
        state_dict = item["state"]
        for key in state_dict.keys():
            for f in forbidden:
                assert f not in key.lower(), f"Forbidden '{f}' in state key '{key}'"

        serialized = json.dumps(state_dict).lower()
        for f in forbidden:
            assert f not in serialized, (
                f"Forbidden '{f}' found in serialized state for spec {item['spec']['spec_id']}"
            )


def test_offline_analysis_accepts_stable_closure_provider():
    """Verify StableClosureProvider passes all preregistered closure gates."""
    result = run_live_closure_experiment(
        provider=StableClosureProvider(),
        replicates=3,
        thresholds=ClosureThresholds(),
    )
    analysis = result["analysis"]
    assert analysis["oracle_pass"]
    assert analysis["provider_complete"]
    assert analysis["supported_within_engineering_gates"]
    assert analysis["verdict"] == "SUPPORTED_WITHIN_PREREGISTERED_ENGINEERING_GATES"

    gates = analysis["gates"]
    assert gates["U0_deterministic_oracle"]
    assert gates["J0_provider_complete"]
    assert gates["J1_repeatability_noise_floor"]
    assert gates["J2_commutator_detectability"]
    assert gates["J3_algebraic_closure_evaluated"]
    assert gates["J4_closure_spectrum_characterized"]

    # Closure in residual space is verified
    spectrum = analysis["dimensional_closure_spectrum"]
    assert len(spectrum) == 5
    assert spectrum["5D"]["mean_R2_percent"] >= 85.0


def test_offline_analysis_rejects_high_noise():
    """Verify high noise provider fails gate J1."""
    result = run_live_closure_experiment(
        provider=HighNoiseClosureProvider(),
        replicates=3,
        thresholds=ClosureThresholds(),
    )
    analysis = result["analysis"]
    assert analysis["gates"]["J1_repeatability_noise_floor"] is False
    assert analysis["supported_within_engineering_gates"] is False
    assert analysis["verdict"] == "NOT_SUPPORTED_BY_THIS_RUN"


def test_offline_analysis_fails_closed_on_missing_observations():
    """Ensure missing observation records fail-closed without claiming qualification."""
    states = build_closure_states()
    partial_obs = [
        {
            "spec_id": states[0]["spec"]["spec_id"],
            "replicate": 0,
            "provider": {"vector": [0.5] * 8},
        }
    ]
    analysis = analyze_closure_observations(
        states,
        partial_obs,
        specs=DEFAULT_CLOSURE_SPECS,
        replicates=3,
        thresholds=ClosureThresholds(),
    )
    assert analysis["provider_complete"] is False
    assert analysis["supported_within_engineering_gates"] is False
    assert analysis["verdict"] == "NOT_SUPPORTED_BY_THIS_RUN"
