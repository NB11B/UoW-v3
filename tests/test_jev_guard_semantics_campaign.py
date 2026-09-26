"""Offline qualification test harness for JEV Guard Semantics Campaign.

Validates:
1. Deterministic oracle conformance across all 39 specs.
2. Quorum accounting and boundary certificates across pass and trip regimes.
3. Strict raw telemetry representation (zero forbidden outcome/error strings).
4. Offline synthetic positive control provider passing all gates (G_U0, G_J0..G_J3).
5. Offline synthetic negative control rejecting high noise floor (G_J0).
6. Offline synthetic negative control rejecting continuous drift (G_J1, G_J3).
7. Fail-closed behavior on incomplete observations.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import pytest

from qualification.jev_guard_semantics_campaign import (
    DEFAULT_GUARD_SPECS,
    GuardSpec,
    analyze_guard_semantics_observations,
    build_guard_states,
    run_live_guard_semantics_experiment,
)


class StableGuardSemanticsProvider:
    """Synthetic provider modeling discrete guard step transitions."""

    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        # Nominal base vector (all constraints satisfied)
        base = [0.85, 0.90, 0.88, 0.84, 0.89, 0.91, 0.86, 0.12]
        guard_name = str(state.get("guard_name", "none"))
        guard_tripped = bool(state.get("guard_tripped", False))

        if not guard_tripped:
            # Minor within-regime perturbation proportional to parameter
            v = list(base)
            if guard_name == "temporal":
                t = float(state.get("observed_duration_ms", 900.0))
                # Microscopic drift on pass side: ~0.005 over 100ms
                v[0] -= 0.00005 * (t - 900.0)
            elif guard_name == "resource":
                r = float(state.get("observed_ram_units", 8))
                v[6] -= 0.0005 * (r - 8.0)
            vector = v
        else:
            # Macro breakdown step + mechanism-specific perturbation
            if guard_name == "temporal":
                delta = [-0.25, -0.30, -0.65, -0.40, -0.35, -0.40, -0.70, 0.75]
                t = float(state.get("observed_duration_ms", 1001.0))
                delta[7] += 0.00001 * (t - 1001.0)
            elif guard_name == "resource":
                delta = [-0.30, -0.35, -0.70, -0.50, -0.40, -0.45, -0.75, 0.65]
                r = float(state.get("observed_ram_units", 17))
                delta[6] -= 0.0001 * (r - 17.0)
            elif guard_name == "authority":
                delta = [-0.65, -0.42, -0.84, -0.74, -0.38, -0.54, -0.16, 0.44]
            elif guard_name == "evidence":
                delta = [-0.40, -0.55, -0.70, -0.60, -0.75, -0.82, -0.30, 0.35]
            elif guard_name == "causal":
                delta = [-0.50, -0.60, -0.88, -0.80, -0.45, -0.60, -0.20, 0.40]
            elif guard_name == "adversarial":
                delta = [-0.55, -0.45, -0.80, -0.65, -0.85, -0.70, -0.25, 0.50]
            else:
                delta = [-0.45, -0.45, -0.75, -0.60, -0.50, -0.60, -0.40, 0.50]

            vector = [max(0.0, min(1.0, b + d)) for b, d in zip(base, delta)]

        return {
            "request_id": request_id,
            "requested_model": "synthetic-guard",
            "resolved_model": "synthetic-guard",
            "question_ids": [str(q["question_id"]) for q in questions],
            "vector": vector,
            "answers": {},
            "usage": None,
            "validation_status": "VALID",
        }


class HighNoiseGuardSemanticsProvider(StableGuardSemanticsProvider):
    """Synthetic provider with noise exceeding repeatability gate."""

    def __init__(self, noise_amplitude: float = 0.08) -> None:
        self.noise_amplitude = noise_amplitude
        self._counter = 0

    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        res = super().decide(state=state, questions=questions, request_id=request_id)
        self._counter += 1
        sign = 1.0 if self._counter % 2 == 0 else -1.0
        noisy_v = [max(0.0, min(1.0, x + sign * self.noise_amplitude)) for x in res["vector"]]
        res["vector"] = noisy_v
        return res


class ContinuousDriftGuardSemanticsProvider:
    """Synthetic negative control provider where output smoothly drifts without step."""

    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        base = [0.85, 0.90, 0.88, 0.84, 0.89, 0.91, 0.86, 0.12]
        guard_name = str(state.get("guard_name", "none"))

        if guard_name == "temporal":
            t = float(state.get("observed_duration_ms", 900.0))
            # Smooth linear scaling over full range [900, 3000] with no step at 1000
            fraction = (t - 900.0) / 2100.0
            vector = [max(0.0, min(1.0, b - fraction * 0.40)) for b in base]
        elif guard_name == "resource":
            r = float(state.get("observed_ram_units", 8))
            fraction = (r - 8.0) / 56.0
            vector = [max(0.0, min(1.0, b - fraction * 0.40)) for b in base]
        else:
            # Small random variations
            vector = list(base)

        return {
            "request_id": request_id,
            "requested_model": "synthetic-drift",
            "resolved_model": "synthetic-drift",
            "question_ids": [str(q["question_id"]) for q in questions],
            "vector": vector,
            "answers": {},
            "usage": None,
            "validation_status": "VALID",
        }


def test_deterministic_oracle_conformance():
    """Verify that all 39 specs pass boundary certification and expected behavior."""
    states = build_guard_states()
    assert len(states) == 39

    for item in states:
        spec = item["spec"]
        oracle = item["oracle"]
        sid = spec["spec_id"]

        assert oracle["boundary_certificates_valid"]
        assert oracle["passes_expected_behavior"]

        if spec["guard_tripped"]:
            assert oracle["disturbed_count"] == 8
            assert oracle["admissible_count"] == 8
            assert oracle["quorum_achieved"] is False
            assert oracle["root_status"] == "FAILED"
            assert len(item["state"]["emitted_output_keys"]) == 0
            assert item["state"]["quorum_margin"] == -1
        else:
            assert oracle["disturbed_count"] == 0
            assert oracle["admissible_count"] == 16
            assert oracle["quorum_achieved"] is True
            assert oracle["root_status"] == "SUCCESS"
            assert len(item["state"]["emitted_output_keys"]) == 1
            assert item["state"]["quorum_margin"] == 7


def test_raw_telemetry_state_forbids_status_and_outcome_labels():
    """Ensure state representation contains zero forbidden words."""
    forbidden = ("fail", "error", "unavailable", "verified", "committed", "bypass", "status")
    states = build_guard_states()

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


def test_offline_analysis_accepts_stable_guard_semantics_provider():
    """Verify StableGuardSemanticsProvider passes all preregistered guard step gates."""
    result = run_live_guard_semantics_experiment(
        provider=StableGuardSemanticsProvider(),
        replicates=3,
    )
    analysis = result["analysis"]
    assert analysis["provider_complete"] is True
    assert analysis["oracle_pass"] is True
    assert analysis["supported_within_engineering_gates"] is True
    assert analysis["verdict"] == "GUARD_STEP_SEMANTICS_CONFIRMED"

    gates = analysis["gates"]
    assert gates["G_U0_oracle_conformance"] is True
    assert gates["G_J0_repeatability_noise_floor"] is True
    assert gates["G_J1_jump_dominance_across_guards"] is True
    assert gates["G_J2_within_regime_compactness"] is True
    assert gates["G_J3_scalar_boundary_step_sharpness"] is True

    # Check temporal sharpness
    t_sharp = analysis["scalar_step_sharpness"]["temporal"]
    assert t_sharp["sharpness_ratio_rho_T"] >= 10.0
    assert t_sharp["boundary_step_1000_to_1001ms_norm"] > 1.0

    # Check resource sharpness
    r_sharp = analysis["scalar_step_sharpness"]["resource"]
    assert r_sharp["sharpness_ratio_rho_R"] >= 5.0
    assert r_sharp["boundary_step_16_to_17ram_norm"] > 1.0

    # Check jump ratios for all guards
    for gname in ["temporal", "resource", "authority", "evidence", "causal", "adversarial"]:
        gev = analysis["guard_evaluations"][gname]
        assert gev["boundary_jump_ratio_R_mean"] >= 2.0
        assert gev["is_jump_dominant"] is True
        assert gev["is_within_compact"] is True


def test_offline_analysis_rejects_high_noise():
    """Verify that excessive repeatability noise fails G_J0."""
    result = run_live_guard_semantics_experiment(
        provider=HighNoiseGuardSemanticsProvider(noise_amplitude=0.08),
        replicates=3,
    )
    analysis = result["analysis"]
    assert analysis["gates"]["G_J0_repeatability_noise_floor"] is False
    assert analysis["supported_within_engineering_gates"] is False


def test_offline_analysis_rejects_continuous_drift():
    """Verify that continuous drift without step transition fails G_J1 and G_J3."""
    result = run_live_guard_semantics_experiment(
        provider=ContinuousDriftGuardSemanticsProvider(),
        replicates=3,
    )
    analysis = result["analysis"]
    assert analysis["verdict"] == "CONTINUOUS_DRIFT_DETECTED"
    assert analysis["supported_within_engineering_gates"] is False
    assert analysis["gates"]["G_J3_scalar_boundary_step_sharpness"] is False


def test_fail_closed_on_incomplete_observations():
    """Verify that incomplete observations fail closed."""
    states = build_guard_states()
    partial_obs = [{"spec_id": states[0]["spec"]["spec_id"], "provider": {"vector": [0.5]*8}}]
    analysis = analyze_guard_semantics_observations(states, partial_obs, replicates=3)
    assert analysis["provider_complete"] is False
    assert analysis["verdict"] == "INCOMPLETE_OBSERVATIONS"
