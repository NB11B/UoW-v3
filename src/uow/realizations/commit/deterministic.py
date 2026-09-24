"""In-memory deterministic commit realization."""
from __future__ import annotations

from typing import Optional, Tuple

from ...contracts import UoW
from ...engine import CertificateResult, EvidenceLedger, EvidenceRecord, Proposal
from ...state import WorldState
from ...transactions.descriptor import TransactionDescriptor
from ...transactions.occ import TransactionConflictError, apply_transaction, validate_occ
from ...transactions.protocol import CommitSequencer, verify_commit_bindings


class DeterministicSequencer(CommitSequencer):
    def __init__(
        self,
        initial_state: WorldState,
        ledger: Optional[EvidenceLedger] = None,
        *,
        version_key: str = "__versions__",
        coupling_key: str = "__couplings__",
    ) -> None:
        self._state = initial_state
        self._ledger = ledger or EvidenceLedger()
        self._version_key = version_key
        self._coupling_key = coupling_key

    @property
    def current_state(self) -> WorldState:
        return self._state

    @property
    def ledger(self) -> EvidenceLedger:
        return self._ledger

    def commit(
        self,
        uow: UoW,
        proposal: Proposal,
        tx: TransactionDescriptor,
        cert: CertificateResult,
    ) -> Tuple[WorldState, EvidenceRecord]:
        verify_commit_bindings(self._state, uow, proposal, tx, cert)

        is_valid, hazard_type, details = validate_occ(
            self._state,
            tx,
            version_key=self._version_key,
            coupling_key=self._coupling_key,
        )
        if not is_valid:
            assert hazard_type is not None and details is not None
            raise TransactionConflictError(tx.uow_id, hazard_type, details)

        before_state = self._state
        committed_state = apply_transaction(
            before_state,
            proposal,
            tx,
            version_key=self._version_key,
        )

        evidence = EvidenceRecord(
            step_number=len(self._ledger.records) + 1,
            uow_id=uow.H.identity,
            source_category=uow.H.source_category.value,
            target_category=uow.H.target_category.value,
            pre_state_hash=before_state.state_hash,
            selected_route_index=proposal.selected_route_index,
            proposed_state_hash=proposal.proposed_state.state_hash,
            certificate_hash=cert.certificate_hash,
            post_state_hash=committed_state.state_hash,
            next_uow_pointer=proposal.selected_successor,
            prev_evidence_hash=self._ledger.root_hash(),
        )

        self._ledger.append(evidence)
        self._state = committed_state
        return committed_state, evidence
