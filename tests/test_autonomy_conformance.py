"""Differential reference conformance suite comparing uow.autonomy against frozen qualified reference vectors.

Frozen reference vectors generated from c559d6c1c962b436fa9c05c68de42f29afa4ad6f (tagged e1c-gate0-evaluator)
stored in tests/fixtures/autonomy_reference_c559d6c.json.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from uow.state import WorldState
import uow.autonomy.controller as prod_ac
import uow.autonomy.model as prod_m
import uow.autonomy.ports as prod_p

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "autonomy_reference_c559d6c.json"
REFERENCE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
CASES = REFERENCE["cases"]


def _assert_conformance(result, env, expected: dict) -> None:
    assert result.success == expected["success"]
    assert result.terminal_state.value == expected["terminal_state"]
    assert len(result.work_transcript) == expected["work_count"]
    assert list(result.work_transcript) == expected["work_transcript"]
    assert env.state.attributes == expected["final_attributes"]
    assert env.state.state_hash == expected["final_state_hash"]
    assert list(result.transitions) == expected["transitions"]
    assert list(result.rejection_reasons) == expected["rejection_reasons"]
    assert (result.closure_certificate is not None) == expected["has_closure_certificate"]
    assert (result.deficit_certificate is not None) == expected["has_deficit_certificate"]
    assert result.budget_usage.repairs == expected["budget_repairs"]
    assert result.budget_usage.adaptations == expected["budget_adaptations"]
    if expected.get("has_deficit_certificate"):
        assert result.deficit_certificate.basis_id == expected["deficit_basis_id"]
        assert sorted(result.deficit_certificate.proof.missing_effects) == expected["deficit_missing_effects"]


def test_conformance_goal_already_satisfied():
    """Case 1: Goal already satisfied in initial observation (NO_OP)."""
    expected = CASES["goal_already_satisfied"]
    state = WorldState(attributes={"status": "done"})

    crit = prod_m.Criterion("c1", prod_m.StatePredicate("status", prod_m.PredicateOp.EQ, "done"))
    goal = prod_m.GoalEnvelope(
        goal_id="g_satisfied",
        initial_state_ref=state.state_hash,
        desired_state=(crit.predicate,),
        success_criteria=(crit,),
    )
    reg = prod_m.CapabilityRegistry([])
    env = prod_p.Environment(state, reg)
    res = prod_ac.AutonomousClosureController(reg).run(goal, env)

    _assert_conformance(res, env, expected)


def test_conformance_single_step_completion():
    """Case 2: Single-step deterministic completion."""
    expected = CASES["single_step_completion"]
    state = WorldState(attributes={"status": "init"})

    crit = prod_m.Criterion("c1", prod_m.StatePredicate("status", prod_m.PredicateOp.EQ, "ready"))
    cap = prod_m.CapabilityDescriptor("init_cap", "Init", effects=(crit.predicate,))
    goal = prod_m.GoalEnvelope(
        goal_id="g_single",
        initial_state_ref=state.state_hash,
        desired_state=(crit.predicate,),
        success_criteria=(crit,),
    )
    reg = prod_m.CapabilityRegistry([cap])
    env = prod_p.Environment(state, reg)
    res = prod_ac.AutonomousClosureController(reg).run(goal, env)

    _assert_conformance(res, env, expected)
    assert res.budget_usage.cost == expected["budget_cost"]


def test_conformance_multi_step_dependency():
    """Case 3: Multi-step causal DAG synthesis and topological ordering."""
    expected = CASES["multi_step_dependency"]
    state = WorldState(attributes={"stepA": "pending", "stepB": "pending"})

    critA = prod_m.StatePredicate("stepA", prod_m.PredicateOp.EQ, "done")
    critB = prod_m.StatePredicate("stepB", prod_m.PredicateOp.EQ, "done")
    capA = prod_m.CapabilityDescriptor("cap_a", "Cap A", effects=(critA,))
    capB = prod_m.CapabilityDescriptor("cap_b", "Cap B", preconditions=(critA,), effects=(critB,))
    crit = prod_m.Criterion("cb", critB)
    goal = prod_m.GoalEnvelope(
        goal_id="g_multi",
        initial_state_ref=state.state_hash,
        desired_state=(critB,),
        success_criteria=(crit,),
    )
    reg = prod_m.CapabilityRegistry([capA, capB])
    env = prod_p.Environment(state, reg)
    res = prod_ac.AutonomousClosureController(reg).run(goal, env)

    _assert_conformance(res, env, expected)


def test_conformance_missing_capability():
    """Case 4: Goal requires unavailable capability."""
    expected = CASES["missing_capability"]
    state = WorldState(attributes={"status": "init"})

    crit = prod_m.Criterion("c_miss", prod_m.StatePredicate("missing_attr", prod_m.PredicateOp.EQ, "ready"))
    goal = prod_m.GoalEnvelope(
        goal_id="g_miss",
        initial_state_ref=state.state_hash,
        desired_state=(crit.predicate,),
        success_criteria=(crit,),
    )
    reg = prod_m.CapabilityRegistry([])
    env = prod_p.Environment(state, reg)
    res = prod_ac.AutonomousClosureController(reg).run(goal, env)

    _assert_conformance(res, env, expected)


def test_conformance_semantic_non_derivability():
    """Case 5: Open-world semantic deficit certification."""
    expected = CASES["semantic_non_derivability"]
    state = WorldState(attributes={"status": "init"})

    crit = prod_m.Criterion("c_unrep", prod_m.StatePredicate("effect:teleport", prod_m.PredicateOp.EQ, "on"))
    goal = prod_m.GoalEnvelope(
        goal_id="g_unrep",
        initial_state_ref=state.state_hash,
        desired_state=(crit.predicate,),
        success_criteria=(crit,),
        required_effects=("teleport",),
    )
    reg = prod_m.CapabilityRegistry([])
    env = prod_p.Environment(state, reg)
    res = prod_ac.AutonomousClosureController(reg).run(goal, env)

    _assert_conformance(res, env, expected)


def test_conformance_authority_rejection():
    """Case 6: Capability requires unauthorized scope."""
    expected = CASES["authority_rejection"]
    state = WorldState(attributes={"restricted": "locked"})

    crit = prod_m.Criterion("c_auth", prod_m.StatePredicate("restricted", prod_m.PredicateOp.EQ, "open"))
    cap = prod_m.CapabilityDescriptor("unauth_cap", "Unauth", effects=(crit.predicate,), required_authority=("top_secret",))
    goal = prod_m.GoalEnvelope(
        goal_id="g_auth",
        initial_state_ref=state.state_hash,
        desired_state=(crit.predicate,),
        success_criteria=(crit,),
        allowed_authority=prod_m.AuthorityScope(("public_only",)),
    )
    reg = prod_m.CapabilityRegistry([cap])
    env = prod_p.Environment(state, reg)
    res = prod_ac.AutonomousClosureController(reg).run(goal, env)

    _assert_conformance(res, env, expected)


def test_conformance_resource_exhaustion():
    """Case 7: Step budget limit halts execution."""
    expected = CASES["resource_exhaustion"]
    state = WorldState(attributes={"step": 0})

    crit = prod_m.Criterion("c_steps", prod_m.StatePredicate("step", prod_m.PredicateOp.EQ, 10))
    cap = prod_m.CapabilityDescriptor("cap_step", "Step", effects=(crit.predicate,))
    goal = prod_m.GoalEnvelope(
        goal_id="g_budget",
        initial_state_ref=state.state_hash,
        desired_state=(crit.predicate,),
        success_criteria=(crit,),
    )
    reg = prod_m.CapabilityRegistry([cap])
    env = prod_p.Environment(state, reg)
    budget = prod_m.AutonomyBudget(max_steps=0)
    res = prod_ac.AutonomousClosureController(reg, budget=budget).run(goal, env)

    _assert_conformance(res, env, expected)


def test_conformance_bounded_repair_on_transient_failure():
    """Case 8: Execution failure recovered via surgical bounded repair."""
    expected = CASES["bounded_repair_on_transient_failure"]
    state = WorldState(attributes={"stepA": "pending", "stepB": "pending"})

    critA = prod_m.StatePredicate("stepA", prod_m.PredicateOp.EQ, "done")
    critB = prod_m.StatePredicate("stepB", prod_m.PredicateOp.EQ, "done")
    capA = prod_m.CapabilityDescriptor("cap_a", "Cap A", effects=(critA,))
    capB = prod_m.CapabilityDescriptor("cap_b", "Cap B", preconditions=(critA,), effects=(critB,))
    crit = prod_m.Criterion("c_b", critB)
    goal = prod_m.GoalEnvelope(
        goal_id="g_repair",
        initial_state_ref=state.state_hash,
        desired_state=(critB,),
        success_criteria=(crit,),
    )
    reg = prod_m.CapabilityRegistry([capA, capB])
    env = prod_p.Environment(state, reg)

    fails = {"cap_b": 0}
    orig_exec = env.execute_work_item
    def failing(item, authority):
        if item.work_kind == "cap_b" and fails["cap_b"] == 0:
            fails["cap_b"] += 1
            env.advance_step()
            return prod_p.ExecutionOutcome(False, env.state, 1.0, 1.0, "TRANSIENT_FAULT", item.work_id)
        return orig_exec(item, authority)
    env.execute_work_item = failing

    res = prod_ac.AutonomousClosureController(reg).run(goal, env)

    _assert_conformance(res, env, expected)


def test_conformance_repeated_failure_routes_to_adaptation():
    """Case 9: Repeated execution failure triggers bounded repair non-oscillation."""
    expected = CASES["repeated_failure_routes_to_adaptation"]
    state = WorldState(attributes={"step": "pending"})

    crit = prod_m.Criterion("c_adapt", prod_m.StatePredicate("step", prod_m.PredicateOp.EQ, "done"))
    cap = prod_m.CapabilityDescriptor("flaky_cap", "Flaky", effects=(crit.predicate,))
    goal = prod_m.GoalEnvelope(
        goal_id="g_adapt",
        initial_state_ref=state.state_hash,
        desired_state=(crit.predicate,),
        success_criteria=(crit,),
    )
    reg = prod_m.CapabilityRegistry([cap])
    env = prod_p.Environment(state, reg)

    def perm_fail(item, authority):
        env.advance_step()
        return prod_p.ExecutionOutcome(False, env.state, 1.0, 1.0, "PERM_FAULT", item.work_id)
    env.execute_work_item = perm_fail

    res = prod_ac.AutonomousClosureController(reg, budget=prod_m.AutonomyBudget(max_steps=15)).run(goal, env)

    _assert_conformance(res, env, expected)


def test_conformance_provider_disappearance():
    """Case 10: Dynamic capability failure mid-execution."""
    expected = CASES["provider_disappearance"]
    state = WorldState(attributes={"step": "pending"})

    crit = prod_m.Criterion("c_vanish", prod_m.StatePredicate("step", prod_m.PredicateOp.EQ, "done"))
    cap = prod_m.CapabilityDescriptor("cap_vanish", "Vanish", effects=(crit.predicate,))
    goal = prod_m.GoalEnvelope(
        goal_id="g_vanish",
        initial_state_ref=state.state_hash,
        desired_state=(crit.predicate,),
        success_criteria=(crit,),
    )
    reg = prod_m.CapabilityRegistry([cap])
    env = prod_p.Environment(state, reg)
    env.failed_capabilities.add("cap_vanish")

    res = prod_ac.AutonomousClosureController(reg).run(goal, env)

    _assert_conformance(res, env, expected)


def test_conformance_environmental_state_change():
    """Case 11: Adversarial world shift detected in VERIFY triggers re-observation."""
    expected = CASES["environmental_state_change"]
    state = WorldState(attributes={"step": "pending"})

    crit = prod_m.Criterion("c_shift", prod_m.StatePredicate("step", prod_m.PredicateOp.EQ, "done"))
    cap = prod_m.CapabilityDescriptor("cap_shift", "Shift", effects=(crit.predicate,))
    goal = prod_m.GoalEnvelope(
        goal_id="g_shift",
        initial_state_ref=state.state_hash,
        desired_state=(crit.predicate,),
        success_criteria=(crit,),
    )
    reg = prod_m.CapabilityRegistry([cap])
    env = prod_p.Environment(state, reg)
    orig_exec = env.execute_work_item
    def shifting_exec(item, auth):
        res = orig_exec(item, auth)
        env.state = WorldState(attributes={"step": "shifted"})
        return res
    env.execute_work_item = shifting_exec

    res = prod_ac.AutonomousClosureController(reg, budget=prod_m.AutonomyBudget(max_steps=8)).run(goal, env)

    _assert_conformance(res, env, expected)


def test_conformance_cycle_stagnation_termination():
    """Case 12: Distance metric non-progress detects stagnation and halts."""
    expected = CASES["cycle_stagnation_termination"]
    state = WorldState(attributes={"step": "pending"})

    crit = prod_m.Criterion("c_stag", prod_m.StatePredicate("target", prod_m.PredicateOp.EQ, "reached"))
    cap = prod_m.CapabilityDescriptor("dummy_cap", "Dummy", effects=(prod_m.StatePredicate("irrelevant", prod_m.PredicateOp.EQ, "val"),))
    goal = prod_m.GoalEnvelope(
        goal_id="g_stag",
        initial_state_ref=state.state_hash,
        desired_state=(crit.predicate,),
        success_criteria=(crit,),
    )
    reg = prod_m.CapabilityRegistry([cap])
    env = prod_p.Environment(state, reg)

    ctrl = prod_ac.AutonomousClosureController(reg, max_stagnation_steps=2)
    res = ctrl.run(goal, env)

    _assert_conformance(res, env, expected)
