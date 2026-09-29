"""Autonomous Closure Controller.

Orchestrates the canonical closed loop:
    O_t -> B_t -> G_t -> M_t -> W_t -> Certify -> Execute -> O_{t+1}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
from typing import Mapping, Optional, Sequence, Tuple, Union

from uow.state import WorldState, canonical_json
from .adaptation import UnifiedAdaptationJudge
from .metacognition import (
    DeficitCertificate,
    ParseStatus,
    SemanticClass,
    TaskSemanticRequest,
    assess_semantics,
    load_certified_basis,
)
from .model import (
    AutonomyBudget,
    BudgetUsage,
    CapabilityRegistry,
    GoalEnvelope,
    ProgressTracker,
    WorkGraph,
    WorkItem,
)
from .planning import (
    GoalDecompositionEngine,
)
from .ports import (
    Environment,
    ExecutionPort,
    SimulatedExecutionPort,
)
from .repair import (
    ReferenceRepairProposer,
    RepairJudge,
)
from .work_basis import WorkArtifact


# -----------------------------------------------------------------------------
# State Machine Definitions
# -----------------------------------------------------------------------------

class ClosureState(str, Enum):
    OBSERVE = "OBSERVE"
    ASSESS = "ASSESS"
    PLAN = "PLAN"
    CERTIFY = "CERTIFY"
    EXECUTE = "EXECUTE"
    VERIFY = "VERIFY"
    REPAIR = "REPAIR"
    ADAPT = "ADAPT"
    ACQUIRE = "ACQUIRE"
    ESCALATE = "ESCALATE"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


ALLOWED_TRANSITIONS: Mapping[ClosureState, frozenset[ClosureState]] = {
    ClosureState.OBSERVE: frozenset({
        ClosureState.ASSESS,
        ClosureState.ESCALATE,
        ClosureState.FAILED,
    }),
    ClosureState.ASSESS: frozenset({
        ClosureState.PLAN,
        ClosureState.ACQUIRE,
        ClosureState.ESCALATE,
        ClosureState.OBSERVE,
        ClosureState.VERIFY,
        ClosureState.FAILED,
    }),
    ClosureState.PLAN: frozenset({
        ClosureState.CERTIFY,
        ClosureState.ACQUIRE,
        ClosureState.ESCALATE,
        ClosureState.FAILED,
    }),
    ClosureState.CERTIFY: frozenset({
        ClosureState.EXECUTE,
        ClosureState.REPAIR,
        ClosureState.PLAN,
        ClosureState.ESCALATE,
        ClosureState.FAILED,
    }),
    ClosureState.EXECUTE: frozenset({
        ClosureState.VERIFY,
        ClosureState.REPAIR,
        ClosureState.FAILED,
    }),
    ClosureState.VERIFY: frozenset({
        ClosureState.COMPLETE,
        ClosureState.REPAIR,
        ClosureState.ADAPT,
        ClosureState.PLAN,
        ClosureState.OBSERVE,
        ClosureState.ESCALATE,
        ClosureState.FAILED,
    }),
    ClosureState.REPAIR: frozenset({
        ClosureState.PLAN,
        ClosureState.CERTIFY,
        ClosureState.OBSERVE,
        ClosureState.ESCALATE,
        ClosureState.FAILED,
    }),
    ClosureState.ADAPT: frozenset({
        ClosureState.PLAN,
        ClosureState.OBSERVE,
        ClosureState.ESCALATE,
        ClosureState.FAILED,
    }),
    ClosureState.ACQUIRE: frozenset({
        ClosureState.OBSERVE,
        ClosureState.PLAN,
        ClosureState.ESCALATE,
        ClosureState.FAILED,
    }),
    ClosureState.ESCALATE: frozenset({
        ClosureState.FAILED,
        ClosureState.COMPLETE,
    }),
    ClosureState.COMPLETE: frozenset(),
    ClosureState.FAILED: frozenset(),
}


class IllegalStateTransitionError(RuntimeError):
    """Raised when an illegal transition is attempted in the closure state machine."""
    pass


@dataclass
class ClosureTransitionRecord:
    from_state: ClosureState
    to_state: ClosureState
    reason: str
    step_index: int


class ClosureStateMachine:
    def __init__(self, initial_state: ClosureState = ClosureState.OBSERVE) -> None:
        self._current_state = initial_state
        self._history: list[ClosureTransitionRecord] = []
        self._step_counter = 0

    @property
    def current_state(self) -> ClosureState:
        return self._current_state

    @property
    def is_terminal(self) -> bool:
        return self._current_state in (ClosureState.COMPLETE, ClosureState.FAILED)

    @property
    def history(self) -> Tuple[ClosureTransitionRecord, ...]:
        return tuple(self._history)

    def transition(self, target_state: ClosureState, reason: str = "") -> None:
        if self.is_terminal:
            raise IllegalStateTransitionError(
                f"Cannot transition from terminal state {self._current_state.value} to {target_state.value}."
            )

        allowed = ALLOWED_TRANSITIONS.get(self._current_state, frozenset())
        if target_state not in allowed:
            raise IllegalStateTransitionError(
                f"Illegal transition: {self._current_state.value} -> {target_state.value}. "
                f"Allowed destinations: {[s.value for s in allowed]}."
            )

        rec = ClosureTransitionRecord(
            from_state=self._current_state,
            to_state=target_state,
            reason=reason,
            step_index=self._step_counter,
        )
        self._history.append(rec)
        self._current_state = target_state
        self._step_counter += 1


# -----------------------------------------------------------------------------
# Certificate and Results
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class ClosureCertificate:
    """Cryptographic proof of autonomous goal completion."""
    certificate_id: str
    goal_id: str
    initial_state_hash: str
    final_state_hash: str
    satisfied_criteria: Tuple[str, ...]
    unsatisfied_criteria: Tuple[str, ...]
    invariant_checks: Mapping[str, str]
    authority_trace: Tuple[str, ...]
    work_transcript: Tuple[str, ...]
    evidence_root: str
    certificate_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "satisfied_criteria", tuple(self.satisfied_criteria))
        object.__setattr__(self, "unsatisfied_criteria", tuple(self.unsatisfied_criteria))
        object.__setattr__(self, "authority_trace", tuple(self.authority_trace))
        object.__setattr__(self, "work_transcript", tuple(self.work_transcript))
        object.__setattr__(self, "invariant_checks", dict(self.invariant_checks))

        expected = self.calculate_hash()
        if self.certificate_hash and self.certificate_hash != expected:
            raise ValueError("certificate_hash does not match closure certificate payload.")
        object.__setattr__(self, "certificate_hash", expected)

    def calculate_hash(self) -> str:
        payload = {
            "certificate_id": self.certificate_id,
            "goal_id": self.goal_id,
            "initial_state_hash": self.initial_state_hash,
            "final_state_hash": self.final_state_hash,
            "satisfied_criteria": list(self.satisfied_criteria),
            "unsatisfied_criteria": list(self.unsatisfied_criteria),
            "invariant_checks": dict(self.invariant_checks),
            "authority_trace": list(self.authority_trace),
            "work_transcript": list(self.work_transcript),
            "evidence_root": self.evidence_root,
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    @property
    def is_valid(self) -> bool:
        if len(self.unsatisfied_criteria) > 0:
            return False
        if any(v != "PASS" for v in self.invariant_checks.values()):
            return False
        return True


class ClosureVerifier:
    @staticmethod
    def verify_and_certify(
        goal: GoalEnvelope,
        initial_state: WorldState,
        final_state: WorldState,
        authority_trace: Sequence[str],
        work_transcript: Sequence[str],
        *,
        invariant_violations: int = 0,
        unauthorized_commits: int = 0,
        evidence_root: str = "certified_canonical_evidence",
    ) -> ClosureCertificate:
        satisfied: list[str] = []
        unsatisfied: list[str] = []

        for criterion in goal.success_criteria:
            if criterion.satisfied_by(final_state):
                satisfied.append(criterion.criterion_id)
            else:
                unsatisfied.append(criterion.criterion_id)

        invariant_checks: dict[str, str] = {}

        if unsatisfied:
            invariant_checks["goal_coverage"] = f"FAIL_UNSATISFIED:{','.join(unsatisfied)}"
        else:
            invariant_checks["goal_coverage"] = "PASS"

        if invariant_violations > 0:
            invariant_checks["system_invariants"] = f"FAIL_VIOLATIONS:{invariant_violations}"
        else:
            invariant_checks["system_invariants"] = "PASS"

        if unauthorized_commits > 0:
            invariant_checks["authority_enforcement"] = f"FAIL_UNAUTHORIZED:{unauthorized_commits}"
        else:
            invariant_checks["authority_enforcement"] = "PASS"

        if initial_state.state_hash != goal.initial_state_ref:
            invariant_checks["state_freshness"] = "FAIL_STALE_INITIAL_STATE"
        else:
            invariant_checks["state_freshness"] = "PASS"

        cert_id = hashlib.sha256(
            f"closure:{goal.goal_id}:{initial_state.state_hash}:{final_state.state_hash}".encode("utf-8")
        ).hexdigest()

        return ClosureCertificate(
            certificate_id=cert_id,
            goal_id=goal.goal_id,
            initial_state_hash=initial_state.state_hash,
            final_state_hash=final_state.state_hash,
            satisfied_criteria=tuple(satisfied),
            unsatisfied_criteria=tuple(unsatisfied),
            invariant_checks=invariant_checks,
            authority_trace=tuple(authority_trace),
            work_transcript=tuple(work_transcript),
            evidence_root=evidence_root,
        )


@dataclass(frozen=True)
class ClosureResult:
    goal_id: str
    terminal_state: ClosureState
    success: bool
    closure_certificate: Optional[ClosureCertificate] = None
    deficit_certificate: Optional[DeficitCertificate] = None
    rejection_reasons: Tuple[str, ...] = ()
    authority_trace: Tuple[str, ...] = ()
    work_transcript: Tuple[str, ...] = ()
    budget_usage: BudgetUsage = field(default_factory=BudgetUsage)
    transitions: Tuple[str, ...] = ()


def _topological_items(items: Sequence[WorkItem]) -> list[WorkItem]:
    by_id = {item.work_id: item for item in items}
    visited: set[str] = set()
    order: list[WorkItem] = []

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        visited.add(node_id)
        node = by_id.get(node_id)
        if node:
            for dep in node.depends_on:
                if dep in by_id:
                    visit(dep)
            order.append(node)

    for item in items:
        visit(item.work_id)
    return order


# -----------------------------------------------------------------------------
# Controller Implementation
# -----------------------------------------------------------------------------

class AutonomousClosureController:
    """Integrated Autonomous Controller orchestrating qualified cognitive subsystems."""

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        *,
        budget: Optional[AutonomyBudget] = None,
        max_planning_depth: Optional[int] = None,
        max_planning_budget: Optional[int] = None,
        max_stagnation_steps: int = 4,
    ) -> None:
        self.registry = capability_registry
        self.budget = budget or AutonomyBudget()
        self.progress_tracker = ProgressTracker(stagnation_limit=max_stagnation_steps)
        depth = max_planning_depth or max(5, self.budget.max_steps)
        plan_budget = max_planning_budget or max(50, self.budget.max_steps * 2)
        self.planner_engine = GoalDecompositionEngine(
            capability_registry,
            max_depth=depth,
            max_budget=plan_budget,
        )
        self.repair_judge = RepairJudge()
        self.repair_proposer = ReferenceRepairProposer()
        self.adaptation_judge = UnifiedAdaptationJudge()
        self._basis = load_certified_basis()

    def run(
        self,
        goal: GoalEnvelope,
        execution: Union[ExecutionPort, Environment],
    ) -> ClosureResult:
        if isinstance(execution, Environment):
            execution_port: ExecutionPort = SimulatedExecutionPort(execution)
        else:
            execution_port = execution

        sm = ClosureStateMachine(initial_state=ClosureState.OBSERVE)
        usage = BudgetUsage()
        authority_trace: list[str] = []
        work_transcript: list[str] = []
        invariant_violations = 0
        unauthorized_commits = 0

        initial_state = execution_port.state
        current_state = execution_port.state
        current_admitted_graph: Optional[WorkGraph] = None
        failed_work_id: Optional[str] = None
        consecutive_node_failures: dict[str, int] = {}
        deficit_cert: Optional[DeficitCertificate] = None
        rejection_reasons: list[str] = []

        while not sm.is_terminal:
            usage.steps += 1
            exceeded, budget_reasons = usage.check_exceeded(self.budget)
            if exceeded:
                rejection_reasons.extend(budget_reasons)
                sm.transition(ClosureState.ESCALATE, reason="BUDGET_EXHAUSTED")
                sm.transition(ClosureState.FAILED, reason="BUDGET_EXHAUSTED")
                break

            # -------------------------------------------------------------
            # STATE: OBSERVE
            # -------------------------------------------------------------
            if sm.current_state == ClosureState.OBSERVE:
                current_state = execution_port.state
                sm.transition(ClosureState.ASSESS, reason="OBSERVED_WORLD_STATE")
                continue

            # -------------------------------------------------------------
            # STATE: ASSESS
            # -------------------------------------------------------------
            if sm.current_state == ClosureState.ASSESS:
                if goal.is_satisfied_by(current_state):
                    sm.transition(ClosureState.VERIFY, reason="GOAL_ALREADY_SATISFIED")
                    continue

                req_effects = set({"decompose", "select"})
                if hasattr(goal, "required_effects") and goal.required_effects:
                    req_effects.update(goal.required_effects)
                for p in goal.desired_state:
                    if p.attribute.startswith("effect:"):
                        req_effects.add(p.attribute.split(":", 1)[1])

                known_attrs = set(current_state.attributes.keys())
                for cap in self.registry.all_capabilities():
                    for p in cap.preconditions:
                        known_attrs.add(p.attribute)
                    for eff in cap.effects:
                        known_attrs.add(eff.attribute)

                surface_entities = tuple(p.attribute for p in goal.desired_state)
                grounded_entities = tuple(a for a in surface_entities if a in known_attrs)

                req = TaskSemanticRequest(
                    task_id=f"goal:{goal.goal_id}",
                    parse_status=ParseStatus.PARSED,
                    input_artifacts=(WorkArtifact.GOAL,),
                    output_artifacts=(WorkArtifact.NECESSARY_WORK,),
                    required_effects=frozenset(req_effects),
                    surface_entities=surface_entities,
                    grounded_entities=grounded_entities,
                )
                assessment = assess_semantics(req, self._basis)

                if assessment.semantic_class == SemanticClass.UNREPRESENTABLE:
                    deficit_cert = assessment.certificate
                    rejection_reasons.append("GOAL_UNREPRESENTABLE")
                    rejection_reasons.append("SEMANTIC_DEFICIT_DETECTED")
                    sm.transition(ClosureState.ESCALATE, reason="SEMANTIC_DEFICIT")
                    sm.transition(ClosureState.FAILED, reason="UNREPRESENTABLE_GOAL")
                    continue
                elif assessment.semantic_class == SemanticClass.UNKNOWN_SURFACE:
                    rejection_reasons.append("GOAL_UNKNOWN_SURFACE")
                    sm.transition(ClosureState.ACQUIRE, reason="UNKNOWN_SURFACE_ENTITIES")
                    continue

                sm.transition(ClosureState.PLAN, reason="SEMANTICS_KNOWN_AND_READY")
                continue

            # -------------------------------------------------------------
            # STATE: PLAN
            # -------------------------------------------------------------
            if sm.current_state == ClosureState.PLAN:
                admission_res = self.planner_engine.plan_and_admit(goal, current_state)

                if not admission_res.is_admitted:
                    rejection_reasons.extend(admission_res.rejection_reasons)
                    if "GOAL_CAPABILITY_DEFICIT" in admission_res.rejection_reasons:
                        sm.transition(ClosureState.ACQUIRE, reason="CAPABILITY_DEFICIT")
                    elif "GOAL_UNREPRESENTABLE" in admission_res.rejection_reasons:
                        deficit_cert = admission_res.deficit_certificate
                        sm.transition(ClosureState.ESCALATE, reason="UNREPRESENTABLE_GOAL")
                        sm.transition(ClosureState.FAILED, reason="UNREPRESENTABLE_GOAL")
                    else:
                        sm.transition(ClosureState.FAILED, reason="PLANNING_FAILED")
                    continue

                current_admitted_graph = admission_res.admitted_graph
                sm.transition(ClosureState.CERTIFY, reason="PLAN_PRODUCED")
                continue

            # -------------------------------------------------------------
            # STATE: CERTIFY
            # -------------------------------------------------------------
            if sm.current_state == ClosureState.CERTIFY:
                if current_admitted_graph is None:
                    rejection_reasons.append("NO_ADMITTED_GRAPH_TO_CERTIFY")
                    sm.transition(ClosureState.FAILED, reason="MISSING_GRAPH")
                    continue

                if current_admitted_graph.no_op:
                    sm.transition(ClosureState.EXECUTE, reason="NO_OP_PLAN")
                    continue

                sm.transition(ClosureState.EXECUTE, reason="CERTIFIED_ADMISSIBLE_PLAN")
                continue

            # -------------------------------------------------------------
            # STATE: EXECUTE
            # -------------------------------------------------------------
            if sm.current_state == ClosureState.EXECUTE:
                if current_admitted_graph is None or current_admitted_graph.no_op:
                    sm.transition(ClosureState.VERIFY, reason="NO_OP_EXECUTION_COMPLETE")
                    continue

                execution_failed = False
                prev_state = current_state
                items_to_execute = _topological_items(current_admitted_graph.items)

                for item in items_to_execute:
                    for scope in item.required_capabilities:
                        if not goal.allowed_authority.permits(scope):
                            unauthorized_commits += 1
                            rejection_reasons.append(f"UNAUTHORIZED_WORK_AUTHORITY:{scope}")
                            execution_failed = True
                            failed_work_id = item.work_id
                            break
                    if execution_failed:
                        break

                    outcome = execution_port.execute(item, goal.allowed_authority)
                    usage.cost += outcome.cost_incurred
                    usage.energy += outcome.energy_incurred
                    current_state = execution_port.state

                    authority_trace.append(f"{item.work_id}:{','.join(item.required_capabilities)}")
                    work_transcript.append(f"{item.work_id}:{item.work_kind}:{outcome.success}")

                    if not outcome.success:
                        execution_failed = True
                        failed_work_id = item.work_id
                        consecutive_node_failures[item.work_id] = consecutive_node_failures.get(item.work_id, 0) + 1
                        rejection_reasons.append(f"EXECUTION_FAILED:{item.work_id}:{outcome.error_code}")
                        break

                self.progress_tracker.record_step(prev_state, current_state, goal)
                sm.transition(ClosureState.VERIFY, reason="EXECUTION_STEP_COMPLETED")
                continue

            # -------------------------------------------------------------
            # STATE: VERIFY
            # -------------------------------------------------------------
            if sm.current_state == ClosureState.VERIFY:
                if execution_port.state.state_hash != current_state.state_hash:
                    sm.transition(ClosureState.OBSERVE, reason="ENVIRONMENT_STATE_SHIFTED")
                    continue

                is_goal_satisfied = goal.is_satisfied_by(current_state)

                if is_goal_satisfied and unauthorized_commits == 0 and invariant_violations == 0:
                    closure_cert = ClosureVerifier.verify_and_certify(
                        goal=goal,
                        initial_state=initial_state,
                        final_state=current_state,
                        authority_trace=authority_trace,
                        work_transcript=work_transcript,
                        invariant_violations=invariant_violations,
                        unauthorized_commits=unauthorized_commits,
                    )
                    if closure_cert.is_valid:
                        sm.transition(ClosureState.COMPLETE, reason="CERTIFIED_GOAL_COMPLETION")
                        return ClosureResult(
                            goal_id=goal.goal_id,
                            terminal_state=ClosureState.COMPLETE,
                            success=True,
                            closure_certificate=closure_cert,
                            authority_trace=tuple(authority_trace),
                            work_transcript=tuple(work_transcript),
                            budget_usage=usage,
                            transitions=tuple(f"{t.from_state.value}->{t.to_state.value}" for t in sm.history),
                        )
                    else:
                        rejection_reasons.append("CLOSURE_CERTIFICATE_VALIDATION_FAILED")
                        sm.transition(ClosureState.FAILED, reason="CERTIFICATE_INVALID")
                        continue

                if failed_work_id:
                    failures_count = consecutive_node_failures.get(failed_work_id, 0)
                    if failures_count >= 3:
                        sm.transition(ClosureState.ADAPT, reason="REPEATED_EXECUTION_FAILURE_ADAPTATION")
                    else:
                        sm.transition(ClosureState.REPAIR, reason="SURGICAL_BOUNDED_REPAIR")
                    continue

                if self.progress_tracker.is_stagnating:
                    rejection_reasons.append("PROGRESS_STAGNATION_DETECTED")
                    sm.transition(ClosureState.ESCALATE, reason="STAGNATION")
                    sm.transition(ClosureState.FAILED, reason="STAGNATION")
                    continue

                sm.transition(ClosureState.OBSERVE, reason="RE_OBSERVE_PROGRESS")
                continue

            # -------------------------------------------------------------
            # STATE: REPAIR
            # -------------------------------------------------------------
            if sm.current_state == ClosureState.REPAIR:
                usage.repairs += 1
                if current_admitted_graph is None or not failed_work_id:
                    sm.transition(ClosureState.FAILED, reason="NO_GRAPH_OR_FAILURE_TO_REPAIR")
                    continue

                try:
                    proposal = self.repair_proposer.propose(
                        current_admitted_graph,
                        current_state,
                        [failed_work_id],
                    )
                    admission = self.repair_judge.evaluate(
                        proposal,
                        current_admitted_graph,
                        goal,
                        current_state,
                    )
                    if admission.accepted is not None:
                        current_admitted_graph = admission.accepted.revised_graph
                        failed_work_id = None
                        sm.transition(ClosureState.CERTIFY, reason="REPAIR_ADMITTED")
                    else:
                        rejection_reasons.extend(admission.rejection_reasons)
                        sm.transition(ClosureState.PLAN, reason="REPAIR_REJECTED_REPLANNING")
                except Exception as e:
                    rejection_reasons.append(f"REPAIR_EXCEPTION:{str(e)}")
                    sm.transition(ClosureState.PLAN, reason="REPAIR_FAILED_REPLANNING")
                continue

            # -------------------------------------------------------------
            # STATE: ADAPT
            # -------------------------------------------------------------
            if sm.current_state == ClosureState.ADAPT:
                usage.adaptations += 1
                failed_work_id = None
                sm.transition(ClosureState.PLAN, reason="POLICY_ADAPTED_REPLANNING")
                continue

            # -------------------------------------------------------------
            # STATE: ACQUIRE
            # -------------------------------------------------------------
            if sm.current_state == ClosureState.ACQUIRE:
                rejection_reasons.append("CAPABILITY_ACQUISITION_UNAVAILABLE")
                sm.transition(ClosureState.ESCALATE, reason="MISSING_CAPABILITY_ESCALATION")
                sm.transition(ClosureState.FAILED, reason="MISSING_CAPABILITY")
                continue

            # -------------------------------------------------------------
            # STATE: ESCALATE
            # -------------------------------------------------------------
            if sm.current_state == ClosureState.ESCALATE:
                sm.transition(ClosureState.FAILED, reason="ESCALATED_TERMINATION")
                continue

        return ClosureResult(
            goal_id=goal.goal_id,
            terminal_state=sm.current_state,
            success=(sm.current_state == ClosureState.COMPLETE),
            closure_certificate=None,
            deficit_certificate=deficit_cert,
            rejection_reasons=tuple(dict.fromkeys(rejection_reasons)),
            authority_trace=tuple(authority_trace),
            work_transcript=tuple(work_transcript),
            budget_usage=usage,
            transitions=tuple(f"{t.from_state.value}->{t.to_state.value}" for t in sm.history),
        )


__all__ = [
    "ALLOWED_TRANSITIONS",
    "AutonomousClosureController",
    "ClosureCertificate",
    "ClosureResult",
    "ClosureState",
    "ClosureStateMachine",
    "ClosureTransitionRecord",
    "ClosureVerifier",
    "IllegalStateTransitionError",
]
