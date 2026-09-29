"""Domain, goal, capability, work models, and public specification types."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence, Tuple

from uow.state import WorldState, canonical_json


# -----------------------------------------------------------------------------
# Predicates and Goal Models
# -----------------------------------------------------------------------------

class PredicateOp(str, Enum):
    EQ = "EQ"
    NEQ = "NEQ"
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    IN = "IN"
    EXISTS = "EXISTS"


@dataclass(frozen=True)
class StatePredicate:
    attribute: str
    op: PredicateOp
    value: object

    def satisfied_by(self, state: WorldState) -> bool:
        curr = state.attributes.get(self.attribute)
        if self.op == PredicateOp.EXISTS:
            return self.attribute in state.attributes
        if curr is None:
            return False
        if self.op == PredicateOp.EQ:
            return curr == self.value
        if self.op == PredicateOp.NEQ:
            return curr != self.value
        try:
            if self.op == PredicateOp.GT:
                return float(curr) > float(self.value)  # type: ignore[arg-type]
            if self.op == PredicateOp.GTE:
                return float(curr) >= float(self.value)  # type: ignore[arg-type]
            if self.op == PredicateOp.LT:
                return float(curr) < float(self.value)  # type: ignore[arg-type]
            if self.op == PredicateOp.LTE:
                return float(curr) <= float(self.value)  # type: ignore[arg-type]
        except (ValueError, TypeError):
            return False
        if self.op == PredicateOp.IN:
            return curr in self.value  # type: ignore[operator]
        return False


@dataclass(frozen=True)
class Criterion:
    criterion_id: str
    predicate: StatePredicate
    description: str = ""

    def satisfied_by(self, state: WorldState) -> bool:
        return self.predicate.satisfied_by(state)


# Backward-compatible alias
GoalCriterion = Criterion


@dataclass(frozen=True)
class Constraint:
    constraint_id: str
    target: str
    bound: float
    description: str = ""


@dataclass(frozen=True)
class Preference:
    preference_id: str
    metric: str
    direction: str  # MAXIMIZE or MINIMIZE
    weight: float = 1.0


@dataclass(frozen=True)
class AuthorityScope:
    authorized_scopes: Tuple[str, ...]
    max_tier: int = 1

    def permits(self, required_scope: str) -> bool:
        return (
            "authority.admin" in self.authorized_scopes
            or required_scope in self.authorized_scopes
        )


@dataclass(frozen=True)
class ResourceEnvelope:
    max_steps: int = 50
    max_cost: float = 100.0
    max_energy: float = 100.0


@dataclass(frozen=True)
class Provenance:
    source_agent: str
    signal_id: str
    timestamp: Optional[float] = None
    derivation_trace: Tuple[str, ...] = ()


@dataclass(frozen=True)
class GoalEnvelope:
    """Canonical Goal Ingress Contract."""
    goal_id: str
    initial_state_ref: str
    desired_state: Tuple[StatePredicate, ...]
    success_criteria: Tuple[Criterion, ...]
    hard_constraints: Tuple[Constraint, ...] = ()
    preferences: Tuple[Preference, ...] = ()
    allowed_authority: AuthorityScope = AuthorityScope(authorized_scopes=("authority.default",))
    resource_envelope: ResourceEnvelope = ResourceEnvelope()
    deadline: Optional[str] = None
    provenance: Optional[Provenance] = None
    required_effects: Tuple[str, ...] = ()
    goal_hash: str = ""

    def __post_init__(self) -> None:
        if not self.goal_id or not self.initial_state_ref:
            raise ValueError("goal_id and initial_state_ref are required.")
        object.__setattr__(self, "desired_state", tuple(self.desired_state))
        object.__setattr__(self, "success_criteria", tuple(self.success_criteria))
        object.__setattr__(self, "hard_constraints", tuple(self.hard_constraints))
        object.__setattr__(self, "preferences", tuple(self.preferences))
        object.__setattr__(self, "required_effects", tuple(self.required_effects))

        expected = self.calculate_hash()
        if self.goal_hash and self.goal_hash != expected:
            raise ValueError("goal_hash does not match goal envelope payload.")
        object.__setattr__(self, "goal_hash", expected)

    def calculate_hash(self) -> str:
        payload = {
            "goal_id": self.goal_id,
            "initial_state_ref": self.initial_state_ref,
            "desired_state": [
                {"attribute": p.attribute, "op": p.op.value, "value": p.value}
                for p in self.desired_state
            ],
            "success_criteria": [
                {
                    "criterion_id": c.criterion_id,
                    "attribute": c.predicate.attribute,
                    "op": c.predicate.op.value,
                    "value": c.predicate.value,
                }
                for c in self.success_criteria
            ],
            "hard_constraints": [
                {"constraint_id": hc.constraint_id, "target": hc.target, "bound": hc.bound}
                for hc in self.hard_constraints
            ],
            "allowed_authority": list(self.allowed_authority.authorized_scopes),
            "resource_envelope": {
                "max_steps": self.resource_envelope.max_steps,
                "max_cost": self.resource_envelope.max_cost,
            },
            "required_effects": list(self.required_effects),
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def is_satisfied_by(self, state: WorldState) -> bool:
        """Evaluate whether all success criteria are satisfied in state."""
        return all(c.satisfied_by(state) for c in self.success_criteria)


# -----------------------------------------------------------------------------
# Capability Models and Registry
# -----------------------------------------------------------------------------

class CoverageStatus(str, Enum):
    COVERED = "COVERED"
    PARTIAL = "PARTIAL"
    DEFICIT = "DEFICIT"


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    name: str
    preconditions: Tuple[StatePredicate, ...] = ()
    effects: Tuple[StatePredicate, ...] = ()
    required_authority: Tuple[str, ...] = ("authority.default",)
    cost: float = 1.0
    energy: float = 1.0
    is_atomic: bool = True
    description: str = ""


@dataclass(frozen=True)
class CapabilityCoverageResult:
    status: CoverageStatus
    covered_criteria: Tuple[str, ...]
    missing_criteria: Tuple[str, ...]
    unsupported_predicates: Tuple[StatePredicate, ...]
    candidate_capabilities: Tuple[str, ...]


class CapabilityRegistry:
    def __init__(self, capabilities: Sequence[CapabilityDescriptor] = ()) -> None:
        self._capabilities: dict[str, CapabilityDescriptor] = {
            c.capability_id: c for c in capabilities
        }

    def register(self, cap: CapabilityDescriptor) -> None:
        self._capabilities[cap.capability_id] = cap

    def get(self, cap_id: str) -> Optional[CapabilityDescriptor]:
        return self._capabilities.get(cap_id)

    def all_capabilities(self) -> Tuple[CapabilityDescriptor, ...]:
        return tuple(self._capabilities.values())

    def find_producers(self, predicate: StatePredicate) -> Tuple[CapabilityDescriptor, ...]:
        """Find capabilities whose effects satisfy the given predicate."""
        producers = []
        for cap in self._capabilities.values():
            for eff in cap.effects:
                if eff.attribute == predicate.attribute:
                    if predicate.op == PredicateOp.EQ and eff.op == PredicateOp.EQ and eff.value == predicate.value:
                        producers.append(cap)
                    elif predicate.op == PredicateOp.EXISTS:
                        producers.append(cap)
                    elif eff.op == predicate.op and eff.value == predicate.value:
                        producers.append(cap)
        return tuple(producers)

    def check_coverage(self, goal: GoalEnvelope, state: WorldState) -> CapabilityCoverageResult:
        covered: list[str] = []
        missing: list[str] = []
        unsupported: list[StatePredicate] = []
        candidate_caps: set[str] = set()

        for criterion in goal.success_criteria:
            if criterion.satisfied_by(state):
                covered.append(criterion.criterion_id)
                continue

            producers = self.find_producers(criterion.predicate)
            if producers:
                covered.append(criterion.criterion_id)
                for p in producers:
                    candidate_caps.add(p.capability_id)
            else:
                missing.append(criterion.criterion_id)
                unsupported.append(criterion.predicate)

        if not missing:
            status = CoverageStatus.COVERED
        elif covered:
            status = CoverageStatus.PARTIAL
        else:
            status = CoverageStatus.DEFICIT

        return CapabilityCoverageResult(
            status=status,
            covered_criteria=tuple(covered),
            missing_criteria=tuple(missing),
            unsupported_predicates=tuple(unsupported),
            candidate_capabilities=tuple(sorted(candidate_caps)),
        )


# -----------------------------------------------------------------------------
# Work Models
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class WorkItem:
    work_id: str
    work_kind: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    depends_on: Tuple[str, ...] = ()
    achieves_criteria: Tuple[str, ...] = ()
    required_capabilities: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.work_id or not self.work_kind:
            raise ValueError("work_id and work_kind must be non-empty.")
        canonical_json(dict(self.parameters))
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        object.__setattr__(self, "depends_on", tuple(str(x) for x in self.depends_on))
        object.__setattr__(self, "achieves_criteria", tuple(str(x) for x in self.achieves_criteria))
        object.__setattr__(self, "required_capabilities", tuple(str(x) for x in self.required_capabilities))


@dataclass(frozen=True)
class WorkGraphProposal:
    goal_id: str
    pre_state_hash: str
    items: Tuple[WorkItem, ...]
    no_op: bool
    proposer_id: str
    proposal_id: str = ""

    def __post_init__(self) -> None:
        if not self.goal_id or not self.pre_state_hash or not self.proposer_id:
            raise ValueError("goal_id, pre_state_hash, and proposer_id must be non-empty.")
        object.__setattr__(self, "items", tuple(self.items))
        expected = self.calculate_id()
        if self.proposal_id and self.proposal_id != expected:
            raise ValueError("proposal_id does not match work graph proposal.")
        object.__setattr__(self, "proposal_id", expected)

    def calculate_id(self) -> str:
        payload = {
            "goal_id": self.goal_id,
            "pre_state_hash": self.pre_state_hash,
            "no_op": self.no_op,
            "proposer_id": self.proposer_id,
            "items": [
                {
                    "work_id": item.work_id,
                    "work_kind": item.work_kind,
                    "parameters": dict(item.parameters),
                    "depends_on": list(item.depends_on),
                    "achieves_criteria": list(item.achieves_criteria),
                    "required_capabilities": list(item.required_capabilities),
                }
                for item in self.items
            ],
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WorkGraph:
    graph_id: str
    proposal_id: str
    goal_id: str
    pre_state_hash: str
    items: Tuple[WorkItem, ...]
    no_op: bool
    proposer_id: str
    formation_certificate_hash: str


@dataclass(frozen=True)
class WorkGraphAdmissionResult:
    accepted: Tuple[WorkGraph, ...]
    rejected: Mapping[str, Tuple[str, ...]]

    @property
    def all_accepted(self) -> bool:
        return not self.rejected


def criterion_satisfied(state: WorldState, criterion: Any) -> bool:
    """Evaluate if a criterion or predicate is satisfied in state."""
    if hasattr(criterion, "satisfied_by"):
        return criterion.satisfied_by(state)

    subject = getattr(criterion, "subject", None)
    if subject is None:
        return False

    exists = subject in state.attributes
    op = getattr(criterion, "op", None)
    op_name = getattr(op, "name", str(op))
    if op_name == "EXISTS":
        return exists
    if not exists:
        return False

    value = state.attributes[subject]
    operand = getattr(criterion, "operand", None)
    try:
        if op_name in ("EQ", "=="):
            return value == operand
        if op_name in ("NE", "NEQ", "!="):
            return value != operand
        if op_name in ("GTE", ">="):
            return value >= operand
        if op_name in ("LTE", "<="):
            return value <= operand
        if op_name in ("GT", ">"):
            return value > operand
        if op_name in ("LT", "<"):
            return value < operand
    except TypeError:
        return False
    return False


# -----------------------------------------------------------------------------
# Budget and Progress
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class AutonomyBudget:
    max_steps: int = 1000
    max_time_seconds: float = 300.0
    max_cost: float = 1000.0
    max_energy: float = 10000.0
    max_repairs: int = 10
    max_adaptations: int = 5


@dataclass
class BudgetUsage:
    steps: int = 0
    time_seconds: float = 0.0
    cost: float = 0.0
    energy: float = 0.0
    repairs: int = 0
    adaptations: int = 0

    def check_exceeded(self, budget: AutonomyBudget) -> Tuple[bool, Tuple[str, ...]]:
        reasons: list[str] = []
        if self.steps > budget.max_steps:
            reasons.append(f"EXCEEDED_MAX_STEPS:{self.steps}>{budget.max_steps}")
        if self.time_seconds > budget.max_time_seconds:
            reasons.append(f"EXCEEDED_MAX_TIME:{self.time_seconds}>{budget.max_time_seconds}")
        if self.cost > budget.max_cost:
            reasons.append(f"EXCEEDED_MAX_COST:{self.cost}>{budget.max_cost}")
        if self.energy > budget.max_energy:
            reasons.append(f"EXCEEDED_MAX_ENERGY:{self.energy}>{budget.max_energy}")
        if self.repairs > budget.max_repairs:
            reasons.append(f"EXCEEDED_MAX_REPAIRS:{self.repairs}>{budget.max_repairs}")
        if self.adaptations > budget.max_adaptations:
            reasons.append(f"EXCEEDED_MAX_ADAPTATIONS:{self.adaptations}>{budget.max_adaptations}")

        return len(reasons) > 0, tuple(reasons)

    def is_approaching_exhaustion(self, budget: AutonomyBudget, threshold: float = 0.9) -> bool:
        if budget.max_steps > 0 and self.steps / budget.max_steps >= threshold:
            return True
        if budget.max_cost > 0 and self.cost / budget.max_cost >= threshold:
            return True
        if budget.max_energy > 0 and self.energy / budget.max_energy >= threshold:
            return True
        if budget.max_repairs > 0 and self.repairs / budget.max_repairs >= threshold:
            return True
        if budget.max_adaptations > 0 and self.adaptations / budget.max_adaptations >= threshold:
            return True
        return False


class ProgressTracker:
    def __init__(self, stagnation_limit: int = 3) -> None:
        self.stagnation_limit = stagnation_limit
        self._consecutive_non_positive_steps = 0
        self._distance_history: list[float] = []
        self._delta_history: list[float] = []

    @staticmethod
    def distance(state: WorldState, goal: GoalEnvelope) -> float:
        unsatisfied = sum(
            0.0 if criterion.satisfied_by(state) else 1.0
            for criterion in goal.success_criteria
        )
        return float(unsatisfied)

    def record_step(self, prev_state: WorldState, curr_state: WorldState, goal: GoalEnvelope) -> float:
        d_prev = self.distance(prev_state, goal)
        d_curr = self.distance(curr_state, goal)
        delta = d_prev - d_curr

        self._distance_history.append(d_curr)
        self._delta_history.append(delta)

        if delta <= 0:
            self._consecutive_non_positive_steps += 1
        else:
            self._consecutive_non_positive_steps = 0

        return delta

    @property
    def is_stagnating(self) -> bool:
        return self._consecutive_non_positive_steps >= self.stagnation_limit

    @property
    def consecutive_non_positive_steps(self) -> int:
        return self._consecutive_non_positive_steps

    @property
    def delta_history(self) -> Tuple[float, ...]:
        return tuple(self._delta_history)

    def reset_stagnation(self) -> None:
        self._consecutive_non_positive_steps = 0


# -----------------------------------------------------------------------------
# Public Production Specification Types
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class GoalSpec:
    """User-facing goal specification."""
    goal_id: str
    desired_state: Tuple[StatePredicate, ...]
    resource_budget: Optional[ResourceEnvelope] = None
    authority_scope: Optional[AuthorityScope] = None
    required_effects: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CapabilitySpec:
    """User-facing capability specification."""
    capability_id: str
    preconditions: Tuple[StatePredicate, ...] = ()
    effects: Tuple[StatePredicate, ...] = ()
    required_authority: Tuple[str, ...] = ("authority.default",)
    cost: float = 1.0
    energy: float = 1.0
    description: str = ""


class TerminalDisposition(str, Enum):
    """Observable outcome disposition for autonomous runs."""
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"
    STAGNATED = "STAGNATED"
    UNREPRESENTABLE = "UNREPRESENTABLE"


@dataclass(frozen=True)
class AutonomyRequest:
    """Standard input request for autonomous execution."""
    goal: GoalSpec
    capabilities: Tuple[CapabilitySpec, ...]
    initial_state: WorldState
    budget: Optional[AutonomyBudget] = None


@dataclass(frozen=True)
class AutonomyResult:
    """Standard outcome result from autonomous execution."""
    success: bool
    disposition: TerminalDisposition
    final_state: WorldState
    evidence: Tuple[Any, ...] = ()
    diagnostic: Optional[str] = None
    transitions: Tuple[str, ...] = ()


def goal_spec_to_envelope(spec: GoalSpec, initial_state: WorldState) -> GoalEnvelope:
    """Lower a public GoalSpec into an internal GoalEnvelope."""
    criteria = tuple(
        Criterion(
            criterion_id=f"crit_{p.attribute}_{i}",
            predicate=p,
        )
        for i, p in enumerate(spec.desired_state)
    )
    return GoalEnvelope(
        goal_id=spec.goal_id,
        initial_state_ref=initial_state.state_hash,
        desired_state=spec.desired_state,
        success_criteria=criteria,
        allowed_authority=spec.authority_scope or AuthorityScope(authorized_scopes=("authority.default",)),
        resource_envelope=spec.resource_budget or ResourceEnvelope(),
        required_effects=spec.required_effects,
    )


def capability_spec_to_descriptor(spec: CapabilitySpec) -> CapabilityDescriptor:
    """Lower a public CapabilitySpec into an internal CapabilityDescriptor."""
    return CapabilityDescriptor(
        capability_id=spec.capability_id,
        name=spec.capability_id,
        preconditions=spec.preconditions,
        effects=spec.effects,
        required_authority=spec.required_authority,
        cost=spec.cost,
        energy=spec.energy,
        description=spec.description,
    )


__all__ = [
    "AuthorityScope",
    "AutonomyBudget",
    "AutonomyRequest",
    "AutonomyResult",
    "BudgetUsage",
    "CapabilityCoverageResult",
    "CapabilityDescriptor",
    "CapabilityRegistry",
    "CapabilitySpec",
    "Constraint",
    "CoverageStatus",
    "Criterion",
    "GoalCriterion",
    "GoalEnvelope",
    "GoalSpec",
    "PredicateOp",
    "Preference",
    "ProgressTracker",
    "Provenance",
    "ResourceEnvelope",
    "StatePredicate",
    "TerminalDisposition",
    "WorkGraph",
    "WorkGraphAdmissionResult",
    "WorkGraphProposal",
    "WorkItem",
    "capability_spec_to_descriptor",
    "criterion_satisfied",
    "goal_spec_to_envelope",
]
