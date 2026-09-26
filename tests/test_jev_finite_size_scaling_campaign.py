"""Offline qualification test harness for JEV Finite-Size Collective Scaling Campaign.

Validates:
1. Deterministic collective boundary oracle conformance across all 18 ensemble specs.
2. Strict raw telemetry representation (zero forbidden outcome/error strings).
3. Offline synthetic positive control provider passing all gates (U0, J0..J5).
4. Offline synthetic negative control rejecting failing shielding or directional drift.
5. Fail-closed behavior on incomplete observations.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import pytest

from qualification.jev_finite_size_scaling_campaign import (
    DEFAULT_SCALING_SPECS,
    ScalingSpec,
    ScalingThresholds,
    analyze_scaling_observations,
    build_scaling_states,
    run_live_scaling_experiment,
)


class StableScalingProvider:
    """Synthetic provider modeling size-invariant shielding, sharp transition jumps, and invariant attractor."""

    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        base = [0.85, 0.90, 0.88, 0.84, 0.89, 0.91, 0.86, 0.12]
        regime = str(state.get("governance_regime", "quorum"))
        rho = float(state.get("disturbance_density_ratio", 0.0))
        chain_continuous = bool(state.get("hash_chain_continuity", True))
        M = int(state.get("constituent_unit_count", 16))

        # Size-independent slight calibration offset
        size_offset = 0.001 * (M.bit_length() - 3)
        vector = [v + size_offset for v in base]

        if chain_continuous:
            # Sub-critical regime: mild strain dampened by quorum shielding
            strain_delta = [
                -0.08 * rho,
                -0.04 * rho,
                -0.05 * rho,
                -0.04 * rho,
                0.03 * rho,
                -0.03 * rho,
                0.04 * rho,
                0.02 * rho,
            ]
            vector = [v + d for v, d in zip(vector, strain_delta)]
        else:
            # Post-threshold failure: sharp jump into common attractor Delta_A*
            failure_delta = [-0.65, -0.42, -0.84, -0.74, -0.38, -0.54, -0.16, 0.44]
            sat_factor = 1.0 + 0.02 * rho
            vector = [
                max(0.0, min(1.0, v + d * sat_factor))
                for v, d in zip(vector, failure_delta)
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


class WeakShieldingScalingProvider(StableScalingProvider):
    """Synthetic provider whose quorum shielding collapses at large M."""

    def decide(self, **kwargs: Any) -> dict[str, Any]:
        result = super().decide(**kwargs)
        state = kwargs["state"]
        M = int(state.get("constituent_unit_count", 16))
        # Deliberately elevate subcritical quorum displacement at M=32
        if state.get("spec_id") == "M32_sub_25":
            base = [0.85, 0.90, 0.88, 0.84, 0.89, 0.91, 0.86, 0.12]
            large_strain = [-0.50, -0.30, -0.60, -0.50, -0.20, -0.35, -0.10, 0.30]
            result["vector"] = [v + d for v, d in zip(base, large_strain)]
        return result


def test_deterministic_scaling_states_and_oracles():
    """Verify oracle behavior across all 18 ensemble specifications."""
    states = build_scaling_states()
    assert len(states) == len(DEFAULT_SCALING_SPECS) == 18

    for item in states:
        oracle = item["oracle"]
        spec = item["spec"]
        assert oracle["boundary_certificates_valid"]
        assert oracle["passes_expected_behavior"]

        if oracle["quorum_achieved"]:
            assert oracle["root_status"] == "SUCCESS"
            assert item["state"]["hash_chain_continuity"] is True
            assert len(item["state"]["emitted_output_keys"]) == 1
        else:
            assert oracle["root_status"] == "FAILED"
            assert item["state"]["hash_chain_continuity"] is False
            assert len(item["state"]["emitted_output_keys"]) == 0


def test_raw_telemetry_state_forbids_status_and_outcome_labels():
    """Ensure state representation contains zero forbidden words."""
    forbidden = ("fail", "error", "unavailable", "verified", "committed", "bypass", "status")
    states = build_scaling_states()

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


def test_offline_analysis_accepts_stable_scaling_provider():
    """Verify StableScalingProvider passes all preregistered finite-size scaling gates."""
    result = run_live_scaling_experiment(
        provider=StableScalingProvider(),
        replicates=3,
        thresholds=ScalingThresholds(),
    )
    analysis = result["analysis"]
    assert analysis["oracle_pass"]
    assert analysis["provider_complete"]
    assert analysis["supported_within_engineering_gates"]
    assert analysis["verdict"] == "SUPPORTED_WITHIN_PREREGISTERED_ENGINEERING_GATES"

    gates = analysis["gates"]
    assert gates["U0_deterministic_oracle"]
    assert gates["J0_provider_complete"]
    assert gates["J1_subcritical_shielding_universal"]
    assert gates["J2_transition_jump_invariant"]
    assert gates["J3_cross_size_directional_alignment"]
    assert gates["J4_amplitude_stability_across_size"]
    assert gates["J5_policy_shift_consistency"]

    # Verify quantitative metrics
    for M in (8, 16, 32):
        assert analysis["shielding_ratios"][M] >= 3.0
        assert analysis["transition_jumps"][M] >= 0.80

    assert analysis["minimum_cross_size_cosine"] >= 0.950
    assert analysis["amplitude_cv_across_size"] <= 0.15
    assert analysis["policy_q75_metrics"]["q75_jump"] >= 0.80


def test_offline_analysis_rejects_weak_shielding_provider():
    """Verify WeakShieldingScalingProvider fails gate J1 (subcritical shielding)."""
    result = run_live_scaling_experiment(
        provider=WeakShieldingScalingProvider(),
        replicates=3,
        thresholds=ScalingThresholds(),
    )
    analysis = result["analysis"]
    assert analysis["oracle_pass"]
    assert analysis["provider_complete"]
    assert not analysis["gates"]["J1_subcritical_shielding_universal"]
    assert not analysis["supported_within_engineering_gates"]


def test_offline_analysis_fails_closed_on_missing_observations():
    """Verify analyzer fails closed on empty or missing observations."""
    states = build_scaling_states(DEFAULT_SCALING_SPECS[:2])
    analysis = analyze_scaling_observations(
        states,
        observations=[],
        specs=DEFAULT_SCALING_SPECS[:2],
        replicates=3,
        thresholds=ScalingThresholds(),
    )
    assert not analysis["provider_complete"]
    assert not analysis["supported_within_engineering_gates"]
