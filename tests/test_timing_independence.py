"""Regression lock for the original Orchestrator timer-independence invariant."""
from qualification.timing_independence import (
    causal_order_beats_local_clock_order,
    make_clock_bindings,
    nested_clock_isolation_holds,
    run_clock_drift_campaign,
    run_timing_independence_campaign,
    shared_clock_mutant_is_rejected,
    validate_independent_clock_ownership,
    wall_clock_is_not_required,
)


def test_local_clock_bindings_are_independently_owned():
    bindings = make_clock_bindings(20260922)
    validate_independent_clock_ownership(bindings)
    assert len({id(clock) for clock in bindings.values()}) == len(bindings)


def test_shared_mutable_clock_mutant_is_detected():
    assert shared_clock_mutant_is_rejected()


def test_nested_parent_child_clock_isolation():
    assert nested_clock_isolation_holds()


def test_causal_dependency_order_dominates_local_clock_values():
    assert causal_order_beats_local_clock_order()


def test_canonical_orchestration_requires_no_host_wall_clock():
    assert wall_clock_is_not_required()


def test_1000_independent_clock_drift_realizations_preserve_certified_behavior():
    state_ok, order_ok, _baseline_hash, _baseline_ids = run_clock_drift_campaign(1_000)
    assert state_ok
    assert order_ok


def test_full_timing_independence_campaign():
    result = run_timing_independence_campaign(250)
    assert result.state_invariant
    assert result.transition_order_invariant
    assert result.causal_order_dominates_clock_order
    assert result.shared_clock_mutant_rejected
    assert result.nested_clock_isolation
    assert result.wall_clock_independent
