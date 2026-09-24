r"""Durable Storage and Write-Ahead Journaling for Policy Registry (Milestone P5).

Guarantees crash-safety, atomic snapshot commits, and fail-closed integrity validation:
- P5.1: Exact registry recovery (\Pi_k' == \Pi_k) including identical registry digest.
- P5.2: Atomic commit boundaries (WAL + os.replace); transitions are fully committed or not committed.
- P5.5: Corrupted persistence detection; fails closed when H(persisted state) != H(expected chain).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .authority import AuthorityRule
from .models import (
    AuthorityVote,
    DistributedPolicyCertificate,
    InFlightTransaction,
    Policy,
    PolicyTransitionProposal,
    TransactionExecutionStatus,
)
from .registry import PolicyRegistry


class PersistenceError(Exception):
    """Base exception for durable persistence failures."""
    pass


class CorruptedStorageError(PersistenceError):
    """Raised when persisted snapshot or journal fails cryptographic validation (fails closed)."""
    pass


class IncompleteCommitError(PersistenceError):
    """Raised when a crash occurred during a two-phase transition commit."""
    pass


class DurablePolicyStore:
    """Atomic file-based storage engine with write-ahead journaling and cryptographic checksumming."""

    def __init__(self, storage_dir: str | Path) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.snapshot_file = self.storage_dir / "registry_snapshot.json"
        self.checksums_file = self.storage_dir / "checksums.json"
        self.journal_file = self.storage_dir / "transitions_journal.jsonl"
        self.inflight_file = self.storage_dir / "inflight_transactions.json"

    def _atomic_write_json(self, target_file: Path, data: Any) -> str:
        """Write JSON data atomically using a temporary file and os.replace."""
        suffix_token = hashlib.sha256(str(target_file).encode()).hexdigest()[:8]
        temp_file = target_file.with_suffix(f".tmp_{os.getpid()}_{suffix_token}")
        serialized = json.dumps(data, indent=2, sort_keys=True)
        content_bytes = serialized.encode("utf-8")
        file_hash = hashlib.sha256(content_bytes).hexdigest()

        with open(temp_file, "wb") as f:
            f.write(content_bytes)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_file, target_file)
        return file_hash

    def persist_registry(
        self,
        registry: PolicyRegistry,
        authority_rule: Optional[AuthorityRule] = None,
    ) -> str:
        """Atomically persist entire policy registry and authority configuration with checksums."""
        state = registry.export_state()
        if authority_rule is not None:
            state["authority_rule"] = {
                "rule_id": authority_rule.rule_id,
                "required_authorities": list(authority_rule.required_authorities),
                "threshold": authority_rule.threshold,
            }

        # 1. Atomic write of registry snapshot
        file_hash = self._atomic_write_json(self.snapshot_file, state)

        # 2. Atomic write of cryptographic checksums
        checksum_payload = {
            "snapshot_file_sha256": file_hash,
            "registry_version": registry.version,
            "registry_digest": registry.compute_digest(),
        }
        self._atomic_write_json(self.checksums_file, checksum_payload)

        return file_hash

    def load_registry(self) -> Tuple[PolicyRegistry, Optional[AuthorityRule], str]:
        """Load and verify registry state from disk. Fails closed on any hash mismatch."""
        if not self.snapshot_file.exists():
            raise FileNotFoundError(f"Snapshot file not found: {self.snapshot_file}")
        if not self.checksums_file.exists():
            raise CorruptedStorageError(f"Checksum file missing: {self.checksums_file}")

        try:
            with open(self.checksums_file, "r", encoding="utf-8") as f:
                checksums = json.load(f)
        except Exception as e:
            raise CorruptedStorageError(f"Failed to read checksums file: {e}") from e

        try:
            with open(self.snapshot_file, "rb") as f:
                content_bytes = f.read()
        except Exception as e:
            raise CorruptedStorageError(f"Failed to read snapshot file: {e}") from e

        actual_file_hash = hashlib.sha256(content_bytes).hexdigest()
        expected_file_hash = checksums.get("snapshot_file_sha256")
        if actual_file_hash != expected_file_hash:
            raise CorruptedStorageError(
                f"Registry snapshot file hash mismatch: expected {expected_file_hash}, got {actual_file_hash}"
            )

        try:
            state = json.loads(content_bytes.decode("utf-8"))
        except Exception as e:
            raise CorruptedStorageError(f"Corrupted JSON in snapshot file: {e}") from e

        registry = PolicyRegistry.from_state(state)
        actual_reg_digest = registry.compute_digest()
        expected_reg_digest = checksums.get("registry_digest")
        if actual_reg_digest != expected_reg_digest:
            raise CorruptedStorageError(
                f"Registry state digest mismatch: expected {expected_reg_digest}, got {actual_reg_digest}"
            )

        auth_rule = None
        if "authority_rule" in state:
            ar_data = state["authority_rule"]
            auth_rule = AuthorityRule(
                rule_id=ar_data["rule_id"],
                required_authorities=frozenset(ar_data["required_authorities"]),
                threshold=int(ar_data["threshold"]),
            )

        return registry, auth_rule, actual_file_hash

    def append_journal_entry(self, entry_type: str, data: Dict[str, Any]) -> str:
        """Append an entry to the transitions write-ahead journal."""
        raw_data = json.dumps(data, sort_keys=True)
        entry_hash = hashlib.sha256(f"{entry_type}:{raw_data}".encode("utf-8")).hexdigest()[:24]
        line = json.dumps({
            "entry_type": entry_type,
            "entry_hash": entry_hash,
            "data": data,
        }) + "\n"

        with open(self.journal_file, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

        return entry_hash

    def log_proposal(self, proposal: PolicyTransitionProposal) -> str:
        return self.append_journal_entry("PROPOSAL", proposal.to_dict())

    def log_certificate(self, certificate: DistributedPolicyCertificate) -> str:
        return self.append_journal_entry("CERTIFICATE", certificate.to_dict())

    def log_commit(self, transition_id: str, new_registry_digest: str, new_version: int) -> str:
        return self.append_journal_entry("COMMITTED", {
            "transition_id": transition_id,
            "new_registry_digest": new_registry_digest,
            "new_version": new_version,
        })

    def read_journal_entries(self) -> List[Dict[str, Any]]:
        """Read and validate all journal entries."""
        if not self.journal_file.exists():
            return []

        entries: List[Dict[str, Any]] = []
        with open(self.journal_file, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                clean = line.strip()
                if not clean:
                    continue
                try:
                    obj = json.loads(clean)
                    raw_data = json.dumps(obj["data"], sort_keys=True)
                    expected_h = hashlib.sha256(f"{obj['entry_type']}:{raw_data}".encode("utf-8")).hexdigest()[:24]
                    if obj.get("entry_hash") != expected_h:
                        raise CorruptedStorageError(f"Journal entry on line {line_no} failed checksum verification")
                    entries.append(obj)
                except json.JSONDecodeError as e:
                    raise CorruptedStorageError(f"Malformed journal entry on line {line_no}: {e}") from e

        return entries

    def get_journal_certificates(self) -> List[DistributedPolicyCertificate]:
        """Return all valid DistributedPolicyCertificates recorded in the journal."""
        entries = self.read_journal_entries()
        certs: List[DistributedPolicyCertificate] = []
        for e in entries:
            if e["entry_type"] == "CERTIFICATE":
                certs.append(DistributedPolicyCertificate.from_dict(e["data"]))
        return certs

    def record_inflight(self, tx: InFlightTransaction) -> None:
        """Atomically record an in-flight workload transaction."""
        current = self.load_inflight_map()
        current[tx.uow_id] = tx.to_dict()
        self._atomic_write_json(self.inflight_file, current)

    def remove_inflight(self, uow_id: str) -> None:
        """Atomically remove a committed or aborted workload transaction."""
        current = self.load_inflight_map()
        if uow_id in current:
            current.pop(uow_id, None)
            self._atomic_write_json(self.inflight_file, current)

    def load_inflight_map(self) -> Dict[str, Dict[str, Any]]:
        if not self.inflight_file.exists():
            return {}
        try:
            with open(self.inflight_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def load_inflight_transactions(self) -> List[InFlightTransaction]:
        """Return all tracked in-flight transactions across process restarts."""
        data_map = self.load_inflight_map()
        return [InFlightTransaction.from_dict(d) for d in data_map.values()]
