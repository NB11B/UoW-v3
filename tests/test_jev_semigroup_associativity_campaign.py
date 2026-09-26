"""Offline qualification test harness for JEV Transformation Semigroup Associativity Campaign.

Validates:
1. Deterministic oracle conformance across all 15 specs.
2. Exact 7-dimensional comparative evaluation of x_L vs x_R:
   - Final deterministic state equality: state(x_L) == state(x_R)
   - Active reachable graph equality: G_L == G_R
   - Guard activation vector equality: g_L == g_R
   - Emitted evidence equality: E_L == E_R
   - Certificate validity equality: cert(x_L) == cert(x_R) == True
   - Execution trace / provenance tree distinctness: trace_L != trace_R
3. Classification of all 4 triples into:
   "state_associative_but_history_sensitive"
4. Strict raw telemetry representation (zero forbidden outcome/error strings).
5. Offline synthetic positive control provider passing all gates (G_U0, G_U1, G_U2, G_J0, G_J1).
6. Offline synthetic negative control rejecting non-associative dynamics (G_J1).
7. Fail-closed behavior on incomplete observations.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import pytest

from qualification.jev_semigroup_associativity_campaign import (
    DEFAULT_ASSOCIATIVITY_SPECS,
    AssociativitySpec,
    analyze_associativity_observations,
    build_associativity_states,
    run_live_associativity_experiment,
)


class StableAssociativityProvider:
    """Synthetic provider modeling an associative, history-sensitive transformation semigroup."""

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

        if len(records) == 6 and len(edges) == 5 and "verify" in bindings and duration == 450.0 and conflicts == 0 and ram == 8:
            # Baseline nominal
            vector = list(base)
        else:
            # Common failure macrostate vector + physical telemetry adjustments
            d = [-0.45, -0.45, -0.75, -0.60, -0.50, -0.60, -0.40, 0.50]

            if "verify" not in bindings:
                d[0] -= 0.15
            if not state.get("evidence_digest_match", True):
                d[4] -= 0.15
            if len(edges) < 5:
                d[2] -= 0.12
            if duration > 1000.0:
                d[7] += 0.20
            if ram > 16:
                d[6] -= 0.20
            if conflicts > 0:
                d[3] -= 0.15

            vector = [max(0.0, min(1.0, b + val)) for b, val in zip(base, d)]

        return {
            "request_id": request_id,
            "requested_model": "synthetic-associative",
            "resolved_model": "synthetic-associative",
            "question_ids": [str(q["question_id"]) for q in questions],
            "vector": vector,
            "answers": {},
            "usage": None,
            "validation_status": "VALID",
        }


class NonAssociativeProvider(StableAssociativityProvider):
    """Synthetic provider violating observational associativity: Left grouping diverges from Right grouping."""

    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        res = super().decide(state=state, questions=questions, request_id=request_id)
        if "comp_L" in request_id:
            res["vector"] = [max(0.0, min(1.0, x - 0.18)) for x in res["vector"]]
        return res


def test_deterministic_oracle_conformance():
    """Verify that all 15 specs pass boundary certification and expected behavior."""
    states = build_associativity_states()
    assert len(states) == 15

    for item in states:
        spec = item["spec"]
        oracle = item["oracle"]
        sid = spec["spec_id"]

        assert oracle["boundary_certificates_valid"]
        assert oracle["passes_expected_behavior"]

        if sid == "assoc_base":
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


def test_deterministic_runtime_7_dimension_associativity():
    """Verify exact 7-dimensional comparative evaluation of x_L vs x_R across all 4 triples."""
    states = build_associativity_states()
    state_by_spec = {item["spec"]["spec_id"]: item["state"] for item in states}
    oracle_by_spec = {item["spec"]["spec_id"]: item["oracle"] for item in states}

    triples = ["A_E_T", "E_R_Adv", "C_T_R", "A_C_Adv"]

    for tid in triples:
        s_L = state_by_spec[f"comp_L_{tid}"]
        s_R = state_by_spec[f"comp_R_{tid}"]
        o_L = oracle_by_spec[f"comp_L_{tid}"]
        o_R = oracle_by_spec[f"comp_R_{tid}"]

        # 1. Final deterministic state equality
        assert s_L == s_R, f"Final state inequality on {tid}"

        # 2. Active reachable graph equality
        assert o_L["active_graph"] == o_R["active_graph"], f"Graph inequality on {tid}"

        # 3. Guard activation vector equality
        assert o_L["guard_vector"] == o_R["guard_vector"], f"Guard vector inequality on {tid}"

        # 4. Emitted evidence equality
        assert o_L["emitted_evidence"] == o_R["emitted_evidence"], f"Evidence inequality on {tid}"

        # 5. Boundary certificate validity
        assert o_L["boundary_certificates_valid"] is True
        assert o_R["boundary_certificates_valid"] is True

        # 6. Execution trace / provenance tree distinctness (history sensitivity)
        assert o_L["trace_tree"] != o_R["trace_tree"], f"Trace collapsed on {tid}"
        assert o_L["trace_tree"]["grouping"] == "left"
        assert o_R["trace_tree"]["grouping"] == "right"


def test_raw_telemetry_state_forbids_status_and_outcome_labels():
    """Ensure state representation contains zero forbidden words."""
    forbidden = ("fail", "error", "unavailable", "verified", "committed", "bypass", "status")
    states = build_associativity_states()

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


def test_offline_analysis_accepts_stable_associativity_provider():
    """Verify StableAssociativityProvider passes all preregistered semigroup gates."""
    result = run_live_associativity_experiment(
        provider=StableAssociativityProvider(),
        replicates=3,
    )
    analysis = result["analysis"]
    assert analysis["provider_complete"] is True
    assert analysis["oracle_pass"] is True
    assert analysis["supported_within_engineering_gates"] is True
    assert analysis["verdict"] == "STATE_ASSOCIATIVE_TRANSFORMATION_SEMIGROUP_CONFIRMED"

    gates = analysis["gates"]
    assert gates["G_U0_oracle_conformance"] is True
    assert gates["G_U1_deterministic_state_associativity"] is True
    assert gates["G_U2_trace_provenance_hierarchy_distinct"] is True
    assert gates["G_J0_repeatability_noise_floor"] is True
    assert gates["G_J1_observational_associativity"] is True

    # Check that all triples are classified into Regime 2
    for tid in ["A_E_T", "E_R_Adv", "C_T_R", "A_C_Adv"]:
        det = analysis["deterministic_comparison"][tid]
        assert det["classified_regime"] == "state_associative_but_history_sensitive"
        assert det["final_deterministic_state_equal"] is True
        assert det["execution_trace_distinct"] is True

        obs = analysis["observational_results"][tid]
        assert obs["is_observationally_associative"] is True
        assert obs["associativity_defect_ratio_eta"] <= 1.50


def test_offline_analysis_rejects_non_associative_provider():
    """Verify that non-associative dynamics fail G_J1."""
    result = run_live_associativity_experiment(
        provider=NonAssociativeProvider(),
        replicates=3,
    )
    analysis = result["analysis"]
    assert analysis["verdict"] == "NON_ASSOCIATIVE_SYSTEM_DETECTED"
    assert analysis["supported_within_engineering_gates"] is False
    assert analysis["gates"]["G_J1_observational_associativity"] is False


def test_fail_closed_on_incomplete_observations():
    """Verify that incomplete observations fail closed."""
    states = build_associativity_states()
    partial_obs = [{"spec_id": states[0]["spec"]["spec_id"], "provider": {"vector": [0.5]*8}}]
    analysis = analyze_associativity_observations(states, partial_obs, replicates=3)
    assert analysis["provider_complete"] is False
    assert analysis["verdict"] == "INCOMPLETE_OBSERVATIONS"
