"""Common authoritative application spine.

This is the production realization of the control-flow seam validated by the
reconstruction campaign:

UoW -> Proposal -> Conformance -> Transaction -> Commit -> Evidence

Domain-specific proposal formation, materialization certification, authority
provider behavior, and external physical effects remain outside this seam.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .contracts import UoW
from .engine import CertificateResult, EvidenceRecord, Proposal, certify, propose
from .state import WorldState
from .transactions.descriptor import TransactionDescriptor, create_transaction_descriptor
from .transactions.sequencer import CommitSequencer


class CursorPolicy(str, Enum):
    OWNED = "OWNED"
    DETACHED = "DETACHED"


@dataclass(frozen=True)
class ApplicationResult:
    state: WorldState
    evidence: EvidenceRecord
    proposal: Proposal
    certificate: CertificateResult
    transaction: TransactionDescriptor


class ApplicationSpine:
    """Apply one native UoW through the common authority/application sequence."""

    def execute(
        self,
        uow: UoW,
        sequencer: CommitSequencer,
        *,
        cursor_policy: CursorPolicy = CursorPolicy.OWNED,
    ) -> ApplicationResult:
        before = sequencer.current_state
        if before.status != "RUNNING":
            raise ValueError("Application spine requires RUNNING authoritative state.")

        if cursor_policy is CursorPolicy.OWNED:
            if before.cursor is None:
                raise ValueError("Cursor-owned application requires an active cursor.")
            if before.cursor != uow.H.identity:
                raise ValueError(
                    f"Cursor-owned application expected {before.cursor!r}, "
                    f"got UoW {uow.H.identity!r}."
                )

        proposal = propose(uow, before)
        certificate = certify(uow, before, proposal)
        if not certificate.is_valid:
            raise ValueError(
                f"UoW failed deterministic certification: {certificate.rejection_reason}"
            )
        transaction = create_transaction_descriptor(uow, before)
        committed, evidence = sequencer.commit(
            uow,
            proposal,
            transaction,
            certificate,
        )
        return ApplicationResult(
            state=committed,
            evidence=evidence,
            proposal=proposal,
            certificate=certificate,
            transaction=transaction,
        )


DEFAULT_APPLICATION_SPINE = ApplicationSpine()
