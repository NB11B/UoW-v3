"""Offline qualification test harness for JEV Governed Lifecycle Grammar Campaign (Phase 6).

Validates:
1. Deterministic oracle conformance across all 21 lifecycle specifications.
2. Complete deterministic closed-loop orbit return:
   - For all 6 failure modes (A, Adv, E, C, T, R), lawful repair sequences return to pristine nominal state:
     state(x_recert) == state(x_nom).
3. Fail-closed safety invariant on premature recertification:
   - Attempting recertification without required remediation strictly fails closed:
     oracle["governed_status"] == "FAILED".
4. Strict raw telemetry discipline (zero forbidden outcome/error strings).
5. Offline synthetic positive control provider passing all gates:
   - G_L0, G_L1, G_L2, G_L3.
6. Offline synthetic negative control rejecting unclosed or drifting orbits:
   - G_L1 failure and LIFECYCLE_GRAMMAR_ANOMALY verdict.
7. Fail-closed behavior on incomplete observations.
8. Deterministic finite automaton (DFA) canonical macrostate transitions across Q.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import pytest

from qualification.jev_lifecycle_grammar_campaign import (
    DEFAULT_LIFECYCLE_SPECS,
    SIGMA_FAIL,
    SIGMA_FULL,
    SIGMA_LIFE,
    LifecycleSpec,
    analyze_lifecycle_observations,
    apply_lifecycle_op,
    build_lifecycle_specs,
    build_lifecycle_states,
    make_nominal_lifecycle_state,
    run_lifecycle_spec,
    run_live_lifecycle_experiment,
)


class StableLifecycleProvider:
    """Synthetic provider modeling lawful closed-loop cybernetic lifecycle orbits."""

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
        records = state.get("evidence_records_present", [])
        ram = int(state.get("observed_ram_units", 8))
        duration = float(state.get("observed_duration_ms", 450.0))
        conflicts = int(state.get("conflicting_attestation_count", 0))
        disturbed = int(state.get("disturbed_constituent_units", 0))

        if (
            disturbed == 0
            and len(records) == 6
            and len(edges) == 5
            and "verify" in bindings
            and duration == 450.0
            and conflicts == 0
            and ram == 8
        ):
            vec = list(base)
        else:
            d = [-0.45, -0.45, -0.75, -0.60, -0.50, -0.60, -0.40, 0.50]
            if "verify" not in bindings:
                d[0] -= 0.10
            if not state.get("evidence_digest_match", True):
                d[4] -= 0.10
            if len(edges) < 5:
                d[2] -= 0.10
            if duration > 1000.0:
                d[7] += 0.15
            if ram > 16:
                d[6] -= 0.15
            if conflicts > 0:
                d[3] -= 0.10
            vec = [max(0.0, min(1.0, b + val)) for b, val in zip(base, d)]

        return {
            "request_id": request_id,
            "requested_model": "synthetic-lifecycle",
            "resolved_model": "synthetic-lifecycle",
            "question_ids": [str(q["question_id"]) for q in questions],
            "vector": vec,
            "answers": {},
            "usage": None,
            "validation_status": "VALID",
        }


class UnclosedOrbitProvider(StableLifecycleProvider):
    """Synthetic provider violating closed-loop orbit return (recertification state drifts from nominal)."""

    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        res = super().decide(state=state, questions=questions, request_id=request_id)
        if "recert" in request_id:
            res["vector"] = [max(0.0, min(1.0, x - 0.40)) for x in res["vector"]]
        return res


def test_lifecycle_specs_count_and_oracle_conformance():
    """Verify that all 21 canonical lifecycle path specs pass boundary certification and expected behavior."""
    states = build_lifecycle_states()
    assert len(states) == 21

    for item in states:
        oracle = item["oracle"]
        sid = item["spec"]["spec_id"]

        assert oracle["boundary_certificates_valid"], f"Boundary certificate invalid for {sid}"
        assert oracle["passes_expected_behavior"], f"Expected behavior check failed for {sid}"

        if sid == "life_nom":
            assert oracle["target_macrostate"] == "NOMINAL"
            assert oracle["governed_status"] == "NOMINAL"
            assert oracle["disturbed_count"] == 0
            assert oracle["admissible_count"] == 16
            assert oracle["quorum_margin"] == 7
        elif sid.endswith("_recert"):
            assert oracle["target_macrostate"] == "RECERTIFIED"
            assert oracle["governed_status"] == "RECERTIFIED"
            assert oracle["disturbed_count"] == 0
            assert oracle["admissible_count"] == 16
            assert oracle["quorum_margin"] == 7
        elif sid == "life_premature_fail":
            assert oracle["target_macrostate"] == "FAILED"
            assert oracle["governed_status"] == "FAILED"
            assert oracle["disturbed_count"] == 8
            assert oracle["admissible_count"] == 8
            assert oracle["quorum_margin"] == -1
        elif sid.endswith("_contain"):
            assert oracle["target_macrostate"] == "CONTAINED"
            assert oracle["governed_status"] == "CONTAINED"
            assert oracle["disturbed_count"] == 8
            assert oracle["admissible_count"] == 8
            assert oracle["quorum_margin"] == -1
        elif sid.endswith("_recov"):
            assert oracle["target_macrostate"] == "RECOVERING"
            assert oracle["governed_status"] == "RECOVERING"
            assert oracle["disturbed_count"] == 8
            assert oracle["admissible_count"] == 8
            assert oracle["quorum_margin"] == -1
        elif sid.endswith("_fail"):
            assert oracle["target_macrostate"] == "FAILED"
            assert oracle["governed_status"] == "FAILED"
            assert oracle["disturbed_count"] == 8
            assert oracle["admissible_count"] == 8
            assert oracle["quorum_margin"] == -1


def test_deterministic_closed_loop_orbit_return():
    """Verify that lawful repair sequences return precisely to the baseline nominal state telemetry."""
    states = build_lifecycle_states()
    state_map = {item["spec"]["spec_id"]: item["state"] for item in states}
    nom_state = state_map["life_nom"]

    recert_ids = [
        "life_A_recert",
        "life_Adv_recert",
        "life_E_recert",
        "life_C_recert",
        "life_T_recert",
        "life_R_recert",
    ]

    for rid in recert_ids:
        r_state = state_map[rid]
        assert r_state == nom_state, f"Closed-loop orbit failed to match nominal for {rid}"


def test_premature_recertification_fails_closed():
    """Verify that attempting recertification without required remediation strictly fails closed."""
    premature_spec = LifecycleSpec(
        spec_id="test_premature",
        path_name="test_premature",
        target_macrostate="FAILED",
        sequence=("A", "Recertify"),
        disturbed_count=8,
        expected_status="FAILED",
        expected_margin=-1,
    )
    res = run_lifecycle_spec(premature_spec)
    oracle = res["oracle"]
    state = res["state"]

    assert oracle["governed_status"] == "FAILED"
    assert oracle["passes_expected_behavior"] is True
    assert oracle["quorum_margin"] == -1
    assert oracle["admissible_count"] == 8
    assert state["disturbed_constituent_units"] == 8
    assert len(state["emitted_output_keys"]) == 0


def test_raw_telemetry_state_forbids_status_and_outcome_labels():
    """Ensure raw telemetry sent to JEV contains zero forbidden words."""
    forbidden = ("fail", "error", "unavailable", "verified", "committed", "bypass", "status")
    states = build_lifecycle_states()

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


def test_stable_lifecycle_provider_passes_all_gates():
    """Verify that StableLifecycleProvider satisfies all four engineering and scientific gates."""
    result = run_live_lifecycle_experiment(
        provider=StableLifecycleProvider(),
        replicates=3,
    )
    analysis = result["analysis"]
    assert analysis["provider_complete"] is True
    assert analysis["oracle_pass"] is True
    assert analysis["supported_within_engineering_gates"] is True
    assert analysis["verdict"] == "GOVERNED_LIFECYCLE_GRAMMAR_CONFIRMED"
    assert (
        analysis["formal_mathematical_object"]
        == "finite_governed_lifecycle_automaton_with_closed_loop_orbits"
    )

    gates = analysis["gates"]
    assert gates["G_L0_oracle_conformance"] is True
    assert gates["G_L1_lifecycle_closed_loop_orbit_return"] is True
    assert gates["G_L2_premature_recertification_fails_closed"] is True
    assert gates["G_L3_repeatability_noise_floor"] is True

    # Check that defect ratios are well within threshold
    assert analysis["mean_recertification_defect_ratio_eta"] <= 1.50
    assert analysis["repeatability_noise_floor_sigma_rep"] <= 0.050


def test_unclosed_orbit_provider_fails_closed_loop_gate():
    """Verify that unclosed or drifting orbits fail gate G_L1."""
    result = run_live_lifecycle_experiment(
        provider=UnclosedOrbitProvider(),
        replicates=3,
    )
    analysis = result["analysis"]
    assert analysis["supported_within_engineering_gates"] is False
    assert analysis["verdict"] == "LIFECYCLE_GRAMMAR_ANOMALY"
    assert analysis["formal_mathematical_object"] == "unclosed_lifecycle_system"

    gates = analysis["gates"]
    assert gates["G_L0_oracle_conformance"] is True
    assert gates["G_L1_lifecycle_closed_loop_orbit_return"] is False
    assert gates["G_L2_premature_recertification_fails_closed"] is True


def test_fail_closed_on_incomplete_observations():
    """Verify that incomplete observations fail closed with INCOMPLETE_OBSERVATIONS verdict."""
    states = build_lifecycle_states()
    partial_obs = [{"spec_id": states[0]["spec"]["spec_id"], "provider": {"vector": [0.5] * 8}}]
    analysis = analyze_lifecycle_observations(states, partial_obs, replicates=3)
    assert analysis["provider_complete"] is False
    assert analysis["verdict"] == "INCOMPLETE_OBSERVATIONS"


def test_dfa_canonical_macrostate_transitions():
    """Verify DFA canonical macrostate transitions across Q = {NOMINAL, FAILED, CONTAINED, RECOVERING, RECERTIFIED}."""
    # 1. Authority path: NOMINAL -> FAILED -> RECOVERING -> RECERTIFIED
    s0 = make_nominal_lifecycle_state()
    assert s0["governed_status"] == "NOMINAL"

    s1 = apply_lifecycle_op(s0, "A")
    assert s1["governed_status"] == "FAILED"

    s2 = apply_lifecycle_op(s1, "Rebind")
    assert s2["governed_status"] == "RECOVERING"

    s3 = apply_lifecycle_op(s2, "Recertify")
    assert s3["governed_status"] == "RECERTIFIED"

    # 2. Adversarial path: NOMINAL -> FAILED -> CONTAINED -> RECOVERING -> RECERTIFIED
    s_adv1 = apply_lifecycle_op(s0, "Adv")
    assert s_adv1["governed_status"] == "FAILED"

    s_adv2 = apply_lifecycle_op(s_adv1, "Quarantine")
    assert s_adv2["governed_status"] == "CONTAINED"

    s_adv3 = apply_lifecycle_op(s_adv2, "Release")
    assert s_adv3["governed_status"] == "RECOVERING"

    s_adv4 = apply_lifecycle_op(s_adv3, "Recertify")
    assert s_adv4["governed_status"] == "RECERTIFIED"

    # 3. Premature recertification: NOMINAL -> FAILED --Recertify--> FAILED
    s_prem = apply_lifecycle_op(s1, "Recertify")
    assert s_prem["governed_status"] == "FAILED"
