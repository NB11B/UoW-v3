"""R6 prototype: common authority application spine.

This is the candidate common internal control flow recovered from the experiment
chain. It is research-only and does not replace src/uow.

Domain-specific proposal formation, validators, authorization profiles, and
external-effect invocation remain outside this spine.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from uow.contracts import UoW
from uow.engine import Proposal, propose
from uow.state import WorldState

from .adapters import adapt_world_state, core_certify_adapter
from .identity import shadow_identity
from .kernel import LocalAuthorization, apply_authorized_transition, authorize_local_conformance
from .types import CausalCoordinate, ConformanceResult, EvidenceEntryRef, ProposalEnvelope


class CursorPolicy(str, Enum):
    OWNED = "OWNED"
    DETACHED = "DETACHED"


@dataclass(frozen=True)
class SpineResult:
    state: WorldState
    evidence: EvidenceEntryRef
    proposal: Proposal
    proposal_envelope: ProposalEnvelope
    conformance: ConformanceResult
    authorization: LocalAuthorization


def _proposal_envelope(
    before: WorldState,
    proposal: Proposal,
) -> tuple[ProposalEnvelope, WorldState]:
    committed_mirror = proposal.proposed_state.advance_sequence()
    payload = {
        "proposed_state_id": proposal.proposed_state.state_hash,
        "committed_state_id": committed_mirror.state_hash,
        "next_semantic_payload": dict(committed_mirror.attributes),
        "next_status": committed_mirror.status,
        "next_cursor": committed_mirror.cursor,
    }
    proposal_id = shadow_identity(
        "application-spine-proposal",
        {
            "uow_id": proposal.uow_id,
            "pre_state_hash": proposal.pre_state_hash,
            "selected_route_index": proposal.selected_route_index,
            "selected_successor": proposal.selected_successor,
            "halted": proposal.halted,
            "payload": payload,
        },
    )
    return (
        ProposalEnvelope(
            proposal_id=proposal_id,
            proposal_kind="STATE_TRANSITION",
            proposer_id="canonical-native-proposer",
            subject_contract_id=proposal.uow_id,
            precondition_context_id=before.state_hash,
            causal_coordinate=CausalCoordinate("pre_state_hash", before.state_hash),
            candidate_payload=payload,
            proposal_identity=proposal_id,
            source_type="r6.application_spine",
        ),
        committed_mirror,
    )


class ApplicationSpine:
    """Common native-UoW application path.

    OWNED requires the current cursor to name the supplied UoW.
    DETACHED permits a certified control-plane UoW whose own transition relation
    explicitly determines whether the enclosing cursor is preserved or changed.
    """

    def execute(
        self,
        uow: UoW,
        state: WorldState,
        *,
        cursor_policy: CursorPolicy,
        authority_id: str = "canonical-deterministic-certifier",
        evidence_profile: str = "SHADOW-SEMANTIC-L2",
    ) -> SpineResult:
        if state.status != "RUNNING":
            raise ValueError("Application spine requires RUNNING authoritative state.")

        if cursor_policy is CursorPolicy.OWNED:
            if state.cursor is None:
                raise ValueError("Cursor-owned application requires an active cursor.")
            if state.cursor != uow.H.identity:
                raise ValueError(
                    f"Cursor-owned application expected {state.cursor!r}, got UoW {uow.H.identity!r}."
                )

        proposal = propose(uow, state)
        conformance = core_certify_adapter(uow, state, proposal)
        if not conformance.accepted:
            raise ValueError(
                f"Canonical conformance rejected application-spine proposal: {conformance.violations}"
            )
        authorization = authorize_local_conformance(
            conformance,
            authority_id=authority_id,
        )
        envelope, committed_mirror = _proposal_envelope(state, proposal)

        after_ref, evidence = apply_authorized_transition(
            adapt_world_state(state),
            envelope,
            conformance,
            authorization,
            evidence_profile=evidence_profile,
        )

        if dict(after_ref.semantic_payload) != dict(committed_mirror.attributes):
            raise AssertionError("Application spine payload divergence.")
        if after_ref.cursor != committed_mirror.cursor:
            raise AssertionError("Application spine cursor divergence.")
        if after_ref.status != committed_mirror.status:
            raise AssertionError("Application spine status divergence.")
        if int(after_ref.causal_coordinate.value) != committed_mirror.sequence:
            raise AssertionError("Application spine sequence divergence.")
        if after_ref.state_id != committed_mirror.state_hash:
            raise AssertionError("Application spine state-identity divergence.")

        return SpineResult(
            state=committed_mirror,
            evidence=evidence,
            proposal=proposal,
            proposal_envelope=envelope,
            conformance=conformance,
            authorization=authorization,
        )


DEFAULT_APPLICATION_SPINE = ApplicationSpine()
