"""Durable WAL commit realization."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Tuple

from ...contracts import UoW
from ...engine import CertificateResult, EvidenceLedger, EvidenceRecord, Proposal
from ...state import WorldState, canonical_json
from ...transactions.descriptor import TransactionDescriptor
from ...transactions.occ import TransactionConflictError, apply_transaction, validate_occ
from ...transactions.protocol import CommitSequencer, verify_commit_bindings


class WALSequencer(CommitSequencer):
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
            self._write_entry({"type": "INITIAL_STATE", "state": initial_state.to_dict()})

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

        self._write_entry(
            {
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
        )

        self._ledger.append(evidence)
        self._state = committed_state
        return committed_state, evidence

    @classmethod
    def recover(
        cls,
        wal_path: Path | str,
        *,
        ignore_torn_tail: bool = True,
    ) -> Tuple[WorldState, EvidenceLedger]:
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
                    break
                raise ValueError(f"Corrupt WAL entry at line {idx + 1}")

            entry_type = entry.get("type")
            if entry_type == "INITIAL_STATE":
                s = entry["state"]
                current_state = WorldState(
                    attributes=s["attributes"],
                    cursor=s["cursor"],
                    status=s["status"],
                    sequence=s["sequence"],
                )
            elif entry_type == "COMMIT":
                s = entry["state"]
                recovered_s = WorldState(
                    attributes=s["attributes"],
                    cursor=s["cursor"],
                    status=s["status"],
                    sequence=s["sequence"],
                )
                e = entry["evidence"]
                record = EvidenceRecord(
                    step_number=int(e["step_number"]),
                    uow_id=str(e["uow_id"]),
                    source_category=str(e["source_category"]),
                    target_category=str(e["target_category"]),
                    pre_state_hash=str(e["pre_state_hash"]),
                    selected_route_index=int(e["selected_route_index"]),
                    proposed_state_hash=str(e["proposed_state_hash"]),
                    certificate_hash=str(e["certificate_hash"]),
                    post_state_hash=str(e["post_state_hash"]),
                    next_uow_pointer=e["next_uow_pointer"],
                    prev_evidence_hash=str(e["prev_evidence_hash"]),
                    record_hash=str(e["record_hash"]),
                )
                ledger.append(record)
                current_state = recovered_s
            else:
                raise ValueError(f"Unknown WAL entry type: {entry_type!r}")

        if current_state is None:
            raise ValueError("WAL contains no valid state entries.")
        if not ledger.verify_integrity():
            raise ValueError("Recovered evidence ledger failed integrity verification.")
        return current_state, ledger
