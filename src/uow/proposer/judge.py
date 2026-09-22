"""Deterministic Judge certifying external model proposals against legality invariants (Gate U14)."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..resources.requirement import ResourceBoundTask, ResourceRequirement
from ..resources.state import ResourceState, get_authoritative_resource_state
from ..state import WorldState
from ..transactions.descriptor import infer_footprint
from .types import ModelProposal, ProposalCertificate


def certify_proposal(
    proposal: Optional[ModelProposal],
    ready_tasks: Sequence[str],
    graph: Mapping[str, Any],
    state: WorldState,
    *,
    resource_registry: Optional[Mapping[str, ResourceRequirement]] = None,
) -> ProposalCertificate:
    """Deterministic Judge certifying a candidate proposal against legality invariants.

    Enforces:
    1. Freshness check: input_state_hash and input_sequence match authoritative WorldState (Gate U14.6).
    2. Dependency readiness: tasks exist in graph and pending ready frontier (Gate U14.3).
    3. Disjoint OCC concurrency: no intra-batch read/write or write/write hazards (Gate U14.4).
    4. Resource capacity legality: aggregate batch demand <= available capacities/budgets (Gate U14.5).

    Returns an immutable ProposalCertificate. If accepted_tasks is empty, fallback_triggered is True.
    """
    if proposal is None:
        return ProposalCertificate(
            proposal_hash="NULL_PROPOSAL_HASH",
            is_valid=False,
            accepted_tasks=(),
            rejected_tasks={"*": "PROPOSER_CRASHED_OR_RETURNED_NONE"},
            fallback_triggered=True,
        )

    accepted: List[str] = []
    rejected: Dict[str, str] = {}

    # Invariant 1: State Hash and Freshness (Gate U14.6)
    if proposal.input_state_hash != state.state_hash or proposal.input_sequence != state.sequence:
        for t in proposal.candidate_schedule:
            rejected[t] = (
                f"STALE_STATE_HASH_OR_EPOCH: proposal sequence {proposal.input_sequence} "
                f"or state_hash {proposal.input_state_hash[:16]} != current sequence {state.sequence} / {state.state_hash[:16]}"
            )
        return ProposalCertificate(
            proposal_hash=proposal.proposal_hash,
            is_valid=False,
            accepted_tasks=(),
            rejected_tasks=rejected,
            fallback_triggered=True,
        )

    # Invariant 2: Dependency Readiness (Gate U14.3)
    ready_set = set(ready_tasks)
    valid_ready_candidates: List[str] = []
    for t in proposal.candidate_schedule:
        if t not in graph:
            rejected[t] = f"UNKNOWN_TASK: task '{t}' does not exist in graph"
        elif t not in ready_set:
            rejected[t] = f"DEPENDENCY_UNSATISFIED: task '{t}' is not in ready set"
        else:
            valid_ready_candidates.append(t)

    # Invariant 3: Intra-batch OCC Conflict Checking (Gate U14.4)
    occ_passed: List[str] = []
    batch_writes: Dict[str, str] = {}
    batch_reads: Dict[str, str] = {}

    for t in valid_ready_candidates:
        item = graph[t]
        uow = item.uow if isinstance(item, ResourceBoundTask) else item
        _idx, route = uow.Gamma.select_route(state)
        r_set, w_set = infer_footprint(route)

        conflict = False
        # Write-Write Conflict
        for w in w_set:
            if w in batch_writes:
                rejected[t] = (
                    f"OCC_WRITE_WRITE_CONFLICT: target '{w}' already written by '{batch_writes[w]}'"
                )
                conflict = True
                break
        if conflict:
            continue

        # Write-Read Conflict
        for w in w_set:
            if w in batch_reads:
                rejected[t] = (
                    f"OCC_READ_WRITE_CONFLICT: target '{w}' concurrently read by '{batch_reads[w]}'"
                )
                conflict = True
                break
        if conflict:
            continue

        # Read-Write Conflict
        for r in r_set:
            if r in batch_writes:
                rejected[t] = (
                    f"OCC_WRITE_READ_CONFLICT: target '{r}' concurrently written by '{batch_writes[r]}'"
                )
                conflict = True
                break
        if conflict:
            continue

        for w in w_set:
            batch_writes[w] = t
        for r in r_set:
            batch_reads[r] = t
        occ_passed.append(t)

    # Invariant 4: Resource Capacity Bounds (Gate U14.5)
    sim_res: ResourceState = get_authoritative_resource_state(state)

    for t in occ_passed:
        item = graph[t]
        req: Optional[ResourceRequirement] = None
        if isinstance(item, ResourceBoundTask):
            req = item.requirement
        elif resource_registry and t in resource_registry:
            req = resource_registry[t]
        elif hasattr(item, "resources") and isinstance(item.resources, ResourceRequirement):
            req = item.resources

        if req is not None:
            if sim_res.can_accommodate(req):
                sim_res, _ = sim_res.acquire_lease(t, req, sequence=state.sequence)
                accepted.append(t)
            else:
                rejected[t] = (
                    f"RESOURCE_CAPACITY_EXCEEDED: insufficient capacity for task '{t}' "
                    f"demanding {req.leased_allocations_dict()}"
                )
        else:
            accepted.append(t)

    is_valid = len(accepted) > 0 and len(rejected) == 0
    fallback_triggered = len(accepted) == 0

    return ProposalCertificate(
        proposal_hash=proposal.proposal_hash,
        is_valid=is_valid,
        accepted_tasks=tuple(accepted),
        rejected_tasks=rejected,
        fallback_triggered=fallback_triggered,
    )
