"""Distributed Quorum-Certified Runtime Mutation for Campaign A2 (Gate A2.7).

Enforces:
1. Proposers Have Zero Authority: Proposals to mutate the realization graph G or
   actor binding B carry zero authority to alter runtime state.
2. Quorum-Certified Mutation: A runtime topology substitution is valid if and only if
   certified by a cryptographic Quorum Certificate (RuntimeMutationQC) signed by at least
   a threshold (e.g. 2-of-3) of independent authority nodes.
3. Cryptographic Context Binding: The Quorum Certificate binds:
   - Parent contract U (semantic intent)
   - Candidate graph G_{t+1} and candidate actor binding B_{t+1}
   - Generation epoch
   - Canonical history head (pre-state tip)
   - Multi-party HMAC-SHA256 signatures of independent verifier nodes
4. Negative Control Falsification: Rejection of uncertified proposals, insufficient votes,
   stale history heads, stale generations, and semantic projection violations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import json
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from uow.composition.actor import ActorRegistry
from uow.composition.binding import ActorBinding, validate_binding
from uow.composition.contract import ParentContract
from uow.composition.fabric import canonical_json
from uow.composition.graph import RealizationGraph
from uow.composition.projection import check_conformance, project_semantics


@dataclass(frozen=True)
class RuntimeMutationProposal:
    """Proposal from an adaptive engine or remote host to replace active graph and binding."""

    proposal_id: str
    proposer_id: str
    parent_contract_id: str
    parent_contract_hash: str
    current_graph_hash: str
    current_binding_hash: str
    candidate_graph: RealizationGraph
    candidate_binding: ActorBinding
    generation: int
    history_head: str
    strategy: str = "adaptive_optimization"
    speedup_estimate: float = 1.0
    rationale: str = ""
    proposer_signature: str = ""
    timestamp_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def compute_hash(self) -> str:
        payload = {
            "proposal_id": self.proposal_id,
            "proposer_id": self.proposer_id,
            "parent_contract_id": self.parent_contract_id,
            "parent_contract_hash": self.parent_contract_hash,
            "current_graph_hash": self.current_graph_hash,
            "current_binding_hash": self.current_binding_hash,
            "candidate_graph_hash": self.candidate_graph.compute_hash(),
            "candidate_binding_hash": self.candidate_binding.compute_hash(),
            "generation": self.generation,
            "history_head": self.history_head,
            "strategy": self.strategy,
            "speedup_estimate": f"{self.speedup_estimate:.4f}",
            "rationale": self.rationale,
        }
        raw = canonical_json(payload).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class AuthorityMutationVote:
    """Cryptographic vote from an authority node evaluating a mutation proposal."""

    vote_id: str
    voter_id: str
    proposal_id: str
    proposal_hash: str
    parent_contract_hash: str
    candidate_graph_hash: str
    candidate_binding_hash: str
    generation: int
    history_head: str
    conformance_verified: bool
    accepted: bool
    rejection_reason: Optional[str] = None
    signature: str = ""
    timestamp_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def compute_hash(self) -> str:
        payload = {
            "vote_id": self.vote_id,
            "voter_id": self.voter_id,
            "proposal_id": self.proposal_id,
            "proposal_hash": self.proposal_hash,
            "parent_contract_hash": self.parent_contract_hash,
            "candidate_graph_hash": self.candidate_graph_hash,
            "candidate_binding_hash": self.candidate_binding_hash,
            "generation": self.generation,
            "history_head": self.history_head,
            "conformance_verified": self.conformance_verified,
            "accepted": self.accepted,
            "rejection_reason": self.rejection_reason or "",
        }
        raw = canonical_json(payload).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


def sign_mutation_vote(
    voter_id: str,
    secret_key: str,
    proposal: RuntimeMutationProposal,
    parent_contract: ParentContract,
    current_history_head: str,
    current_generation: int,
    actor_registry: Optional[ActorRegistry] = None,
) -> AuthorityMutationVote:
    """Evaluates a mutation proposal from an authority perspective and produces a signed vote."""
    vote_id = f"vote_{voter_id}_{proposal.proposal_id}"
    prop_hash = proposal.compute_hash()
    cand_graph_hash = proposal.candidate_graph.compute_hash()
    cand_bind_hash = proposal.candidate_binding.compute_hash()
    u_hash = parent_contract.compute_hash()

    # 1. Check parent contract match
    if proposal.parent_contract_hash != u_hash:
        vote = AuthorityMutationVote(
            vote_id=vote_id,
            voter_id=voter_id,
            proposal_id=proposal.proposal_id,
            proposal_hash=prop_hash,
            parent_contract_hash=proposal.parent_contract_hash,
            candidate_graph_hash=cand_graph_hash,
            candidate_binding_hash=cand_bind_hash,
            generation=proposal.generation,
            history_head=proposal.history_head,
            conformance_verified=False,
            accepted=False,
            rejection_reason=f"PARENT_CONTRACT_MISMATCH: expected {u_hash[:8]}",
        )
        return _attach_signature(vote, secret_key)

    # 2. Check history head match
    if proposal.history_head != current_history_head:
        vote = AuthorityMutationVote(
            vote_id=vote_id,
            voter_id=voter_id,
            proposal_id=proposal.proposal_id,
            proposal_hash=prop_hash,
            parent_contract_hash=proposal.parent_contract_hash,
            candidate_graph_hash=cand_graph_hash,
            candidate_binding_hash=cand_bind_hash,
            generation=proposal.generation,
            history_head=proposal.history_head,
            conformance_verified=False,
            accepted=False,
            rejection_reason=f"STALE_HISTORY_HEAD: expected {current_history_head[:8]}, got {proposal.history_head[:8]}",
        )
        return _attach_signature(vote, secret_key)

    # 3. Check generation match
    if proposal.generation != current_generation:
        vote = AuthorityMutationVote(
            vote_id=vote_id,
            voter_id=voter_id,
            proposal_id=proposal.proposal_id,
            proposal_hash=prop_hash,
            parent_contract_hash=proposal.parent_contract_hash,
            candidate_graph_hash=cand_graph_hash,
            candidate_binding_hash=cand_bind_hash,
            generation=proposal.generation,
            history_head=proposal.history_head,
            conformance_verified=False,
            accepted=False,
            rejection_reason=f"STALE_GENERATION: expected {current_generation}, got {proposal.generation}",
        )
        return _attach_signature(vote, secret_key)

    # 4. Check semantic conformance Phi(G_cand, U) == Phi(U)
    projection = project_semantics(proposal.candidate_graph, parent_contract)
    if not projection.conforms:
        violations_str = "; ".join(projection.violations)
        vote = AuthorityMutationVote(
            vote_id=vote_id,
            voter_id=voter_id,
            proposal_id=proposal.proposal_id,
            proposal_hash=prop_hash,
            parent_contract_hash=proposal.parent_contract_hash,
            candidate_graph_hash=cand_graph_hash,
            candidate_binding_hash=cand_bind_hash,
            generation=proposal.generation,
            history_head=proposal.history_head,
            conformance_verified=False,
            accepted=False,
            rejection_reason=f"SEMANTIC_PROJECTION_MISMATCH: {violations_str}",
        )
        return _attach_signature(vote, secret_key)

    # 5. Check actor binding if registry is available
    if actor_registry is not None:
        binding_valid, binding_violations = validate_binding(
            proposal.candidate_graph,
            proposal.candidate_binding,
            actor_registry,
        )
        if not binding_valid:
            violations_str = "; ".join(binding_violations)
            vote = AuthorityMutationVote(
                vote_id=vote_id,
                voter_id=voter_id,
                proposal_id=proposal.proposal_id,
                proposal_hash=prop_hash,
                parent_contract_hash=proposal.parent_contract_hash,
                candidate_graph_hash=cand_graph_hash,
                candidate_binding_hash=cand_bind_hash,
                generation=proposal.generation,
                history_head=proposal.history_head,
                conformance_verified=True,
                accepted=False,
                rejection_reason=f"ACTOR_BINDING_INVALID: {violations_str}",
            )
            return _attach_signature(vote, secret_key)

    # All criteria satisfied: vote accepted
    vote = AuthorityMutationVote(
        vote_id=vote_id,
        voter_id=voter_id,
        proposal_id=proposal.proposal_id,
        proposal_hash=prop_hash,
        parent_contract_hash=proposal.parent_contract_hash,
        candidate_graph_hash=cand_graph_hash,
        candidate_binding_hash=cand_bind_hash,
        generation=proposal.generation,
        history_head=proposal.history_head,
        conformance_verified=True,
        accepted=True,
        rejection_reason=None,
    )
    return _attach_signature(vote, secret_key)


def _attach_signature(vote: AuthorityMutationVote, secret_key: str) -> AuthorityMutationVote:
    digest = vote.compute_hash()
    sig = hmac.new(secret_key.encode("utf-8"), digest.encode("utf-8"), hashlib.sha256).hexdigest()
    return AuthorityMutationVote(
        vote_id=vote.vote_id,
        voter_id=vote.voter_id,
        proposal_id=vote.proposal_id,
        proposal_hash=vote.proposal_hash,
        parent_contract_hash=vote.parent_contract_hash,
        candidate_graph_hash=vote.candidate_graph_hash,
        candidate_binding_hash=vote.candidate_binding_hash,
        generation=vote.generation,
        history_head=vote.history_head,
        conformance_verified=vote.conformance_verified,
        accepted=vote.accepted,
        rejection_reason=vote.rejection_reason,
        signature=sig,
        timestamp_iso=vote.timestamp_iso,
    )


def verify_mutation_vote(vote: AuthorityMutationVote, secret_key: str) -> Tuple[bool, str]:
    """Verifies HMAC-SHA256 signature integrity of an authority mutation vote."""
    if not vote.signature:
        return False, "MISSING_VOTE_SIGNATURE"
    digest = vote.compute_hash()
    expected_sig = hmac.new(secret_key.encode("utf-8"), digest.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(vote.signature, expected_sig):
        return False, "INVALID_VOTE_SIGNATURE"
    return True, "VALID_VOTE"


@dataclass(frozen=True)
class RuntimeMutationQC:
    """Cryptographic multi-signature Quorum Certificate authorizing runtime mutation."""

    qc_id: str
    proposal_id: str
    proposal_hash: str
    parent_contract_hash: str
    candidate_graph_hash: str
    candidate_binding_hash: str
    generation: int
    history_head: str
    threshold: int
    signers: Tuple[str, ...]
    vote_hashes: Tuple[str, ...]
    votes: Tuple[AuthorityMutationVote, ...]
    timestamp_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    qc_hash: str = ""

    def __post_init__(self) -> None:
        if not self.qc_hash:
            payload = {
                "qc_id": self.qc_id,
                "proposal_id": self.proposal_id,
                "proposal_hash": self.proposal_hash,
                "parent_contract_hash": self.parent_contract_hash,
                "candidate_graph_hash": self.candidate_graph_hash,
                "candidate_binding_hash": self.candidate_binding_hash,
                "generation": self.generation,
                "history_head": self.history_head,
                "threshold": self.threshold,
                "signers": sorted(self.signers),
                "vote_hashes": sorted(self.vote_hashes),
            }
            digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
            object.__setattr__(self, "qc_hash", digest)

    def compute_hash(self) -> str:
        return self.qc_hash


def assemble_mutation_qc(
    proposal: RuntimeMutationProposal,
    votes: Sequence[AuthorityMutationVote],
    threshold: int = 2,
) -> Tuple[Optional[RuntimeMutationQC], str]:
    """Assembles a Quorum Certificate from a collection of authority votes if threshold is met."""
    accepted_votes = [v for v in votes if v.accepted]
    unique_signers: Dict[str, AuthorityMutationVote] = {}
    for v in accepted_votes:
        if v.voter_id not in unique_signers:
            unique_signers[v.voter_id] = v

    if len(unique_signers) < threshold:
        return (
            None,
            f"QUORUM_THRESHOLD_NOT_MET: collected {len(unique_signers)} votes, threshold requires {threshold}",
        )

    signers = tuple(sorted(unique_signers.keys()))
    sorted_votes = tuple(unique_signers[s] for s in signers)
    vote_hashes = tuple(v.compute_hash() for v in sorted_votes)

    cand_graph_hash = proposal.candidate_graph.compute_hash()
    cand_bind_hash = proposal.candidate_binding.compute_hash()

    qc = RuntimeMutationQC(
        qc_id=f"qc_mut_{proposal.proposal_id}",
        proposal_id=proposal.proposal_id,
        proposal_hash=proposal.compute_hash(),
        parent_contract_hash=proposal.parent_contract_hash,
        candidate_graph_hash=cand_graph_hash,
        candidate_binding_hash=cand_bind_hash,
        generation=proposal.generation,
        history_head=proposal.history_head,
        threshold=threshold,
        signers=signers,
        vote_hashes=vote_hashes,
        votes=sorted_votes,
    )
    return qc, "QUORUM_CERTIFICATE_ASSEMBLED"


def verify_mutation_qc(
    qc: RuntimeMutationQC,
    parent_contract: ParentContract,
    current_history_head: str,
    current_generation: int,
    authority_keys: Mapping[str, str],
    threshold: int = 2,
) -> Tuple[bool, str]:
    """Rigorously verifies all cryptographic invariants and signatures of a RuntimeMutationQC."""
    # 1. Verify signers threshold
    if len(qc.signers) < threshold or len(set(qc.signers)) != len(qc.signers):
        return False, f"QUORUM_THRESHOLD_NOT_MET: signers={len(qc.signers)}, threshold={threshold}"

    # 2. Check parent contract hash
    expected_u_hash = parent_contract.compute_hash()
    if qc.parent_contract_hash != expected_u_hash:
        return False, f"PARENT_CONTRACT_MISMATCH: expected {expected_u_hash[:8]}, got {qc.parent_contract_hash[:8]}"

    # 3. Check history head
    if qc.history_head != current_history_head:
        return False, f"STALE_HISTORY_HEAD: expected {current_history_head[:8]}, got {qc.history_head[:8]}"

    # 4. Check generation
    if qc.generation != current_generation:
        return False, f"STALE_GENERATION: expected {current_generation}, got {qc.generation}"

    # 5. Verify individual votes and signatures
    voter_set = set(qc.signers)
    for vote in qc.votes:
        if vote.voter_id not in voter_set:
            return False, f"UNLISTED_VOTER: {vote.voter_id}"
        if not vote.accepted:
            return False, f"REJECTED_VOTE_IN_QC: {vote.voter_id}"
        secret = authority_keys.get(vote.voter_id)
        if not secret:
            return False, f"UNKNOWN_AUTHORITY_VOTER: {vote.voter_id}"
        valid, reason = verify_mutation_vote(vote, secret)
        if not valid:
            return False, f"INVALID_VOTE_SIGNATURE: voter {vote.voter_id} failed: {reason}"

    return True, "VALID_MUTATION_QC"


from ..realizations.authority.runtime_mutation import QuorumMutationCoordinator

__all__ = [
    "RuntimeMutationProposal",
    "AuthorityMutationVote",
    "RuntimeMutationQC",
    "QuorumMutationCoordinator",
    "sign_mutation_vote",
    "verify_mutation_vote",
    "assemble_mutation_qc",
    "verify_mutation_qc",
]
