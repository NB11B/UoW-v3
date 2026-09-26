r"""Offline and online qualification test harness for JEV Rewriting Grammar Campaign (Phase 7).

Validates:
1. Generator Irreducibility (Gate G-R0):
   - All 14 generators in Sigma_full are algebraically irreducible in Sigma \ {g}.
   - The minimal generating set |G_min| = 14 is strictly minimal.
2. Strict Quotient Congruence (Gate G-R1):
   - All 14 operators are strictly well-defined deterministic endofunctions over
     both Q_222 (regime-predictive) and Q_97 (admission-predictive).
   - 0 violations across all 32,438 transitions (2,317 states x 14 operators).
3. Commutation Subspaces:
   - All 15 physical failure pairs commute on Q_222 (15/15).
   - All 20 physical/quarantine/release remediation pairs commute on Q_222 (20/20).
4. Local Confluence (Church-Rosser) & Strong Normalization (Gates G-R2 & G-R3):
   - Critical pairs across commuting and reducing operators join to identical normal forms.
   - Zero divergences in term rewriting normal form N(w).
5. Observer Equivalence Invariant (Gate G-R4):
   - Test words w and their reduced normal forms N(w) yield identical deterministic
     state variables and observer defect within noise: ||J(w) - J(N(w))|| <= 1.50 * sigma_rep.
6. Provenance Integrity & Synthetic Provider Discipline:
   - Synthetic provider must return provider_kind='synthetic_calibrated_replay'.
   - Resolved model must be 'calibrated-jev-replay-v1', never live JEV.
   - Token usage must be None.
7. Live Artifact Audit (Gate G-R-LIVE):
   - When run live, asserts live_api provenance, jev-1.13.0 model, and genuine token metrics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from qualification.jev_lifecycle_grammar_campaign import (
    SIGMA_FAIL,
    SIGMA_FULL,
    SIGMA_LIFE,
    CalibratedEmpiricalJevProvider,
    compute_lifecycle_reachable_closure,
    make_nominal_lifecycle_state,
    apply_lifecycle_op,
)
from qualification.jev_rewriting_grammar_campaign import (
    DEFAULT_GRAMMAR_SPECS,
    DEFAULT_OUTPUT,
    admission_state_variable,
    apply_word_regime,
    compute_commutation_analysis,
    execute_word_on_state,
    normalize_operational_word,
    regime_state_variable,
    run_live_grammar_experiment,
    run_rewriting_grammar_campaign,
    symbolic_step_regime,
    verify_generator_irreducibility,
    verify_local_confluence,
)


@pytest.fixture(scope="module")
def reachable_closure():
    states, visited, depth = compute_lifecycle_reachable_closure()
    return states, visited, depth


def test_generator_irreducibility_g_r0(reachable_closure):
    """Gate G-R0: All 14 generators in Sigma_full are proven strictly minimal via inductive separating invariants."""
    states, _, _ = reachable_closure
    irred = verify_generator_irreducibility(states, depth_limit=3)

    assert irred["alphabet_size"] == 14
    assert irred["minimal_generating_set_size"] == 14
    assert irred["all_generators_strictly_minimal"] is True
    assert irred["inductive_invariants_all_verified"] is True

    for op in SIGMA_FULL:
        assert irred["details"][op]["is_irreducible_bounded"] is True
        assert irred["details"][op]["inductive_invariant_verified"] is True
        assert irred["details"][op]["synthesized_by"] is None


def test_strict_quotient_congruence_g_r1(reachable_closure):
    """Gate G-R1: 100% congruence across all 32,438 transitions on Q_222 and Q_97."""
    states, _, _ = reachable_closure

    total_checks = 0
    congruence_violations_regime = 0
    congruence_violations_admission = 0

    for s in states:
        q_reg = regime_state_variable(s)
        q_adm = admission_state_variable(s)

        for op in SIGMA_FULL:
            total_checks += 1
            next_s = apply_lifecycle_op(s, op)

            # Check regime congruence
            expected_reg = regime_state_variable(next_s)
            actual_reg = symbolic_step_regime(q_reg, op)
            if expected_reg != actual_reg:
                congruence_violations_regime += 1

            # Check admission congruence
            expected_adm = admission_state_variable(next_s)
            actual_adm = (
                actual_reg[0],
                actual_reg[1],
                actual_reg[2],
                actual_reg[3],
                actual_reg[4],
                actual_reg[5],
                actual_reg[7],
                actual_reg[8] == "NOMINAL",
            )
            if expected_adm != actual_adm:
                congruence_violations_admission += 1

    assert total_checks == 2317 * 14 == 32438
    assert congruence_violations_regime == 0
    assert congruence_violations_admission == 0


def test_commutation_subspaces_and_confluent_pairs(reachable_closure):
    """Verify that independent subspaces commute on regime quotient Q_222."""
    states, _, _ = reachable_closure
    comm = compute_commutation_analysis(states)

    assert comm["all_15_failures_commute_on_regime"] is True
    assert comm["failure_pairs_count"] == 15
    assert comm["all_20_remediations_commute_on_regime"] is True
    assert comm["repair_pairs_count"] == 20
    assert comm["regime_commuting_pairs_count"] == 42


def test_local_confluence_and_strong_normalization(reachable_closure):
    """Gates G-R2 & G-R3: Verify local confluence and zero divergences across all 213 algorithmic critical overlaps."""
    states, _, _ = reachable_closure

    test_words = [
        ("A", "A"),
        ("E", "E"),
        ("C", "C"),
        ("T", "T"),
        ("R", "R"),
        ("Adv", "Adv"),
        ("Rebind", "Rebind"),
        ("RepairEvidence", "RepairEvidence"),
        ("RestoreCausalPath", "RestoreCausalPath"),
        ("Refresh", "Refresh"),
        ("Reallocate", "Reallocate"),
        ("Quarantine", "Quarantine"),
        ("Release", "Release"),
        ("Recertify", "Recertify"),
        ("E", "A"),
        ("T", "C"),
        ("R", "A"),
        ("Adv", "A"),
        ("RepairEvidence", "Rebind"),
        ("RestoreCausalPath", "Refresh"),
        ("Reallocate", "Rebind"),
        ("Quarantine", "Rebind"),
        ("A", "Recertify"),
        ("E", "Recertify"),
        ("C", "Recertify"),
        ("T", "Recertify"),
        ("R", "Recertify"),
        ("Adv", "Recertify"),
        ("Adv", "Release"),
        ("Rebind", "A"),
        ("RepairEvidence", "E"),
        ("Refresh", "T"),
        ("A", "T", "Refresh", "Rebind"),
        ("C", "RestoreCausalPath", "Recertify"),
        ("Adv", "Quarantine", "Release", "Recertify"),
    ]

    conf = verify_local_confluence(test_words, states)
    assert conf["total_rules_in_trs"] == 61
    assert conf["all_rules_verified_across_222_states"] is True
    assert conf["total_algorithmic_critical_overlaps"] == 213
    assert conf["critical_pairs_confluent_count"] == 213
    assert conf["confluence_rate"] == 1.0
    assert conf["divergences_count"] == 0
    assert conf["strong_normalization_proven"] is True
    assert conf["newman_lemma_confluence_established"] is True


def test_deterministic_and_synthetic_observer_invariance():
    """Gate G-R4: Verify observer invariance under semantic rewrites (mean_eta <= 1.50)."""
    provider = CalibratedEmpiricalJevProvider()
    results = run_live_grammar_experiment(provider, specs=DEFAULT_GRAMMAR_SPECS, replicates=3)

    assert results["all_pairs_deterministic_equal"] is True
    assert results["mean_normalized_defect_eta"] <= 1.50
    assert results["all_pairs_within_observer_noise"] is True

    for p in results["pair_analyses"]:
        assert p["deterministic_state_equal"] is True
        assert p["equivalent_within_noise"] is True
        assert p["defect_ratio_eta"] <= 1.50


def test_provenance_and_synthetic_discipline():
    """Verify synthetic provider discipline and provenance quarantine."""
    provider = CalibratedEmpiricalJevProvider()
    x0 = make_nominal_lifecycle_state()
    x0.pop("governed_status", None)

    obs = provider.decide(state=x0, questions=[], request_id="synth-check")
    assert obs["provider_kind"] == "synthetic_calibrated_replay"
    assert obs["resolved_model"] == "calibrated-jev-replay-v1"
    assert obs["usage"] is None

    campaign_res = run_rewriting_grammar_campaign(provider, replicates=2)
    assert campaign_res["gates"]["G-R-LIVE"]["passed"] is False


def test_live_artifact_audit():
    """Audit the generated Phase 7 artifact if present."""
    if not DEFAULT_OUTPUT.exists():
        pytest.skip(f"Artifact {DEFAULT_OUTPUT} not present; skipping live audit.")

    payload = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
    summary = payload["summary"]
    gates = payload["gates"]

    assert summary["closure_microstates"] == 2317
    assert summary["regime_classes"] == 222
    assert summary["admission_classes"] == 97
    assert summary["minimal_generators_count"] == 14
    assert summary["congruence_violations"] == 0
    assert summary["total_instantiated_rules"] == 61
    assert summary["algorithmic_critical_overlaps_count"] == 213
    assert summary["critical_pairs_confluent_count"] == 213
    assert summary["critical_pairs_confluence_rate"] == 1.0

    assert gates["G-R0"]["passed"] is True
    assert gates["G-R1"]["passed"] is True
    assert gates["G-R2"]["passed"] is True
    assert gates["G-R3"]["passed"] is True
    assert gates["G-R4"]["passed"] is True

    # If live_api was used, assert authentic provenance and tokens
    prov = payload["live_experiment"]["provider_provenance"]
    if prov["is_live_api"]:
        assert gates["G-R-LIVE"]["passed"] is True
        assert prov["provider_kind"] == "live_api"
        assert prov["resolved_model"] == "jev-1.13.0"
        assert prov["total_token_usage"] > 0

