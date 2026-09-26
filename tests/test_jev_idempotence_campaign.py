"""Offline qualification test harness for JEV Operator Idempotence Campaign.

Validates:
1. Deterministic oracle conformance across all 25 specs.
2. Deterministic state equivalence state(F_i^2(x)) == state(F_i(x)).
3. Strict raw telemetry representation (zero forbidden outcome/error strings).
4. Offline synthetic positive control provider passing all gates (G_U0, G_U1, G_J0..G_J3).
5. Offline synthetic negative control rejecting non-idempotent dynamics (G_J1).
6. Fail-closed behavior on incomplete observations.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import pytest

from qualification.jev_idempotence_campaign import (
    DEFAULT_IDEMPOTENCE_SPECS,
    IdempotenceSpec,
    analyze_idempotence_observations,
    build_idempotence_states,
    run_live_idempotence_experiment,
)


class StableIdempotenceProvider:
    """Synthetic provider modeling exact idempotent state operators."""

    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        base = [0.85, 0.90, 0.88, 0.84, 0.89, 0.91, 0.86, 0.12]
        bindings = state.get("actor_role_bindings", {})
        edges = state.get("declared_causal_edges", [])

        if not state.get("temporal_admissibility", True) or float(state.get("observed_duration_ms", 0)) > 1000.0:
            mech = "temporal"
        elif not state.get("resource_envelope_admissible", True) or int(state.get("observed_ram_units", 0)) > 16:
            mech = "resource"
        elif state.get("quarantine_active", False) or int(state.get("conflicting_attestation_count", 0)) > 0:
            mech = "adversarial"
        elif not state.get("evidence_digest_match", True):
            mech = "evidence"
        elif "verify" not in bindings:
            mech = "authority"
        elif len(edges) < 5:
            mech = "causal"
        else:
            mech = "none"

        if mech == "none":
            vector = list(base)
        else:
            delta_map = {
                "authority": [-0.65, -0.42, -0.84, -0.74, -0.38, -0.54, -0.16, 0.44],
                "evidence": [-0.40, -0.55, -0.70, -0.60, -0.75, -0.82, -0.30, 0.35],
                "causal": [-0.50, -0.60, -0.88, -0.80, -0.45, -0.60, -0.20, 0.40],
                "temporal": [-0.25, -0.30, -0.65, -0.40, -0.35, -0.40, -0.70, 0.75],
                "resource": [-0.30, -0.35, -0.70, -0.50, -0.40, -0.45, -0.75, 0.65],
                "adversarial": [-0.55, -0.45, -0.80, -0.65, -0.85, -0.70, -0.25, 0.50],
            }
            d = list(delta_map[mech])
            if "accum" in request_id:
                # Microscopic bounded shift from compounding (< 0.03 norm)
                d[0] += 0.01
                d[7] += 0.01

            vector = [max(0.0, min(1.0, b + val)) for b, val in zip(base, d)]

        return {
            "request_id": request_id,
            "requested_model": "synthetic-idempotent",
            "resolved_model": "synthetic-idempotent",
            "question_ids": [str(q["question_id"]) for q in questions],
            "vector": vector,
            "answers": {},
            "usage": None,
            "validation_status": "VALID",
        }


class NonIdempotentProvider(StableIdempotenceProvider):
    """Synthetic provider violating idempotence: F_i^2 deviates significantly from F_i."""

    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        res = super().decide(state=state, questions=questions, request_id=request_id)
        if "_2" in request_id:
            # Significant deviation of 0.20 on F_i^2
            res["vector"] = [max(0.0, min(1.0, x - 0.20)) for x in res["vector"]]
        return res


def test_deterministic_oracle_conformance():
    """Verify that all 25 specs pass boundary certification and expected behavior."""
    states = build_idempotence_states()
    assert len(states) == 25

    for item in states:
        spec = item["spec"]
        oracle = item["oracle"]
        sid = spec["spec_id"]

        assert oracle["boundary_certificates_valid"]
        assert oracle["passes_expected_behavior"]

        if sid == "idem_base":
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


def test_deterministic_state_idempotence():
    """Verify state(F_i^2(x)) == state(F_i(x)) == state(F_i^3(x)) in core state representation."""
    states = build_idempotence_states()
    state_by_spec = {item["spec"]["spec_id"]: item["state"] for item in states}

    mechanisms = ("authority", "evidence", "causal", "temporal", "resource", "adversarial")
    mech_tags = {
        "authority": "A",
        "evidence": "E",
        "causal": "C",
        "temporal": "T",
        "resource": "R",
        "adversarial": "Adv",
    }

    for m in mechanisms:
        tag = mech_tags[m]
        s1 = state_by_spec[f"idem_F_{tag}_1"]
        s2 = state_by_spec[f"idem_F_{tag}_2"]
        s3 = state_by_spec[f"idem_F_{tag}_3"]

        assert s1 == s2, f"State divergence in F_{m}^2 vs F_{m}"
        assert s1 == s3, f"State divergence in F_{m}^3 vs F_{m}"


def test_raw_telemetry_state_forbids_status_and_outcome_labels():
    """Ensure state representation contains zero forbidden words."""
    forbidden = ("fail", "error", "unavailable", "verified", "committed", "bypass", "status")
    states = build_idempotence_states()

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


def test_offline_analysis_accepts_stable_idempotence_provider():
    """Verify StableIdempotenceProvider passes all preregistered idempotence gates."""
    result = run_live_idempotence_experiment(
        provider=StableIdempotenceProvider(),
        replicates=3,
    )
    analysis = result["analysis"]
    assert analysis["provider_complete"] is True
    assert analysis["oracle_pass"] is True
    assert analysis["deterministic_idempotence_passes"] is True
    assert analysis["supported_within_engineering_gates"] is True
    assert analysis["verdict"] == "OPERATOR_IDEMPOTENCE_CONFIRMED"

    gates = analysis["gates"]
    assert gates["G_U0_oracle_conformance"] is True
    assert gates["G_U1_deterministic_state_idempotence"] is True
    assert gates["G_J0_repeatability_noise_floor"] is True
    assert gates["G_J1_observational_idempotence_order2"] is True
    assert gates["G_J2_observational_idempotence_order3"] is True
    assert gates["G_J3_compounded_physical_invariance"] is True

    # Check defect ratios
    for m in ["authority", "evidence", "causal", "temporal", "resource", "adversarial"]:
        op = analysis["operator_evaluations"][m]
        assert op["order2_defect_ratio_eta"] <= 1.50
        assert op["order3_defect_ratio_eta"] <= 1.50
        assert op["is_exact_idempotent_order2"] is True
        assert op["is_exact_idempotent_order3"] is True
        assert op["is_accumulative_stable"] is True


def test_offline_analysis_rejects_non_idempotent_provider():
    """Verify that non-idempotent dynamics fail G_J1."""
    result = run_live_idempotence_experiment(
        provider=NonIdempotentProvider(),
        replicates=3,
    )
    analysis = result["analysis"]
    assert analysis["verdict"] == "NON_IDEMPOTENT_DYNAMICS_DETECTED"
    assert analysis["supported_within_engineering_gates"] is False
    assert analysis["gates"]["G_J1_observational_idempotence_order2"] is False


def test_fail_closed_on_incomplete_observations():
    """Verify that incomplete observations fail closed."""
    states = build_idempotence_states()
    partial_obs = [{"spec_id": states[0]["spec"]["spec_id"], "provider": {"vector": [0.5]*8}}]
    analysis = analyze_idempotence_observations(states, partial_obs, replicates=3)
    assert analysis["provider_complete"] is False
    assert analysis["verdict"] == "INCOMPLETE_OBSERVATIONS"
