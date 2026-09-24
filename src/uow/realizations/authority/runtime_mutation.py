"""Quorum-authorized runtime mutation coordinator realization."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import List, Mapping, Optional, Tuple

from ...composition.actor import ActorRegistry
from ...composition.binding import ActorBinding
from ...composition.contract import ParentContract
from ...composition.graph import RealizationGraph
from ...composition.history import AuthoritativeHistory, HistoryEntry, HistoryEntryKind
from ...composition.mutation import (
    AuthorityMutationVote,
    RuntimeMutationProposal,
    RuntimeMutationQC,
    sign_mutation_vote,
    verify_mutation_qc,
)
from ...implementations.distributed.host_node import DurableWAL


class QuorumMutationCoordinator:
    """Coordinates runtime mutation proposal, authority voting, QC verification, and atomic commit."""

    def __init__(
        self,
        parent_contract: ParentContract,
        active_graph: RealizationGraph,
        active_binding: ActorBinding,
        history: AuthoritativeHistory,
        authority_keys: Mapping[str, str],
        wal: Optional[DurableWAL] = None,
        generation: int = 0,
        quorum_threshold: int = 2,
        actor_registry: Optional[ActorRegistry] = None,
    ) -> None:
        self.parent_contract = parent_contract
        self.active_graph = active_graph
        self.active_binding = active_binding
        self.history = history
        self.authority_keys = dict(authority_keys)
        self.wal = wal
        self.generation = generation
        self.quorum_threshold = quorum_threshold
        self.actor_registry = actor_registry
        self._mutation_qc_history: List[RuntimeMutationQC] = []

    @property
    def mutation_qc_history(self) -> Tuple[RuntimeMutationQC, ...]:
        return tuple(self._mutation_qc_history)

    def propose_mutation(
        self,
        proposer_id: str,
        candidate_graph: RealizationGraph,
        candidate_binding: ActorBinding,
        strategy: str = "adaptive_optimization",
        speedup_estimate: float = 1.0,
        rationale: str = "",
    ) -> RuntimeMutationProposal:
        """Constructs a mutation proposal bound to current generation and history head."""
        proposal_id = f"mut_prop_gen{self.generation}_{hashlib.sha256(f'{proposer_id}:{datetime.now(timezone.utc).isoformat()}'.encode('utf-8')).hexdigest()[:8]}"
        return RuntimeMutationProposal(
            proposal_id=proposal_id,
            proposer_id=proposer_id,
            parent_contract_id=self.parent_contract.contract_id,
            parent_contract_hash=self.parent_contract.compute_hash(),
            current_graph_hash=self.active_graph.compute_hash(),
            current_binding_hash=self.active_binding.compute_hash(),
            candidate_graph=candidate_graph,
            candidate_binding=candidate_binding,
            generation=self.generation,
            history_head=self.history.tip_hash(),
            strategy=strategy,
            speedup_estimate=speedup_estimate,
            rationale=rationale,
        )

    def collect_votes(
        self,
        proposal: RuntimeMutationProposal,
    ) -> List[AuthorityMutationVote]:
        """Dispatches proposal to all registered authority voters and collects signed votes."""
        votes: List[AuthorityMutationVote] = []
        for voter_id, secret_key in self.authority_keys.items():
            vote = sign_mutation_vote(
                voter_id=voter_id,
                secret_key=secret_key,
                proposal=proposal,
                parent_contract=self.parent_contract,
                current_history_head=self.history.tip_hash(),
                current_generation=self.generation,
                actor_registry=self.actor_registry,
            )
            votes.append(vote)
        return votes

    def apply_mutation(
        self,
        qc: RuntimeMutationQC,
        candidate_graph: RealizationGraph,
        candidate_binding: ActorBinding,
    ) -> Tuple[bool, str]:
        """Atomically applies graph and binding mutation if and only if verified by the QC."""
        # 1. Verify QC against authoritative state
        valid, reason = verify_mutation_qc(
            qc=qc,
            parent_contract=self.parent_contract,
            current_history_head=self.history.tip_hash(),
            current_generation=self.generation,
            authority_keys=self.authority_keys,
            threshold=self.quorum_threshold,
        )
        if not valid:
            return False, f"MUTATION_REJECTED: {reason}"

        # 2. Verify candidate hashes match QC payload
        if candidate_graph.compute_hash() != qc.candidate_graph_hash:
            return False, "MUTATION_REJECTED: CANDIDATE_GRAPH_HASH_MISMATCH"
        if candidate_binding.compute_hash() != qc.candidate_binding_hash:
            return False, "MUTATION_REJECTED: CANDIDATE_BINDING_HASH_MISMATCH"

        # 3. Apply substitution atomically
        self.active_graph = candidate_graph
        self.active_binding = candidate_binding
        next_gen = self.generation + 1

        # 4. Form and commit history entry
        expected_seq = self.history.tip_sequence() + 1
        entry = HistoryEntry(
            entry_id=f"entry_sub_{next_gen}_{qc.qc_id[:8]}",
            sequence_number=expected_seq,
            prev_hash=self.history.tip_hash(),
            kind=HistoryEntryKind.GRAPH_SUBSTITUTION,
            author_node_id=qc.qc_id,
            generation=next_gen,
            payload={
                "candidate_graph_hash": qc.candidate_graph_hash,
                "candidate_binding_hash": qc.candidate_binding_hash,
                "signers": list(qc.signers),
            },
            quorum_signatures=qc.signers,
        )

        appended, append_reason = self.history.append(entry)
        if not appended:
            return False, f"HISTORY_APPEND_FAILED: {append_reason}"

        # 5. Persist to WAL if configured
        if self.wal is not None:
            self.wal.append(entry)

        self.generation = next_gen
        self._mutation_qc_history.append(qc)
        return True, "MUTATION_COMMITTED"


__all__ = ["QuorumMutationCoordinator"]
