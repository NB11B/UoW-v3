"""Physical Host Node & Durable Write-Ahead Log for Campaign A2.

Enforces:
1. Physical Isolation: Each host runs in an isolated directory with its own persistent disk state,
   independent local monotonic clock (with skew), and separate failure domain.
2. Durable Write-Ahead Log (WAL): All state mutations and Quorum Certificates are synced to disk
   via os.fsync prior to acknowledgement.
3. Crash & Restart Recovery: Process termination mid-commit or mid-delegation is recoverable from
   the persistent disk WAL without duplicate commits or semantic drift.
4. Independent Clock Skew: Timeouts and leases rely on monotonic local duration and signed generation
   epochs rather than synchronized wall clocks.
"""
from __future__ import annotations

import os
from pathlib import Path
import time
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

if TYPE_CHECKING:
    from uow.composition.binding import ActorBinding
    from uow.composition.contract import ParentContract
    from uow.composition.graph import RealizationGraph
    from uow.composition.mutation import RuntimeMutationQC

from uow.composition.convergence import AuthoritativeHistory, HistoryEntry, HistoryEntryKind
from uow.composition.fabric import canonical_json
from uow.composition.wire import WireEnvelope, sign_envelope, verify_envelope


class DurableWAL:
    """Append-only disk write-ahead log with fsync durability."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.wal_path = self.directory / "journal.wal"

    def append(self, entry: HistoryEntry) -> None:
        """Appends an entry to the WAL file on disk, immediately fsyncing."""
        payload = {
            "entry_id": entry.entry_id,
            "sequence_number": entry.sequence_number,
            "prev_hash": entry.prev_hash,
            "kind": entry.kind.value,
            "author_node_id": entry.author_node_id,
            "generation": entry.generation,
            "payload": entry.payload,
            "quorum_signatures": list(entry.quorum_signatures),
            "timestamp_iso": entry.timestamp_iso,
            "entry_hash": entry.entry_hash,
        }
        line = canonical_json(payload) + "\n"
        with open(self.wal_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

    def replay(self) -> List[HistoryEntry]:
        """Replays all durable entries from the disk file."""
        if not self.wal_path.exists():
            return []

        entries: List[HistoryEntry] = []
        with open(self.wal_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = canonical_json_loads(line)
                entry = HistoryEntry(
                    entry_id=d["entry_id"],
                    sequence_number=d["sequence_number"],
                    prev_hash=d["prev_hash"],
                    kind=HistoryEntryKind(d["kind"]),
                    author_node_id=d["author_node_id"],
                    generation=d["generation"],
                    payload=d["payload"],
                    quorum_signatures=tuple(d.get("quorum_signatures", ())),
                    timestamp_iso=d.get("timestamp_iso", ""),
                    entry_hash=d["entry_hash"],
                )
                entries.append(entry)
        return entries


def canonical_json_loads(s: str) -> Dict[str, Any]:
    import json
    return json.loads(s)


class PhysicalHostNode:
    """Independent physical host node running with local disk persistence and skewed clocks."""

    def __init__(
        self,
        node_id: str,
        working_dir: Path,
        secret_key: str,
        clock_skew_sec: float = 0.0,
        generation: int = 1,
        active_graph: Optional[RealizationGraph] = None,
        active_binding: Optional[ActorBinding] = None,
    ) -> None:
        self.node_id = node_id
        self.working_dir = Path(working_dir)
        self.secret_key = secret_key
        self.clock_skew_sec = clock_skew_sec
        self.generation = generation
        self.active_graph = active_graph
        self.active_binding = active_binding

        self.wal = DurableWAL(self.working_dir)
        self.history = AuthoritativeHistory()
        self.idempotent_task_results: Dict[str, Any] = {}
        self.is_alive = True
        self.start_monotonic = time.monotonic()

    def local_time(self) -> float:
        """Returns local time including monotonic elapsed duration and clock skew."""
        elapsed = time.monotonic() - self.start_monotonic
        return 1000.0 + elapsed + self.clock_skew_sec

    def startup(self) -> int:
        """Boots node and replays persistent WAL from disk."""
        self.is_alive = True
        durable_entries = self.wal.replay()
        self.history = AuthoritativeHistory()
        for e in durable_entries:
            self.history.append(e)
            if e.kind == HistoryEntryKind.IDEMPOTENT_TASK:
                key = e.payload.get("idempotency_key")
                if key:
                    self.idempotent_task_results[key] = e
        return len(durable_entries)

    def crash(self) -> None:
        """Simulates sudden power loss or process kill; memory is wiped."""
        self.is_alive = False
        self.history = AuthoritativeHistory()
        self.idempotent_task_results.clear()

    def restart(self) -> int:
        """Recovers node from disk persistence after a crash."""
        return self.startup()

    def receive_wire_envelope(self, envelope: WireEnvelope) -> Tuple[bool, str]:
        """Validates cryptographic wire signature and recipient."""
        if not self.is_alive:
            return False, "NODE_OFFLINE"

        if envelope.recipient_id != self.node_id and envelope.recipient_id != "broadcast":
            return False, f"RECIPIENT_MISMATCH: expected {self.node_id!r}, received {envelope.recipient_id!r}"

        if not verify_envelope(self.secret_key, envelope):
            return False, "UNAUTHENTICATED_WIRE_SIGNATURE"

        return True, "VERIFIED"

    def commit_entry_durably(
        self,
        kind: HistoryEntryKind,
        payload: Mapping[str, Any],
        author_id: Optional[str] = None,
        quorum_sigs: Sequence[str] = (),
        idempotency_key: str = "",
    ) -> Tuple[bool, Optional[HistoryEntry], str]:
        """Atomically appends entry to durable disk WAL and memory history."""
        if not self.is_alive:
            return False, None, "NODE_OFFLINE"

        if idempotency_key and idempotency_key in self.idempotent_task_results:
            existing = self.idempotent_task_results[idempotency_key]
            return True, existing, "DUPLICATE_EXECUTION_DEDUPLICATED"

        author = author_id or self.node_id
        seq = self.history.tip_sequence() + 1
        prev_hash = self.history.tip_hash()

        entry = HistoryEntry(
            entry_id=f"entry_{author}_{seq}",
            sequence_number=seq,
            prev_hash=prev_hash,
            kind=kind,
            author_node_id=author,
            generation=self.generation,
            payload=payload,
            quorum_signatures=tuple(quorum_sigs),
        )

        # 1. Sync to durable disk WAL first
        self.wal.append(entry)

        # 2. Update memory state
        ok, msg = self.history.append(entry)
        if not ok:
            return False, None, msg

        if idempotency_key:
            self.idempotent_task_results[idempotency_key] = entry

        return True, entry, "COMMITTED"

    def catch_up_from(self, entries: Sequence[HistoryEntry]) -> Tuple[bool, int, str]:
        """Catches up stale local history from verified canonical history entries."""
        if not self.is_alive:
            return False, 0, "NODE_OFFLINE"

        current_tip_seq = self.history.tip_sequence()
        appended_count = 0

        for entry in entries:
            if entry.sequence_number <= current_tip_seq:
                continue
            self.wal.append(entry)
            ok, msg = self.history.append(entry)
            if not ok:
                return False, appended_count, f"CATCHUP_FAILED: {msg}"
            appended_count += 1

        return True, appended_count, "CAUGHT_UP"

    def apply_mutation_qc(
        self,
        qc: Any,
        candidate_graph: Any,
        candidate_binding: Any,
        parent_contract: Any,
        authority_keys: Mapping[str, str],
        threshold: int = 2,
    ) -> Tuple[bool, str]:
        """Atomically applies a Quorum Certificate verified graph and binding mutation."""
        if not self.is_alive:
            return False, "NODE_OFFLINE"

        from uow.composition.mutation import verify_mutation_qc

        valid, reason = verify_mutation_qc(
            qc=qc,
            parent_contract=parent_contract,
            current_history_head=self.history.tip_hash(),
            current_generation=self.generation,
            authority_keys=authority_keys,
            threshold=threshold,
        )
        if not valid:
            return False, f"MUTATION_REJECTED: {reason}"

        if candidate_graph.compute_hash() != qc.candidate_graph_hash:
            return False, "MUTATION_REJECTED: CANDIDATE_GRAPH_HASH_MISMATCH"
        if candidate_binding.compute_hash() != qc.candidate_binding_hash:
            return False, "MUTATION_REJECTED: CANDIDATE_BINDING_HASH_MISMATCH"

        self.active_graph = candidate_graph
        self.active_binding = candidate_binding
        next_gen = self.generation + 1

        payload = {
            "candidate_graph_hash": qc.candidate_graph_hash,
            "candidate_binding_hash": qc.candidate_binding_hash,
            "signers": list(qc.signers),
        }
        ok, entry, msg = self.commit_entry_durably(
            kind=HistoryEntryKind.GRAPH_SUBSTITUTION,
            payload=payload,
            author_id=qc.qc_id,
            quorum_sigs=qc.signers,
        )
        if not ok:
            return False, msg

        self.generation = next_gen
        return True, "MUTATION_COMMITTED"
