"""R4 A2 composition reconstruction helpers.

R3 closure helpers build ordinary UoWs for accepted meta-runtime changes. This
module applies those UoWs through the R3 minimal authority kernel rather than
through canonical uow.engine.commit.
"""
from __future__ import annotations

from typing import Mapping, Tuple

from uow.composition.binding import ActorBinding
from uow.composition.contract import ParentContract
from uow.composition.convergence import AuthoritativeHistory
from uow.composition.delegation import DelegationCertificate
from uow.composition.graph import RealizationGraph
from uow.composition.mutation import RuntimeMutationQC, verify_mutation_qc
from uow.composition.substitution import GraphReplacementCertificate
from uow.state import WorldState

from .adapters import adapt_world_state
from .identity import shadow_identity
from .kernel import LocalAuthorization, apply_authorized_transition
from .types import CausalCoordinate, ConformanceDecision, ProposalEnvelope
from .closure import (
    make_certified_graph_substitution_uow,
    make_qc_authorized_runtime_mutation_uow,
    make_validated_delegation_registration_uow,
    make_validated_rebinding_uow,
    make_verified_history_reconciliation_uow,
)
from .reconstruction import execute_explicit_uow_reconstructed
from .types import ConformanceResult, EvidenceEntryRef


def apply_graph_substitution_reconstructed(
    state: WorldState,
    certificate: GraphReplacementCertificate,
) -> Tuple[WorldState, EvidenceEntryRef]:
    return execute_explicit_uow_reconstructed(
        make_certified_graph_substitution_uow(certificate),
        state,
    )


def apply_rebinding_reconstructed(
    state: WorldState,
    *,
    active_graph_hash: str,
    candidate_binding_hash: str,
    conformance: ConformanceResult,
) -> Tuple[WorldState, EvidenceEntryRef]:
    return execute_explicit_uow_reconstructed(
        make_validated_rebinding_uow(
            active_graph_hash=active_graph_hash,
            candidate_binding_hash=candidate_binding_hash,
            conformance=conformance,
        ),
        state,
    )


def apply_delegation_reconstructed(
    state: WorldState,
    certificate: DelegationCertificate,
    conformance: ConformanceResult,
) -> Tuple[WorldState, EvidenceEntryRef]:
    return execute_explicit_uow_reconstructed(
        make_validated_delegation_registration_uow(certificate, conformance),
        state,
    )


def apply_history_reconciliation_reconstructed(
    state: WorldState,
    canonical_history: AuthoritativeHistory,
) -> Tuple[WorldState, EvidenceEntryRef]:
    return execute_explicit_uow_reconstructed(
        make_verified_history_reconciliation_uow(canonical_history),
        state,
    )


def apply_runtime_mutation_reconstructed(
    state: WorldState,
    qc: RuntimeMutationQC,
) -> Tuple[WorldState, EvidenceEntryRef]:
    return execute_explicit_uow_reconstructed(
        make_qc_authorized_runtime_mutation_uow(qc),
        state,
    )



def apply_runtime_mutation_qc_semantic(
    state: WorldState,
    qc: RuntimeMutationQC,
    *,
    parent_contract_id: str,
) -> Tuple[WorldState, EvidenceEntryRef]:
    """Apply an already-verified runtime mutation QC through the minimal kernel."""
    proposed = (
        state
        .with_attribute("__runtime_active_graph_hash__", qc.candidate_graph_hash)
        .with_attribute("__runtime_active_binding_hash__", qc.candidate_binding_hash)
        .with_attribute("__runtime_generation__", int(state.get("__runtime_generation__", 0)) + 1)
        .with_attribute("__runtime_history_parent__", qc.history_head)
        .with_attribute("__runtime_last_mutation_qc_hash__", qc.compute_hash())
    )
    committed = proposed.advance_sequence()

    conformance_id = shadow_identity(
        "runtime-mutation-qc-conformance",
        {
            "qc_hash": qc.compute_hash(),
            "parent_contract_id": parent_contract_id,
            "pre_state_hash": state.state_hash,
            "proposed_state_hash": proposed.state_hash,
        },
    )
    conformance = ConformanceResult(
        conformance_id=conformance_id,
        subject_id=proposed.state_hash,
        contract_id=parent_contract_id,
        context_id=state.state_hash,
        decision=ConformanceDecision.ACCEPT,
        violations=(),
        evidence={
            "qc_hash": qc.compute_hash(),
            "signers": qc.signers,
            "candidate_graph_hash": qc.candidate_graph_hash,
            "candidate_binding_hash": qc.candidate_binding_hash,
            "history_head": qc.history_head,
        },
        source_validator="r4.runtime_mutation_qc",
    )
    authorization = LocalAuthorization(
        authorization_id=qc.compute_hash(),
        authority_id="runtime-mutation-quorum",
        profile="DISTRIBUTED_QUORUM",
        conformance_id=conformance.conformance_id,
        contract_id=parent_contract_id,
        context_id=state.state_hash,
    )
    proposal_id = shadow_identity(
        "runtime-mutation-application",
        {
            "qc_hash": qc.compute_hash(),
            "pre_state_hash": state.state_hash,
            "proposed_state_hash": proposed.state_hash,
        },
    )
    envelope = ProposalEnvelope(
        proposal_id=proposal_id,
        proposal_kind="RUNTIME_MUTATION_APPLICATION",
        proposer_id=qc.qc_id,
        subject_contract_id=parent_contract_id,
        precondition_context_id=state.state_hash,
        causal_coordinate=CausalCoordinate("runtime_meta_state_hash", state.state_hash),
        candidate_payload={
            "proposed_state_id": proposed.state_hash,
            "committed_state_id": committed.state_hash,
            "next_semantic_payload": dict(committed.attributes),
            "next_status": committed.status,
            "next_cursor": committed.cursor,
        },
        proposal_identity=proposal_id,
        metadata={"qc_hash": qc.compute_hash()},
        source_type="r4.a2.runtime-mutation",
    )
    after_ref, evidence = apply_authorized_transition(
        adapt_world_state(state),
        envelope,
        conformance,
        authorization,
        evidence_profile="SHADOW-A2-MUTATION-L2",
    )
    if after_ref.state_id != committed.state_hash:
        raise AssertionError("R4 runtime mutation state identity divergence.")
    return committed, evidence


def apply_verified_runtime_mutation_reconstructed(
    state: WorldState,
    qc: RuntimeMutationQC,
    *,
    parent_contract: ParentContract,
    candidate_graph: RealizationGraph,
    candidate_binding: ActorBinding,
    authority_keys: Mapping[str, str],
    current_history_head: str,
    current_generation: int,
    threshold: int = 2,
) -> Tuple[WorldState, EvidenceEntryRef]:
    """Verify the complete A2.7 authorization context then apply through shadow authority."""
    valid, reason = verify_mutation_qc(
        qc=qc,
        parent_contract=parent_contract,
        current_history_head=current_history_head,
        current_generation=current_generation,
        authority_keys=authority_keys,
        threshold=threshold,
    )
    if not valid:
        raise ValueError(f"Invalid runtime mutation QC: {reason}")
    if candidate_graph.compute_hash() != qc.candidate_graph_hash:
        raise ValueError("CANDIDATE_GRAPH_HASH_MISMATCH")
    if candidate_binding.compute_hash() != qc.candidate_binding_hash:
        raise ValueError("CANDIDATE_BINDING_HASH_MISMATCH")
    if int(state.get("__runtime_generation__", current_generation)) != current_generation:
        raise ValueError("META_STATE_GENERATION_MISMATCH")
    if str(state.get("__runtime_history_parent__", current_history_head)) != current_history_head:
        raise ValueError("META_STATE_HISTORY_HEAD_MISMATCH")

    return apply_runtime_mutation_qc_semantic(
        state,
        qc,
        parent_contract_id=parent_contract.contract_id,
    )
