"""Commit sequencers and durable Write-Ahead Logging (WAL) for transactions."""
from __future__ import annotations

from abc import ABC, abstractmethod
import json
from pathlib import Path
from typing import List, Optional, Tuple

from ..contracts import UoW
from ..engine import CertificateResult, EvidenceLedger, EvidenceRecord, Proposal
from ..state import WorldState, canonical_json
from .descriptor import TransactionDescriptor
from .occ import TransactionConflictError, apply_transaction, validate_occ


class CommitSequencer(ABC):
    """Abstract interface separating transaction concurrency from commit sequencing."""

    @property
    @abstractmethod
    def current_state(self) -> WorldState:
        """The authoritative state."""
        ...

    @property
    @abstractmethod
    def ledger(self) -> EvidenceLedger:
        """The immutable evidence ledger."""
        ...

    @abstractmethod
    def commit(
        self,
        uow: UoW,
        proposal: Proposal,
        tx: TransactionDescriptor,
        cert: CertificateResult,
    ) -> Tuple[WorldState, EvidenceRecord]:
        """Atomically validates OCC and commits transaction, or raises TransactionConflictError."""
        ...


class DeterministicSequencer(CommitSequencer):
    """In-memory sequential commit processor enforcing pure OCC invariants."""

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
        if not cert.is_valid:
            raise ValueError(f"Cannot commit rejected transaction: {cert.rejection_reason}")

        # 1. OCC Hazard Validation against current authoritative state
        is_valid, hazard_type, details = validate_occ(
            self._state,
            tx,
            version_key=self._version_key,
            coupling_key=self._coupling_key,
        )
        if not is_valid:
            assert hazard_type is not None and details is not None
            raise TransactionConflictError(tx.uow_id, hazard_type, details)

        # 2. Atomic state mutation
        before_state = self._state
        committed_state = apply_transaction(
            before_state,
            proposal,
            tx,
            version_key=self._version_key,
        )

        # 3. Create and append evidence record
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


class WALSequencer(CommitSequencer):
    """Durable append-only Write-Ahead Log (WAL) sequencer.

    Persists committed transitions to disk for crash recovery and audit replay.
    """

    def __init__(
        self,
        wal_path: Path | str,
        initial_state: WorldState,
        ledger: Optional[EvidenceLedger] = None,
        *,
        version_key: str = "__versions__",
        coupling_key: str = "__couplings__",
    ) -> None:
        self.wal_path = Path(wal_path)
        self._inner = DeterministicSequencer(
            initial_state,
            ledger,
            version_key=version_key,
            coupling_key=coupling_key,
        )
        # If WAL does not exist, write header
        if not self.wal_path.exists():
            self.wal_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_entry({
                "type": "INITIAL_STATE",
                "state": initial_state.to_dict(),
            })

    @property
    def current_state(self) -> WorldState:
        return self._inner.current_state

    @property
    def ledger(self) -> EvidenceLedger:
        return self._inner.ledger

    def _write_entry(self, entry: dict) -> None:
        with self.wal_path.open("a", encoding="utf-8") as f:
            f.write(canonical_json(entry) + "\n")

    def commit(
        self,
        uow: UoW,
        proposal: Proposal,
        tx: TransactionDescriptor,
        cert: CertificateResult,
    ) -> Tuple[WorldState, EvidenceRecord]:
        committed_state, evidence = self._inner.commit(uow, proposal, tx, cert)

        # Append to durable WAL
        entry = {
            "type": "COMMIT",
            "uow_id": uow.H.identity,
            "step_number": evidence.step_number,
            "post_state_hash": committed_state.state_hash,
            "evidence_record_hash": evidence.record_hash,
            "state": committed_state.to_dict(),
        }
        self._write_entry(entry)
        return committed_state, evidence

    @classmethod
    def recover(cls, wal_path: Path | str) -> Tuple[WorldState, EvidenceLedger]:
        """Reconstructs authoritative WorldState and EvidenceLedger from a durable WAL."""
        path = Path(wal_path)
        if not path.exists():
            raise FileNotFoundError(f"WAL file does not exist: {path}")

        current_state: Optional[WorldState] = None
        ledger = EvidenceLedger()

        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry["type"] == "INITIAL_STATE":
                    s_dict = entry["state"]
                    current_state = WorldState(
                        attributes=s_dict["attributes"],
                        cursor=s_dict["cursor"],
                        status=s_dict["status"],
                        sequence=s_dict["sequence"],
                    )
                elif entry["type"] == "COMMIT":
                    s_dict = entry["state"]
                    current_state = WorldState(
                        attributes=s_dict["attributes"],
                        cursor=s_dict["cursor"],
                        status=s_dict["status"],
                        sequence=s_dict["sequence"],
                    )

        if current_state is None:
            raise ValueError("WAL contains no valid state entries.")

        return current_state, ledger
