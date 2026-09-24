"""Minimal research-only authority kernel for R3.4.

This module is independent of the canonical commit implementation. It exercises
only the R2 semantic flow:

State -> Proposal -> Conformance -> Authorization -> Transition -> Evidence

The LOCAL_DETERMINISTIC_CERTIFIER profile models the current canonical core,
where an accepted certificate from the trusted deterministic certifier is
sufficient local authorization to commit. This is a profile-specific rule, not
a universal claim that conformance always equals authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .identity import shadow_identity
from .types import (
    AuthoritativeStateRef,
    CausalCoordinate,
    ConformanceResult,
    EvidenceEntryRef,
    ProposalEnvelope,
)


LOCAL_DETERMINISTIC_CERTIFIER = "LOCAL_DETERMINISTIC_CERTIFIER"


@dataclass(frozen=True)
class LocalAuthorization:
    authorization_id: str
    authority_id: str
    profile: str
    conformance_id: str
    contract_id: str
    context_id: str


def authorize_local_conformance(
    conformance: ConformanceResult,
    *,
    authority_id: str = "canonical-deterministic-certifier",
) -> LocalAuthorization:
    if not conformance.accepted:
        raise ValueError("Rejected conformance cannot be locally authorized.")

    payload = {
        "authority_id": authority_id,
        "profile": LOCAL_DETERMINISTIC_CERTIFIER,
        "conformance_id": conformance.conformance_id,
        "contract_id": conformance.contract_id,
        "context_id": conformance.context_id,
    }
    return LocalAuthorization(
        authorization_id=shadow_identity("local-authorization", payload),
        authority_id=authority_id,
        profile=LOCAL_DETERMINISTIC_CERTIFIER,
        conformance_id=conformance.conformance_id,
        contract_id=conformance.contract_id,
        context_id=conformance.context_id,
    )


def apply_authorized_transition(
    before: AuthoritativeStateRef,
    proposal: ProposalEnvelope,
    conformance: ConformanceResult,
    authorization: LocalAuthorization,
    *,
    evidence_profile: str = "SHADOW-SEMANTIC-L2",
) -> Tuple[AuthoritativeStateRef, EvidenceEntryRef]:
    """Apply one already-conformed and locally authorized state transition."""
    if not conformance.accepted:
        raise ValueError("Rejected conformance cannot mutate authoritative state.")
    if proposal.subject_contract_id != conformance.contract_id:
        raise ValueError("Proposal/conformance contract mismatch.")
    if proposal.precondition_context_id != before.state_id:
        raise ValueError("Proposal is stale for the supplied authoritative state.")
    if conformance.context_id != before.state_id:
        raise ValueError("Conformance is stale for the supplied authoritative state.")
    if authorization.conformance_id != conformance.conformance_id:
        raise ValueError("Authorization does not bind the supplied conformance.")
    if authorization.contract_id != conformance.contract_id:
        raise ValueError("Authorization contract mismatch.")
    if authorization.context_id != before.state_id:
        raise ValueError("Authorization is stale for the supplied authoritative state.")

    candidate_state_id = str(proposal.candidate_payload.get("proposed_state_id", ""))
    if candidate_state_id != conformance.subject_id:
        raise ValueError("Conformance does not bind the proposal's candidate state.")

    if before.causal_coordinate.kind != "state_sequence":
        raise ValueError("Local authority profile requires state_sequence causal coordinates.")
    next_sequence = int(before.causal_coordinate.value) + 1

    next_payload = dict(proposal.candidate_payload.get("next_semantic_payload", {}))
    next_status = str(proposal.candidate_payload.get("next_status", before.status))
    next_cursor = proposal.candidate_payload.get("next_cursor")

    state_identity_payload = {
        "schema_id": before.schema_id,
        "schema_version": before.schema_version,
        "semantic_payload": next_payload,
        "status": next_status,
        "cursor": next_cursor,
        "causal_coordinate": {
            "kind": "state_sequence",
            "value": next_sequence,
        },
    }
    after_id = shadow_identity("authoritative-state", state_identity_payload)
    after = AuthoritativeStateRef(
        state_id=after_id,
        schema_id=before.schema_id,
        schema_version=before.schema_version,
        semantic_payload=next_payload,
        causal_coordinate=CausalCoordinate("state_sequence", next_sequence),
        status=next_status,
        cursor=next_cursor,
        source_type="uow_shadow.kernel",
    )

    evidence_payload = {
        "subject_id": proposal.subject_contract_id,
        "pre_context_identity": before.state_id,
        "post_context_identity_or_outcome": after.state_id,
        "proposal_reference": proposal.proposal_identity,
        "conformance_reference": conformance.conformance_id,
        "authorization_reference": authorization.authorization_id,
        "causal_references": (before.state_id,),
        "evidence_profile": evidence_profile,
    }
    entry_id = shadow_identity("evidence-entry", evidence_payload)
    evidence = EvidenceEntryRef(
        entry_id=entry_id,
        event_kind="AUTHORIZED_TRANSITION",
        subject_id=proposal.subject_contract_id,
        causal_references=(before.state_id,),
        pre_context_identity=before.state_id,
        post_context_identity_or_outcome=after.state_id,
        evidence_profile=evidence_profile,
        entry_identity=entry_id,
        proposal_reference=proposal.proposal_identity,
        conformance_reference=conformance.conformance_id,
        authorization_reference=authorization.authorization_id,
        issuer_or_source=authorization.authority_id,
        source_type="uow_shadow.kernel",
    )
    return after, evidence
