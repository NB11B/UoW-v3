"""Differential reference conformance suite comparing uow.autonomy against qualified shadow reference."""
from __future__ import annotations

from pathlib import Path
import sys
import pytest

from uow.state import WorldState

# Dynamically import qualified reference from worktree
QUALIFIED_PATH = str(Path(r"..\UoW-v2-qualified\architecture\shadow\python").resolve())
if QUALIFIED_PATH not in sys.path:
    sys.path.insert(0, QUALIFIED_PATH)

import uow_shadow.autonomous_closure as shadow_ac
import uow_shadow.goal_decomposition as shadow_gd
import uow.autonomy.controller as prod_ac
import uow.autonomy.model as prod_m
import uow.autonomy.ports as prod_p


def test_conformance_goal_already_satisfied():
    """Case 1: Goal already satisfied in initial observation (NO_OP)."""
    state = WorldState(attributes={"status": "done"})

    crit_s = shadow_gd.Criterion("c1", shadow_gd.StatePredicate("status", shadow_gd.PredicateOp.EQ, "done"))
    goal_s = shadow_gd.GoalEnvelope(
        goal_id="g_satisfied",
        initial_state_ref=state.state_hash,
        desired_state=(crit_s.predicate,),
        success_criteria=(crit_s,),
    )
    reg_s = shadow_gd.CapabilityRegistry([])
    env_s = shadow_ac.Environment(state, reg_s)
    res_s = shadow_ac.AutonomousClosureController(reg_s).run(goal_s, env_s)

    crit_p = prod_m.Criterion("c1", prod_m.StatePredicate("status", prod_m.PredicateOp.EQ, "done"))
    goal_p = prod_m.GoalEnvelope(
        goal_id="g_satisfied",
        initial_state_ref=state.state_hash,
        desired_state=(crit_p.predicate,),
        success_criteria=(crit_p,),
    )
    reg_p = prod_m.CapabilityRegistry([])
    env_p = prod_p.Environment(state, reg_p)
    res_p = prod_ac.AutonomousClosureController(reg_p).run(goal_p, env_p)

    assert res_s.success == res_p.success == True
    assert res_s.terminal_state.value == res_p.terminal_state.value == "COMPLETE"
    assert env_s.state.state_hash == env_p.state.state_hash
    assert len(res_p.work_transcript) == len(res_s.work_transcript) == 0


def test_conformance_single_step_completion():
    """Case 2: Single-step deterministic completion."""
    state = WorldState(attributes={"status": "init"})

    crit_s = shadow_gd.Criterion("c1", shadow_gd.StatePredicate("status", shadow_gd.PredicateOp.EQ, "ready"))
    cap_s = shadow_gd.CapabilityDescriptor("init_cap", "Init", effects=(crit_s.predicate,))
    goal_s = shadow_gd.GoalEnvelope(
        goal_id="g_single",
        initial_state_ref=state.state_hash,
        desired_state=(crit_s.predicate,),
        success_criteria=(crit_s,),
    )
    reg_s = shadow_gd.CapabilityRegistry([cap_s])
    env_s = shadow_ac.Environment(state, reg_s)
    res_s = shadow_ac.AutonomousClosureController(reg_s).run(goal_s, env_s)

    crit_p = prod_m.Criterion("c1", prod_m.StatePredicate("status", prod_m.PredicateOp.EQ, "ready"))
    cap_p = prod_m.CapabilityDescriptor("init_cap", "Init", effects=(crit_p.predicate,))
    goal_p = prod_m.GoalEnvelope(
        goal_id="g_single",
        initial_state_ref=state.state_hash,
        desired_state=(crit_p.predicate,),
        success_criteria=(crit_p,),
    )
    reg_p = prod_m.CapabilityRegistry([cap_p])
    env_p = prod_p.Environment(state, reg_p)
    res_p = prod_ac.AutonomousClosureController(reg_p).run(goal_p, env_p)

    assert res_s.success == res_p.success == True
    assert res_s.terminal_state.value == res_p.terminal_state.value == "COMPLETE"
    assert env_s.state.state_hash == env_p.state.state_hash
    assert res_p.budget_usage.cost == res_s.budget_usage.cost


def test_conformance_multi_step_dependency():
    """Case 3: Multi-step causal DAG synthesis and topological ordering."""
    state = WorldState(attributes={"stepA": "pending", "stepB": "pending"})

    critA_s = shadow_gd.StatePredicate("stepA", shadow_gd.PredicateOp.EQ, "done")
    critB_s = shadow_gd.StatePredicate("stepB", shadow_gd.PredicateOp.EQ, "done")
    capA_s = shadow_gd.CapabilityDescriptor("cap_a", "Cap A", effects=(critA_s,))
    capB_s = shadow_gd.CapabilityDescriptor("cap_b", "Cap B", preconditions=(critA_s,), effects=(critB_s,))
    crit_s = shadow_gd.Criterion("cb", critB_s)
    goal_s = shadow_gd.GoalEnvelope(
        goal_id="g_multi",
        initial_state_ref=state.state_hash,
        desired_state=(critB_s,),
        success_criteria=(crit_s,),
    )
    reg_s = shadow_gd.CapabilityRegistry([capA_s, capB_s])
    env_s = shadow_ac.Environment(state, reg_s)
    res_s = shadow_ac.AutonomousClosureController(reg_s).run(goal_s, env_s)

    critA_p = prod_m.StatePredicate("stepA", prod_m.PredicateOp.EQ, "done")
    critB_p = prod_m.StatePredicate("stepB", prod_m.PredicateOp.EQ, "done")
    capA_p = prod_m.CapabilityDescriptor("cap_a", "Cap A", effects=(critA_p,))
    capB_p = prod_m.CapabilityDescriptor("cap_b", "Cap B", preconditions=(critA_p,), effects=(critB_p,))
    crit_p = prod_m.Criterion("cb", critB_p)
    goal_p = prod_m.GoalEnvelope(
        goal_id="g_multi",
        initial_state_ref=state.state_hash,
        desired_state=(critB_p,),
        success_criteria=(crit_p,),
    )
    reg_p = prod_m.CapabilityRegistry([capA_p, capB_p])
    env_p = prod_p.Environment(state, reg_p)
    res_p = prod_ac.AutonomousClosureController(reg_p).run(goal_p, env_p)

    assert res_s.success == res_p.success == True
    assert res_s.terminal_state.value == res_p.terminal_state.value == "COMPLETE"
    assert env_s.state.state_hash == env_p.state.state_hash
    # Both executed cap_a before cap_b
    assert len(res_p.work_transcript) == len(res_s.work_transcript) == 2


def test_conformance_missing_capability():
    """Case 4: Goal requires unavailable capability."""
    state = WorldState(attributes={"status": "init"})

    crit_s = shadow_gd.Criterion("c_miss", shadow_gd.StatePredicate("missing_attr", shadow_gd.PredicateOp.EQ, "ready"))
    goal_s = shadow_gd.GoalEnvelope(
        goal_id="g_miss",
        initial_state_ref=state.state_hash,
        desired_state=(crit_s.predicate,),
        success_criteria=(crit_s,),
    )
    reg_s = shadow_gd.CapabilityRegistry([])
    env_s = shadow_ac.Environment(state, reg_s)
    res_s = shadow_ac.AutonomousClosureController(reg_s).run(goal_s, env_s)

    crit_p = prod_m.Criterion("c_miss", prod_m.StatePredicate("missing_attr", prod_m.PredicateOp.EQ, "ready"))
    goal_p = prod_m.GoalEnvelope(
        goal_id="g_miss",
        initial_state_ref=state.state_hash,
        desired_state=(crit_p.predicate,),
        success_criteria=(crit_p,),
    )
    reg_p = prod_m.CapabilityRegistry([])
    env_p = prod_p.Environment(state, reg_p)
    res_p = prod_ac.AutonomousClosureController(reg_p).run(goal_p, env_p)

    assert res_s.success == res_p.success == False
    assert res_s.terminal_state.value == res_p.terminal_state.value == "FAILED"
    assert any("CAPABILITY" in r for r in res_p.rejection_reasons)


def test_conformance_semantic_non_derivability():
    """Case 5: Open-world semantic deficit certification."""
    state = WorldState(attributes={"status": "init"})

    crit_s = shadow_gd.Criterion("c_unrep", shadow_gd.StatePredicate("effect:teleport", shadow_gd.PredicateOp.EQ, "on"))
    goal_s = shadow_gd.GoalEnvelope(
        goal_id="g_unrep",
        initial_state_ref=state.state_hash,
        desired_state=(crit_s.predicate,),
        success_criteria=(crit_s,),
        required_effects=("teleport",),
    )
    reg_s = shadow_gd.CapabilityRegistry([])
    env_s = shadow_ac.Environment(state, reg_s)
    res_s = shadow_ac.AutonomousClosureController(reg_s).run(goal_s, env_s)

    crit_p = prod_m.Criterion("c_unrep", prod_m.StatePredicate("effect:teleport", prod_m.PredicateOp.EQ, "on"))
    goal_p = prod_m.GoalEnvelope(
        goal_id="g_unrep",
        initial_state_ref=state.state_hash,
        desired_state=(crit_p.predicate,),
        success_criteria=(crit_p,),
        required_effects=("teleport",),
    )
    reg_p = prod_m.CapabilityRegistry([])
    env_p = prod_p.Environment(state, reg_p)
    res_p = prod_ac.AutonomousClosureController(reg_p).run(goal_p, env_p)

    assert res_s.success == res_p.success == False
    assert res_s.terminal_state.value == res_p.terminal_state.value == "FAILED"
    assert res_s.deficit_certificate is not None
    assert res_p.deficit_certificate is not None
    assert res_p.deficit_certificate.basis_id == res_s.deficit_certificate.basis_id
    assert "teleport" in res_p.deficit_certificate.proof.missing_effects


def test_conformance_authority_rejection():
    """Case 6: Capability requires unauthorized scope."""
    state = WorldState(attributes={"restricted": "locked"})

    crit_s = shadow_gd.Criterion("c_auth", shadow_gd.StatePredicate("restricted", shadow_gd.PredicateOp.EQ, "open"))
    cap_s = shadow_gd.CapabilityDescriptor("unauth_cap", "Unauth", effects=(crit_s.predicate,), required_authority=("top_secret",))
    goal_s = shadow_gd.GoalEnvelope(
        goal_id="g_auth",
        initial_state_ref=state.state_hash,
        desired_state=(crit_s.predicate,),
        success_criteria=(crit_s,),
        allowed_authority=shadow_gd.AuthorityScope(("public_only",)),
    )
    reg_s = shadow_gd.CapabilityRegistry([cap_s])
    env_s = shadow_ac.Environment(state, reg_s)
    res_s = shadow_ac.AutonomousClosureController(reg_s).run(goal_s, env_s)

    crit_p = prod_m.Criterion("c_auth", prod_m.StatePredicate("restricted", prod_m.PredicateOp.EQ, "open"))
    cap_p = prod_m.CapabilityDescriptor("unauth_cap", "Unauth", effects=(crit_p.predicate,), required_authority=("top_secret",))
    goal_p = prod_m.GoalEnvelope(
        goal_id="g_auth",
        initial_state_ref=state.state_hash,
        desired_state=(crit_p.predicate,),
        success_criteria=(crit_p,),
        allowed_authority=prod_m.AuthorityScope(("public_only",)),
    )
    reg_p = prod_m.CapabilityRegistry([cap_p])
    env_p = prod_p.Environment(state, reg_p)
    res_p = prod_ac.AutonomousClosureController(reg_p).run(goal_p, env_p)

    assert res_s.success == res_p.success == False
    assert any("UNAUTHORIZED" in r for r in res_p.rejection_reasons)


def test_conformance_resource_exhaustion():
    """Case 7: Step budget limit halts execution."""
    state = WorldState(attributes={"step": 0})

    crit_s = shadow_gd.Criterion("c_steps", shadow_gd.StatePredicate("step", shadow_gd.PredicateOp.EQ, 10))
    cap_s = shadow_gd.CapabilityDescriptor("cap_step", "Step", effects=(crit_s.predicate,))
    goal_s = shadow_gd.GoalEnvelope(
        goal_id="g_budget",
        initial_state_ref=state.state_hash,
        desired_state=(crit_s.predicate,),
        success_criteria=(crit_s,),
    )
    reg_s = shadow_gd.CapabilityRegistry([cap_s])
    env_s = shadow_ac.Environment(state, reg_s)
    budget_s = shadow_ac.AutonomyBudget(max_steps=0)
    res_s = shadow_ac.AutonomousClosureController(reg_s, budget=budget_s).run(goal_s, env_s)

    crit_p = prod_m.Criterion("c_steps", prod_m.StatePredicate("step", prod_m.PredicateOp.EQ, 10))
    cap_p = prod_m.CapabilityDescriptor("cap_step", "Step", effects=(crit_p.predicate,))
    goal_p = prod_m.GoalEnvelope(
        goal_id="g_budget",
        initial_state_ref=state.state_hash,
        desired_state=(crit_p.predicate,),
        success_criteria=(crit_p,),
    )
    reg_p = prod_m.CapabilityRegistry([cap_p])
    env_p = prod_p.Environment(state, reg_p)
    budget_p = prod_m.AutonomyBudget(max_steps=0)
    res_p = prod_ac.AutonomousClosureController(reg_p, budget=budget_p).run(goal_p, env_p)

    assert res_s.success == res_p.success == False
    assert res_s.terminal_state.value == res_p.terminal_state.value == "FAILED"
    assert any("EXCEEDED_MAX_STEPS" in r for r in res_p.rejection_reasons)


def test_conformance_bounded_repair_on_transient_failure():
    """Case 8 & 9: Execution failure recovered via surgical bounded repair."""
    state = WorldState(attributes={"stepA": "pending", "stepB": "pending"})

    # Setup for shadow
    critA_s = shadow_gd.StatePredicate("stepA", shadow_gd.PredicateOp.EQ, "done")
    critB_s = shadow_gd.StatePredicate("stepB", shadow_gd.PredicateOp.EQ, "done")
    capA_s = shadow_gd.CapabilityDescriptor("cap_a", "Cap A", effects=(critA_s,))
    capB_s = shadow_gd.CapabilityDescriptor("cap_b", "Cap B", preconditions=(critA_s,), effects=(critB_s,))
    crit_s = shadow_gd.Criterion("c_b", critB_s)
    goal_s = shadow_gd.GoalEnvelope(
        goal_id="g_repair",
        initial_state_ref=state.state_hash,
        desired_state=(critB_s,),
        success_criteria=(crit_s,),
    )
    reg_s = shadow_gd.CapabilityRegistry([capA_s, capB_s])
    env_s = shadow_ac.Environment(state, reg_s)

    fails_s = {"cap_b": 0}
    orig_exec_s = env_s.execute_work_item
    def failing_s(item, authority):
        if item.work_kind == "cap_b" and fails_s["cap_b"] == 0:
            fails_s["cap_b"] += 1
            env_s.advance_step()
            return shadow_ac.ExecutionOutcome(False, env_s.state, 1.0, 1.0, "TRANSIENT_FAULT", item.work_id)
        return orig_exec_s(item, authority)
    env_s.execute_work_item = failing_s

    res_s = shadow_ac.AutonomousClosureController(reg_s).run(goal_s, env_s)

    # Setup for production
    critA_p = prod_m.StatePredicate("stepA", prod_m.PredicateOp.EQ, "done")
    critB_p = prod_m.StatePredicate("stepB", prod_m.PredicateOp.EQ, "done")
    capA_p = prod_m.CapabilityDescriptor("cap_a", "Cap A", effects=(critA_p,))
    capB_p = prod_m.CapabilityDescriptor("cap_b", "Cap B", preconditions=(critA_p,), effects=(critB_p,))
    crit_p = prod_m.Criterion("c_b", critB_p)
    goal_p = prod_m.GoalEnvelope(
        goal_id="g_repair",
        initial_state_ref=state.state_hash,
        desired_state=(critB_p,),
        success_criteria=(crit_p,),
    )
    reg_p = prod_m.CapabilityRegistry([capA_p, capB_p])
    env_p = prod_p.Environment(state, reg_p)

    fails_p = {"cap_b": 0}
    orig_exec_p = env_p.execute_work_item
    def failing_p(item, authority):
        if item.work_kind == "cap_b" and fails_p["cap_b"] == 0:
            fails_p["cap_b"] += 1
            env_p.advance_step()
            return prod_p.ExecutionOutcome(False, env_p.state, 1.0, 1.0, "TRANSIENT_FAULT", item.work_id)
        return orig_exec_p(item, authority)
    env_p.execute_work_item = failing_p

    res_p = prod_ac.AutonomousClosureController(reg_p).run(goal_p, env_p)

    assert res_s.success == res_p.success == True
    assert res_s.terminal_state.value == res_p.terminal_state.value == "COMPLETE"
    assert res_s.budget_usage.repairs == res_p.budget_usage.repairs == 1
    assert env_s.state.state_hash == env_p.state.state_hash


def test_conformance_repeated_failure_routes_to_adaptation():
    """Case 10 & 11: Repeated execution failure triggers adaptation routing."""
    state = WorldState(attributes={"step": "pending"})

    crit_s = shadow_gd.Criterion("c_adapt", shadow_gd.StatePredicate("step", shadow_gd.PredicateOp.EQ, "done"))
    cap_s = shadow_gd.CapabilityDescriptor("flaky_cap", "Flaky", effects=(crit_s.predicate,))
    goal_s = shadow_gd.GoalEnvelope(
        goal_id="g_adapt",
        initial_state_ref=state.state_hash,
        desired_state=(crit_s.predicate,),
        success_criteria=(crit_s,),
    )
    reg_s = shadow_gd.CapabilityRegistry([cap_s])
    env_s = shadow_ac.Environment(state, reg_s)

    def perm_fail_s(item, authority):
        env_s.advance_step()
        return shadow_ac.ExecutionOutcome(False, env_s.state, 1.0, 1.0, "PERM_FAULT", item.work_id)
    env_s.execute_work_item = perm_fail_s
    res_s = shadow_ac.AutonomousClosureController(reg_s, budget=shadow_ac.AutonomyBudget(max_steps=15)).run(goal_s, env_s)

    crit_p = prod_m.Criterion("c_adapt", prod_m.StatePredicate("step", prod_m.PredicateOp.EQ, "done"))
    cap_p = prod_m.CapabilityDescriptor("flaky_cap", "Flaky", effects=(crit_p.predicate,))
    goal_p = prod_m.GoalEnvelope(
        goal_id="g_adapt",
        initial_state_ref=state.state_hash,
        desired_state=(crit_p.predicate,),
        success_criteria=(crit_p,),
    )
    reg_p = prod_m.CapabilityRegistry([cap_p])
    env_p = prod_p.Environment(state, reg_p)

    def perm_fail_p(item, authority):
        env_p.advance_step()
        return prod_p.ExecutionOutcome(False, env_p.state, 1.0, 1.0, "PERM_FAULT", item.work_id)
    env_p.execute_work_item = perm_fail_p
    res_p = prod_ac.AutonomousClosureController(reg_p, budget=prod_m.AutonomyBudget(max_steps=15)).run(goal_p, env_p)

    assert res_s.success == res_p.success == False
    assert res_s.terminal_state.value == res_p.terminal_state.value == "FAILED"
    assert res_s.transitions == res_p.transitions
    assert res_s.budget_usage.repairs == res_p.budget_usage.repairs


def test_conformance_provider_disappearance():
    """Case 12: Dynamic capability failure mid-execution."""
    state = WorldState(attributes={"step": "pending"})

    crit_p = prod_m.Criterion("c_vanish", prod_m.StatePredicate("step", prod_m.PredicateOp.EQ, "done"))
    cap_p = prod_m.CapabilityDescriptor("cap_vanish", "Vanish", effects=(crit_p.predicate,))
    goal_p = prod_m.GoalEnvelope(
        goal_id="g_vanish",
        initial_state_ref=state.state_hash,
        desired_state=(crit_p.predicate,),
        success_criteria=(crit_p,),
    )
    reg_p = prod_m.CapabilityRegistry([cap_p])
    env_p = prod_p.Environment(state, reg_p)
    # Fail capability before execute
    env_p.failed_capabilities.add("cap_vanish")

    res_p = prod_ac.AutonomousClosureController(reg_p).run(goal_p, env_p)
    assert res_p.success is False
    assert any("CAPABILITY_UNAVAILABLE" in r for r in res_p.rejection_reasons)


def test_conformance_environmental_state_change():
    """Case 13: Adversarial world shift detected in VERIFY triggers re-observation."""
    state = WorldState(attributes={"step": "pending"})

    # Shadow run
    crit_s = shadow_gd.Criterion("c_shift", shadow_gd.StatePredicate("step", shadow_gd.PredicateOp.EQ, "done"))
    cap_s = shadow_gd.CapabilityDescriptor("cap_shift", "Shift", effects=(crit_s.predicate,))
    goal_s = shadow_gd.GoalEnvelope(
        goal_id="g_shift",
        initial_state_ref=state.state_hash,
        desired_state=(crit_s.predicate,),
        success_criteria=(crit_s,),
    )
    reg_s = shadow_gd.CapabilityRegistry([cap_s])
    env_s = shadow_ac.Environment(state, reg_s)
    orig_exec_s = env_s.execute_work_item
    def shifting_exec_s(item, auth):
        res = orig_exec_s(item, auth)
        env_s.state = WorldState(attributes={"step": "shifted"})
        return res
    env_s.execute_work_item = shifting_exec_s
    res_s = shadow_ac.AutonomousClosureController(reg_s, budget=shadow_ac.AutonomyBudget(max_steps=8)).run(goal_s, env_s)

    # Prod run
    crit_p = prod_m.Criterion("c_shift", prod_m.StatePredicate("step", prod_m.PredicateOp.EQ, "done"))
    cap_p = prod_m.CapabilityDescriptor("cap_shift", "Shift", effects=(crit_p.predicate,))
    goal_p = prod_m.GoalEnvelope(
        goal_id="g_shift",
        initial_state_ref=state.state_hash,
        desired_state=(crit_p.predicate,),
        success_criteria=(crit_p,),
    )
    reg_p = prod_m.CapabilityRegistry([cap_p])
    env_p = prod_p.Environment(state, reg_p)
    orig_exec_p = env_p.execute_work_item
    def shifting_exec_p(item, auth):
        res = orig_exec_p(item, auth)
        env_p.state = WorldState(attributes={"step": "shifted"})
        return res
    env_p.execute_work_item = shifting_exec_p
    res_p = prod_ac.AutonomousClosureController(reg_p, budget=prod_m.AutonomyBudget(max_steps=8)).run(goal_p, env_p)

    # Both must detect shift and transition to OBSERVE from VERIFY
    assert res_s.success == res_p.success == False
    assert res_s.transitions == res_p.transitions
    assert "VERIFY->OBSERVE" in res_p.transitions


def test_conformance_cycle_stagnation_termination():
    """Case 14: Distance metric non-progress detects stagnation and halts."""
    state = WorldState(attributes={"step": "pending"})

    crit_p = prod_m.Criterion("c_stag", prod_m.StatePredicate("target", prod_m.PredicateOp.EQ, "reached"))
    cap_p = prod_m.CapabilityDescriptor("dummy_cap", "Dummy", effects=(prod_m.StatePredicate("irrelevant", prod_m.PredicateOp.EQ, "val"),))
    goal_p = prod_m.GoalEnvelope(
        goal_id="g_stag",
        initial_state_ref=state.state_hash,
        desired_state=(crit_p.predicate,),
        success_criteria=(crit_p,),
    )
    reg_p = prod_m.CapabilityRegistry([cap_p])
    env_p = prod_p.Environment(state, reg_p)

    # Force tracker stagnation limit 2
    ctrl_p = prod_ac.AutonomousClosureController(reg_p, max_stagnation_steps=2)
    res_p = ctrl_p.run(goal_p, env_p)

    assert res_p.success is False
    assert res_p.terminal_state.value == "FAILED"
