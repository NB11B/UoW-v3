"""Generate frozen qualification reference vectors from the qualified UoW-v2 shadow reference.

Usage:
    python qualification/generate_autonomy_reference_vectors.py \\
        --reference ..\\UoW-v2-qualified \\
        --output tests\\fixtures\\autonomy_reference_c559d6c.json
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from uow.state import WorldState, canonical_json

EXPECTED_COMMIT = "c559d6c1c962b436fa9c05c68de42f29afa4ad6f"


def _extract_observables(res, env) -> dict:
    obs = {
        "success": bool(res.success),
        "terminal_state": str(res.terminal_state.value),
        "work_count": len(res.work_transcript),
        "work_transcript": list(res.work_transcript),
        "authority_trace": list(res.authority_trace),
        "budget_steps": int(res.budget_usage.steps),
        "budget_cost": float(res.budget_usage.cost),
        "budget_energy": float(res.budget_usage.energy),
        "budget_repairs": int(res.budget_usage.repairs),
        "budget_adaptations": int(res.budget_usage.adaptations),
        "final_attributes": dict(env.state.attributes),
        "final_state_hash": str(env.state.state_hash),
        "transitions": list(res.transitions),
        "rejection_reasons": list(res.rejection_reasons),
        "has_closure_certificate": res.closure_certificate is not None,
        "has_deficit_certificate": res.deficit_certificate is not None,
    }
    if res.deficit_certificate is not None:
        obs["deficit_basis_id"] = str(res.deficit_certificate.basis_id)
        obs["deficit_missing_effects"] = sorted(res.deficit_certificate.proof.missing_effects)
    return obs


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate frozen reference vectors from qualified shadow worktree.")
    parser.add_argument("--reference", required=True, help="Path to qualified reference repository/worktree.")
    parser.add_argument("--output", required=True, help="Path to write the fixture JSON.")
    args = parser.parse_args()

    ref_path = Path(args.reference).resolve()
    if not ref_path.exists():
        raise FileNotFoundError(f"Reference path does not exist: {ref_path}")

    # 1. Assert reference commit
    res = subprocess.run(
        ["git", "-C", str(ref_path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    actual_commit = res.stdout.strip()
    if actual_commit != EXPECTED_COMMIT:
        raise ValueError(f"Reference HEAD mismatch: expected {EXPECTED_COMMIT}, found {actual_commit}")

    # 2. Add shadow package to sys.path
    shadow_python = ref_path / "architecture" / "shadow" / "python"
    if not shadow_python.exists():
        raise FileNotFoundError(f"Shadow python package directory not found: {shadow_python}")
    sys.path.insert(0, str(shadow_python))

    import uow_shadow.autonomous_closure as shadow_ac
    import uow_shadow.goal_decomposition as shadow_gd

    cases: dict[str, dict] = {}

    # Case 1: goal_already_satisfied
    state1 = WorldState(attributes={"status": "done"})
    crit1 = shadow_gd.Criterion("c1", shadow_gd.StatePredicate("status", shadow_gd.PredicateOp.EQ, "done"))
    goal1 = shadow_gd.GoalEnvelope(
        goal_id="g_satisfied",
        initial_state_ref=state1.state_hash,
        desired_state=(crit1.predicate,),
        success_criteria=(crit1,),
    )
    reg1 = shadow_gd.CapabilityRegistry([])
    env1 = shadow_ac.Environment(state1, reg1)
    res1 = shadow_ac.AutonomousClosureController(reg1).run(goal1, env1)
    cases["goal_already_satisfied"] = _extract_observables(res1, env1)

    # Case 2: single_step_completion
    state2 = WorldState(attributes={"status": "init"})
    crit2 = shadow_gd.Criterion("c1", shadow_gd.StatePredicate("status", shadow_gd.PredicateOp.EQ, "ready"))
    cap2 = shadow_gd.CapabilityDescriptor("init_cap", "Init", effects=(crit2.predicate,))
    goal2 = shadow_gd.GoalEnvelope(
        goal_id="g_single",
        initial_state_ref=state2.state_hash,
        desired_state=(crit2.predicate,),
        success_criteria=(crit2,),
    )
    reg2 = shadow_gd.CapabilityRegistry([cap2])
    env2 = shadow_ac.Environment(state2, reg2)
    res2 = shadow_ac.AutonomousClosureController(reg2).run(goal2, env2)
    cases["single_step_completion"] = _extract_observables(res2, env2)

    # Case 3: multi_step_dependency
    state3 = WorldState(attributes={"stepA": "pending", "stepB": "pending"})
    crit3_a = shadow_gd.StatePredicate("stepA", shadow_gd.PredicateOp.EQ, "done")
    crit3_b = shadow_gd.StatePredicate("stepB", shadow_gd.PredicateOp.EQ, "done")
    cap3_a = shadow_gd.CapabilityDescriptor("cap_a", "Cap A", effects=(crit3_a,))
    cap3_b = shadow_gd.CapabilityDescriptor("cap_b", "Cap B", preconditions=(crit3_a,), effects=(crit3_b,))
    crit3 = shadow_gd.Criterion("cb", crit3_b)
    goal3 = shadow_gd.GoalEnvelope(
        goal_id="g_multi",
        initial_state_ref=state3.state_hash,
        desired_state=(crit3_b,),
        success_criteria=(crit3,),
    )
    reg3 = shadow_gd.CapabilityRegistry([cap3_a, cap3_b])
    env3 = shadow_ac.Environment(state3, reg3)
    res3 = shadow_ac.AutonomousClosureController(reg3).run(goal3, env3)
    cases["multi_step_dependency"] = _extract_observables(res3, env3)

    # Case 4: missing_capability
    state4 = WorldState(attributes={"status": "init"})
    crit4 = shadow_gd.Criterion("c_miss", shadow_gd.StatePredicate("missing_attr", shadow_gd.PredicateOp.EQ, "ready"))
    goal4 = shadow_gd.GoalEnvelope(
        goal_id="g_miss",
        initial_state_ref=state4.state_hash,
        desired_state=(crit4.predicate,),
        success_criteria=(crit4,),
    )
    reg4 = shadow_gd.CapabilityRegistry([])
    env4 = shadow_ac.Environment(state4, reg4)
    res4 = shadow_ac.AutonomousClosureController(reg4).run(goal4, env4)
    cases["missing_capability"] = _extract_observables(res4, env4)

    # Case 5: semantic_non_derivability
    state5 = WorldState(attributes={"status": "init"})
    crit5 = shadow_gd.Criterion("c_unrep", shadow_gd.StatePredicate("effect:teleport", shadow_gd.PredicateOp.EQ, "on"))
    goal5 = shadow_gd.GoalEnvelope(
        goal_id="g_unrep",
        initial_state_ref=state5.state_hash,
        desired_state=(crit5.predicate,),
        success_criteria=(crit5,),
        required_effects=("teleport",),
    )
    reg5 = shadow_gd.CapabilityRegistry([])
    env5 = shadow_ac.Environment(state5, reg5)
    res5 = shadow_ac.AutonomousClosureController(reg5).run(goal5, env5)
    cases["semantic_non_derivability"] = _extract_observables(res5, env5)

    # Case 6: authority_rejection
    state6 = WorldState(attributes={"restricted": "locked"})
    crit6 = shadow_gd.Criterion("c_auth", shadow_gd.StatePredicate("restricted", shadow_gd.PredicateOp.EQ, "open"))
    cap6 = shadow_gd.CapabilityDescriptor("unauth_cap", "Unauth", effects=(crit6.predicate,), required_authority=("top_secret",))
    goal6 = shadow_gd.GoalEnvelope(
        goal_id="g_auth",
        initial_state_ref=state6.state_hash,
        desired_state=(crit6.predicate,),
        success_criteria=(crit6,),
        allowed_authority=shadow_gd.AuthorityScope(("public_only",)),
    )
    reg6 = shadow_gd.CapabilityRegistry([cap6])
    env6 = shadow_ac.Environment(state6, reg6)
    res6 = shadow_ac.AutonomousClosureController(reg6).run(goal6, env6)
    cases["authority_rejection"] = _extract_observables(res6, env6)

    # Case 7: resource_exhaustion
    state7 = WorldState(attributes={"step": 0})
    crit7 = shadow_gd.Criterion("c_steps", shadow_gd.StatePredicate("step", shadow_gd.PredicateOp.EQ, 10))
    cap7 = shadow_gd.CapabilityDescriptor("cap_step", "Step", effects=(crit7.predicate,))
    goal7 = shadow_gd.GoalEnvelope(
        goal_id="g_budget",
        initial_state_ref=state7.state_hash,
        desired_state=(crit7.predicate,),
        success_criteria=(crit7,),
    )
    reg7 = shadow_gd.CapabilityRegistry([cap7])
    env7 = shadow_ac.Environment(state7, reg7)
    budget7 = shadow_ac.AutonomyBudget(max_steps=0)
    res7 = shadow_ac.AutonomousClosureController(reg7, budget=budget7).run(goal7, env7)
    cases["resource_exhaustion"] = _extract_observables(res7, env7)

    # Case 8: bounded_repair_on_transient_failure
    state8 = WorldState(attributes={"stepA": "pending", "stepB": "pending"})
    crit8_a = shadow_gd.StatePredicate("stepA", shadow_gd.PredicateOp.EQ, "done")
    crit8_b = shadow_gd.StatePredicate("stepB", shadow_gd.PredicateOp.EQ, "done")
    cap8_a = shadow_gd.CapabilityDescriptor("cap_a", "Cap A", effects=(crit8_a,))
    cap8_b = shadow_gd.CapabilityDescriptor("cap_b", "Cap B", preconditions=(crit8_a,), effects=(crit8_b,))
    crit8 = shadow_gd.Criterion("c_b", crit8_b)
    goal8 = shadow_gd.GoalEnvelope(
        goal_id="g_repair",
        initial_state_ref=state8.state_hash,
        desired_state=(crit8_b,),
        success_criteria=(crit8,),
    )
    reg8 = shadow_gd.CapabilityRegistry([cap8_a, cap8_b])
    env8 = shadow_ac.Environment(state8, reg8)
    fails8 = {"cap_b": 0}
    orig_exec8 = env8.execute_work_item
    def failing8(item, authority):
        if item.work_kind == "cap_b" and fails8["cap_b"] == 0:
            fails8["cap_b"] += 1
            env8.advance_step()
            return shadow_ac.ExecutionOutcome(False, env8.state, 1.0, 1.0, "TRANSIENT_FAULT", item.work_id)
        return orig_exec8(item, authority)
    env8.execute_work_item = failing8
    res8 = shadow_ac.AutonomousClosureController(reg8).run(goal8, env8)
    cases["bounded_repair_on_transient_failure"] = _extract_observables(res8, env8)

    # Case 9: repeated_failure_routes_to_adaptation
    state9 = WorldState(attributes={"step": "pending"})
    crit9 = shadow_gd.Criterion("c_adapt", shadow_gd.StatePredicate("step", shadow_gd.PredicateOp.EQ, "done"))
    cap9 = shadow_gd.CapabilityDescriptor("flaky_cap", "Flaky", effects=(crit9.predicate,))
    goal9 = shadow_gd.GoalEnvelope(
        goal_id="g_adapt",
        initial_state_ref=state9.state_hash,
        desired_state=(crit9.predicate,),
        success_criteria=(crit9,),
    )
    reg9 = shadow_gd.CapabilityRegistry([cap9])
    env9 = shadow_ac.Environment(state9, reg9)
    def perm_fail9(item, authority):
        env9.advance_step()
        return shadow_ac.ExecutionOutcome(False, env9.state, 1.0, 1.0, "PERM_FAULT", item.work_id)
    env9.execute_work_item = perm_fail9
    res9 = shadow_ac.AutonomousClosureController(reg9, budget=shadow_ac.AutonomyBudget(max_steps=15)).run(goal9, env9)
    cases["repeated_failure_routes_to_adaptation"] = _extract_observables(res9, env9)

    # Case 10: provider_disappearance
    state10 = WorldState(attributes={"step": "pending"})
    crit10 = shadow_gd.Criterion("c_vanish", shadow_gd.StatePredicate("step", shadow_gd.PredicateOp.EQ, "done"))
    cap10 = shadow_gd.CapabilityDescriptor("cap_vanish", "Vanish", effects=(crit10.predicate,))
    goal10 = shadow_gd.GoalEnvelope(
        goal_id="g_vanish",
        initial_state_ref=state10.state_hash,
        desired_state=(crit10.predicate,),
        success_criteria=(crit10,),
    )
    reg10 = shadow_gd.CapabilityRegistry([cap10])
    env10 = shadow_ac.Environment(state10, reg10)
    env10.failed_capabilities.add("cap_vanish")
    res10 = shadow_ac.AutonomousClosureController(reg10).run(goal10, env10)
    cases["provider_disappearance"] = _extract_observables(res10, env10)

    # Case 11: environmental_state_change
    state11 = WorldState(attributes={"step": "pending"})
    crit11 = shadow_gd.Criterion("c_shift", shadow_gd.StatePredicate("step", shadow_gd.PredicateOp.EQ, "done"))
    cap11 = shadow_gd.CapabilityDescriptor("cap_shift", "Shift", effects=(crit11.predicate,))
    goal11 = shadow_gd.GoalEnvelope(
        goal_id="g_shift",
        initial_state_ref=state11.state_hash,
        desired_state=(crit11.predicate,),
        success_criteria=(crit11,),
    )
    reg11 = shadow_gd.CapabilityRegistry([cap11])
    env11 = shadow_ac.Environment(state11, reg11)
    orig_exec11 = env11.execute_work_item
    def shifting_exec11(item, auth):
        res = orig_exec11(item, auth)
        env11.state = WorldState(attributes={"step": "shifted"})
        return res
    env11.execute_work_item = shifting_exec11
    res11 = shadow_ac.AutonomousClosureController(reg11, budget=shadow_ac.AutonomyBudget(max_steps=8)).run(goal11, env11)
    cases["environmental_state_change"] = _extract_observables(res11, env11)

    # Case 12: cycle_stagnation_termination
    state12 = WorldState(attributes={"step": "pending"})
    crit12 = shadow_gd.Criterion("c_stag", shadow_gd.StatePredicate("target", shadow_gd.PredicateOp.EQ, "reached"))
    cap12 = shadow_gd.CapabilityDescriptor("dummy_cap", "Dummy", effects=(shadow_gd.StatePredicate("irrelevant", shadow_gd.PredicateOp.EQ, "val"),))
    goal12 = shadow_gd.GoalEnvelope(
        goal_id="g_stag",
        initial_state_ref=state12.state_hash,
        desired_state=(crit12.predicate,),
        success_criteria=(crit12,),
    )
    reg12 = shadow_gd.CapabilityRegistry([cap12])
    env12 = shadow_ac.Environment(state12, reg12)
    ctrl12 = shadow_ac.AutonomousClosureController(reg12, max_stagnation_steps=2)
    res12 = ctrl12.run(goal12, env12)
    cases["cycle_stagnation_termination"] = _extract_observables(res12, env12)

    cases_json = canonical_json(cases)
    fixture_hash = hashlib.sha256(cases_json.encode("utf-8")).hexdigest()

    output_payload = {
        "reference_commit": EXPECTED_COMMIT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixture_sha256": fixture_hash,
        "cases": cases,
    }

    out_file = Path(args.output).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")
    print(f"Successfully generated {len(cases)} reference vectors into {out_file}")
    print(f"Fixture SHA-256: {fixture_hash}")


if __name__ == "__main__":
    main()
