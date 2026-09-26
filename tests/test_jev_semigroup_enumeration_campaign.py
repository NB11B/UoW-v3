"""Offline qualification test harness for JEV Transformation Semigroup Enumeration Campaign (Phase 5).

Validates:
1. Finite transformation semigroup enumeration and stabilization at Level 7 with |S| = 103 elements.
2. Exhaustive band theorem: s^2 == s for all 103 transformations in S.
3. Complete 103x103 Cayley table structure, noncommutativity (41.52% commuting pairs), and 4 right absorbing zeros.
4. Green's relations and H-triviality: |H| == 103 singletons, confirming standard band structure.
5. Canonical normal form reduction N: Sigma* -> S.
6. Multi-tiered quotient compression:
   - Governance quotient: |S| / |S/~_G| = 103.0x
   - Guard lattice quotient: |S| / |S/~_guard| = 1.63x (63 distinct guard configurations)
   - Observer quotient: |S| / |S/~_J| = 1.63x
7. All 5 engineering and mathematical gates pass.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from qualification.jev_semigroup_enumeration_campaign import (
    GENERATORS,
    apply_generator,
    build_test_universe,
    compute_guard_vector,
    compute_transformation_signature,
    enumerate_semigroup,
    evaluate_word,
    make_nominal_state,
)


@pytest.fixture(scope="module")
def enumeration_result() -> dict[str, Any]:
    """Run enumeration once for test module."""
    return enumerate_semigroup(max_depth=10)


def test_semigroup_stabilization_at_103_elements(enumeration_result: dict[str, Any]):
    """Verify that transformation enumeration stabilizes at level 7 with exactly 103 elements."""
    summary = enumeration_result["summary"]
    assert summary["total_transformations"] == 103
    assert summary["stabilization_level"] == 7

    growth = enumeration_result["level_growth"]
    assert len(growth) == 7
    # Check level transitions
    assert growth[0]["new_transformations"] == 6
    assert growth[0]["cumulative_transformations"] == 6
    assert growth[-1]["new_transformations"] == 0
    assert growth[-1]["cumulative_transformations"] == 103


def test_exhaustive_band_idempotence(enumeration_result: dict[str, Any]):
    """Verify that all 103 elements in S satisfy s^2 = s (Band Theorem)."""
    summary = enumeration_result["summary"]
    assert summary["is_exhaustive_band"] is True
    assert enumeration_result["gates"]["G_E1_exhaustive_band_idempotence"] is True


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
    assert enumeration_result["gates"]["G_E2_green_h_triviality"] is True
    assert enumeration_result["gates"]["G_E3_right_absorbing_zeros"] is True


def test_quotient_compression_ratios(enumeration_result: dict[str, Any]):
    """Verify multi-tier quotient compression (governance, guard lattice, observer)."""
    summary = enumeration_result["summary"]
    ratios = summary["compression_ratios"]

    assert summary["guard_states_count"] == 63
    assert ratios["governance_quotient"] == 103.0
    assert ratios["guard_quotient"] == 1.63
    assert ratios["observer_quotient"] == 1.63
    assert enumeration_result["gates"]["G_E4_guard_lattice_quotient_faithful"] is True


def test_canonical_normal_form_reduction():
    """Verify normal form reducer N: Sigma* -> S maps composite words to canonical elements."""
    test_universe = build_test_universe()
    x0 = test_universe[0]

    # Test that applying each generator twice produces identical transformation signature
    for g in GENERATORS:
        sig_single = compute_transformation_signature((g,), test_universe)
        sig_double = compute_transformation_signature((g, g), test_universe)
        assert sig_single == sig_double, f"Normal form reduction failed for {g}^2 -> {g}"

    # Test an arbitrary higher-order composite word
    # w = (A, E, A, E) should reduce to (A, E)
    sig_ae = compute_transformation_signature(("A", "E"), test_universe)
    sig_aeae = compute_transformation_signature(("A", "E", "A", "E"), test_universe)
    assert sig_ae == sig_aeae, "Normal form reduction failed for (AE)^2 -> AE"


def test_all_engineering_gates_pass(enumeration_result: dict[str, Any]):
    """Verify all Phase 5 gates pass and formal object is characterized."""
    gates = enumeration_result["gates"]
    assert gates["G_E0_finite_semigroup_stabilization"] is True
    assert gates["G_E1_exhaustive_band_idempotence"] is True
    assert gates["G_E2_green_h_triviality"] is True
    assert gates["G_E3_right_absorbing_zeros"] is True
    assert gates["G_E4_guard_lattice_quotient_faithful"] is True

    summary = enumeration_result["summary"]
    assert summary["verdict"] == "SEMIGROUP_EXHAUSTIVELY_ENUMERATED_AND_BAND_PROVEN"
    assert (
        summary["final_mathematical_object"]
        == "finite_noncommutative_band_with_absorbing_ideals_and_history_sensitive_provenance"
    )
