"""Tests for Phase 9 Compliance Blind Derivation Campaign.

Validates:
  1. Reachable closure exploration (|X_C| = 2,804 microstates).
  2. Paige-Tarjan minimization (|Q_C^(1)| = 384 admission classes, |Q_C^(2)| = 930 disposition classes).
  3. 17-generator irreducibility via inductive separating predicates.
  4. Algebraic idempotence, commutation matrices, and forensic containment quarantine.
  5. TRS canonical rules and 100% Church-Rosser confluence of 205 critical overlaps.
  6. Falsification of naive isomorphism to 222/97 and verification of Governance Kernel Projection.
  7. Observer invariance and faithfulness on frozen compliance grammar.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from qualification.compliance_blind_derivation_campaign import (
    SIGMA_COMP,
    SIGMA_COMP_DISRUPT,
    SIGMA_COMP_REMEDY,
    apply_compliance_op,
    make_nominal_compliance_state,
    compute_compliance_reachable_closure,
    minimize_compliance_automaton,
    verify_compliance_generator_irreducibility,
    analyze_compliance_algebra,
    build_compliance_trs_and_verify_confluence,
    evaluate_structural_relationship_with_uow,
    evaluate_compliance_observer_invariance,
)
from qualification.jev_lifecycle_grammar_campaign import CalibratedEmpiricalJevProvider


@pytest.fixture(scope="module")
def compliance_universe():
    """Compute reachable closure and minimization once for module tests."""
    states, visited, max_depth = compute_compliance_reachable_closure()
    min_res = minimize_compliance_automaton(states, visited)
    return {
        "states": states,
        "visited": visited,
        "max_depth": max_depth,
        "min_res": min_res,
    }


def test_reachable_closure_cardinality(compliance_universe):
    """Verify that blind exploration yields exactly 2,804 reachable microstates at depth 11."""
    states = compliance_universe["states"]
    max_depth = compliance_universe["max_depth"]
    assert len(states) == 2804
    assert max_depth == 11


def test_paige_tarjan_minimization(compliance_universe):
    """Verify Paige-Tarjan minimization under O_1 (384 classes) and O_2 (930 classes)."""
    min_res = compliance_universe["min_res"]
    assert min_res["minimized_admission_classes_count"] == 384
    assert min_res["minimized_disposition_classes_count"] == 930


def test_17_generator_irreducibility(compliance_universe):
    """Verify that all 17 compliance operators are strictly irreducible."""
    states = compliance_universe["states"]
    irred_res = verify_compliance_generator_irreducibility(states)
    assert irred_res["generator_count"] == 17
    assert irred_res["all_17_generators_irreducible"] is True
    for op, proof in irred_res["irreducibility_proofs"].items():
        assert proof["strictly_irreducible"] is True, f"Operator {op} failed irreducibility"


def test_algebraic_properties_and_containment(compliance_universe):
    """Verify algebraic properties: 16 idempotent operators, commutation, and forensic hold."""
    states = compliance_universe["states"]
    visited = compliance_universe["visited"]
    part_o2 = compliance_universe["min_res"]["partition_o2"]

    algebra_res = analyze_compliance_algebra(states, visited, part_o2)
    assert algebra_res["idempotent_operators_count"] == 16
    assert "SubmitStatutoryFiling" in algebra_res["non_idempotent_operators"]
    assert algebra_res["disruption_commutation_pairs"] == "21 / 21"
    assert algebra_res["remediation_commutation_pairs"] == "28 / 45"
    assert algebra_res["containment_bypass_prevented"] is True
    assert algebra_res["containment_clear_path_verified"] is True


def test_trs_local_confluence_modulo_q2(compliance_universe):
    """Verify Church-Rosser confluence across all 205 algorithmic critical overlaps."""
    states = compliance_universe["states"]
    visited = compliance_universe["visited"]
    part_o2 = compliance_universe["min_res"]["partition_o2"]

    trs_res = build_compliance_trs_and_verify_confluence(states, visited, part_o2)
    assert trs_res["canonical_rules_count"] == 65
    assert trs_res["total_critical_overlaps"] == 205
    assert trs_res["confluent_critical_overlaps"] == 205
    assert trs_res["confluence_rate"] == 1.0
    assert trs_res["confluence_modulo_q2_certified"] is True


def test_structural_comparison_and_kernel_projection(compliance_universe):
    """Verify falsification of naive isomorphism and confirm Governance Kernel Classification."""
    min_res = compliance_universe["min_res"]
    struct_res = evaluate_structural_relationship_with_uow(min_res)

    assert struct_res["strict_isomorphism_candidate"] is False
    assert "FALSIFIED" in struct_res["strict_isomorphism_verdict"]
    assert struct_res["sub_automaton_embedding_candidate"] is False
    assert struct_res["governance_kernel_projection"] is True
    assert struct_res["theoretical_classification"] == "CONSERVATIVE_NORMATIVE_SUPERSET"


def test_observer_invariance_and_faithfulness():
    """Verify observer invariance and faithfulness using calibrated provider."""
    provider = CalibratedEmpiricalJevProvider(seed=42)
    obs_res = evaluate_compliance_observer_invariance(provider, repeats=3)

    assert obs_res["total_evaluated_pairs"] == 12
    assert obs_res["outlier_bound_passing_count"] == 12
    assert obs_res["mean_normalized_ratio_eta"] <= 1.50
    assert obs_res["invariance_gate_passed"] is True
    assert obs_res["faithfulness_distinguished"] is True
