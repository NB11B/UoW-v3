"""Quorum-backed commit realization.

This implementation is the production realization of quorum commit semantics.
It depends only on the semantic authority-provider protocol, not on
qualification implementations.
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

from ...authority import (
    AuthorityReplica,
    QuorumAuthorityProvider,
    QuorumRoundResult,
    authority_mode_is_active,
)
from ...contracts import UoW
from ...engine import CertificateResult, EvidenceLedger, EvidenceRecord, Proposal
from ...state import WorldState
from ...transactions.descriptor import TransactionDescriptor
from ...transactions.protocol import CommitSequencer


class QuorumCommitError(RuntimeError):
    """Raised when a transition fails to achieve quorum or authority application."""


class QuorumCommitSequencer(CommitSequencer):
    """Commit sequencer backed by a semantic quorum authority provider.

    Invariants:
    1. A proposal has zero authority to mutate state.
    2. Commit requires the provider's threshold authority.
    3. Provider replicas independently certify/apply authority artifacts.
    4. Minority partitions cannot commit.
    5. Conflicting proposals from one pre-state remain excluded.
    """

    def __init__(
        self,
        cluster: QuorumAuthorityProvider,
        *,
        primary_node_id: Optional[str] = None,
    ) -> None:
        self.cluster = cluster
        self._primary_node_id = primary_node_id or sorted(cluster.nodes.keys())[0]
        self._qc_history: List[Any] = []
        self._last_round_result: Optional[QuorumRoundResult] = None

    @property
    def primary_node(self) -> AuthorityReplica:
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
    def qc_history(self) -> Tuple[Any, ...]:
        return tuple(self._qc_history)

    @property
    def last_round_result(self) -> Optional[QuorumRoundResult]:
        return self._last_round_result

    def is_converged(self) -> bool:
        reachable = self.cluster.reachable_nodes()
        active_nodes = [
            self.cluster.nodes[nid]
            for nid in reachable
            if authority_mode_is_active(self.cluster.nodes[nid].mode)
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

        return primary.state, primary.ledger.records[-1]
