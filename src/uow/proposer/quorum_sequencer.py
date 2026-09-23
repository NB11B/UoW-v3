"""Distributed Quorum Commit Sequencer (Gate U15.8).

Enforces that every authoritative state transition proposed by an adaptive or deterministic
proposer is committed ONLY when validated and certified by a 2-of-3 quorum of independent
authority nodes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..contracts import UoW
from ..engine import CertificateResult, EvidenceLedger, EvidenceRecord, Proposal
from ..state import WorldState
from ..transactions.descriptor import TransactionDescriptor
from ..transactions.sequencer import CommitSequencer

# Import DistributedAuthorityCluster and related types from qualification harness
from qualification.distributed_authority.authority import (
    AuthorityNode,
    DistributedAuthorityCluster,
    NodeMode,
    QuorumCertificate,
    RoundResult,
)


class QuorumCommitError(RuntimeError):
    """Raised when a state transition fails to achieve quorum or is rejected by authority nodes."""


class QuorumCommitSequencer(CommitSequencer):
    """Commit sequencer backed by an independent replicated authority cluster.
    
    Invariants:
    1. A proposal has ZERO authority to mutate state on any node.
    2. Commit requires at least threshold (e.g. 2-of-3) independent authority votes.
    3. Replicas independently re-certify and apply Quorum Certificates (QCs).
    4. Minority partitions (< threshold) cannot commit.
    5. Conflicting proposals from the same pre-state are locked and rejected.
    """

    def __init__(
        self,
        cluster: DistributedAuthorityCluster,
        *,
        primary_node_id: Optional[str] = None,
    ) -> None:
        self.cluster = cluster
        self._primary_node_id = primary_node_id or sorted(cluster.nodes.keys())[0]
        self._qc_history: List[QuorumCertificate] = []
        self._last_round_result: Optional[RoundResult] = None

    @property
    def primary_node(self) -> AuthorityNode:
        reachable = self.cluster.reachable_nodes()
        if self._primary_node_id in reachable:
            return self.cluster.nodes[self._primary_node_id]
        if reachable:
            return self.cluster.nodes[reachable[0]]
        return self.cluster.nodes[sorted(self.cluster.nodes.keys())[0]]

    @property
    def current_state(self) -> WorldState:
        return self.primary_node.state

    @property
    def ledger(self) -> EvidenceLedger:
        return self.primary_node.ledger

    @property
    def qc_history(self) -> Tuple[QuorumCertificate, ...]:
        return tuple(self._qc_history)

    @property
    def last_round_result(self) -> Optional[RoundResult]:
        return self._last_round_result

    def is_converged(self) -> bool:
        """Verifies that all reachable active nodes agree on state hash and ledger root."""
        reachable = self.cluster.reachable_nodes()
        active_nodes = [
            self.cluster.nodes[nid]
            for nid in reachable
            if self.cluster.nodes[nid].mode == NodeMode.ACTIVE
        ]
        if not active_nodes:
            return False
        states = {n.state.state_hash for n in active_nodes}
        roots = {n.ledger.root_hash() for n in active_nodes}
        return len(states) == 1 and len(roots) == 1

    def commit(
        self,
        uow: UoW,
        proposal: Proposal,
        tx: TransactionDescriptor,
        cert: CertificateResult,
    ) -> Tuple[WorldState, EvidenceRecord]:
        """Submits transition to the authority cluster and requires quorum certification to commit."""
        round_res = self.cluster.submit(uow, proposal)
        self._last_round_result = round_res

        if not round_res.committed or round_res.quorum_certificate is None:
            raise QuorumCommitError(
                f"Quorum commit rejected: reason='{round_res.reason}', "
                f"reachable={round_res.reachable_nodes}, "
                f"votes={[v.accepted for v in round_res.votes]}"
            )

        qc = round_res.quorum_certificate
        self._qc_history.append(qc)

        # Enforce replica convergence across all nodes that applied the QC
        applied_nodes = [
            self.cluster.nodes[nid]
            for nid, res in round_res.apply_results.items()
            if res.applied
        ]
        if not applied_nodes:
            raise QuorumCommitError("QC formed but no replicas successfully applied it.")

        state_hashes = {n.state.state_hash for n in applied_nodes}
        ledger_roots = {n.ledger.root_hash() for n in applied_nodes}
        if len(state_hashes) > 1 or len(ledger_roots) > 1:
            raise QuorumCommitError("Quorum replicas diverged following QC application!")

        primary = self.primary_node
        if not primary.ledger.records:
            raise QuorumCommitError("Primary ledger empty after successful quorum commit.")

        last_record = primary.ledger.records[-1]
        return primary.state, last_record
