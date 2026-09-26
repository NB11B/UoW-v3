"""Offline harness tests for the live JEV recursive-scale campaign.

These tests validate experiment construction and analysis only. The fake provider
is not JEV evidence and is never used by the live CLI.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from qualification.jev_recursive_scale_campaign import (
    ExperimentThresholds,
    analyze_observations,
    build_deterministic_states,
    run_live_experiment,
)


class StableFakeProvider:
    """Synthetic provider with a scale-invariant authority-loss displacement."""

    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        depth = int(state["recursive_level_count"]) - 1
        base = [0.86, 0.91, 0.88, 0.84, 0.90, 0.92, 0.87, 0.12]
        depth_offset = 0.002 * depth
        vector = [min(1.0, value + depth_offset) for value in base]

        if int(state["worker_binding_change_count"]) > 0:
            control_delta = [-0.01, 0.00, -0.01, 0.00, 0.01, 0.00, 0.01, 0.00]
            vector = [value + delta for value, delta in zip(vector, control_delta)]

        if int(state["unavailable_verifier_count"]) > 0:
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


class DepthDriftFakeProvider(StableFakeProvider):
    """Synthetic provider whose authority-loss direction deliberately rotates."""

    def decide(self, **kwargs):
        result = super().decide(**kwargs)
        state = kwargs["state"]
        if int(state["unavailable_verifier_count"]) > 0:
            depth = int(state["recursive_level_count"]) - 1
            if depth % 2 == 1:
                result["vector"] = list(reversed(result["vector"]))
        return result


def test_deterministic_surface_matches_current_recursive_boundary_contract():
    states = build_deterministic_states(max_depth=3)
    assert len(states) == 12

    for item in states:
        assert item["oracle"]["boundary_valid"]
        assert item["oracle"]["certificate_hashes_stable"]
        assert item["oracle"]["passes_expected_behavior"]

    for depth in range(4):
        by_condition = {
            item["condition"]: item
            for item in states
            if item["depth"] == depth
        }
        assert by_condition["baseline"]["oracle"]["root_status"] == "SUCCESS"
        assert by_condition["lawful_rebind"]["oracle"]["root_status"] == "SUCCESS"
        assert by_condition["authority_loss"]["oracle"]["root_status"] == "FAILED"
        assert by_condition["authority_loss"]["state"]["unavailable_verifier_count"] == 1


def test_analysis_accepts_scale_invariant_synthetic_signature():
    result = run_live_experiment(
        provider=StableFakeProvider(),
        max_depth=3,
        replicates=3,
        thresholds=ExperimentThresholds(),
    )
    analysis = result["analysis"]
    assert analysis["oracle_pass"]
    assert analysis["provider_complete"]
    assert analysis["supported_within_engineering_gates"]
    assert all(analysis["gates"].values())


def test_analysis_rejects_depth_dependent_synthetic_signature():
    result = run_live_experiment(
        provider=DepthDriftFakeProvider(),
        max_depth=3,
        replicates=3,
        thresholds=ExperimentThresholds(),
    )
    analysis = result["analysis"]
    assert analysis["oracle_pass"]
    assert analysis["provider_complete"]
    assert not analysis["gates"]["J3_cross_depth_direction_stable"]
    assert not analysis["supported_within_engineering_gates"]


def test_analyzer_fails_closed_on_missing_provider_observations():
    states = build_deterministic_states(max_depth=1)
    analysis = analyze_observations(
        states,
        observations=[],
        max_depth=1,
        replicates=3,
        thresholds=ExperimentThresholds(),
    )
    assert not analysis["provider_complete"]
    assert not analysis["supported_within_engineering_gates"]
