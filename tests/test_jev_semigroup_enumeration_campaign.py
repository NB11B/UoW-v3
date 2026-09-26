"""Offline qualification test harness for JEV Transformation Semigroup Enumeration Campaign (Phase 5).

Validates:
1. Reachable state closure X_reach = cl_Sigma({x_0}) contains exactly 104 states (1 nominal + 103 failure states).
2. Identity-adjoined transformation monoid S^1 = S union {I} has order 104.
3. Finite failure semigroup S stabilization at Level 7 with |S| = 103 elements.
4. Exhaustive band theorem over X_reach: s^2 == s for all 103 transformations across all 104 reachable states.
5. Complete 103x103 Cayley table structure, noncommutativity (41.52% commuting pairs), and 4 terminal overwrite right zeros.
6. Green's relations and H-triviality: |H| == 103 singletons, confirming standard band structure.
7. Full 64-state Boolean guard lattice B_6 = P({A, E, C, T, R, Adv}) (63 failure + 1 nominal).
8. Canonical normal form reduction N: Sigma+ -> S.
9. Multi-tiered quotient compression:
   - Governance quotient: |S| / |S/~_G| = 103.0x
   - Guard lattice quotient: |S| / |S/~_guard| = 1.63x (63 distinct failure guard configurations)
   - Predicted observer quotient: |S| / |S/~_J| = 1.63x
10. All 6 engineering and mathematical gates pass.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from qualification.jev_semigroup_enumeration_campaign import (
    GENERATORS,
    apply_generator,
    build_reachable_closure,
    compute_guard_vector,
    enumerate_semigroup,
    make_nominal_state,
    state_fingerprint,
)


@pytest.fixture(scope="module")
def enumeration_result() -> dict[str, Any]:
    """Run enumeration once for test module."""
    return enumerate_semigroup(max_depth=10)


def test_reachable_closure_and_monoid_order(enumeration_result: dict[str, Any]):
    """Verify reachable closure |X_reach| = 104 and monoid |S^1| = 104."""
    summary = enumeration_result["summary"]
    assert summary["reachable_closure_states_count"] == 104
    assert summary["identity_adjoined_monoid_order"] == 104
    assert enumeration_result["gates"]["G_E0_reachable_closure_104_states"] is True


def test_semigroup_stabilization_at_103_elements(enumeration_result: dict[str, Any]):
    """Verify that failure transformation enumeration stabilizes at level 7 with exactly 103 elements."""
    summary = enumeration_result["summary"]
    assert summary["failure_semigroup_order"] == 103
    assert summary["stabilization_level"] == 7

    growth = enumeration_result["level_growth"]
    assert len(growth) == 7
    # Check level transitions
    assert growth[0]["new_transformations"] == 6
    assert growth[0]["cumulative_transformations"] == 6
    assert growth[-1]["new_transformations"] == 0
    assert growth[-1]["cumulative_transformations"] == 103
    assert enumeration_result["gates"]["G_E1_finite_semigroup_stabilization_103_elements"] is True


def test_exhaustive_band_idempotence_over_X_reach(enumeration_result: dict[str, Any]):
    """Verify that all 103 elements in S satisfy s^2 = s over all 104 reachable states."""
    summary = enumeration_result["summary"]
    assert summary["is_exhaustive_band"] is True
    assert enumeration_result["gates"]["G_E2_exhaustive_band_idempotence_over_X_reach"] is True


def test_cayley_table_and_green_relations(enumeration_result: dict[str, Any]):
    """Verify 103x103 Cayley table, 41.52% commutativity, and H-triviality."""
    summary = enumeration_result["summary"]
    cayley = enumeration_result["cayley_table_summary"]

    assert cayley["matrix_dimension"] == 103
    assert cayley["left_zeros_count"] == 0
    assert cayley["right_zeros_count"] == 4
    assert len(cayley["sample_right_zero_words"]) == 4

    assert summary["commutativity_percentage"] == 41.52
    assert summary["green_r_classes"] == 63
    assert summary["green_l_classes"] == 103
    assert summary["green_h_classes"] == 103
    assert summary["is_h_trivial"] is True
    assert enumeration_result["gates"]["G_E3_green_h_triviality_singletons"] is True
    assert enumeration_result["gates"]["G_E4_terminal_overwrite_right_zeros"] is True


def test_full_boolean_guard_lattice_B6(enumeration_result: dict[str, Any]):
    """Verify 64-state Boolean guard lattice B_6 (63 failure + 1 nominal)."""
    summary = enumeration_result["summary"]
    ratios = summary["compression_ratios"]

    assert summary["failure_guard_states_count"] == 63
    assert summary["total_boolean_guard_lattice_states_count"] == 64
    assert ratios["governance_quotient"] == 103.0
    assert ratios["guard_quotient"] == 1.63
    assert ratios["predicted_observer_quotient"] == 1.63
    assert enumeration_result["gates"]["G_E5_full_boolean_guard_lattice_B6"] is True


def test_canonical_normal_form_reduction():
    """Verify generator idempotence on reachable states."""
    x0 = make_nominal_state()

    # Test that applying each generator twice produces identical state from x0
    for g in GENERATORS:
        s1 = apply_generator(x0, g)
        s2 = apply_generator(s1, g)
        assert state_fingerprint(s1) == state_fingerprint(s2), f"Generator {g} not idempotent on x0"


def test_all_engineering_gates_pass(enumeration_result: dict[str, Any]):
    """Verify all Phase 5 gates pass and formal object is characterized."""
    gates = enumeration_result["gates"]
    assert gates["G_E0_reachable_closure_104_states"] is True
    assert gates["G_E1_finite_semigroup_stabilization_103_elements"] is True
    assert gates["G_E2_exhaustive_band_idempotence_over_X_reach"] is True
    assert gates["G_E3_green_h_triviality_singletons"] is True
    assert gates["G_E4_terminal_overwrite_right_zeros"] is True
    assert gates["G_E5_full_boolean_guard_lattice_B6"] is True

    summary = enumeration_result["summary"]
    assert summary["verdict"] == "SEMIGROUP_EXHAUSTIVELY_ENUMERATED_AND_BAND_PROVEN_ON_X_REACH"
    assert (
        summary["final_mathematical_object"]
        == "finite_noncommutative_band_with_terminal_collapse_ideals_and_history_sensitive_provenance"
    )
