"""Offline qualification test harness for JEV Disturbance Density & Phase Transition Campaign.

Validates:
1. Deterministic collective boundary oracle conformance across all density ladder points and regimes.
2. Strict raw telemetry representation (zero forbidden outcome/error strings).
3. Offline synthetic positive control provider passing all gates (U0, J0..J4).
4. Offline synthetic negative control rejecting lack of phase transition jump or direction drift.
5. Fail-closed behavior on incomplete observations.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import pytest

from qualification.jev_disturbance_density_campaign import (
    DISTURBANCE_LADDER_K,
    REGIMES,
    TOTAL_CONSTITUENT_UNITS,
    DensityThresholds,
    analyze_density_observations,
    build_disturbance_density_states,
    run_live_density_experiment,
)


class StableDensityProvider:
    """Synthetic provider modeling sub-critical strain, quorum phase jump, and supercritical saturation."""

    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        base = [0.85, 0.90, 0.88, 0.84, 0.89, 0.91, 0.86, 0.12]
        regime = str(state.get("governance_regime", "quorum_consensus"))
        k = int(state.get("disturbed_constituent_units", 0))
        rho = float(state.get("disturbance_density_ratio", 0.0))
        chain_continuous = bool(state.get("hash_chain_continuity", True))

        vector = list(base)

        if regime == "quorum_consensus":
            if chain_continuous:
                # Sub-critical regime: monotonic strain proportional to disturbance density rho
                strain_delta = [
                    -0.08 * rho,
                    -0.04 * rho,
                    -0.06 * rho,
                    -0.05 * rho,
                    0.03 * rho,
                    -0.04 * rho,
                    0.05 * rho,
                    0.02 * rho,
                ]
                vector = [val + delta for val, delta in zip(vector, strain_delta)]
            else:
                # Super-critical regime (k >= 8): sharp phase transition jump into failure attractor
                failure_delta = [-0.55, -0.32, -0.75, -0.68, -0.30, -0.48, -0.15, 0.45]
                # Slight non-linear saturation for k = 8, 12, 16
                sat_factor = 1.0 + 0.05 * (rho - 0.50)
                vector = [
                    max(0.0, min(1.0, val + delta * sat_factor))
                    for val, delta in zip(vector, failure_delta)
                ]
        else:
            # Serial cascade: any k > 0 triggers failure
            if chain_continuous:
                vector = list(base)
            else:
                failure_delta = [-0.55, -0.32, -0.75, -0.68, -0.30, -0.48, -0.15, 0.45]
                sat_factor = 1.0 + 0.04 * rho
                vector = [
                    max(0.0, min(1.0, val + delta * sat_factor))
                    for val, delta in zip(vector, failure_delta)
                ]

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


class NoJumpDensityProvider(StableDensityProvider):
    """Synthetic provider that fails to produce a phase jump at the quorum threshold."""

    def decide(self, **kwargs: Any) -> dict[str, Any]:
        result = super().decide(**kwargs)
        state = kwargs["state"]
        k = int(state.get("disturbed_constituent_units", 0))
        # Deliberately smooth out the displacement so k=8 has no jump above k=6
        if k >= 8 and str(state.get("governance_regime")) == "quorum_consensus":
            base = [0.85, 0.90, 0.88, 0.84, 0.89, 0.91, 0.86, 0.12]
            strain_delta = [-0.03, -0.01, -0.02, -0.02, 0.01, -0.01, 0.02, 0.01]
            result["vector"] = [v + d for v, d in zip(base, strain_delta)]
        return result


def test_deterministic_density_states_and_oracles():
    """Verify oracle behavior across the full density ladder for both regimes."""
    states = build_disturbance_density_states()
    assert len(states) == len(REGIMES) * len(DISTURBANCE_LADDER_K) == 16

    for item in states:
        oracle = item["oracle"]
        regime = item["regime"]
        k = item["k_disturbed"]
        rho = item["disturbance_density"]
        assert oracle["boundary_certificates_valid"]
        assert oracle["passes_expected_behavior"]

        if regime == "quorum_consensus":
            if k <= 6:
                assert oracle["root_status"] == "SUCCESS"
                assert oracle["quorum_achieved"] is True
                assert oracle["quorum_margin"] >= 1
                assert item["state"]["hash_chain_continuity"] is True
                assert len(item["state"]["emitted_output_keys"]) == 1
            else:
                assert oracle["root_status"] == "FAILED"
                assert oracle["quorum_achieved"] is False
                assert oracle["quorum_margin"] < 0
                assert item["state"]["hash_chain_continuity"] is False
                assert len(item["state"]["emitted_output_keys"]) == 0
        else:
            # Serial cascade
            if k == 0:
                assert oracle["root_status"] == "SUCCESS"
                assert oracle["quorum_achieved"] is True
                assert item["state"]["hash_chain_continuity"] is True
            else:
                assert oracle["root_status"] == "FAILED"
                assert oracle["quorum_achieved"] is False
                assert item["state"]["hash_chain_continuity"] is False


def test_raw_telemetry_forbids_status_and_outcome_labels():
    """Ensure state representation contains zero forbidden words."""
    forbidden = ("fail", "error", "unavailable", "verified", "committed", "bypass", "status")
    states = build_disturbance_density_states()

    for item in states:
        state_dict = item["state"]
        for key in state_dict.keys():
            for f in forbidden:
                assert f not in key.lower(), f"Forbidden '{f}' in state key '{key}'"

        serialized = json.dumps(state_dict).lower()
        for f in forbidden:
            assert f not in serialized, (
                f"Forbidden '{f}' found in serialized state for regime {item['regime']} k={item['k_disturbed']}"
            )


def test_offline_analysis_accepts_stable_density_provider():
    """Verify StableDensityProvider passes all preregistered density & phase transition gates."""
    result = run_live_density_experiment(
        provider=StableDensityProvider(),
        replicates=3,
        thresholds=DensityThresholds(),
    )
    analysis = result["analysis"]
    assert analysis["oracle_pass"]
    assert analysis["provider_complete"]
    assert analysis["supported_within_engineering_gates"]
    assert analysis["verdict"] == "SUPPORTED_WITHIN_PREREGISTERED_ENGINEERING_GATES"

    gates = analysis["gates"]
    assert gates["U0_deterministic_oracle"]
    assert gates["J0_provider_complete"]
    assert gates["J1_subcritical_monotonic_strain"]
    assert gates["J2_critical_phase_transition_jump"]
    assert gates["J3_supercritical_directional_saturation"]
    assert gates["J4_quorum_shielding_effect"]

    metrics = analysis["metrics"]
    assert metrics["critical_transition_jump_k6_to_k8"] >= 0.15
    assert metrics["min_supercritical_cosine"] >= 0.95
    assert metrics["k4_quorum_displacement_norm"] < metrics["k4_cascade_displacement_norm"]


def test_offline_analysis_rejects_missing_phase_jump():
    """Verify NoJumpDensityProvider fails gate J2 (critical phase transition jump)."""
    result = run_live_density_experiment(
        provider=NoJumpDensityProvider(),
        replicates=3,
        thresholds=DensityThresholds(),
    )
    analysis = result["analysis"]
    assert analysis["oracle_pass"]
    assert analysis["provider_complete"]
    assert not analysis["gates"]["J2_critical_phase_transition_jump"]
    assert not analysis["supported_within_engineering_gates"]


def test_offline_analysis_fails_closed_on_missing_observations():
    """Verify analyzer fails closed on empty or missing observations."""
    states = build_disturbance_density_states(regimes=REGIMES[:1], ladder=DISTURBANCE_LADDER_K[:2])
    analysis = analyze_density_observations(
        states,
        observations=[],
        regimes=REGIMES[:1],
        ladder=DISTURBANCE_LADDER_K[:2],
        replicates=3,
        thresholds=DensityThresholds(),
    )
    assert not analysis["provider_complete"]
    assert not analysis["supported_within_engineering_gates"]
