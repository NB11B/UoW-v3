"""Semantic commit-sequencer protocol and binding invariants."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Tuple

from ..contracts import UoW
from ..engine import CertificateResult, EvidenceLedger, EvidenceRecord, Proposal
from ..state import WorldState
from .descriptor import TransactionDescriptor


def verify_commit_bindings(
    current_state: WorldState,
    uow: UoW,
    proposal: Proposal,
    tx: TransactionDescriptor,
    cert: CertificateResult,
) -> None:
    """Cross-validates semantic/cryptographic bindings before authoritative commit."""
    if not cert.is_valid:
        raise ValueError(f"Cannot commit rejected certificate: {cert.rejection_reason}")

    identity = uow.H.identity
    if tx.uow_id != identity:
        raise ValueError(f"Transaction identity mismatch: {tx.uow_id!r} != {identity!r}")
    if cert.uow_id != identity:
        raise ValueError(f"Certificate identity mismatch: {cert.uow_id!r} != {identity!r}")
    if proposal.uow_id != identity:
        raise ValueError(f"Proposal identity mismatch: {proposal.uow_id!r} != {identity!r}")

    if cert.pre_state_hash != proposal.pre_state_hash:
        raise ValueError("Certificate is not bound to proposal pre-state.")

    proposed_hash = proposal.proposed_state.state_hash
    if tx.proposed_state_hash != proposed_hash:
        raise ValueError("Transaction descriptor does not match proposed state hash.")
    if cert.proposed_state_hash != proposed_hash:
        raise ValueError("Certificate does not match proposed state hash.")

    if proposal.selected_route_index != cert.selected_route_index:
        raise ValueError("Route index divergence between proposal and certificate.")
    if proposal.selected_successor != cert.selected_successor:
        raise ValueError("Successor divergence between proposal and certificate.")
    if proposal.halted != cert.halted:
        raise ValueError("Halt decision divergence between proposal and certificate.")


class CommitSequencer(ABC):
    """Semantic interface separating transaction legality from commit realization."""

    @property
    @abstractmethod
    def current_state(self) -> WorldState:
        ...

    @property
    @abstractmethod
    def ledger(self) -> EvidenceLedger:
        ...

    @abstractmethod
    def commit(
        self,
        uow: UoW,
        proposal: Proposal,
        tx: TransactionDescriptor,
        cert: CertificateResult,
    ) -> Tuple[WorldState, EvidenceRecord]:
        ...
