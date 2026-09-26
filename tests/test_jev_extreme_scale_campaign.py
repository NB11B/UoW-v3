"""Offline qualification test harness for the JEV x UoW Extreme Recursive Scale Campaign.

Validates:
1. Mathematical scale formulas N(b,d) and flat control profiles.
2. Deterministic boundary oracle conformance and O(d) witness stack execution across all 6 tiers.
3. Raw telemetry representation invariance (zero forbidden outcome labels).
4. Full offline positive control (StableFakeExtremeScaleProvider) passing all gates (U0, J0..J5).
5. Full offline negative control (DriftFakeExtremeScaleProvider) rejecting direction drift.
6. Fail-closed behavior on missing or incomplete provider responses.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import pytest

from qualification.jev_extreme_scale_campaign import (
    CONDITIONS,
    DEFAULT_SCALE_TIERS,
    ExtremeScaleThresholds,
    ScaleTier,
    analyze_extreme_scale_observations,
    build_extreme_scale_states,
    generate_flat_control_profile,
    run_live_extreme_scale_experiment,
)


class StableFakeExtremeScaleProvider:
    """Synthetic provider with scale-invariant authority displacement and attenuating rebind."""

    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        base = [0.86, 0.91, 0.88, 0.84, 0.90, 0.92, 0.87, 0.12]
        depth = int(state.get("recursive_depth", 0))
        depth_offset = 0.001 * depth
        vector = [min(1.0, value + depth_offset) for value in base]

        # Lawful rebind: subtle displacement that attenuates with scale
        if state.get("worker_binding_changed", False):
            scale_factor = 1.0 / (1.0 + 0.1 * depth)
            control_delta = [
                -0.02 * scale_factor,
                0.00,
                -0.01 * scale_factor,
                0.00,
                0.01 * scale_factor,
                0.00,
                0.01 * scale_factor,
                0.00,
            ]
            vector = [value + delta for value, delta in zip(vector, control_delta)]

        # Authority loss: detected via broken hash chain or missing sequence
        if not state.get("hash_chain_continuity", True) or len(state.get("node_execution_sequence", [])) < 4:
            authority_delta = [-0.42, -0.02, -0.55, -0.16, 0.04, -0.02, 0.10, 0.08]
            vector = [
                max(0.0, min(1.0, value + delta))
                for value, delta in zip(vector, authority_delta)
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


class DriftFakeExtremeScaleProvider(StableFakeExtremeScaleProvider):
    """Synthetic provider whose authority-loss direction deliberately rotates across tiers."""

    def decide(self, **kwargs: Any) -> dict[str, Any]:
        result = super().decide(**kwargs)
        state = kwargs["state"]
        if not state.get("hash_chain_continuity", True) or len(state.get("node_execution_sequence", [])) < 4:
            tier_id = str(state.get("scale_tier", "S0"))
            tier_num = int(tier_id[1:]) if len(tier_id) > 1 and tier_id[1:].isdigit() else 0
            if tier_num % 2 == 1:
                result["vector"] = list(reversed(result["vector"]))
        return result


def test_logical_uow_count_formula():
    """Verify N(b,d) closed-form calculation matches recursive summation."""
    for tier in DEFAULT_SCALE_TIERS:
        b = tier.branching_factor
        d = tier.recursive_depth
        if b <= 1:
            expected = d + 1
        else:
            expected = sum(b ** k for k in range(d + 1))
        assert tier.logical_uow_count == expected

    # Verify exact precalculated milestone values
    tier_counts = {t.tier_id: t.logical_uow_count for t in DEFAULT_SCALE_TIERS}
    assert tier_counts["S0"] == 1
    assert tier_counts["S1"] == 85
    assert tier_counts["S2"] == 1_365
    assert tier_counts["S3"] == 37_449
    assert tier_counts["S4"] == 2_396_745
    assert tier_counts["S5"] == 19_173_961


def test_flat_control_profile_computation():
    """Verify flat control profile correctly identifies context window saturation."""
    s0_prof = generate_flat_control_profile(DEFAULT_SCALE_TIERS[0])
    assert s0_prof["logical_uow_count"] == 1
    assert not s0_prof["saturates_standard_context_window"]
    assert s0_prof["recursive_contracted_payload_bytes"] == 620

    s2_prof = generate_flat_control_profile(DEFAULT_SCALE_TIERS[2])
    assert s2_prof["logical_uow_count"] == 1_365
    assert s2_prof["saturates_standard_context_window"]  # > 32k tokens

    s5_prof = generate_flat_control_profile(DEFAULT_SCALE_TIERS[5])
    assert s5_prof["logical_uow_count"] == 19_173_961
    assert s5_prof["flat_total_nodes"] == 19_173_961 * 4
    assert s5_prof["saturates_standard_context_window"]
    assert s5_prof["compression_ratio"] > 10_000_000


def test_deterministic_surface_all_tiers_and_witness_stack():
    """Verify deterministic boundary oracle execution across all 6 tiers with O(d) witness stack."""
    states = build_extreme_scale_states(DEFAULT_SCALE_TIERS)
    assert len(states) == len(DEFAULT_SCALE_TIERS) * len(CONDITIONS) == 18

    for item in states:
        oracle = item["oracle"]
        assert oracle["boundary_valid"]
        assert oracle["certificate_hashes_stable"]
        assert oracle["passes_expected_behavior"]

        cond = item["condition"]
        if cond in {"baseline", "lawful_rebind"}:
            assert oracle["root_status"] == "SUCCESS"
            assert item["state"]["hash_chain_continuity"] is True
            assert len(item["state"]["node_execution_sequence"]) == 4
        else:
            assert oracle["root_status"] == "FAILED"
            assert item["state"]["hash_chain_continuity"] is False
            assert len(item["state"]["node_execution_sequence"]) < 4
            assert "ACTOR_UNAVAILABLE" in item["diagnostics"]["root_error_message"]


def test_raw_telemetry_state_forbids_outcome_and_status_labels():
    """Enforce that normalized state representation never contains forbidden outcome words."""
    forbidden_substrings = (
        "fail",
        "error",
        "unavailable",
        "verified",
        "committed",
        "bypass",
        "status",
    )
    states = build_extreme_scale_states(DEFAULT_SCALE_TIERS)

    for item in states:
        state_dict = item["state"]
        # Check all keys
        for key in state_dict.keys():
            key_lower = key.lower()
            for forbidden in forbidden_substrings:
                assert forbidden not in key_lower, f"Forbidden '{forbidden}' found in state key '{key}'"

        # Check full serialized state
        serialized = json.dumps(state_dict).lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in serialized, (
                f"Forbidden '{forbidden}' found in serialized state for tier {item['tier']['tier_id']} "
                f"under condition {item['condition']}"
            )


def test_offline_analysis_accepts_stable_provider():
    """Verify StableFakeExtremeScaleProvider satisfies all preregistered engineering gates."""
    result = run_live_extreme_scale_experiment(
        provider=StableFakeExtremeScaleProvider(),
        tiers=DEFAULT_SCALE_TIERS,
        replicates=3,
        thresholds=ExtremeScaleThresholds(),
    )
    analysis = result["analysis"]
    assert analysis["oracle_pass"]
    assert analysis["provider_complete"]
    assert analysis["supported_within_engineering_gates"]
    assert analysis["verdict"] == "SUPPORTED_WITHIN_PREREGISTERED_ENGINEERING_GATES"

    gates = analysis["gates"]
    assert gates["U0_deterministic_oracle"]
    assert gates["J0_provider_complete"]
    assert gates["J1_authority_signal_above_repeatability"]
    assert gates["J2_authority_distinct_from_lawful_rebind"]
    assert gates["J3_cross_tier_direction_stable"]
    assert gates["J4_cross_tier_magnitude_stable"]
    assert gates["J5_lawful_rebind_attenuation_trend"]

    assert analysis["minimum_authority_loss_cosine_across_scale"] >= 0.90
    assert analysis["authority_loss_norm_cv_across_scale"] <= 0.25


def test_offline_analysis_rejects_drift_provider():
    """Verify DriftFakeExtremeScaleProvider is rejected by directional stability gate J3."""
    result = run_live_extreme_scale_experiment(
        provider=DriftFakeExtremeScaleProvider(),
        tiers=DEFAULT_SCALE_TIERS,
        replicates=3,
        thresholds=ExtremeScaleThresholds(),
    )
    analysis = result["analysis"]
    assert analysis["oracle_pass"]
    assert analysis["provider_complete"]
    assert not analysis["gates"]["J3_cross_tier_direction_stable"]
    assert not analysis["supported_within_engineering_gates"]
    assert analysis["verdict"] == "NOT_SUPPORTED_BY_THIS_RUN"


def test_offline_analysis_fails_closed_on_missing_observations():
    """Verify analyzer fails closed if any observations are missing."""
    states = build_extreme_scale_states(DEFAULT_SCALE_TIERS[:2])
    analysis = analyze_extreme_scale_observations(
        states,
        observations=[],
        tiers=DEFAULT_SCALE_TIERS[:2],
        replicates=3,
        thresholds=ExtremeScaleThresholds(),
    )
    assert not analysis["provider_complete"]
    assert not analysis["supported_within_engineering_gates"]
    assert analysis["verdict"] == "NOT_SUPPORTED_BY_THIS_RUN"
