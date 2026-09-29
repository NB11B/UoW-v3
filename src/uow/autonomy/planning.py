"""Goal decomposition, causal DAG dependency synthesis, and coverage certification."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
from types import MappingProxyType
from typing import Mapping, Optional, Sequence, Tuple

from uow.state import WorldState, canonical_json
from .metacognition import (
    DeficitCertificate,
    ParseStatus,
    SemanticClass,
    TaskSemanticRequest,
    assess_semantics,
    load_certified_basis,
)
from .model import (
    CapabilityRegistry,
    CoverageStatus,
    Criterion,
    GoalEnvelope,
    StatePredicate,
    WorkGraph,
    WorkItem,
)
from .work_basis import WorkArtifact


@dataclass(frozen=True)
class PlanNode:
    work_id: str
    capability_id: str
    parameters: Mapping[str, object] = field(default_factory=dict)
    preconditions: Tuple[StatePredicate, ...] = ()
    effects: Tuple[StatePredicate, ...] = ()
    depends_on: Tuple[str, ...] = ()
    achieves_criteria: Tuple[str, ...] = ()
    required_authority: Tuple[str, ...] = ("authority.default",)
    cost: float = 1.0
    energy: float = 1.0


def _has_cycle(deps: Mapping[str, Sequence[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for parent in deps.get(node, ()):
            if visit(parent):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in deps)


@dataclass(frozen=True)
class CausalDependencyGraph:
    nodes: Tuple[PlanNode, ...]
    graph_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(self.nodes))
        expected = self.calculate_hash()
        if self.graph_hash and self.graph_hash != expected:
            raise ValueError("graph_hash does not match graph nodes.")
        object.__setattr__(self, "graph_hash", expected)

    def calculate_hash(self) -> str:
        payload = [
            {
                "work_id": n.work_id,
                "capability_id": n.capability_id,
                "depends_on": sorted(list(n.depends_on)),
                "achieves_criteria": sorted(list(n.achieves_criteria)),
            }
            for n in self.nodes
        ]
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def validate(self) -> Tuple[bool, Tuple[str, ...]]:
        reasons: list[str] = []
        node_ids = {n.work_id for n in self.nodes}
        if len(node_ids) != len(self.nodes):
            reasons.append("DUPLICATE_WORK_ID")

        deps = {n.work_id: tuple(n.depends_on) for n in self.nodes}
        for n in self.nodes:
            for dep in n.depends_on:
                if dep not in node_ids:
                    reasons.append(f"UNKNOWN_DEPENDENCY:{dep}")

        if _has_cycle(deps):
            reasons.append("CYCLIC_WORK_GRAPH")

        return len(reasons) == 0, tuple(reasons)

    @classmethod
    def synthesize_causal_dependencies(
        cls,
        nodes: Sequence[PlanNode],
        initial_state: WorldState,
    ) -> CausalDependencyGraph:
        """Derive true causal edges where node B's precondition is produced by node A's effect."""
        producers_by_attr: dict[str, list[PlanNode]] = {}
        for node in nodes:
            for eff in node.effects:
                producers_by_attr.setdefault(eff.attribute, []).append(node)

        node_ids = {n.work_id for n in nodes}
        resolved_nodes: list[PlanNode] = []
        for node in nodes:
            causal_deps = {dep for dep in node.depends_on if dep in node_ids}
            for pre in node.preconditions:
                if pre.satisfied_by(initial_state):
                    continue
                producers = producers_by_attr.get(pre.attribute, [])
                for prod in producers:
                    if prod.work_id != node.work_id:
                        causal_deps.add(prod.work_id)

            resolved_nodes.append(
                PlanNode(
                    work_id=node.work_id,
                    capability_id=node.capability_id,
                    parameters=node.parameters,
                    preconditions=node.preconditions,
                    effects=node.effects,
                    depends_on=tuple(sorted(causal_deps)),
                    achieves_criteria=node.achieves_criteria,
                    required_authority=node.required_authority,
                    cost=node.cost,
                    energy=node.energy,
                )
            )
        return cls(nodes=tuple(resolved_nodes))

    def to_work_graph(
        self,
        goal_id: str,
        pre_state_hash: str,
        proposer_id: str = "goal_decomposition.planner",
    ) -> WorkGraph:
        """Lower the causal dependency graph to an admitted WorkGraph."""
        items = tuple(
            WorkItem(
                work_id=n.work_id,
                work_kind=n.capability_id,
                parameters=n.parameters,
                depends_on=n.depends_on,
                achieves_criteria=n.achieves_criteria,
                required_capabilities=n.required_authority,
            )
            for n in self.nodes
        )
        payload = {
            "goal_id": goal_id,
            "pre_state_hash": pre_state_hash,
            "graph_hash": self.graph_hash,
        }
        cert_hash = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        graph_id = hashlib.sha256(f"work-graph:{goal_id}:{cert_hash}".encode("utf-8")).hexdigest()

        return WorkGraph(
            graph_id=graph_id,
            proposal_id=f"prop:{graph_id}",
            goal_id=goal_id,
            pre_state_hash=pre_state_hash,
            items=items,
            no_op=(len(items) == 0),
            proposer_id=proposer_id,
            formation_certificate_hash=cert_hash,
        )


@dataclass(frozen=True)
class GoalCoverageCertificate:
    """Deterministic cryptographic proof that a WorkGraph satisfies its GoalEnvelope."""
    certificate_id: str
    goal_id: str
    initial_state_hash: str
    work_graph_hash: str
    success_criterion_ids: Tuple[str, ...]
    criterion_to_terminal_work_mapping: Mapping[str, str]
    constraint_checks: Mapping[str, str]
    authority_checks: Mapping[str, str]
    capability_bindings: Mapping[str, str]
    uncovered_criteria: Tuple[str, ...]
    certificate_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "success_criterion_ids", tuple(self.success_criterion_ids))
        object.__setattr__(self, "uncovered_criteria", tuple(self.uncovered_criteria))
        object.__setattr__(self, "criterion_to_terminal_work_mapping", MappingProxyType(dict(self.criterion_to_terminal_work_mapping)))
        object.__setattr__(self, "constraint_checks", MappingProxyType(dict(self.constraint_checks)))
        object.__setattr__(self, "authority_checks", MappingProxyType(dict(self.authority_checks)))
        object.__setattr__(self, "capability_bindings", MappingProxyType(dict(self.capability_bindings)))

        expected = self.calculate_hash()
        if self.certificate_hash and self.certificate_hash != expected:
            raise ValueError("certificate_hash does not match certificate payload.")
        object.__setattr__(self, "certificate_hash", expected)

    def calculate_hash(self) -> str:
        payload = {
            "goal_id": self.goal_id,
            "initial_state_hash": self.initial_state_hash,
            "work_graph_hash": self.work_graph_hash,
            "success_criterion_ids": list(self.success_criterion_ids),
            "criterion_to_terminal_work_mapping": dict(self.criterion_to_terminal_work_mapping),
            "constraint_checks": dict(self.constraint_checks),
            "authority_checks": dict(self.authority_checks),
            "capability_bindings": dict(self.capability_bindings),
            "uncovered_criteria": list(self.uncovered_criteria),
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    @property
    def is_valid(self) -> bool:
        if self.uncovered_criteria:
            return False
        if any(v != "PASS" for v in self.constraint_checks.values()):
            return False
        if any(v != "PASS" for v in self.authority_checks.values()):
            return False
        return True


class GoalCoverageVerifier:
    @staticmethod
    def verify_and_certify(
        goal: GoalEnvelope,
        graph: CausalDependencyGraph,
        initial_state: WorldState,
    ) -> GoalCoverageCertificate:
        success_criterion_ids = tuple(c.criterion_id for c in goal.success_criteria)
        criterion_mapping: dict[str, str] = {}
        capability_bindings: dict[str, str] = {}
        authority_checks: dict[str, str] = {}

        covered_set: set[str] = set()
        for node in graph.nodes:
            capability_bindings[node.work_id] = node.capability_id
            for scope in node.required_authority:
                if goal.allowed_authority.permits(scope):
                    authority_checks[f"{node.work_id}:{scope}"] = "PASS"
                else:
                    authority_checks[f"{node.work_id}:{scope}"] = "FAIL_UNAUTHORIZED"

            for criterion_id in node.achieves_criteria:
                covered_set.add(criterion_id)
                criterion_mapping[criterion_id] = node.work_id

        for criterion in goal.success_criteria:
            if criterion.satisfied_by(initial_state):
                covered_set.add(criterion.criterion_id)
                criterion_mapping[criterion.criterion_id] = "INITIAL_STATE_SATISFIED"

        uncovered = tuple(sorted(set(success_criterion_ids) - covered_set))

        constraint_checks: dict[str, str] = {}
        for hc in goal.hard_constraints:
            if hc.target == "max_steps" and len(graph.nodes) > hc.bound:
                constraint_checks[hc.constraint_id] = f"EXCEEDED_BOUND:{len(graph.nodes)} > {hc.bound}"
            elif hc.target == "max_cost":
                total_cost = sum(n.cost for n in graph.nodes)
                if total_cost > hc.bound:
                    constraint_checks[hc.constraint_id] = f"EXCEEDED_COST:{total_cost} > {hc.bound}"
                else:
                    constraint_checks[hc.constraint_id] = "PASS"
            else:
                constraint_checks[hc.constraint_id] = "PASS"

        if len(graph.nodes) > goal.resource_envelope.max_steps:
            constraint_checks["resource_envelope:max_steps"] = (
                f"EXCEEDED:{len(graph.nodes)} > {goal.resource_envelope.max_steps}"
            )
        total_cost = sum(n.cost for n in graph.nodes)
        if total_cost > goal.resource_envelope.max_cost:
            constraint_checks["resource_envelope:max_cost"] = (
                f"EXCEEDED:{total_cost} > {goal.resource_envelope.max_cost}"
            )

        cert_id = hashlib.sha256(
            f"goal-cert:{goal.goal_id}:{graph.graph_hash}:{initial_state.state_hash}".encode("utf-8")
        ).hexdigest()

        return GoalCoverageCertificate(
            certificate_id=cert_id,
            goal_id=goal.goal_id,
            initial_state_hash=initial_state.state_hash,
            work_graph_hash=graph.graph_hash,
            success_criterion_ids=success_criterion_ids,
            criterion_to_terminal_work_mapping=criterion_mapping,
            constraint_checks=constraint_checks,
            authority_checks=authority_checks,
            capability_bindings=capability_bindings,
            uncovered_criteria=uncovered,
        )


class DecompositionStrategy(str, Enum):
    TOP_DOWN = "TOP_DOWN"
    BOTTOM_UP = "BOTTOM_UP"
    BACKWARD_CHAINING = "BACKWARD_CHAINING"
    FORWARD_CHAINING = "FORWARD_CHAINING"
    RULE_BASED = "RULE_BASED"


@dataclass(frozen=True)
class DecompositionResult:
    success: bool
    nodes: Tuple[PlanNode, ...] = ()
    rejection_reasons: Tuple[str, ...] = ()
    deficit_certificate: Optional[DeficitCertificate] = None
    depth_reached: int = 0
    strategy_used: DecompositionStrategy = DecompositionStrategy.TOP_DOWN


class RecursiveDecomposer:
    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        *,
        max_depth: int = 5,
        max_budget: int = 50,
    ) -> None:
        self.registry = capability_registry
        self.max_depth = max_depth
        self.max_budget = max_budget
        self._basis = load_certified_basis()

    def decompose(
        self,
        goal: GoalEnvelope,
        state: WorldState,
        strategy: DecompositionStrategy = DecompositionStrategy.TOP_DOWN,
    ) -> DecompositionResult:
        if goal.is_satisfied_by(state):
            return DecompositionResult(
                success=True,
                nodes=(),
                rejection_reasons=(),
                strategy_used=strategy,
            )

        known_attrs = set(state.attributes.keys())
        for cap in self.registry.all_capabilities():
            for p in cap.preconditions:
                known_attrs.add(p.attribute)
            for eff in cap.effects:
                known_attrs.add(eff.attribute)

        surface_entities = tuple(p.attribute for p in goal.desired_state)
        grounded_entities = tuple(attr for attr in surface_entities if attr in known_attrs)

        req_effects = set({"decompose", "select"})
        if hasattr(goal, "required_effects") and goal.required_effects:
            req_effects.update(goal.required_effects)
        for p in goal.desired_state:
            if p.attribute.startswith("effect:"):
                req_effects.add(p.attribute.split(":", 1)[1])

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
            return DecompositionResult(
                success=False,
                rejection_reasons=("GOAL_UNREPRESENTABLE", "SEMANTIC_DEFICIT_DETECTED"),
                deficit_certificate=assessment.certificate,
                strategy_used=strategy,
            )
        if assessment.semantic_class == SemanticClass.UNKNOWN_SURFACE:
            return DecompositionResult(
                success=False,
                rejection_reasons=("GOAL_UNKNOWN_SURFACE", "UNGROUNDED_ENTITIES"),
                strategy_used=strategy,
            )

        cov = self.registry.check_coverage(goal, state)
        if cov.status == CoverageStatus.DEFICIT:
            return DecompositionResult(
                success=False,
                rejection_reasons=("GOAL_CAPABILITY_DEFICIT", f"UNSUPPORTED:{','.join(p.attribute for p in cov.unsupported_predicates)}"),
                strategy_used=strategy,
            )

        collected_nodes: list[PlanNode] = []
        pending_criteria: list[tuple[Criterion, int]] = [(c, 0) for c in goal.success_criteria if not c.satisfied_by(state)]
        steps_consumed = 0

        while pending_criteria:
            crit, depth = pending_criteria.pop(0)
            if depth >= self.max_depth:
                return DecompositionResult(
                    success=False,
                    rejection_reasons=("GOAL_DECOMPOSITION_EXHAUSTED", f"MAX_DEPTH_EXCEEDED:{depth}"),
                    strategy_used=strategy,
                    depth_reached=depth,
                )

            steps_consumed += 1
            if steps_consumed > self.max_budget:
                return DecompositionResult(
                    success=False,
                    rejection_reasons=("GOAL_DECOMPOSITION_EXHAUSTED", f"MAX_BUDGET_EXCEEDED:{steps_consumed}"),
                    strategy_used=strategy,
                    depth_reached=depth,
                )

            producers = self.registry.find_producers(crit.predicate)
            if not producers:
                return DecompositionResult(
                    success=False,
                    rejection_reasons=("GOAL_CAPABILITY_DEFICIT", f"NO_PRODUCER_FOR:{crit.criterion_id}"),
                    strategy_used=strategy,
                    depth_reached=depth,
                )

            selected_cap = producers[0] if strategy != DecompositionStrategy.BOTTOM_UP else producers[-1]
            node_id = f"w_{crit.criterion_id}"

            unmet_preconditions = [p for p in selected_cap.preconditions if not p.satisfied_by(state)]
            for pre in unmet_preconditions:
                sub_crit = Criterion(
                    criterion_id=f"pre_{pre.attribute}_{depth+1}",
                    predicate=pre,
                    description=f"Precondition for {selected_cap.capability_id}",
                )
                pending_criteria.append((sub_crit, depth + 1))

            collected_nodes.append(
                PlanNode(
                    work_id=node_id,
                    capability_id=selected_cap.capability_id,
                    preconditions=selected_cap.preconditions,
                    effects=selected_cap.effects,
                    achieves_criteria=(crit.criterion_id,),
                    required_authority=selected_cap.required_authority,
                    cost=selected_cap.cost,
                    energy=selected_cap.energy,
                )
            )

        unique_nodes: dict[str, PlanNode] = {}
        for n in collected_nodes:
            if n.work_id not in unique_nodes:
                unique_nodes[n.work_id] = n
            else:
                existing = unique_nodes[n.work_id]
                merged_criteria = tuple(sorted(set(existing.achieves_criteria + n.achieves_criteria)))
                unique_nodes[n.work_id] = PlanNode(
                    work_id=existing.work_id,
                    capability_id=existing.capability_id,
                    parameters=existing.parameters,
                    preconditions=existing.preconditions,
                    effects=existing.effects,
                    depends_on=existing.depends_on,
                    achieves_criteria=merged_criteria,
                    required_authority=existing.required_authority,
                    cost=existing.cost,
                    energy=existing.energy,
                )

        return DecompositionResult(
            success=True,
            nodes=tuple(unique_nodes.values()),
            rejection_reasons=(),
            depth_reached=1,
            strategy_used=strategy,
        )


@dataclass(frozen=True)
class GoalDecompositionAdmissionResult:
    admitted_graph: Optional[WorkGraph]
    causal_graph: Optional[CausalDependencyGraph]
    coverage_certificate: Optional[GoalCoverageCertificate]
    rejection_reasons: Tuple[str, ...] = ()
    deficit_certificate: Optional[DeficitCertificate] = None

    @property
    def is_admitted(self) -> bool:
        return self.admitted_graph is not None and self.coverage_certificate is not None and self.coverage_certificate.is_valid


class GoalDecompositionEngine:
    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        *,
        max_depth: int = 5,
        max_budget: int = 50,
    ) -> None:
        self.registry = capability_registry
        self.decomposer = RecursiveDecomposer(
            capability_registry,
            max_depth=max_depth,
            max_budget=max_budget,
        )

    def plan_and_admit(
        self,
        goal: GoalEnvelope,
        initial_state: WorldState,
        *,
        strategy: DecompositionStrategy = DecompositionStrategy.TOP_DOWN,
        proposer_id: str = "goal_decomposition.planner",
    ) -> GoalDecompositionAdmissionResult:
        reasons: list[str] = []

        if goal.initial_state_ref != initial_state.state_hash:
            return GoalDecompositionAdmissionResult(
                admitted_graph=None,
                causal_graph=None,
                coverage_certificate=None,
                rejection_reasons=("STALE_INITIAL_STATE",),
            )

        if goal.is_satisfied_by(initial_state):
            empty_causal = CausalDependencyGraph(nodes=())
            work_graph = empty_causal.to_work_graph(goal.goal_id, initial_state.state_hash, proposer_id)
            cert = GoalCoverageVerifier.verify_and_certify(goal, empty_causal, initial_state)
            return GoalDecompositionAdmissionResult(
                admitted_graph=work_graph,
                causal_graph=empty_causal,
                coverage_certificate=cert,
                rejection_reasons=(),
            )

        decomp_result: DecompositionResult = self.decomposer.decompose(
            goal, initial_state, strategy=strategy
        )
        if not decomp_result.success:
            return GoalDecompositionAdmissionResult(
                admitted_graph=None,
                causal_graph=None,
                coverage_certificate=None,
                rejection_reasons=decomp_result.rejection_reasons,
                deficit_certificate=decomp_result.deficit_certificate,
            )

        causal_graph = CausalDependencyGraph.synthesize_causal_dependencies(
            decomp_result.nodes, initial_state
        )
        is_valid_dag, dag_errors = causal_graph.validate()
        if not is_valid_dag:
            return GoalDecompositionAdmissionResult(
                admitted_graph=None,
                causal_graph=causal_graph,
                coverage_certificate=None,
                rejection_reasons=dag_errors,
            )

        needed_criteria = {c.criterion_id for c in goal.success_criteria if not c.satisfied_by(initial_state)}
        nodes_by_id = {n.work_id: n for n in causal_graph.nodes}

        terminal_nodes: dict[str, PlanNode] = {}
        for crit_id in needed_criteria:
            for node in causal_graph.nodes:
                if crit_id in node.achieves_criteria:
                    terminal_nodes[crit_id] = node
                    break

        essential_ids: set[str] = set()
        queue: list[str] = [n.work_id for n in terminal_nodes.values()]
        while queue:
            curr_id = queue.pop(0)
            if curr_id not in essential_ids:
                essential_ids.add(curr_id)
                curr_node = nodes_by_id.get(curr_id)
                if curr_node:
                    for dep_id in curr_node.depends_on:
                        if dep_id not in essential_ids and dep_id in nodes_by_id:
                            queue.append(dep_id)

        essential_nodes = [n for n in causal_graph.nodes if n.work_id in essential_ids]
        if len(essential_nodes) < len(causal_graph.nodes):
            causal_graph = CausalDependencyGraph.synthesize_causal_dependencies(
                essential_nodes, initial_state
            )

        for node in causal_graph.nodes:
            for scope in node.required_authority:
                if not goal.allowed_authority.permits(scope):
                    reasons.append(f"UNAUTHORIZED_WORK_AUTHORITY:{scope}")

        if len(causal_graph.nodes) > goal.resource_envelope.max_steps:
            reasons.append("RESOURCE_ENVELOPE_EXCEEDED:steps")
        total_cost = sum(n.cost for n in causal_graph.nodes)
        if total_cost > goal.resource_envelope.max_cost:
            reasons.append("RESOURCE_ENVELOPE_EXCEEDED:cost")

        cert = GoalCoverageVerifier.verify_and_certify(goal, causal_graph, initial_state)
        if cert.uncovered_criteria:
            reasons.append(f"UNCOVERED_SUCCESS_CRITERION:{','.join(cert.uncovered_criteria)}")

        if reasons:
            return GoalDecompositionAdmissionResult(
                admitted_graph=None,
                causal_graph=causal_graph,
                coverage_certificate=cert,
                rejection_reasons=tuple(dict.fromkeys(reasons)),
            )

        admitted_work = causal_graph.to_work_graph(goal.goal_id, initial_state.state_hash, proposer_id)
        return GoalDecompositionAdmissionResult(
            admitted_graph=admitted_work,
            causal_graph=causal_graph,
            coverage_certificate=cert,
            rejection_reasons=(),
        )


__all__ = [
    "CausalDependencyGraph",
    "DecompositionResult",
    "DecompositionStrategy",
    "GoalCoverageCertificate",
    "GoalCoverageVerifier",
    "GoalDecompositionAdmissionResult",
    "GoalDecompositionEngine",
    "PlanNode",
    "RecursiveDecomposer",
]
