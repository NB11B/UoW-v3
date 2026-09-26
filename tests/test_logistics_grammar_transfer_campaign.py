"""Tests for Logistics Domain Operational Grammar Transfer Campaign (Phase 8)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from qualification.logistics_grammar_transfer_campaign import (
    DEFAULT_OUTPUT,
    PSI_LOG_TO_UOW,
    SIGMA_LOGISTICS,
    SIGMA_LOGISTICS_DISRUPT,
    SIGMA_LOGISTICS_REPAIR,
    STATUS_MAP_LOG_TO_UOW,
    analyze_logistics_commutation,
    apply_logistics_op,
    build_logistics_trs_rules,
    compute_logistics_reachable_closure,
    logistics_dispatch_variable,
    logistics_status_variable,
    logistics_step_regime,
    make_nominal_logistics_state,
    minimize_logistics_automaton,
    phi_state_map,
    run_logistics_transfer_campaign,
    verify_cross_domain_isomorphism,
    verify_logistics_generator_irreducibility,
    verify_logistics_local_confluence,
)


@pytest.fixture(scope="module")
def logistics_closure():
    states, visited, depth = compute_logistics_reachable_closure()
    return states, visited, depth


def test_logistics_reachable_closure_and_minimization(logistics_closure):
    states, visited, depth = logistics_closure
    assert len(states) == 330
    assert depth == 8

    min_res = minimize_logistics_automaton(states, visited)
    assert min_res["minimized_status_classes_count"] == 222
    assert min_res["minimized_dispatch_classes_count"] == 97
    assert min_res["status_bijection_verified"] is True
    assert min_res["dispatch_bijection_verified"] is True


def test_logistics_generator_irreducibility(logistics_closure):
    states, _, _ = logistics_closure
    all_status_states = {logistics_status_variable(s) for s in states}
    res = verify_logistics_generator_irreducibility(all_status_states)
    assert res["all_generators_irreducible"] is True
    assert res["generators_count"] == 14
    for op, proof in res["proofs"].items():
        assert proof["strictly_irreducible"] is True, f"Operator {op} failed irreducibility proof"


def test_logistics_commutation_subspaces(logistics_closure):
    states, _, _ = logistics_closure
    all_status_states = {logistics_status_variable(s) for s in states}
    comm_res = analyze_logistics_commutation(all_status_states)
    assert comm_res["all_15_disruptions_commute"] is True
    assert comm_res["all_20_remediations_commute"] is True
    assert comm_res["impound_clear_order_sensitive"] is True


def test_logistics_algorithmic_critical_overlaps_and_confluence(logistics_closure):
    states, _, _ = logistics_closure
    all_status_states = {logistics_status_variable(s) for s in states}
    rules = build_logistics_trs_rules()
    assert len(rules) == 61

    conf_res = verify_logistics_local_confluence(all_status_states, rules)
    assert conf_res["total_algorithmic_critical_overlaps"] == 213
    assert conf_res["confluent_critical_overlaps"] == 213
    assert conf_res["confluence_rate"] == 1.0
    assert conf_res["all_critical_overlaps_confluent"] is True


def test_cross_domain_automata_isomorphism(logistics_closure):
    states, _, _ = logistics_closure
    all_status_states = {logistics_status_variable(s) for s in states}
    iso_res = verify_cross_domain_isomorphism(all_status_states)
    assert iso_res["total_transitions_checked"] == 3108
    assert iso_res["isomorphism_violations"] == 0
    assert iso_res["isomorphism_certified"] is True
    assert iso_res["admission_preservation_violations"] == 0
    assert iso_res["admission_preservation_certified"] is True


def test_logistics_artifact_integrity():
    if not DEFAULT_OUTPUT.exists():
        run_logistics_transfer_campaign(use_live_api=False)

    with open(DEFAULT_OUTPUT, encoding="utf-8") as f:
        data = json.load(f)

    assert data["isomorphism_summary"]["isomorphism_certified"] is True
    assert data["isomorphism_summary"]["isomorphism_violations"] == 0
    assert data["isomorphism_summary"]["total_transitions_checked"] == 3108
    assert data["isomorphism_summary"]["logistics_status_quotient_size"] == 222
    assert data["isomorphism_summary"]["logistics_dispatch_quotient_size"] == 97
    assert data["gates"]["G-TRANS-0"] is True
    assert data["gates"]["G-TRANS-1"] is True
    assert data["gates"]["G-TRANS-2"] is True
    assert data["gates"]["G-TRANS-3"] is True
    assert data["gates"]["G-TRANS-4"] is True
    assert data["gates"]["G-TRANS-5"] is True
    assert data["all_gates_passed"] is True
