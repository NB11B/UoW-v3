"""Bounded repair over admitted work graphs.

Repair is graph surgery, not global replanning:
Computes the dependency-descendant closure of failed work and rejects any
proposal that modifies work outside that closure.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Optional, Protocol, Sequence, Tuple, runtime_checkable

from uow.state import WorldState, canonical_json
from .metacognition import (
    DeficitCertificate,
    Readiness,
    SemanticAssessment,
    SemanticClass,
)
from .model import (
    GoalEnvelope,
    WorkGraph,
    WorkItem,
    criterion_satisfied,
)


def affected_closure(
    graph: WorkGraph,
    failed_work_ids: Sequence[str],
) -> Tuple[str, ...]:
    """Return failed nodes plus every transitive descendant that depends on them."""
    by_id = {item.work_id: item for item in graph.items}
    failed = set(failed_work_ids)
    if any(work_id not in by_id for work_id in failed):
        missing = sorted(work_id for work_id in failed if work_id not in by_id)
        raise KeyError(f"Unknown failed work ids: {missing}")

    affected = set(failed)
    changed = True
    while changed:
        changed = False
        for item in graph.items:
            if item.work_id in affected:
                continue
            if any(parent in affected for parent in item.depends_on):
                affected.add(item.work_id)
                changed = True

    ordered = tuple(item.work_id for item in graph.items if item.work_id in affected)
    return ordered


@dataclass(frozen=True)
class RepairProposal:
    graph_id: str
    pre_state_hash: str
    failed_work_ids: Tuple[str, ...]
    affected_work_ids: Tuple[str, ...]
    replacement_items: Tuple[WorkItem, ...]
    proposer_id: str
    proposal_id: str = ""
    deficit_certificate: Optional[DeficitCertificate] = None
    declared_capabilities: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.graph_id or not self.pre_state_hash or not self.proposer_id:
            raise ValueError("graph_id, pre_state_hash, and proposer_id are required.")
        if not self.failed_work_ids:
            raise ValueError("RepairProposal requires at least one failed work id.")
        object.__setattr__(self, "failed_work_ids", tuple(str(x) for x in self.failed_work_ids))
        object.__setattr__(self, "affected_work_ids", tuple(str(x) for x in self.affected_work_ids))
        object.__setattr__(self, "replacement_items", tuple(self.replacement_items))
        object.__setattr__(self, "declared_capabilities", tuple(str(x) for x in self.declared_capabilities))
        expected = self.calculate_id()
        if self.proposal_id and self.proposal_id != expected:
            raise ValueError("proposal_id does not match repair proposal.")
        object.__setattr__(self, "proposal_id", expected)

    def calculate_id(self) -> str:
        payload: dict[str, object] = {
            "graph_id": self.graph_id,
            "pre_state_hash": self.pre_state_hash,
            "failed_work_ids": list(self.failed_work_ids),
            "affected_work_ids": list(self.affected_work_ids),
            "replacement_items": [
                {
                    "work_id": item.work_id,
                    "work_kind": item.work_kind,
                    "parameters": dict(item.parameters),
                    "depends_on": list(item.depends_on),
                    "achieves_criteria": list(item.achieves_criteria),
                    "required_capabilities": list(item.required_capabilities),
                }
                for item in self.replacement_items
            ],
            "proposer_id": self.proposer_id,
        }
        if self.deficit_certificate is not None:
            payload["deficit_certificate_hash"] = self.deficit_certificate.certificate_hash
        if self.declared_capabilities:
            payload["declared_capabilities"] = list(self.declared_capabilities)
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@runtime_checkable
class RepairProposer(Protocol):
    def propose(
        self,
        graph: WorkGraph,
        state: WorldState,
        failed_work_ids: Sequence[str],
    ) -> RepairProposal:
        ...


class ReferenceRepairProposer:
    """Conservative repair baseline that reconstructs exactly the affected closure."""

    def propose(
        self,
        graph: WorkGraph,
        state: WorldState,
        failed_work_ids: Sequence[str],
    ) -> RepairProposal:
        affected = affected_closure(graph, failed_work_ids)
        affected_set = set(affected)
        id_map = {work_id: f"repair:{work_id}" for work_id in affected}

        replacements: list[WorkItem] = []
        for item in graph.items:
            if item.work_id not in affected_set:
                continue
            replacements.append(
                WorkItem(
                    work_id=id_map[item.work_id],
                    work_kind=item.work_kind,
                    parameters=item.parameters,
                    depends_on=tuple(
                        id_map[parent] if parent in affected_set else parent
                        for parent in item.depends_on
                    ),
                    achieves_criteria=item.achieves_criteria,
                    required_capabilities=item.required_capabilities,
                )
            )

        return RepairProposal(
            graph_id=graph.graph_id,
            pre_state_hash=state.state_hash,
            failed_work_ids=tuple(failed_work_ids),
            affected_work_ids=affected,
            replacement_items=tuple(replacements),
            proposer_id="reference.bounded-repair.v1",
        )


@dataclass(frozen=True)
class RepairPlan:
    repair_id: str
    proposal_id: str
    original_graph_id: str
    failed_work_ids: Tuple[str, ...]
    affected_work_ids: Tuple[str, ...]
    revised_graph: WorkGraph
    repair_certificate_hash: str
    operator_trace: Tuple[str, ...] = ("S", "D", "S", "K")
    deficit_certificate: Optional[DeficitCertificate] = None


@dataclass(frozen=True)
class RepairAdmissionResult:
    accepted: Optional[RepairPlan]
    rejection_reasons: Tuple[str, ...] = ()
    deficit_certificate: Optional[DeficitCertificate] = None


def _has_cycle(items: Sequence[WorkItem]) -> bool:
    deps = {item.work_id: tuple(item.depends_on) for item in items}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for parent in deps.get(node, ()):
            if parent in deps and visit(parent):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in deps)


class SDSKRepairPipeline:
    """Explicit four-operator semantic repair pipeline: S -> D -> S -> K."""

    @staticmethod
    def select_failure(
        graph: WorkGraph,
        failed_work_ids: Sequence[str],
    ) -> Tuple[Tuple[WorkItem, ...], Tuple[str, ...]]:
        affected = affected_closure(graph, failed_work_ids)
        affected_set = set(affected)
        unaffected = tuple(item for item in graph.items if item.work_id not in affected_set)
        return unaffected, affected

    @staticmethod
    def deliberate_replacements(
        graph: WorkGraph,
        affected_work_ids: Sequence[str],
        id_prefix: str = "repair:",
    ) -> Tuple[WorkItem, ...]:
        affected_set = set(affected_work_ids)
        id_map = {work_id: f"{id_prefix}{work_id}" for work_id in affected_work_ids}
        replacements: list[WorkItem] = []
        for item in graph.items:
            if item.work_id not in affected_set:
                continue
            replacements.append(
                WorkItem(
                    work_id=id_map[item.work_id],
                    work_kind=item.work_kind,
                    parameters=item.parameters,
                    depends_on=tuple(
                        id_map[parent] if parent in affected_set else parent
                        for parent in item.depends_on
                    ),
                    achieves_criteria=item.achieves_criteria,
                    required_capabilities=item.required_capabilities,
                )
            )
        return tuple(replacements)

    @staticmethod
    def synthesize_splice(
        unaffected_items: Sequence[WorkItem],
        replacement_items: Sequence[WorkItem],
    ) -> Tuple[WorkItem, ...]:
        spliced = tuple(unaffected_items) + tuple(replacement_items)
        if _has_cycle(spliced):
            raise ValueError("CYCLIC_REPAIR_GRAPH: spliced graph contains a cycle.")
        return spliced

    @staticmethod
    def certify_repair(
        proposal: RepairProposal,
        graph: WorkGraph,
        state: WorldState,
        final_items: Sequence[WorkItem],
        expected_closure: Sequence[str],
    ) -> Tuple[str, str, str, WorkGraph]:
        certificate_payload = {
            "proposal_id": proposal.proposal_id,
            "original_graph_id": graph.graph_id,
            "state_hash": state.state_hash,
            "failed_work_ids": list(proposal.failed_work_ids),
            "affected_work_ids": list(expected_closure),
            "final_work_ids": [item.work_id for item in final_items],
        }
        certificate_hash = hashlib.sha256(
            canonical_json(certificate_payload).encode("utf-8")
        ).hexdigest()
        revised_graph_id = hashlib.sha256(
            f"repair-graph:{graph.graph_id}:{proposal.proposal_id}:{certificate_hash}".encode("utf-8")
        ).hexdigest()
        revised_graph = WorkGraph(
            graph_id=revised_graph_id,
            proposal_id=proposal.proposal_id,
            goal_id=graph.goal_id,
            pre_state_hash=state.state_hash,
            items=tuple(final_items),
            no_op=False,
            proposer_id=proposal.proposer_id,
            formation_certificate_hash=certificate_hash,
        )
        repair_id = hashlib.sha256(
            f"repair:{proposal.proposal_id}:{certificate_hash}".encode("utf-8")
        ).hexdigest()
        return repair_id, certificate_hash, revised_graph_id, revised_graph


class RepairJudge:
    """Admit only dependency-bounded repair that preserves unaffected work."""

    def __init__(
        self,
        *,
        allowed_capabilities: Optional[Sequence[str]] = None,
    ) -> None:
        self.allowed_capabilities = (
            frozenset(allowed_capabilities) if allowed_capabilities is not None else None
        )

    def evaluate(
        self,
        proposal: RepairProposal,
        graph: WorkGraph,
        goal: GoalEnvelope,
        state: WorldState,
        *,
        semantic_assessment: Optional[SemanticAssessment] = None,
        deficit_certificate: Optional[DeficitCertificate] = None,
    ) -> RepairAdmissionResult:
        reasons: list[str] = []

        cert = deficit_certificate or proposal.deficit_certificate
        if semantic_assessment is not None and semantic_assessment.certificate is not None:
            cert = cert or semantic_assessment.certificate

        if cert is not None:
            reasons.append("SEMANTIC_DEFICIT_UNREPAIRABLE")

        if semantic_assessment is not None:
            if semantic_assessment.semantic_class == SemanticClass.UNREPRESENTABLE:
                if "SEMANTIC_DEFICIT_UNREPAIRABLE" not in reasons:
                    reasons.append("SEMANTIC_DEFICIT_UNREPAIRABLE")
            elif (
                semantic_assessment.semantic_class == SemanticClass.UNKNOWN_SURFACE
                or semantic_assessment.semantic_class is None
            ):
                reasons.append("AMBIGUOUS_SURFACE_UNREPAIRABLE")
            if semantic_assessment.readiness == Readiness.POLICY_BLOCKED:
                reasons.append("POLICY_BLOCKED_REPAIR")

        if proposal.graph_id != graph.graph_id:
            reasons.append("GRAPH_LINEAGE_MISMATCH")
        if proposal.pre_state_hash != state.state_hash:
            reasons.append("STALE_PRE_STATE")
        if graph.goal_id != goal.goal_id:
            reasons.append("GOAL_LINEAGE_MISMATCH")

        try:
            expected = affected_closure(graph, proposal.failed_work_ids)
        except KeyError:
            expected = ()
            reasons.append("UNKNOWN_FAILED_WORK")

        proposed_scope = set(proposal.affected_work_ids)
        expected_scope = set(expected)
        if expected_scope - proposed_scope:
            reasons.append("INCOMPLETE_REPAIR_SCOPE")
        if proposed_scope - expected_scope:
            reasons.append("OUT_OF_SCOPE_REPAIR")

        original_by_id = {item.work_id: item for item in graph.items}
        unaffected = tuple(
            item for item in graph.items if item.work_id not in expected_scope
        )
        unaffected_ids = {item.work_id for item in unaffected}
        replacement_ids = [item.work_id for item in proposal.replacement_items]

        if len(replacement_ids) != len(set(replacement_ids)):
            reasons.append("DUPLICATE_REPLACEMENT_ID")
        if unaffected_ids & set(replacement_ids):
            reasons.append("REPLACEMENT_OVERWRITES_UNAFFECTED_WORK")

        if self.allowed_capabilities is not None:
            for item in proposal.replacement_items:
                for cap in item.required_capabilities:
                    if cap not in self.allowed_capabilities:
                        reasons.append("UNAUTHORIZED_REPAIR_CAPABILITY")
                        break

        final_items = unaffected + proposal.replacement_items
        final_ids = {item.work_id for item in final_items}

        for item in proposal.replacement_items:
            if any(dep not in final_ids for dep in item.depends_on):
                reasons.append("UNKNOWN_REPAIR_DEPENDENCY")

        if _has_cycle(final_items):
            reasons.append("CYCLIC_REPAIR_GRAPH")

        original_affected_criteria = {
            criterion
            for work_id in expected_scope
            for criterion in original_by_id[work_id].achieves_criteria
            if work_id in original_by_id
        }
        still_needed_criteria = {
            criterion.criterion_id if hasattr(criterion, "criterion_id") else getattr(criterion, "subject", str(criterion))
            for criterion in goal.success_criteria
            if not criterion_satisfied(state, criterion)
        }
        required_repair_criteria = original_affected_criteria & still_needed_criteria
        replacement_coverage = {
            criterion
            for item in proposal.replacement_items
            for criterion in item.achieves_criteria
        }
        if required_repair_criteria - replacement_coverage:
            reasons.append("REPAIR_LOSES_GOAL_COVERAGE")

        if reasons:
            return RepairAdmissionResult(
                accepted=None,
                rejection_reasons=tuple(dict.fromkeys(reasons)),
                deficit_certificate=cert,
            )

        repair_id, certificate_hash, revised_graph_id, revised_graph = (
            SDSKRepairPipeline.certify_repair(
                proposal,
                graph,
                state,
                final_items,
                expected,
            )
        )
        return RepairAdmissionResult(
            accepted=RepairPlan(
                repair_id=repair_id,
                proposal_id=proposal.proposal_id,
                original_graph_id=graph.graph_id,
                failed_work_ids=proposal.failed_work_ids,
                affected_work_ids=expected,
                revised_graph=revised_graph,
                repair_certificate_hash=certificate_hash,
                operator_trace=("S", "D", "S", "K"),
                deficit_certificate=None,
            ),
            rejection_reasons=(),
            deficit_certificate=None,
        )


class BoundedRepairEngine:
    def __init__(
        self,
        proposer: RepairProposer,
        *,
        judge: Optional[RepairJudge] = None,
        max_budget: int = 3,
    ) -> None:
        self.proposer = proposer
        self.judge = judge or RepairJudge()
        self.max_budget = max_budget

    def repair(
        self,
        graph: WorkGraph,
        goal: GoalEnvelope,
        state: WorldState,
        failed_work_ids: Sequence[str],
        *,
        semantic_assessment: Optional[SemanticAssessment] = None,
        deficit_certificate: Optional[DeficitCertificate] = None,
    ) -> RepairAdmissionResult:
        proposal = self.proposer.propose(graph, state, failed_work_ids)
        return self.judge.evaluate(
            proposal,
            graph,
            goal,
            state,
            semantic_assessment=semantic_assessment,
            deficit_certificate=deficit_certificate,
        )

    def repair_with_budget(
        self,
        graph: WorkGraph,
        goal: GoalEnvelope,
        state: WorldState,
        failed_work_ids: Sequence[str],
        *,
        budget_remaining: int,
        seen_proposals: Tuple[str, ...] = (),
        semantic_assessment: Optional[SemanticAssessment] = None,
        deficit_certificate: Optional[DeficitCertificate] = None,
    ) -> RepairAdmissionResult:
        if budget_remaining <= 0:
            return RepairAdmissionResult(
                accepted=None,
                rejection_reasons=("REPAIR_BUDGET_EXHAUSTED",),
                deficit_certificate=None,
            )
        proposal = self.proposer.propose(graph, state, failed_work_ids)
        if proposal.proposal_id in seen_proposals:
            return RepairAdmissionResult(
                accepted=None,
                rejection_reasons=("REPAIR_OSCILLATION_DETECTED",),
                deficit_certificate=None,
            )
        return self.judge.evaluate(
            proposal,
            graph,
            goal,
            state,
            semantic_assessment=semantic_assessment,
            deficit_certificate=deficit_certificate,
        )


__all__ = [
    "BoundedRepairEngine",
    "ReferenceRepairProposer",
    "RepairAdmissionResult",
    "RepairJudge",
    "RepairPlan",
    "RepairProposal",
    "RepairProposer",
    "SDSKRepairPipeline",
    "affected_closure",
]
