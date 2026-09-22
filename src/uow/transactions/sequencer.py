"""Commit sequencers and durable Write-Ahead Logging (WAL) for transactions."""
from __future__ import annotations

from abc import ABC, abstractmethod
import json
import os
from pathlib import Path
from typing import List, Optional, Tuple

from ..contracts import UoW
from ..engine import CertificateResult, EvidenceLedger, EvidenceRecord, Proposal
from ..state import WorldState, canonical_json
from .descriptor import TransactionDescriptor
from .occ import (
    HazardType,
    TransactionConflictError,
    apply_transaction,
    validate_occ,
)


def verify_commit_bindings(
    current_state: WorldState,
    uow: UoW,
    proposal: Proposal,
    tx: TransactionDescriptor,
    cert: CertificateResult,
) -> None:
    """Rigidly cross-validates cryptographic and semantic bindings across UoW, Proposal, Transaction, and Certificate."""
    if not cert.is_valid:
        raise ValueError(f"Cannot commit rejected certificate: {cert.rejection_reason}")

    identity = uow.H.identity
    if tx.uow_id != identity:
        raise ValueError(f"Transaction identity mismatch: {tx.uow_id!r} != {identity!r}")
    if cert.uow_id != identity:
        raise ValueError(f"Certificate identity mismatch: {cert.uow_id!r} != {identity!r}")
    if proposal.uow_id != identity:
        raise ValueError(f"Proposal identity mismatch: {proposal.uow_id!r} != {identity!r}")

    # State hash bindings
    if cert.pre_state_hash != proposal.pre_state_hash:
        raise ValueError("Certificate is not bound to proposal pre-state.")

    proposed_hash = proposal.proposed_state.state_hash
    if tx.proposed_state_hash != proposed_hash:
        raise ValueError("Transaction descriptor does not match proposed state hash.")
    if cert.proposed_state_hash != proposed_hash:
        raise ValueError("Certificate does not match proposed state hash.")

    # Decision bindings
    if proposal.selected_route_index != cert.selected_route_index:
        raise ValueError("Route index divergence between proposal and certificate.")
    if proposal.selected_successor != cert.selected_successor:
        raise ValueError("Successor divergence between proposal and certificate.")
    if proposal.halted != cert.halted:
        raise ValueError("Halt decision divergence between proposal and certificate.")


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
        """Atomically validates bindings, OCC, and commits transaction, or raises TransactionConflictError."""
        ...


class DeterministicSequencer(CommitSequencer):
    """In-memory sequential commit processor enforcing multi-object binding and OCC invariants."""

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
        # 1. Multi-object cryptographic cross-binding
        verify_commit_bindings(self._state, uow, proposal, tx, cert)

        # 2. OCC Hazard Validation against current authoritative state
        is_valid, hazard_type, details = validate_occ(
            self._state,
            tx,
            version_key=self._version_key,
            coupling_key=self._coupling_key,
        )
        if not is_valid:
            assert hazard_type is not None and details is not None
            raise TransactionConflictError(tx.uow_id, hazard_type, details)

        # 3. Pure atomic state mutation and evidence construction
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

        # 4. Memory publish
        self._ledger.append(evidence)
        self._state = committed_state
        return committed_state, evidence


class WALSequencer(CommitSequencer):
    """Durable append-only Write-Ahead Log (WAL) sequencer.

    Commit Order:
    validate -> construct commit -> durably persist (fsync) -> publish memory.
    """

    def __init__(
        self,
        wal_path: Path | str,
        initial_state: WorldState,
        ledger: Optional[EvidenceLedger] = None,
        *,
        version_key: str = "__versions__",
        coupling_key: str = "__couplings__",
        fsync: bool = True,
    ) -> None:
        self.wal_path = Path(wal_path)
        self._state = initial_state
        self._ledger = ledger or EvidenceLedger()
        self._version_key = version_key
        self._coupling_key = coupling_key
        self.fsync = fsync

        if not self.wal_path.exists():
            self.wal_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_entry({
                "type": "INITIAL_STATE",
                "state": initial_state.to_dict(),
            })

    @property
    def current_state(self) -> WorldState:
        return self._state

    @property
    def ledger(self) -> EvidenceLedger:
        return self._ledger

    def _write_entry(self, entry: dict) -> None:
        raw = canonical_json(entry).encode("utf-8") + b"\n"
        with open(self.wal_path, "ab") as f:
            f.write(raw)
            f.flush()
            if self.fsync:
                os.fsync(f.fileno())

    def commit(
        self,
        uow: UoW,
        proposal: Proposal,
        tx: TransactionDescriptor,
        cert: CertificateResult,
    ) -> Tuple[WorldState, EvidenceRecord]:
        # 1. Validation phase (pure, non-mutating)
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

        # 2. Construction phase (pure, non-mutating)
        before_state = self._state
        committed_state = apply_transaction(
            before_state,
            proposal,
            tx,
            version_key=self._version_key,
        )

        step_num = len(self._ledger.records) + 1
        evidence = EvidenceRecord(
            step_number=step_num,
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

        # 3. Durably persist to Write-Ahead Log BEFORE memory publish
        entry = {
            "type": "COMMIT",
            "step_number": evidence.step_number,
            "post_state_hash": committed_state.state_hash,
            "state": committed_state.to_dict(),
            "evidence": {
                "step_number": evidence.step_number,
                "uow_id": evidence.uow_id,
                "source_category": evidence.source_category,
                "target_category": evidence.target_category,
                "pre_state_hash": evidence.pre_state_hash,
                "selected_route_index": evidence.selected_route_index,
                "proposed_state_hash": evidence.proposed_state_hash,
                "certificate_hash": evidence.certificate_hash,
                "post_state_hash": evidence.post_state_hash,
                "next_uow_pointer": evidence.next_uow_pointer,
                "prev_evidence_hash": evidence.prev_evidence_hash,
                "record_hash": evidence.record_hash,
            },
        }
        self._write_entry(entry)

        # 4. Memory publish
        self._ledger.append(evidence)
        self._state = committed_state
        return committed_state, evidence

    @classmethod
    def recover(cls, wal_path: Path | str, *, ignore_torn_tail: bool = True) -> Tuple[WorldState, EvidenceLedger]:
        """Reconstructs authoritative WorldState AND complete EvidenceLedger from durable WAL.

        Cryptographically verifies the entire evidence hash chain during recovery.
        """
        path = Path(wal_path)
        if not path.exists():
            raise FileNotFoundError(f"WAL file does not exist: {path}")

        current_state: Optional[WorldState] = None
        ledger = EvidenceLedger()

        with open(path, "rb") as f:
            lines = f.readlines()

        for idx, raw_line in enumerate(lines):
            line_str = raw_line.decode("utf-8", errors="replace").strip()
            if not line_str:
                continue

            try:
                entry = json.loads(line_str)
            except Exception:
                if ignore_torn_tail and idx == len(lines) - 1:
                    # Torn tail at EOF, ignore and recover up to last valid entry
                    break
                raise ValueError(f"Corrupt WAL entry at line {idx + 1}")

            entry_type = entry.get("type")
            if entry_type == "INITIAL_STATE":
                s_dict = entry["state"]
                current_state = WorldState(
                    attributes=s_dict["attributes"],
                    cursor=s_dict["cursor"],
                    status=s_dict["status"],
                    sequence=s_dict["sequence"],
                )
            elif entry_type == "COMMIT":
                s_dict = entry["state"]
                recovered_s = WorldState(
                    attributes=s_dict["attributes"],
                    cursor=s_dict["cursor"],
                    status=s_dict["status"],
                    sequence=s_dict["sequence"],
                )
                ev_dict = entry["evidence"]
                ev_record = EvidenceRecord(
                    step_number=int(ev_dict["step_number"]),
                    uow_id=str(ev_dict["uow_id"]),
                    source_category=str(ev_dict["source_category"]),
                    target_category=str(ev_dict["target_category"]),
                    pre_state_hash=str(ev_dict["pre_state_hash"]),
                    selected_route_index=int(ev_dict["selected_route_index"]),
                    proposed_state_hash=str(ev_dict["proposed_state_hash"]),
                    certificate_hash=str(ev_dict["certificate_hash"]),
                    post_state_hash=str(ev_dict["post_state_hash"]),
                    next_uow_pointer=ev_dict["next_uow_pointer"],
                    prev_evidence_hash=str(ev_dict["prev_evidence_hash"]),
                    record_hash=str(ev_dict["record_hash"]),
                )
                # Appending to ledger verifies contiguous sequence and hash chain
                ledger.append(ev_record)
                current_state = recovered_s
            else:
                raise ValueError(f"Unknown WAL entry type: {entry_type!r}")

        if current_state is None:
            raise ValueError("WAL contains no valid state entries.")

        if not ledger.verify_integrity():
            raise ValueError("Recovered evidence ledger failed integrity verification.")

        return current_state, ledger
