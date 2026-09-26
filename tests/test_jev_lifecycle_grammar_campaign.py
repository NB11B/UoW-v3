"""Offline qualification test harness for JEV Governed Lifecycle Grammar Campaign (Phase 6).

Validates:
1. Deterministic oracle conformance across all 21 lifecycle specifications.
2. Complete deterministic closed-loop orbit return:
   - For all 6 failure modes (A, Adv, E, C, T, R), lawful repair sequences return to pristine nominal state:
     state(x_recert) == state(x_nom).
3. Fail-closed safety invariant on premature recertification:
   - Attempting recertification without required remediation strictly fails closed:
     oracle["governed_status"] == "FAILED".
4. Full reachable state space closure under Sigma_full (|Sigma_full| = 14):
   - |X_life| = cl_{Sigma_full}({x_0}) contains exactly 2,317 states (max depth 10).
5. Exact Nerode DFA minimization:
   - Minimizes to 97 behavioral classes under binary admission observation.
   - Minimizes to 222 behavioral classes under fine-grained regime observation.
   - Quotients to 4 coarse operational macrostates (NOMINAL/RECERTIFIED, FAILED, CONTAINED, RECOVERING).
6. Strict raw telemetry discipline (zero forbidden outcome/error strings).
7. Provenance integrity & synthetic provider discipline:
   - Synthetic/replay providers MUST return provider_kind='synthetic_calibrated_replay'.
   - Resolved model MUST be 'calibrated-jev-replay-v1', never masquerading as live JEV.
   - Token usage MUST be None (never fabricated).
   - Synthetic providers CANNOT satisfy independent live-JEV confirmation gates.
8. Live artifact verification:
   - Asserts live_api provenance, jev-1.13.0 model, and genuine live evidence when credentials succeed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

from qualification.jev_lifecycle_grammar_campaign import (
    DEFAULT_LIFECYCLE_SPECS,
    SIGMA_FAIL,
    SIGMA_FULL,
    SIGMA_LIFE,
    CalibratedEmpiricalJevProvider,
    LifecycleSpec,
    analyze_lifecycle_observations,
    apply_lifecycle_op,
    build_lifecycle_specs,
    build_lifecycle_states,
    compute_lifecycle_reachable_closure,
    make_nominal_lifecycle_state,
    minimize_lifecycle_automaton,
    run_lifecycle_spec,
    run_live_lifecycle_experiment,
)


class StableLifecycleProvider:
    """Synthetic provider modeling lawful closed-loop cybernetic lifecycle orbits."""

    def __init__(self) -> None:
        self.requested_model = "calibrated-jev-replay"
        self.resolved_model = "calibrated-jev-replay-v1"
        self.provider_kind = "synthetic_calibrated_replay"
        self.source_dataset = "qualification/artifacts/jev_semigroup_structure_results.json"

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
            "requested_model": self.requested_model,
            "resolved_model": self.resolved_model,
            "provider_kind": self.provider_kind,
            "source_dataset": self.source_dataset,
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


def test_full_lifecycle_reachable_closure_and_minimization():
    """Verify reachable state space closure X_life (|X_life| = 2,317) and exact Nerode minimization."""
    states, visited, max_depth = compute_lifecycle_reachable_closure()
    assert len(states) == 2317
    assert max_depth == 10

    analysis = minimize_lifecycle_automaton(states, visited)
    assert analysis["reachable_closure_states_count"] == 2317
    assert analysis["coarse_governance_macrostates_count"] == 4
    assert analysis["nerode_admission_classes_count"] == 97
    assert analysis["nerode_regime_classes_count"] == 222

    dist = analysis["regime_distribution"]
    assert dist["NOMINAL"] == 1
    assert dist["RECERTIFIED"] == 1
    assert dist["FAILED"] == 1016
    assert dist["CONTAINED"] == 344
    assert dist["RECOVERING"] == 955


def test_provenance_and_synthetic_provider_gate_discipline():
    """Verify that synthetic replay providers have strict provenance tags and cannot satisfy live gates."""
    replay_prov = CalibratedEmpiricalJevProvider(seed=101)
    res = replay_prov.decide(
        state=make_nominal_lifecycle_state(),
        questions=[{"question_id": "effective_authority", "instructions": "test"}],
        request_id="prov-check",
    )

    assert res["requested_model"] == "calibrated-jev-replay"
    assert res["resolved_model"] == "calibrated-jev-replay-v1"
    assert res["provider_kind"] == "synthetic_calibrated_replay"
    assert res["source_dataset"] == "qualification/artifacts/jev_semigroup_structure_results.json"
    assert res["usage"] is None  # Never fabricate token usage!

    # Execute experiment with synthetic provider
    result = run_live_lifecycle_experiment(provider=replay_prov, replicates=3)
    analysis = result["analysis"]

    assert analysis["independent_live_jev_evidence"] is False
    assert analysis["live_jev_validation_status"] == "PENDING_LIVE_CREDENTIALS"
    assert analysis["deterministic_lifecycle_confirmed"] is True
    assert analysis["verdict"] == "DETERMINISTIC_LIFECYCLE_GRAMMAR_CONFIRMED_LIVE_JEV_PENDING"

    gates = analysis["gates"]
    assert gates["G_L0_oracle_conformance"] is True
    assert gates["G_L1_deterministic_closed_loop_recovery"] is True
    assert gates["G_L2_premature_recertification_fails_closed"] is True
    assert gates["G_L3_replay_trajectory_consistency"] is True
    # Synthetic providers CANNOT satisfy the live confirmation gate:
    assert gates["G_L_LIVE_independent_observer_confirmation"] is False


def test_unclosed_orbit_provider_fails_replay_gate():
    """Verify that unclosed or drifting orbits fail gate G_L3."""
    result = run_live_lifecycle_experiment(
        provider=UnclosedOrbitProvider(),
        replicates=3,
    )
    analysis = result["analysis"]
    assert analysis["verdict"] == "REPLAY_OBSERVER_ANOMALY"

    gates = analysis["gates"]
    assert gates["G_L0_oracle_conformance"] is True
    assert gates["G_L1_deterministic_closed_loop_recovery"] is True
    assert gates["G_L2_premature_recertification_fails_closed"] is True
    assert gates["G_L3_replay_trajectory_consistency"] is False


def test_live_artifact_conformance_if_present():
    """Verify that live artifacts produced by TypeSafeJevProvider pass all gates including live confirmation."""
    artifact_path = Path("qualification/artifacts/jev_lifecycle_grammar_results.json")
    if not artifact_path.exists():
        pytest.skip("Artifact not found")

    data = json.loads(artifact_path.read_text(encoding="utf-8"))
    analysis = data["analysis"]

    assert analysis["oracle_pass"] is True
    assert analysis["deterministic_lifecycle_confirmed"] is True

    # If the artifact was generated live, verify live provider properties:
    if analysis.get("independent_live_jev_evidence"):
        assert analysis["provider_kinds"] == ["live_api"]
        assert analysis["resolved_models"] == ["jev-1.13.0"]
        assert analysis["live_jev_validation_status"] == "CONFIRMED_LIVE_EVIDENCE"
        assert analysis["verdict"] == "GOVERNED_LIFECYCLE_GRAMMAR_CONFIRMED"
        assert analysis["gates"]["G_L_LIVE_independent_observer_confirmation"] is True
        assert analysis["repeatability_noise_floor_sigma_rep"] <= 0.050
        assert analysis["mean_recertification_defect_ratio_eta"] <= 1.50
        assert analysis["premature_recertification_prevented"] is True
