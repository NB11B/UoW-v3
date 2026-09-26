"""Offline qualification test harness for JEV Transformation Semigroup Structure Campaign (Phase 4).

Validates:
1. Deterministic oracle conformance across all 60 specs.
2. Phase 4A: Identity transformation duality:
   - State level: state(I o F_i) == state(F_i o I) == state(F_i)
   - Provenance level: trace(I o F_i) != trace(F_i) and trace(F_i o I) != trace(F_i)
3. Phase 4B & 4C: Absorbing state vs. absorbing class:
   - Full 6x6 transition matrix F_j(x_i) exhibits exactly 6 microstate fixed points (only diagonal F_i(x_i) == x_i).
   - All 36 transitions belong to the absorbing governance equivalence class [x_bot] (failed, quorum margin = -1).
4. Phase 4D: Universal zero transformation Z:
   - Two-sided absorption: state(Z o F_i) == state(F_i o Z) == state(Z).
5. Phase 4E: Product idempotence (band test):
   - All tested pairs P_{ij}^2 == P_{ij} and triples P_{ijk}^2 == P_{ijk} at the deterministic state level.
6. Strict raw telemetry representation (zero forbidden outcome/error strings).
7. Offline synthetic positive control provider passing all gates:
   - G_U0, G_U1, G_U2, G_U3, G_U4, G_J0, G_J1, G_J2, G_J3.
8. Offline synthetic negative control rejecting non-band / non-idempotent product dynamics.
9. Fail-closed behavior on incomplete observations.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import pytest

from qualification.jev_semigroup_structure_campaign import (
    DEFAULT_STRUCTURE_SPECS,
    StructureSpec,
    analyze_structure_observations,
    build_structure_specs,
    build_structure_states,
    run_live_structure_experiment,
)


class StableStructureProvider:
    """Synthetic provider modeling a transformation semigroup with a zero element and band structure."""

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
            "requested_model": "synthetic-structure",
            "resolved_model": "synthetic-structure",
            "question_ids": [str(q["question_id"]) for q in questions],
            "vector": vector,
            "answers": {},
            "usage": None,
            "validation_status": "VALID",
        }


class NonBandProvider(StableStructureProvider):
    """Synthetic provider violating product idempotence (squared products diverge from single products)."""

    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        res = super().decide(state=state, questions=questions, request_id=request_id)
        if "prod_sq" in request_id:
            res["vector"] = [max(0.0, min(1.0, x - 0.25)) for x in res["vector"]]
        return res


def test_deterministic_oracle_conformance():
    """Verify that all 60 specs pass boundary certification and expected behavior."""
    states = build_structure_states()
    assert len(states) == 60

    for item in states:
        spec = item["spec"]
        oracle = item["oracle"]
        sid = spec["spec_id"]

        assert oracle["boundary_certificates_valid"]
        assert oracle["passes_expected_behavior"]

        if sid == "base_nominal":
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


def test_phase_4a_identity_duality():
    """Verify identity preserves deterministic state while recording distinct provenance traces."""
    states = build_structure_states()
    state_by_spec = {item["spec"]["spec_id"]: item["state"] for item in states}
    oracle_by_spec = {item["spec"]["spec_id"]: item["oracle"] for item in states}

    for m in ("authority", "evidence", "temporal"):
        tag = m[:3]
        s_pure = state_by_spec[f"pure_{m[0].upper()}"]
        s_left = state_by_spec[f"idem_I_{tag}_left"]
        s_right = state_by_spec[f"idem_I_{tag}_right"]

        o_pure = oracle_by_spec[f"pure_{m[0].upper()}"]
        o_left = oracle_by_spec[f"idem_I_{tag}_left"]
        o_right = oracle_by_spec[f"idem_I_{tag}_right"]

        # Deterministic state identity
        assert s_left == s_pure, f"Left identity failed for {m}"
        assert s_right == s_pure, f"Right identity failed for {m}"

        # Provenance distinctness
        assert o_left["trace_info"] != o_pure["trace_info"]
        assert o_right["trace_info"] != o_pure["trace_info"]
        assert o_left["trace_info"]["grouping"] == "left"
        assert o_right["trace_info"]["grouping"] == "right"


def test_phase_4b_and_4c_absorbing_class():
    """Verify 6x6 transition matrix has only 6 microstate fixed points and all 36 belong to [x_bot]."""
    states = build_structure_states()
    state_by_spec = {item["spec"]["spec_id"]: item["state"] for item in states}
    oracle_by_spec = {item["spec"]["spec_id"]: item["oracle"] for item in states}

    mechs = ("authority", "evidence", "causal", "temporal", "resource", "adversarial")
    tags = {"authority": "A", "evidence": "E", "causal": "C", "temporal": "T", "resource": "R", "adversarial": "Adv"}

    microstate_fps = 0
    for mi in mechs:
        ti = tags[mi]
        s_i = state_by_spec[f"pure_{ti}"]
        for mj in mechs:
            tj = tags[mj]
            if mi == mj:
                microstate_fps += 1
            else:
                s_ij = state_by_spec[f"mat_{tj}_{ti}"]
                o_ij = oracle_by_spec[f"mat_{tj}_{ti}"]
                if s_ij == s_i:
                    microstate_fps += 1
                assert o_ij["governance_class"]["in_absorbing_class"] is True
                assert o_ij["governance_class"]["is_governed_failed"] is True
                assert o_ij["governance_class"]["quorum_margin"] == -1

    assert microstate_fps == 6, f"Expected exactly 6 diagonal microstate fixed points, got {microstate_fps}"


def test_phase_4d_universal_zero():
    """Verify universal zero transformation absorbs both from left and right."""
    states = build_structure_states()
    state_by_spec = {item["spec"]["spec_id"]: item["state"] for item in states}

    s_Z = state_by_spec["zero_Z"]
    for m in ("authority", "evidence", "temporal"):
        tag = m[:3]
        s_left = state_by_spec[f"zero_Z_{tag}_left"]
        s_right = state_by_spec[f"zero_Z_{tag}_right"]

        assert s_left == s_Z, f"Z o {m} did not equal Z"
        assert s_right == s_Z, f"{m} o Z did not equal Z"


def test_phase_4e_product_idempotence():
    """Verify product idempotence P^2 == P across pairs and triples."""
    states = build_structure_states()
    state_by_spec = {item["spec"]["spec_id"]: item["state"] for item in states}
    tags = {"authority": "A", "evidence": "E", "causal": "C", "temporal": "T", "resource": "R", "adversarial": "Adv"}

    pairs = [
        ("authority", "evidence"),
        ("evidence", "authority"),
        ("authority", "causal"),
        ("causal", "authority"),
        ("evidence", "resource"),
        ("resource", "evidence"),
    ]
    for m1, m2 in pairs:
        t1, t2 = tags[m1], tags[m2]
        s_p = state_by_spec[f"mat_{t1}_{t2}"]
        s_p_sq = state_by_spec[f"prod_sq_{t1}{t2}"]
        assert s_p == s_p_sq, f"Pair product idempotence failed for ({t1} o {t2})"

    triples = [
        ("authority", "evidence", "temporal"),
        ("evidence", "resource", "adversarial"),
    ]
    for m1, m2, m3 in triples:
        t1, t2, t3 = tags[m1], tags[m2], tags[m3]
        s_p = state_by_spec[f"prod_{t1}{t2}{t3}"]
        s_p_sq = state_by_spec[f"prod_sq_{t1}{t2}{t3}"]
        assert s_p == s_p_sq, f"Triple product idempotence failed for ({t1} o {t2} o {t3})"


def test_raw_telemetry_state_forbids_status_and_outcome_labels():
    """Ensure state representation contains zero forbidden words."""
    forbidden = ("fail", "error", "unavailable", "verified", "committed", "bypass", "status")
    states = build_structure_states()

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


def test_offline_analysis_accepts_stable_structure_provider():
    """Verify StableStructureProvider passes all preregistered semigroup structure gates."""
    result = run_live_structure_experiment(
        provider=StableStructureProvider(),
        replicates=3,
    )
    analysis = result["analysis"]
    assert analysis["provider_complete"] is True
    assert analysis["oracle_pass"] is True
    assert analysis["supported_within_engineering_gates"] is True
    assert analysis["verdict"] == "SEMIGROUP_STRUCTURE_CHARACTERIZED"
    assert (
        analysis["final_mathematical_object"]
        == "noncommutative_band_with_zero_and_history_sensitive_provenance"
    )

    gates = analysis["gates"]
    assert gates["G_U0_oracle_conformance"] is True
    assert gates["G_U1_identity_duality_state_vs_trace"] is True
    assert gates["G_U2_governance_class_absorption"] is True
    assert gates["G_U3_quotient_zero_transformation"] is True
    assert gates["G_U4_product_idempotence_band"] is True
    assert gates["G_J0_repeatability_noise_floor"] is True
    assert gates["G_J1_identity_observational_defect"] is True
    assert gates["G_J2_zero_observational_defect"] is True
    assert gates["G_J3_band_observational_defect"] is True


def test_offline_analysis_rejects_non_band_provider():
    """Verify that non-band dynamics fail G_J3."""
    result = run_live_structure_experiment(
        provider=NonBandProvider(),
        replicates=3,
    )
    analysis = result["analysis"]
    assert analysis["verdict"] == "STRUCTURAL_ANOMALY_DETECTED"
    assert analysis["supported_within_engineering_gates"] is False
    assert analysis["gates"]["G_J3_band_observational_defect"] is False


def test_fail_closed_on_incomplete_observations():
    """Verify that incomplete observations fail closed."""
    states = build_structure_states()
    partial_obs = [{"spec_id": states[0]["spec"]["spec_id"], "provider": {"vector": [0.5] * 8}}]
    analysis = analyze_structure_observations(states, partial_obs, replicates=3)
    assert analysis["provider_complete"] is False
    assert analysis["verdict"] == "INCOMPLETE_OBSERVATIONS"
