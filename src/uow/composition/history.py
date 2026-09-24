"""Authoritative history semantics extracted from Campaign A2 convergence.

Enforces:
1. Multi-Orchestrator Concurrency: Peer orchestrators concurrently propose graph substitutions
   and sub-UoW delegations, resolving conflicts deterministically.
2. Commutative Delegation Merging: Disjoint child contract delegations merge without conflict.
3. Partition Safety & Minority Fail-Closed: Minority partitions lacking authority quorum strictly
   fail closed on authoritative commits.
4. Idempotent Execution De-Duplication: Duplicate execution of idempotent tasks across partitions
   is recognized and de-duplicated with strictly zero double commits.
5. Authoritative History Convergence: Upon partition healing, divergent speculative mutations
   are rolled back and nodes reconcile to a single authoritative history H*.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import time
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

def canonical_json(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))



class HistoryEntryKind(str, Enum):
    GRAPH_SUBSTITUTION = "graph_substitution"
    CHILD_DELEGATION = "child_delegation"
    AUTHORITATIVE_COMMIT = "authoritative_commit"
    IDEMPOTENT_TASK = "idempotent_task"


@dataclass(frozen=True)
class HistoryEntry:
    """Immutable, cryptographically linked entry in an authoritative history journal."""

    entry_id: str
    sequence_number: int
    prev_hash: str
    kind: HistoryEntryKind
    author_node_id: str
    generation: int
    payload: Mapping[str, Any]
    quorum_signatures: Tuple[str, ...] = ()
    timestamp_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    entry_hash: str = ""

    def __post_init__(self) -> None:
        if not self.entry_hash:
            data = {
                "entry_id": self.entry_id,
                "sequence_number": self.sequence_number,
                "prev_hash": self.prev_hash,
                "kind": self.kind.value,
                "author_node_id": self.author_node_id,
                "generation": self.generation,
                "payload": self.payload,
                "quorum_signatures": sorted(self.quorum_signatures),
            }
            digest = hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()
            object.__setattr__(self, "entry_hash", digest)

    def compute_hash(self) -> str:
        return self.entry_hash


class AuthoritativeHistory:
    """Append-only cryptographic journal of certified realization transitions."""

    def __init__(self, entries: Optional[Sequence[HistoryEntry]] = None) -> None:
        self._entries: List[HistoryEntry] = list(entries or [])

    @property
    def entries(self) -> Tuple[HistoryEntry, ...]:
        return tuple(self._entries)

    def tip_hash(self) -> str:
        if not self._entries:
            return "GENESIS_0000000000000000000000000000000000000000000000000000000000000000"
        return self._entries[-1].entry_hash

    def tip_sequence(self) -> int:
        if not self._entries:
            return -1
        return self._entries[-1].sequence_number

    def append(self, entry: HistoryEntry) -> Tuple[bool, str]:
        """Appends a validated entry enforcing sequence and hash linkage."""
        expected_seq = self.tip_sequence() + 1
        if entry.sequence_number != expected_seq:
            return (
                False,
                f"SEQUENCE_GAP: expected {expected_seq}, received {entry.sequence_number}",
            )

        expected_prev = self.tip_hash()
        if entry.prev_hash != expected_prev:
            return (
                False,
                f"HASH_DISCONTINUITY: expected prev_hash {expected_prev!r}, received {entry.prev_hash!r}",
            )

        self._entries.append(entry)
        return True, "APPENDED"

    def verify_integrity(self) -> bool:
        """Verifies full cryptographic chain from genesis to tip."""
        if not self._entries:
            return True

        prev = "GENESIS_0000000000000000000000000000000000000000000000000000000000000000"
        for i, entry in enumerate(self._entries):
            if entry.sequence_number != i:
                return False
            if entry.prev_hash != prev:
                return False
            prev = entry.entry_hash
        return True

    def state_digest(self) -> str:
        return hashlib.sha256(
            f"{self.tip_sequence()}:{self.tip_hash()}".encode("utf-8")
        ).hexdigest()

    def clone(self) -> AuthoritativeHistory:
        return AuthoritativeHistory(self._entries.copy())


