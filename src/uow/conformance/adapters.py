"""Production adapters over specialized canonical validators.

These adapters normalize invocation/results only. The specialized predicates
remain authoritative and are not replaced by generic matching.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from ..composition.binding import ActorBinding, validate_binding
from ..composition.delegation import AuthorityScope, DelegationCertificate, validate_delegation
from ..composition.mutation import (
    AuthorityMutationVote,
    RuntimeMutationQC,
    verify_mutation_qc,
    verify_mutation_vote,
)
from ..composition.projection import project_semantics
from ..effects.certification import ReceiptAuthenticator, verify_effect_receipt_binding
from ..effects.descriptor import EffectDescriptor, EffectReceipt
from ..resources.requirement import ResourceBoundTask, ResourceRequirement, verify_requirement_binding
from ..resources.state import ResourceState
from ..state import WorldState
from ..transactions.descriptor import TransactionDescriptor
from ..transactions.occ import validate_occ

from .identity import conformance_identity
from .types import ConformanceDecision, ConformanceResult


def occ_adapter(current_state: WorldState, tx: TransactionDescriptor) -> ConformanceResult:
    valid, hazard, details = validate_occ(current_state, tx)
    decision = ConformanceDecision.ACCEPT if valid else ConformanceDecision.REJECT
    violations = () if valid else (hazard.value if hazard is not None else "OCC_REJECTED",)
    cid = conformance_identity(
        "occ-conformance",
        {
            "uow_id": tx.uow_id,
            "base_sequence": tx.base_sequence,
            "current_state_hash": current_state.state_hash,
            "decision": decision.value,
            "hazard": hazard.value if hazard is not None else None,
            "details": details,
        },
    )
    return ConformanceResult(
        conformance_id=cid,
        subject_id=tx.proposed_state_hash,
        contract_id=f"occ::{tx.uow_id}",
        context_id=current_state.state_hash,
        decision=decision,
        violations=violations,
        evidence={"hazard": hazard.value if hazard else None, "details": details},
        source_validator="uow.transactions.validate_occ",
    )


def resource_capacity_adapter(
    requirement: ResourceRequirement,
    resource_state: ResourceState,
    *,
    subject_id: str = "resource-candidate",
    context_id: str = "resource-state",
) -> ConformanceResult:
    valid = resource_state.can_accommodate(requirement)
    decision = ConformanceDecision.ACCEPT if valid else ConformanceDecision.REJECT
    cid = conformance_identity(
        "resource-capacity-conformance",
        {
            "subject_id": subject_id,
            "context_id": context_id,
            "requirement": requirement.to_dict(),
            "resource_state": resource_state.to_dict(),
            "decision": decision.value,
        },
    )
    return ConformanceResult(
        conformance_id=cid,
        subject_id=subject_id,
        contract_id="resource-requirement",
        context_id=context_id,
        decision=decision,
        violations=() if valid else ("RESOURCE_CAPACITY_OR_BUDGET_DEFICIT",),
        evidence={"requirement": requirement.to_dict(), "resource_state": resource_state.to_dict()},
        source_validator="uow.resources.ResourceState.can_accommodate",
    )


def resource_binding_adapter(task: ResourceBoundTask) -> ConformanceResult:
    valid = verify_requirement_binding(task)
    decision = ConformanceDecision.ACCEPT if valid else ConformanceDecision.REJECT
    cid = conformance_identity(
        "resource-binding-conformance",
        {
            "uow_id": task.uow.H.identity,
            "requirement_hash": task.requirement_hash,
            "parent_context": task.uow.H.parent_context,
            "decision": decision.value,
        },
    )
    return ConformanceResult(
        conformance_id=cid,
        subject_id=task.uow.H.identity,
        contract_id="resource-requirement-binding",
        context_id=task.uow.H.parent_context,
        decision=decision,
        violations=() if valid else ("RESOURCE_REQUIREMENT_BINDING_MISMATCH",),
        evidence={"requirement_hash": task.requirement_hash},
        source_validator="uow.resources.verify_requirement_binding",
    )


def actor_binding_adapter(
    graph: Any,
    binding: ActorBinding,
    registry: Any,
    *,
    fabric: Optional[Any] = None,
    current_ts: Optional[float] = None,
) -> ConformanceResult:
    valid, violations = validate_binding(
        graph, binding, registry, fabric=fabric, current_ts=current_ts
    )
    decision = ConformanceDecision.ACCEPT if valid else ConformanceDecision.REJECT
    cid = conformance_identity(
        "actor-binding-conformance",
        {
            "graph_id": graph.graph_id,
            "binding_id": binding.binding_id,
            "binding_hash": binding.compute_hash(),
            "decision": decision.value,
            "violations": violations,
        },
    )
    return ConformanceResult(
        conformance_id=cid,
        subject_id=binding.compute_hash(),
        contract_id=f"binding::{graph.graph_id}",
        context_id=graph.compute_hash(),
        decision=decision,
        violations=tuple(violations),
        evidence={"binding_id": binding.binding_id, "graph_id": graph.graph_id},
        source_validator="uow.composition.validate_binding",
    )


def semantic_projection_adapter(graph: Any, contract: Any) -> ConformanceResult:
    projection = project_semantics(graph, contract)
    decision = ConformanceDecision.ACCEPT if projection.conforms else ConformanceDecision.REJECT
    return ConformanceResult(
        conformance_id=projection.projection_hash,
        subject_id=graph.compute_hash(),
        contract_id=contract.contract_id,
        context_id=contract.compute_hash(),
        decision=decision,
        violations=tuple(projection.violations),
        evidence={
            "projection_hash": projection.projection_hash,
            "outputs": projection.outputs,
            "critical_path_ms": projection.measured_critical_path_ms,
            "cost_units": projection.measured_cost_units,
        },
        source_validator="uow.composition.project_semantics",
    )


def delegation_adapter(
    parent_scope: AuthorityScope,
    certificate: DelegationCertificate,
    *,
    fabric: Optional[Any] = None,
    current_ts: Optional[float] = None,
) -> ConformanceResult:
    valid, violations = validate_delegation(
        parent_scope, certificate, fabric=fabric, current_ts=current_ts
    )
    decision = ConformanceDecision.ACCEPT if valid else ConformanceDecision.REJECT
    return ConformanceResult(
        conformance_id=certificate.compute_hash(),
        subject_id=certificate.child_uow_id,
        contract_id=certificate.parent_contract_id,
        context_id=f"generation:{certificate.generation}",
        decision=decision,
        violations=tuple(violations),
        evidence={
            "delegate_actor_id": certificate.delegate_actor_id,
            "authority_scope": certificate.authority_scope.to_strings(),
            "expires_at_ts": certificate.expires_at_ts,
        },
        source_validator="uow.composition.validate_delegation",
    )


def effect_receipt_adapter(
    effect: EffectDescriptor,
    receipt: EffectReceipt,
    *,
    authenticator: Optional[ReceiptAuthenticator] = None,
    expected_signer: Optional[str] = None,
) -> ConformanceResult:
    violations = []
    try:
        verify_effect_receipt_binding(
            effect, receipt, authenticator=authenticator, expected_signer=expected_signer
        )
    except ValueError as exc:
        violations.append(str(exc))

    decision = ConformanceDecision.ACCEPT if not violations else ConformanceDecision.REJECT
    cid = conformance_identity(
        "effect-receipt-conformance",
        {
            "effect_id": effect.effect_id,
            "receipt_hash": receipt.receipt_hash,
            "decision": decision.value,
            "violations": violations,
        },
    )
    return ConformanceResult(
        conformance_id=cid,
        subject_id=receipt.receipt_hash,
        contract_id=effect.effect_id,
        context_id=effect.pre_state_hash,
        decision=decision,
        violations=tuple(violations),
        evidence={
            "effect_id": receipt.effect_id,
            "idempotency_key": receipt.idempotency_key,
            "response_hash": receipt.response_hash,
        },
        source_validator="uow.effects.verify_effect_receipt_binding",
    )


def mutation_vote_adapter(vote: AuthorityMutationVote, secret_key: str) -> ConformanceResult:
    valid, reason = verify_mutation_vote(vote, secret_key)
    decision = ConformanceDecision.ACCEPT if valid else ConformanceDecision.REJECT
    return ConformanceResult(
        conformance_id=conformance_identity(
            "mutation-vote-verification",
            {"vote_hash": vote.compute_hash(), "decision": decision.value, "reason": reason},
        ),
        subject_id=vote.compute_hash(),
        contract_id=vote.parent_contract_hash,
        context_id=f"{vote.generation}:{vote.history_head}",
        decision=decision,
        violations=() if valid else (reason,),
        evidence={"voter_id": vote.voter_id, "reason": reason},
        source_validator="uow.composition.verify_mutation_vote",
    )


def mutation_qc_adapter(
    qc: RuntimeMutationQC,
    parent_contract: Any,
    current_history_head: str,
    current_generation: int,
    authority_keys: Mapping[str, str],
    *,
    threshold: int = 2,
) -> ConformanceResult:
    valid, reason = verify_mutation_qc(
        qc,
        parent_contract,
        current_history_head,
        current_generation,
        authority_keys,
        threshold=threshold,
    )
    decision = ConformanceDecision.ACCEPT if valid else ConformanceDecision.REJECT
    return ConformanceResult(
        conformance_id=qc.compute_hash(),
        subject_id=qc.proposal_hash,
        contract_id=qc.parent_contract_hash,
        context_id=f"{current_generation}:{current_history_head}",
        decision=decision,
        violations=() if valid else (reason,),
        evidence={
            "qc_id": qc.qc_id,
            "signers": qc.signers,
            "threshold": qc.threshold,
            "reason": reason,
        },
        source_validator="uow.composition.verify_mutation_qc",
    )
