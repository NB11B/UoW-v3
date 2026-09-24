from __future__ import annotations

from dataclasses import replace

import pytest

from uow.contracts import Guard, GuardOp, Mutation, MutationOp, Route, Successor, make_uow
from uow.engine import Proposal, commit, propose, certify
from uow.state import WorldState

from uow_shadow.adapters import adapt_world_state, core_certify_adapter
from uow_shadow.identity import shadow_identity
from uow_shadow.kernel import (
    apply_authorized_transition,
    authorize_local_conformance,
)
from uow_shadow.types import CausalCoordinate, ProposalEnvelope


def _transition():
    uow = make_uow(
        "u1",
        [
            Route(
                guard=Guard(GuardOp.ALWAYS),
                mutations=(Mutation(MutationOp.SET, "x", 1),),
                successor=Successor.halt(),
            )
        ],
    )
    before = WorldState(attributes={"x": 0}, cursor="u1")
    proposal = propose(uow, before)
    certificate = certify(uow, before, proposal)
    assert certificate.is_valid
    canonical_after, canonical_evidence = commit(
        uow,
        before,
        proposal,
        certificate,
        prev_evidence_hash="0" * 64,
        step_number=1,
    )
    return uow, before, proposal, certificate, canonical_after, canonical_evidence


def _proposal_envelope(before, proposal):
    payload = {
        "proposed_state_id": proposal.proposed_state.state_hash,
        "next_semantic_payload": dict(proposal.proposed_state.attributes),
        "next_status": proposal.proposed_state.status,
        "next_cursor": proposal.proposed_state.cursor,
    }
    pid = shadow_identity(
        "minimal-kernel-proposal",
        {
            "contract": proposal.uow_id,
            "pre_state": before.state_hash,
            "payload": payload,
        },
    )
    return ProposalEnvelope(
        proposal_id=pid,
        proposal_kind="STATE_TRANSITION",
        proposer_id="canonical-core-propose",
        subject_contract_id=proposal.uow_id,
        precondition_context_id=before.state_hash,
        causal_coordinate=CausalCoordinate("pre_state_hash", before.state_hash),
        candidate_payload=payload,
        proposal_identity=pid,
        source_type="canonical-parity-test",
    )


def test_minimal_authority_kernel_matches_canonical_transition_semantics():
    uow, before, proposal, certificate, canonical_after, canonical_evidence = _transition()

    before_ref = adapt_world_state(before)
    conformance = core_certify_adapter(uow, before, proposal)
    assert conformance.accepted
    authorization = authorize_local_conformance(conformance)
    envelope = _proposal_envelope(before, proposal)

    shadow_after, shadow_evidence = apply_authorized_transition(
        before_ref,
        envelope,
        conformance,
        authorization,
    )

    assert dict(shadow_after.semantic_payload) == dict(canonical_after.attributes)
    assert shadow_after.cursor == canonical_after.cursor
    assert shadow_after.status == canonical_after.status
    assert shadow_after.causal_coordinate.kind == "state_sequence"
    assert shadow_after.causal_coordinate.value == canonical_after.sequence

    assert shadow_evidence.subject_id == canonical_evidence.uow_id
    assert shadow_evidence.pre_context_identity == before.state_hash
    assert shadow_evidence.proposal_reference == envelope.proposal_identity
    assert shadow_evidence.conformance_reference == conformance.conformance_id
    assert shadow_evidence.authorization_reference == authorization.authorization_id


def test_rejected_conformance_cannot_be_authorized_or_committed():
    uow, before, proposal, _, _, _ = _transition()
    tampered = Proposal(
        uow_id=proposal.uow_id,
        pre_state_hash=proposal.pre_state_hash,
        selected_route_index=proposal.selected_route_index,
        proposed_state=proposal.proposed_state.with_attribute("x", 99),
        selected_successor=proposal.selected_successor,
        halted=proposal.halted,
    )
    conformance = core_certify_adapter(uow, before, tampered)
    assert not conformance.accepted

    with pytest.raises(ValueError, match="Rejected conformance"):
        authorize_local_conformance(conformance)


def test_minimal_kernel_rejects_stale_context_after_authorization():
    uow, before, proposal, _, _, _ = _transition()
    conformance = core_certify_adapter(uow, before, proposal)
    authorization = authorize_local_conformance(conformance)
    envelope = _proposal_envelope(before, proposal)

    stale_ref = replace(
        adapt_world_state(before),
        state_id="different-current-state",
        causal_coordinate=CausalCoordinate("state_sequence", before.sequence + 1),
    )

    with pytest.raises(ValueError, match="stale"):
        apply_authorized_transition(
            stale_ref,
            envelope,
            conformance,
            authorization,
        )


def test_minimal_kernel_rejects_authorization_for_different_conformance():
    uow, before, proposal, _, _, _ = _transition()
    conformance = core_certify_adapter(uow, before, proposal)
    authorization = authorize_local_conformance(conformance)
    envelope = _proposal_envelope(before, proposal)

    wrong_authorization = replace(
        authorization,
        conformance_id="different-conformance",
    )

    with pytest.raises(ValueError, match="Authorization does not bind"):
        apply_authorized_transition(
            adapt_world_state(before),
            envelope,
            conformance,
            wrong_authorization,
        )
