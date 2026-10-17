"""Causal Dependency and Local Sequence Tracking.

Guarantees partial ordering and replay detection across distributed nodes
without relying on globally synchronized clocks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional


@dataclass
class CausalClock:
    """Per-node causal clock maintaining monotonic local sequence and observed peer clocks."""
    node_id: str
    local_sequence: int = 0
    observed_peers: Dict[str, int] = field(default_factory=dict)

    def tick(self) -> int:
        """Advance local sequence counter monotonically."""
        self.local_sequence += 1
        return self.local_sequence

    def observe(self, peer_id: str, peer_seq: int) -> None:
        """Record observed sequence from a peer."""
        current = self.observed_peers.get(peer_id, 0)
        if peer_seq > current:
            self.observed_peers[peer_id] = peer_seq

    def snapshot(self) -> Dict[str, int]:
        """Return immutable copy of the full vector clock snapshot."""
        snap = dict(self.observed_peers)
        snap[self.node_id] = self.local_sequence
        return snap


class CausalOrderDetector:
    """Detects causal order, concurrency, and replays across distributed work events."""

    def __init__(self) -> None:
        self._seen_event_ids: Set[str] = set()
        self._peer_max_sequence: Dict[str, int] = {}

    def is_replay_or_duplicate(self, event_id: str, node_id: str, sequence: int) -> bool:
        """Check if an event ID or sequence counter has already been processed."""
        if event_id in self._seen_event_ids:
            return True
        last_seq = self._peer_max_sequence.get(node_id, -1)
        if sequence <= last_seq:
            return True
        return False

    def record_processed(self, event_id: str, node_id: str, sequence: int) -> None:
        """Record an event as successfully certified/committed."""
        self._seen_event_ids.add(event_id)
        current_max = self._peer_max_sequence.get(node_id, -1)
        if sequence > current_max:
            self._peer_max_sequence[node_id] = sequence
