"""Distributed convergence implementation for A2.5."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ...composition.delegation import DistributedDelegationNode
from ...composition.history import AuthoritativeHistory, HistoryEntry, HistoryEntryKind
from .fabric import DistributedActorFabric

class MultiOrchestratorCluster:
    """Manages an overlay network of peer orchestrators and simulates network partitions."""

    def __init__(
        self,
        nodes: Mapping[str, DistributedDelegationNode],
        fabric: DistributedActorFabric,
        authority_keys: Set[str],
    ) -> None:
        self.nodes: Dict[str, DistributedDelegationNode] = dict(nodes)
        self.fabric = fabric
        self.authority_keys = set(authority_keys)
        # Partition groups: list of sets of reachable node IDs
        self.partitions: List[Set[str]] = [set(self.nodes.keys()) | set(authority_keys)]
        # Individual history journals per orchestrator
        self.node_histories: Dict[str, AuthoritativeHistory] = {
            nid: AuthoritativeHistory() for nid in self.nodes
        }
        self.committed_idempotent_tasks: Dict[str, Any] = {}
        self.active_generation = 1

    def partition_network(self, groups: Sequence[Iterable[str]]) -> None:
        """Divides cluster nodes into mutually unreachable partition components."""
        self.partitions = [set(g) for g in groups]

    def heal_partition(self) -> None:
        """Restores complete network connectivity across all nodes."""
        all_nodes = set(self.nodes.keys()) | self.authority_keys
        self.partitions = [all_nodes]

    def is_connected(self, node_a: str, node_b: str) -> bool:
        for group in self.partitions:
            if node_a in group and node_b in group:
                return True
        return False

    def reachable_from(self, node_id: str) -> Set[str]:
        for group in self.partitions:
            if node_id in group:
                return set(group)
        return {node_id}

    def has_authority_quorum(self, node_id: str) -> bool:
        reachable = self.reachable_from(node_id)
        # Requires at least one certified authority key reachable
        return bool(reachable & self.authority_keys)

    def propose_operation(
        self,
        author_node_id: str,
        kind: HistoryEntryKind,
        payload: Mapping[str, Any],
        is_idempotent: bool = False,
        idempotency_key: str = "",
    ) -> Tuple[bool, Optional[HistoryEntry], str]:
        """Submits a proposed transition from an orchestrator.
        
        Enforces:
        - Quorum presence for authoritative commits / graph substitutions.
        - Idempotent deduplication (zero double commits).
        """
        # 1. Authority Quorum Check
        if kind in (HistoryEntryKind.AUTHORITATIVE_COMMIT, HistoryEntryKind.GRAPH_SUBSTITUTION):
            if not self.has_authority_quorum(author_node_id):
                return False, None, "MINORITY_PARTITION_FAIL_CLOSED: cannot commit without authority quorum"

        # 2. Idempotent Deduplication Check
        if is_idempotent and idempotency_key:
            if idempotency_key in self.committed_idempotent_tasks:
                existing_entry = self.committed_idempotent_tasks[idempotency_key]
                return True, existing_entry, "DUPLICATE_EXECUTION_DEDUPLICATED"

        history = self.node_histories[author_node_id]
        seq = history.tip_sequence() + 1
        prev_hash = history.tip_hash()
        quorum_sigs = tuple(sorted(self.authority_keys)) if self.has_authority_quorum(author_node_id) else ()

        entry = HistoryEntry(
            entry_id=f"entry_{author_node_id}_{seq}",
            sequence_number=seq,
            prev_hash=prev_hash,
            kind=kind,
            author_node_id=author_node_id,
            generation=self.active_generation,
            payload=payload,
            quorum_signatures=quorum_sigs,
        )

        ok, msg = history.append(entry)
        if not ok:
            return False, None, msg

        if is_idempotent and idempotency_key:
            self.committed_idempotent_tasks[idempotency_key] = entry

        # Replicate to all reachable nodes in the same partition
        reachable = self.reachable_from(author_node_id)
        for nid in reachable:
            if nid in self.node_histories and nid != author_node_id:
                # Synchronize if valid
                if self.node_histories[nid].tip_sequence() + 1 == entry.sequence_number:
                    self.node_histories[nid].append(entry)

        return True, entry, "COMMITTED"

    def reconcile_to_canonical(self, canonical_history: AuthoritativeHistory) -> Tuple[bool, str]:
        """Reconciles all orchestrators to a single authoritative history journal."""
        if not canonical_history.verify_integrity():
            return False, "CANONICAL_HISTORY_INTEGRITY_FAILURE"

        canonical_digest = canonical_history.state_digest()
        for nid in self.nodes:
            self.node_histories[nid] = canonical_history.clone()

        # Verify all nodes have identical state digest
        digests = {self.node_histories[nid].state_digest() for nid in self.nodes}
        if len(digests) != 1 or next(iter(digests)) != canonical_digest:
            return False, "STATE_DIVERGENCE_AFTER_RECONCILIATION"

        return True, "CONVERGED"

