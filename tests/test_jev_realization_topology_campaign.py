"""Offline qualification test harness for JEV Realization Graph Topology Invariance Campaign.

Validates:
1. Deterministic reachability, boundary certification, and oracle checks across all 18 specs.
2. Effective governance resilience thresholds rho_c(T) vary by topology (Tree=0.250, Modular=0.3125, Ring=0.375, Star=0.500, Small-World=0.500).
3. Strict raw telemetry representation (zero forbidden outcome/error strings).
4. Offline synthetic positive control provider passing all gates (U0, J0..J4).
5. Offline synthetic negative control rejecting failing shielding or directional drift.
6. Fail-closed behavior on incomplete observations.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import pytest

from qualification.jev_realization_topology_campaign import (
    DEFAULT_TOPOLOGY_SPECS,
    TopologySpec,
    TopologyThresholds,
    analyze_topology_observations,
    build_topology_states,
    compute_causal_reachability,
    run_live_topology_experiment,
)


class StableTopologyProvider:
    """Synthetic provider modeling topology-invariant authority-loss attractor."""

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
        spec_id = str(state.get("spec_id", ""))

        vector = list(base)
        if regime == "cascade":
            casc_delta = [-0.60, -0.40, -0.75, -0.70, -0.35, -0.50, -0.15, 0.40]
            vector = [v + d for v, d in zip(vector, casc_delta)]
        elif chain_continuous:
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
            failure_delta = [-0.65, -0.42, -0.84, -0.74, -0.38, -0.54, -0.16, 0.44]
            top_hash = sum(ord(c) for c in spec_id) % 10
            pert = 0.001 * (top_hash - 5)
            vector = [
                max(0.0, min(1.0, v + d + pert))
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


class WeakShieldingTopologyProvider(StableTopologyProvider):
    """Synthetic provider whose quorum shielding collapses."""

    def decide(self, **kwargs: Any) -> dict[str, Any]:
        result = super().decide(**kwargs)
        state = kwargs["state"]
        if state.get("spec_id") == "tree_sub":
            base = [0.85, 0.90, 0.88, 0.84, 0.89, 0.91, 0.86, 0.12]
            large_strain = [-0.55, -0.35, -0.70, -0.65, -0.30, -0.45, -0.12, 0.35]
            result["vector"] = [v + d for v, d in zip(base, large_strain)]
        return result


class DriftingDirectionTopologyProvider(StableTopologyProvider):
    """Synthetic provider whose post-threshold direction diverges across topologies."""

    def decide(self, **kwargs: Any) -> dict[str, Any]:
        result = super().decide(**kwargs)
        state = kwargs["state"]
        if state.get("spec_id") == "ring_at":
            base = [0.85, 0.90, 0.88, 0.84, 0.89, 0.91, 0.86, 0.12]
            divergent_delta = [0.40, 0.40, -0.40, -0.40, 0.40, 0.40, -0.40, -0.40]
            result["vector"] = [v + d for v, d in zip(base, divergent_delta)]
        return result


def test_deterministic_topology_states_and_oracles():
    """Verify oracle behavior and causal reachability across all 18 specs."""
    states = build_topology_states()
    assert len(states) == len(DEFAULT_TOPOLOGY_SPECS) == 18

    # Effective thresholds map
    expected_thresholds = {
        "tree": 4,      # rho_c = 0.250
        "modular": 5,   # rho_c = 0.3125
        "ring": 6,      # rho_c = 0.375
        "star": 8,      # rho_c = 0.500
        "small_world": 8,  # rho_c = 0.500
    }

    for item in states:
        oracle = item["oracle"]
        spec = item["spec"]
        sid = spec["spec_id"]
        role = spec["condition_role"]
        top = spec["topology_type"]

        assert oracle["boundary_certificates_valid"]
        assert oracle["passes_expected_behavior"]

        if role == "base":
            assert oracle["disturbed_count"] == 0
            assert oracle["reachable_count"] == 16
            assert oracle["quorum_achieved"] is True
            assert oracle["root_status"] == "SUCCESS"
        elif role == "pre":
            assert oracle["disturbed_count"] == expected_thresholds[top] - (2 if top == "modular" and expected_thresholds[top] == 5 else 1) or oracle["disturbed_count"] < expected_thresholds[top]
            assert oracle["reachable_count"] >= 9
            assert oracle["quorum_achieved"] is True
            assert oracle["root_status"] == "SUCCESS"
        elif role == "at":
            assert oracle["disturbed_count"] == expected_thresholds[top]
            assert oracle["reachable_count"] == 8
            assert oracle["quorum_achieved"] is False
            assert oracle["root_status"] == "FAILED"
        elif role == "casc":
            assert oracle["regime"] == "cascade"
            assert oracle["disturbed_count"] == 2
            assert oracle["quorum_achieved"] is False
            assert oracle["root_status"] == "FAILED"


def test_causal_reachability_mechanisms():
    """Directly test the graph reachability logic for all 5 topologies."""
    # 1. Star: N - k
    assert compute_causal_reachability("star", set()) == 16
    assert compute_causal_reachability("star", {0, 1, 2}) == 13
    assert compute_causal_reachability("star", set(range(8))) == 8

    # 2. Tree: 4 branches of 4; branch drops if < 3 valid
    assert compute_causal_reachability("tree", set()) == 16
    assert compute_causal_reachability("tree", {0}) == 15  # B0 has 3 -> valid
    assert compute_causal_reachability("tree", {0, 1}) == 12  # B0 drops -> 12 valid
    assert compute_causal_reachability("tree", {0, 1, 4, 5}) == 8  # B0 & B1 drop -> 8 valid

    # 3. Modular: Bridge units 3, 7, 11
    assert compute_causal_reachability("modular", set()) == 16
    assert compute_causal_reachability("modular", {11}) == 11  # C2 loses u11 (3 left) and severs C3 (0) -> 4+4+3=11
    assert compute_causal_reachability("modular", {7}) == 7   # C1 loses u7 (3 left) and severs C2,C3 -> 4+3=7

    # 4. Ring: Chord step 1 and 2, dual collectors 0 and 8
    assert compute_causal_reachability("ring", set()) == 16
    # Sever arc between 0 and 8
    assert compute_causal_reachability("ring", {1, 2, 3, 6, 7, 9}) == 8

    # 5. Small-World: Shortcuts (0-8, 2-10, 4-12, 6-14)
    assert compute_causal_reachability("small_world", set()) == 16
    assert compute_causal_reachability("small_world", {1, 2, 3, 4, 5, 6, 7}) == 9
    assert compute_causal_reachability("small_world", {1, 2, 3, 4, 5, 6, 7, 9}) == 8


def test_raw_telemetry_state_forbids_status_and_outcome_labels():
    """Ensure state representation contains zero forbidden words."""
    forbidden = ("fail", "error", "unavailable", "verified", "committed", "bypass", "status")
    states = build_topology_states()

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


def test_offline_analysis_accepts_stable_topology_provider():
    """Verify StableTopologyProvider passes all preregistered topology gates."""
    result = run_live_topology_experiment(
        provider=StableTopologyProvider(),
        replicates=3,
        thresholds=TopologyThresholds(),
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
    assert gates["J3_cross_topology_directional_alignment"]
    assert gates["J4_amplitude_stability_across_topology"]

    assert analysis["minimum_cross_topology_cosine"] >= 0.950
    assert analysis["amplitude_cv_across_topology"] <= 0.15


def test_offline_analysis_rejects_weak_shielding():
    """Verify weak shielding provider fails gate J1."""
    result = run_live_topology_experiment(
        provider=WeakShieldingTopologyProvider(),
        replicates=3,
        thresholds=TopologyThresholds(),
    )
    analysis = result["analysis"]
    assert analysis["gates"]["J1_subcritical_shielding_universal"] is False
    assert analysis["supported_within_engineering_gates"] is False
    assert analysis["verdict"] == "NOT_SUPPORTED_BY_THIS_RUN"


def test_offline_analysis_rejects_divergent_direction():
    """Verify divergent post-threshold direction fails gate J3."""
    result = run_live_topology_experiment(
        provider=DriftingDirectionTopologyProvider(),
        replicates=3,
        thresholds=TopologyThresholds(),
    )
    analysis = result["analysis"]
    assert analysis["gates"]["J3_cross_topology_directional_alignment"] is False
    assert analysis["supported_within_engineering_gates"] is False
    assert analysis["verdict"] == "NOT_SUPPORTED_BY_THIS_RUN"


def test_offline_analysis_fails_closed_on_missing_observations():
    """Ensure missing observation records fail-closed without claiming qualification."""
    states = build_topology_states()
    partial_obs = [
        {
            "spec_id": states[0]["spec"]["spec_id"],
            "replicate": 0,
            "provider": {"vector": [0.5] * 8},
        }
    ]
    analysis = analyze_topology_observations(
        states,
        partial_obs,
        specs=DEFAULT_TOPOLOGY_SPECS,
        replicates=3,
        thresholds=TopologyThresholds(),
    )
    assert analysis["provider_complete"] is False
    assert analysis["supported_within_engineering_gates"] is False
    assert analysis["verdict"] == "NOT_SUPPORTED_BY_THIS_RUN"
