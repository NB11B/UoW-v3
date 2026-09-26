"""Offline qualification tests for the Phase-2 recursive stress campaign."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from qualification.jev_recursive_stress_campaign import (
    DEFAULT_STRESS_PROFILES,
    StressThresholds,
    analyze_observations,
    build_stress_states,
    deterministic_summary,
    run_live_experiment,
)


class StableStressProvider:
    """Synthetic observer with a scale-stable authority-loss displacement."""

    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        runtime_count = int(state["runtime_count"])
        actor_population = int(state["actor_population"])
        substitutions = int(state["certified_substitution_count"])
        scale_offset = min(
            0.02,
            0.001 * (runtime_count.bit_length() - 1)
            + 0.00001 * actor_population
            + 0.0001 * substitutions,
        )
        base = [0.86, 0.91, 0.88, 0.84, 0.90, 0.92, 0.87, 0.12]
        vector = [min(1.0, value + scale_offset) for value in base]

        if int(state["worker_binding_change_count"]) > 0:
            control = [-0.01, 0.00, -0.01, 0.00, 0.01, 0.00, 0.01, 0.00]
            vector = [value + delta for value, delta in zip(vector, control)]

        if int(state["unavailable_verifier_count"]) > 0:
            authority = [-0.42, -0.02, -0.55, -0.16, 0.04, -0.02, 0.10, 0.08]
            vector = [
                max(0.0, min(1.0, value + delta))
                for value, delta in zip(vector, authority)
            ]

        return {
            "request_id": request_id,
            "requested_model": "fake",
            "resolved_model": "fake",
            "question_ids": [str(item["question_id"]) for item in questions],
            "vector": vector,
            "answers": {},
            "usage": None,
            "validation_status": "VALID",
        }


class ScaleDriftStressProvider(StableStressProvider):
    """Synthetic observer whose authority-loss geometry changes at large scale."""

    def decide(self, **kwargs):
        result = super().decide(**kwargs)
        state = kwargs["state"]
        if int(state["unavailable_verifier_count"]) > 0 and (
            int(state["branching_factor"]) >= 4
            or int(state["certified_substitution_count"]) >= 16
        ):
            result["vector"] = list(reversed(result["vector"]))
        return result


def test_native_stress_matrix_preserves_recursive_invariants():
    states = build_stress_states()
    summary = deterministic_summary(states)

    assert summary["profile_count"] == len(DEFAULT_STRESS_PROFILES) == 10
    assert summary["state_count"] == 30
    assert summary["maximum_runtime_count"] == 121
    assert summary["maximum_certified_substitution_count"] == 16
    assert summary["maximum_actor_population"] >= 2000
    assert summary["passed"]
    assert all(summary["gates"].values())

    for item in states:
        assert item["oracle"]["boundary_valid"]
        assert item["oracle"]["certificate_hashes_stable"]
        assert item["oracle"]["substitutions_accepted"]
        assert item["oracle"]["evidence_links_valid"]
        assert item["oracle"]["root_output_signature_valid"]
        assert item["oracle"]["passes_expected_behavior"]

        if item["condition"] in {"baseline", "lawful_rebind"}:
            assert item["state"]["root_execution_status"] == "success"
            assert (
                item["state"]["recursive_evidence_link_count"]
                == item["state"]["expected_recursive_evidence_link_count"]
            )
        else:
            assert item["state"]["root_execution_status"] == "failed"
            assert item["state"]["unavailable_verifier_count"] == 1
            assert item["state"]["execution_error_class"] in {
                "actor_unavailable",
                "child_execution_failed",
            }


def test_stable_synthetic_observer_passes_multi_axis_stress_gates():
    result = run_live_experiment(
        provider=StableStressProvider(),
        profiles=DEFAULT_STRESS_PROFILES,
        replicates=3,
        thresholds=StressThresholds(),
    )
    analysis = result["analysis"]

    assert analysis["deterministic_summary"]["passed"]
    assert analysis["provider_complete"]
    assert analysis["supported_within_engineering_gates"]
    assert all(analysis["gates"].values())
    assert analysis["minimum_authority_loss_cosine_across_profiles"] >= 0.90
    assert analysis["authority_loss_norm_cv_across_profiles"] <= 0.25


def test_scale_dependent_synthetic_observer_is_rejected():
    result = run_live_experiment(
        provider=ScaleDriftStressProvider(),
        profiles=DEFAULT_STRESS_PROFILES,
        replicates=3,
        thresholds=StressThresholds(),
    )
    analysis = result["analysis"]

    assert analysis["deterministic_summary"]["passed"]
    assert analysis["provider_complete"]
    assert not analysis["gates"]["J3_cross_profile_direction_stable"]
    assert not analysis["supported_within_engineering_gates"]


def test_stress_analyzer_fails_closed_on_missing_observations():
    profiles = DEFAULT_STRESS_PROFILES[:2]
    states = build_stress_states(profiles)
    analysis = analyze_observations(
        states,
        observations=[],
        profiles=profiles,
        replicates=3,
        thresholds=StressThresholds(),
    )

    assert analysis["deterministic_summary"]["passed"]
    assert not analysis["provider_complete"]
    assert not analysis["supported_within_engineering_gates"]
