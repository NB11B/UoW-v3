"""Offline qualification test harness for JEV Failure Semantics Operator Family Campaign.

Validates:
1. Deterministic oracle conformance across all 13 specs.
2. Common-output control: identical macro-outcome (FAILED, uncommitted, Q margin = -1) across all failure modes.
3. Strict raw telemetry representation (zero forbidden outcome/error strings).
4. Offline synthetic positive control provider passing all gates (U0, J0..J4).
5. Offline synthetic negative control rejecting high noise floor.
6. Fail-closed behavior on incomplete observations.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import pytest

from qualification.jev_failure_semantics_campaign import (
    DEFAULT_FAILURE_SPECS,
    FailureSemanticsThresholds,
    FailureSpec,
    analyze_failure_semantics_observations,
    build_failure_states,
    run_live_failure_semantics_experiment,
)


class StableMultiOperatorProvider:
    """Synthetic provider modeling distinct operator directions for distinct failure mechanisms."""

    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        base = [0.85, 0.90, 0.88, 0.84, 0.89, 0.91, 0.86, 0.12]
        mech = str(state.get("mechanism", "none"))

        if mech == "none":
            vector = list(base)
        elif mech == "authority":
            # Delta_A: authority loss specifically lowers effective authority (q0) and path (q2)
            delta = [-0.65, -0.42, -0.84, -0.74, -0.38, -0.54, -0.16, 0.44]
            vector = [max(0.0, min(1.0, v + d)) for v, d in zip(base, delta)]
        elif mech == "evidence":
            # Delta_E: digest mismatch lowers boundary semantics (q5) and coherence (q4)
            delta = [-0.40, -0.55, -0.70, -0.60, -0.75, -0.82, -0.30, 0.35]
            vector = [max(0.0, min(1.0, v + d)) for v, d in zip(base, delta)]
        elif mech == "causal":
            # Delta_C: severed pipeline halts early; severe drop on commit path (q2) and control (q3)
            delta = [-0.50, -0.60, -0.88, -0.80, -0.45, -0.60, -0.20, 0.40]
            vector = [max(0.0, min(1.0, v + d)) for v, d in zip(base, delta)]
        elif mech == "temporal":
            # Delta_T: timed out; high recertification required (q7), authority nominally higher
            delta = [-0.25, -0.30, -0.65, -0.40, -0.35, -0.40, -0.70, 0.75]
            vector = [max(0.0, min(1.0, v + d)) for v, d in zip(base, delta)]
        elif mech == "resource":
            # Delta_R: resource breach; non-recoverable without budget adjustment (q6)
            delta = [-0.30, -0.35, -0.70, -0.50, -0.40, -0.45, -0.75, 0.65]
            vector = [max(0.0, min(1.0, v + d)) for v, d in zip(base, delta)]
        elif mech == "adversarial":
            # Delta_Adv: quarantine active; strong drop on failure handling (q4)
            delta = [-0.55, -0.45, -0.80, -0.65, -0.85, -0.70, -0.25, 0.50]
            vector = [max(0.0, min(1.0, v + d)) for v, d in zip(base, delta)]
        elif mech == "authority_evidence":
            delta = [-0.60, -0.48, -0.82, -0.70, -0.50, -0.65, -0.20, 0.42]
            vector = [max(0.0, min(1.0, v + d)) for v, d in zip(base, delta)]
        elif mech == "evidence_authority":
            delta = [-0.45, -0.52, -0.78, -0.68, -0.65, -0.75, -0.25, 0.40]
            vector = [max(0.0, min(1.0, v + d)) for v, d in zip(base, delta)]
        elif mech == "authority_causal":
            delta = [-0.62, -0.45, -0.85, -0.72, -0.42, -0.58, -0.18, 0.43]
            vector = [max(0.0, min(1.0, v + d)) for v, d in zip(base, delta)]
        elif mech == "causal_authority":
            delta = [-0.52, -0.58, -0.86, -0.78, -0.46, -0.62, -0.22, 0.41]
            vector = [max(0.0, min(1.0, v + d)) for v, d in zip(base, delta)]
        elif mech == "evidence_resource":
            delta = [-0.38, -0.50, -0.72, -0.58, -0.68, -0.72, -0.45, 0.48]
            vector = [max(0.0, min(1.0, v + d)) for v, d in zip(base, delta)]
        elif mech == "resource_evidence":
            delta = [-0.32, -0.38, -0.74, -0.52, -0.45, -0.50, -0.68, 0.58]
            vector = [max(0.0, min(1.0, v + d)) for v, d in zip(base, delta)]
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


class HighNoiseFailureProvider(StableMultiOperatorProvider):
    """Synthetic provider with noisy replicate fluctuations exceeding the 0.05 threshold."""

    def decide(self, **kwargs: Any) -> dict[str, Any]:
        result = super().decide(**kwargs)
        req_id = kwargs.get("request_id", "")
        # Add random-like large noise depending on replicate
        rep_noise = 0.08 if "r1" in req_id else (-0.08 if "r2" in req_id else 0.0)
        result["vector"] = [max(0.0, min(1.0, v + rep_noise)) for v in result["vector"]]
        return result


def test_deterministic_failure_states_and_oracles():
    """Verify oracle behavior across all 13 failure specifications."""
    states = build_failure_states()
    assert len(states) == len(DEFAULT_FAILURE_SPECS) == 13

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
    """Verify that all failure states produce the identical macroscopic failure outcome."""
    states = build_failure_states()
    failure_states = [s for s in states if s["spec"]["spec_id"] != "op_base"]
    assert len(failure_states) == 12

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
    states = build_failure_states()

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


def test_offline_analysis_accepts_stable_multi_operator_provider():
    """Verify StableMultiOperatorProvider passes all preregistered failure semantics gates."""
    result = run_live_failure_semantics_experiment(
        provider=StableMultiOperatorProvider(),
        replicates=3,
        thresholds=FailureSemanticsThresholds(),
    )
    analysis = result["analysis"]
    assert analysis["oracle_pass"]
    assert analysis["provider_complete"]
    assert analysis["supported_within_engineering_gates"]
    assert analysis["verdict"] == "SUPPORTED_WITHIN_PREREGISTERED_ENGINEERING_GATES"

    gates = analysis["gates"]
    assert gates["U0_deterministic_oracle"]
    assert gates["J0_provider_complete"]
    assert gates["J1_operator_detectability"]
    assert gates["J2_repeatability_noise_floor"]
    assert gates["J3_operator_family_characterization"]
    assert gates["J4_noncommutativity_evaluated"]

    assert analysis["operator_family_geometry"]["regime"] == "MULTI_OPERATOR_FAMILY"
    assert analysis["operator_family_geometry"]["minimum_pairwise_cosine"] < 0.950


def test_offline_analysis_rejects_high_noise():
    """Verify high noise provider fails gate J2."""
    result = run_live_failure_semantics_experiment(
        provider=HighNoiseFailureProvider(),
        replicates=3,
        thresholds=FailureSemanticsThresholds(),
    )
    analysis = result["analysis"]
    assert analysis["gates"]["J2_repeatability_noise_floor"] is False
    assert analysis["supported_within_engineering_gates"] is False
    assert analysis["verdict"] == "NOT_SUPPORTED_BY_THIS_RUN"


def test_offline_analysis_fails_closed_on_missing_observations():
    """Ensure missing observation records fail-closed without claiming qualification."""
    states = build_failure_states()
    partial_obs = [
        {
            "spec_id": states[0]["spec"]["spec_id"],
            "replicate": 0,
            "provider": {"vector": [0.5] * 8},
        }
    ]
    analysis = analyze_failure_semantics_observations(
        states,
        partial_obs,
        specs=DEFAULT_FAILURE_SPECS,
        replicates=3,
        thresholds=FailureSemanticsThresholds(),
    )
    assert analysis["provider_complete"] is False
    assert analysis["supported_within_engineering_gates"] is False
    assert analysis["verdict"] == "NOT_SUPPORTED_BY_THIS_RUN"
