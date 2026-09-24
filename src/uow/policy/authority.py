r"""Distributed Policy Authority Engine (Milestone P4).

Implements distributed multi-authority governance over policy state transitions (\Pi_k -> \Pi_{k+1}):
    Architecture understands capabilities;
    Policy understands realizations;
    Drivers understand devices;
    Distributed Authority certifies operational truth.

Core Physical Topology:
    A1: Host Authority (x86_64 host / Linux / Windows)
    A2: ESP32-S3 Authority (Dual-core Xtensa / FreeRTOS)
    A3: STM32U585 Authority (ARM Cortex-M33 / TrustZone secure element)

Invariants Enforced:
    1. Execution Capability != Policy Authority
    2. Authority Quorum: Q(A1, A2, A3, ΔΠ) = 1 required for durable registry transitions
    3. Registry Version Agreement: \Pi_k^{A1} == \Pi_k^{A2} == \Pi_k^{A3}
    4. Conflicting Proposal Rejection: N_{double_commits} = 0
    5. Node Loss Fault Tolerance: 2-of-3 threshold quorum survives physical node failure
    6. Partition Reconciliation: Certificate chain determines truth, not arrival time (no last-writer-wins)
    7. Malformed / Stale Vote Rejection
    8. In-Flight Execution Isolation during distributed transitions
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import time
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Set, Tuple

from .models import (
    AuthorityVote,
    DistributedPolicyCertificate,
    Policy,
    PolicyLifecycleEvent,
    PolicyState,
    PolicyTransitionProposal,
    PolicyTransitionType,
    WorldConditions,
)
from .registry import PolicyRegistry


class AuthorityError(Exception):
    """Base exception for distributed authority failures."""
    pass


class StaleProposalError(AuthorityError):
    """Proposal references a parent registry version that has already advanced."""
    pass


class ConflictingProposalError(AuthorityError):
    """Multiple proposals attempt to mutate the same parent registry version."""
    pass


class QuorumNotSatisfiedError(AuthorityError):
    """Collected votes do not satisfy the configured authority rule."""
    pass


class InvalidVoteError(AuthorityError):
    """An authority vote failed cryptographic or semantic validation."""
    pass


@dataclass(frozen=True)
class AuthorityRule:
    """Configured quorum / authority rule Q(A1, A2, A3, ΔΠ)."""
    rule_id: str
    required_authorities: FrozenSet[str]
    threshold: int  # Number of affirmative votes required

    def evaluate(self, votes: Sequence[AuthorityVote], proposal: PolicyTransitionProposal) -> bool:
        """Evaluate if collected votes satisfy this authority rule."""
        seen_authorities: Set[str] = set()
        affirmative_count = 0

        for v in votes:
            # 1. Authority must be recognized
            if v.authority_id not in self.required_authorities:
                continue

            # 2. Reject duplicate votes from the same authority
            if v.authority_id in seen_authorities:
                continue
            seen_authorities.add(v.authority_id)

            # 3. Must match proposal digest
            if v.proposal_digest != proposal.proposal_digest:
                continue

            # 4. Must match expected pre-state
            if v.pre_state_hash != proposal.previous_registry_digest:
                continue

            # 5. Must be an affirmative vote
            if v.vote:
                affirmative_count += 1

        return affirmative_count >= self.threshold


class DistributedAuthorityNode:
    """Represents an independent physical authority participant (e.g. Host, ESP32-S3, STM32U585)."""

    def __init__(
        self,
        authority_id: str,
        node_id: str,
        domain: str,
        registry: Optional[PolicyRegistry] = None,
    ) -> None:
        self.authority_id = authority_id
        self.node_id = node_id
        self.domain = domain
        self.registry = registry or PolicyRegistry()
        self.is_online = True
        self.rejected_proposals_count = 0
        self.approved_votes_count = 0

    def evaluate_proposal(
        self,
        proposal: PolicyTransitionProposal,
        candidate_policy: Optional[Policy] = None,
    ) -> AuthorityVote:
        """Independently verify proposal against local registry state and produce certified vote."""
        now = time.time()
        current_version = self.registry.version
        current_digest = self.registry.compute_digest()

        # Reject if offline
        if not self.is_online:
            return AuthorityVote(
                authority_id=self.authority_id,
                node_id=self.node_id,
                proposal_id=proposal.proposal_id,
                proposal_digest=proposal.proposal_digest,
                vote=False,
                pre_state_hash=current_digest,
                post_state_hash=current_digest,
                reason=f"Node {self.node_id} is offline",
                timestamp=now,
            )

        # 1. Hard Invariant: Stale Registry Version Rejection
        if proposal.registry_version_expected != current_version:
            self.rejected_proposals_count += 1
            return AuthorityVote(
                authority_id=self.authority_id,
                node_id=self.node_id,
                proposal_id=proposal.proposal_id,
                proposal_digest=proposal.proposal_digest,
                vote=False,
                pre_state_hash=current_digest,
                post_state_hash=current_digest,
                reason=f"Stale registry version: proposal expects {proposal.registry_version_expected}, but node is at {current_version}",
                timestamp=now,
            )

        # 2. Hard Invariant: Registry Digest Divergence Rejection
        if proposal.previous_registry_digest != current_digest:
            self.rejected_proposals_count += 1
            return AuthorityVote(
                authority_id=self.authority_id,
                node_id=self.node_id,
                proposal_id=proposal.proposal_id,
                proposal_digest=proposal.proposal_digest,
                vote=False,
                pre_state_hash=current_digest,
                post_state_hash=current_digest,
                reason=f"Registry digest mismatch: proposal expects {proposal.previous_registry_digest}, but node digest is {current_digest}",
                timestamp=now,
            )

        # 3. Transition-Specific Validation
        if proposal.transition_type == PolicyTransitionType.PROMOTE:
            if candidate_policy is None:
                self.rejected_proposals_count += 1
                return AuthorityVote(
                    authority_id=self.authority_id,
                    node_id=self.node_id,
                    proposal_id=proposal.proposal_id,
                    proposal_digest=proposal.proposal_digest,
                    vote=False,
                    pre_state_hash=current_digest,
                    post_state_hash=current_digest,
                    reason="Missing candidate policy for promotion",
                    timestamp=now,
                )

            # Strict correctness gate
            if candidate_policy.evidence.correctness_breaches > 0:
                self.rejected_proposals_count += 1
                return AuthorityVote(
                    authority_id=self.authority_id,
                    node_id=self.node_id,
                    proposal_id=proposal.proposal_id,
                    proposal_digest=proposal.proposal_digest,
                    vote=False,
                    pre_state_hash=current_digest,
                    post_state_hash=current_digest,
                    reason=f"Correctness gate violation: {candidate_policy.evidence.correctness_breaches} breaches",
                    timestamp=now,
                )

        elif proposal.transition_type == PolicyTransitionType.INVALIDATE:
            existing = self.registry.get_policy(proposal.policy_id)
            if existing is None or not existing.is_active:
                self.rejected_proposals_count += 1
                return AuthorityVote(
                    authority_id=self.authority_id,
                    node_id=self.node_id,
                    proposal_id=proposal.proposal_id,
                    proposal_digest=proposal.proposal_digest,
                    vote=False,
                    pre_state_hash=current_digest,
                    post_state_hash=current_digest,
                    reason=f"Cannot invalidate policy {proposal.policy_id}: not active or non-existent",
                    timestamp=now,
                )

        # Compute post-state hash deterministically
        simulated_raw = f"{current_digest}:{proposal.transition_type.value}:{proposal.policy_id}:{proposal.candidate_policy_version}:{current_version + 1}"
        post_state_hash = hashlib.sha256(simulated_raw.encode("utf-8")).hexdigest()[:32]

        self.approved_votes_count += 1
        return AuthorityVote(
            authority_id=self.authority_id,
            node_id=self.node_id,
            proposal_id=proposal.proposal_id,
            proposal_digest=proposal.proposal_digest,
            vote=True,
            pre_state_hash=current_digest,
            post_state_hash=post_state_hash,
            reason="Proposal verified against local policy state and invariants",
            timestamp=now,
        )

    def apply_certificate(
        self,
        certificate: DistributedPolicyCertificate,
        policy: Optional[Policy] = None,
    ) -> int:
        """Apply a certified policy transition to local registry."""
        if not self.is_online:
            raise AuthorityError(f"Node {self.node_id} is offline; cannot apply certificate")
        return self.registry.register_certified_transition(certificate, policy=policy)


class DistributedPolicyGovernor:
    """Coordinates distributed policy authority across physical nodes (Host, ESP32-S3, STM32U585)."""

    def __init__(
        self,
        nodes: Sequence[DistributedAuthorityNode],
        default_rule: Optional[AuthorityRule] = None,
    ) -> None:
        if not nodes:
            raise ValueError("DistributedPolicyGovernor requires at least one authority node")

        self.nodes: Dict[str, DistributedAuthorityNode] = {n.authority_id: n for n in nodes}
        self.default_rule = default_rule or AuthorityRule(
            rule_id="two_of_three_quorum",
            required_authorities=frozenset(self.nodes.keys()),
            threshold=max(1, (len(nodes) * 2) // 3 if len(nodes) >= 3 else len(nodes)),
        )

        self._pending_proposals: Dict[str, PolicyTransitionProposal] = {}
        self._committed_parent_versions: Set[int] = set()
        self._committed_certificates: List[DistributedPolicyCertificate] = []
        self._proposal_sequence = 0

    @property
    def committed_certificates_count(self) -> int:
        return len(self._committed_certificates)

    def create_proposal(
        self,
        transition_type: PolicyTransitionType,
        policy_id: str,
        candidate_policy_version: int,
        world_snapshot: WorldConditions,
        candidate_policy: Optional[Policy] = None,
        evidence_digest: str = "",
        qualification_digest: str = "",
        proposer_id: str = "A1_HOST",
        details: Optional[Mapping[str, Any]] = None,
    ) -> PolicyTransitionProposal:
        """Create a formal policy transition proposal stamped with expected parent registry state."""
        self._proposal_sequence += 1
        proposer_node = self.nodes.get(proposer_id) or next(iter(self.nodes.values()))
        expected_version = proposer_node.registry.version
        expected_digest = proposer_node.registry.compute_digest()

        cand_digest = candidate_policy.compute_digest() if candidate_policy else ""
        ev_digest = evidence_digest or (candidate_policy.evidence.evidence_digest if candidate_policy else "")

        proposal = PolicyTransitionProposal(
            proposal_id=f"prop_{transition_type.value.lower()}_{policy_id}_v{candidate_policy_version}_{self._proposal_sequence}",
            transition_type=transition_type,
            policy_id=policy_id,
            candidate_policy_version=candidate_policy_version,
            registry_version_expected=expected_version,
            previous_registry_digest=expected_digest,
            candidate_policy_digest=cand_digest,
            evidence_digest=ev_digest,
            qualification_digest=qualification_digest,
            world_snapshot_id=world_snapshot.snapshot_id,
            proposer_id=proposer_id,
            timestamp=time.time(),
            details=details or {},
        )
        self._pending_proposals[proposal.proposal_id] = proposal
        return proposal

    def collect_votes(
        self,
        proposal: PolicyTransitionProposal,
        candidate_policy: Optional[Policy] = None,
    ) -> List[AuthorityVote]:
        """Collect independent votes from all reachable physical authority nodes."""
        votes: List[AuthorityVote] = []
        for node in self.nodes.values():
            if node.is_online:
                vote = node.evaluate_proposal(proposal, candidate_policy=candidate_policy)
                votes.append(vote)
        return votes

    def certify_and_commit(
        self,
        proposal: PolicyTransitionProposal,
        votes: Sequence[AuthorityVote],
        rule: Optional[AuthorityRule] = None,
        candidate_policy: Optional[Policy] = None,
    ) -> DistributedPolicyCertificate:
        """Validate collected votes, verify quorum rule, issue certificate, and commit across authorities.
        
        Enforces Hard Invariants:
        - Conflicting proposals claiming same parent version fail (N_{double_commits} = 0)
        - Quorum must be satisfied by valid, un-tampered votes
        - Registry state advances atomically across all reachable participants
        """
        active_rule = rule or self.default_rule

        # 1. Hard Invariant: Conflicting Proposal / Double-Commit Prevention
        if proposal.registry_version_expected in self._committed_parent_versions:
            raise ConflictingProposalError(
                f"Conflicting proposal rejected: parent registry version {proposal.registry_version_expected} "
                f"has already committed a policy transition."
            )

        # 2. Vote Validation: Reject malformed or unauthorized votes
        validated_votes: List[AuthorityVote] = []
        for v in votes:
            if v.authority_id not in self.nodes:
                continue  # Unknown authority rejected
            if v.proposal_digest != proposal.proposal_digest:
                continue  # Wrong proposal digest rejected
            if v.pre_state_hash != proposal.previous_registry_digest:
                continue  # Wrong parent digest rejected
            validated_votes.append(v)

        # 3. Evaluate Quorum Rule Q(votes)
        quorum_ok = active_rule.evaluate(validated_votes, proposal)
        if not quorum_ok:
            raise QuorumNotSatisfiedError(
                f"Authority rule {active_rule.rule_id} not satisfied: "
                f"threshold is {active_rule.threshold}, but affirmative votes were insufficient."
            )

        v_before = proposal.registry_version_expected
        v_after = v_before + 1
        now = time.time()

        # Predict deterministic post-commit registry digest
        proposer_node = self.nodes.get(proposal.proposer_id) or next(iter(self.nodes.values()))
        expected_post_digest = proposer_node.registry.predict_transition_digest(
            proposal.transition_type,
            proposal.policy_id,
            policy=candidate_policy,
        )

        cert = DistributedPolicyCertificate(
            transition_id=f"cert_trans_{proposal.proposal_id}",
            transition_type=proposal.transition_type,
            policy_id=proposal.policy_id,
            policy_version=proposal.candidate_policy_version,
            registry_version_before=v_before,
            registry_version_after=v_after,
            previous_registry_digest=proposal.previous_registry_digest,
            new_registry_digest=expected_post_digest,
            proposal_digest=proposal.proposal_digest,
            qualification_digest=proposal.qualification_digest,
            evidence_digest=proposal.evidence_digest,
            authority_rule_id=active_rule.rule_id,
            authority_votes=tuple(validated_votes),
            quorum_satisfied=True,
            commit_timestamp=now,
        )

        # 4. Commit Transition Across All Reachable Online Authorities
        applied_digests: Set[str] = set()
        for node in self.nodes.values():
            if node.is_online:
                node.apply_certificate(cert, policy=candidate_policy)
                applied_digests.add(node.registry.compute_digest())

        # 5. Registry-Version Agreement Invariant: All online authorities must converge identically
        if len(applied_digests) > 1:
            raise AuthorityError(f"Registry divergence detected across authorities: {applied_digests}")

        agreed_digest = next(iter(applied_digests)) if applied_digests else ""
        if agreed_digest != expected_post_digest:
            raise AuthorityError(f"Post-commit digest divergence: expected {expected_post_digest}, but actual is {agreed_digest}")

        self._committed_parent_versions.add(proposal.registry_version_expected)
        self._committed_certificates.append(cert)
        self._pending_proposals.pop(proposal.proposal_id, None)

        return cert

    def emergency_fail_closed_containment(
        self,
        policy_id: str,
        reason: str,
        triggering_node_id: str = "A1_HOST",
    ) -> None:
        """Immediate fail-closed local containment for safety/correctness breaches without waiting for quorum."""
        for node in self.nodes.values():
            if node.is_online and node.registry.get_policy(policy_id) is not None:
                node.registry.invalidate(
                    policy_id,
                    reason=f"EMERGENCY_FAIL_CLOSED: {reason} (triggered by {triggering_node_id})",
                )

    def reconcile_node(
        self,
        node_id: str,
        policies_by_id: Optional[Mapping[str, Policy]] = None,
    ) -> int:
        """Reconcile a disconnected or partitioned authority node via certified transition chain."""
        node = self.nodes.get(node_id)
        if node is None or not node.is_online:
            return 0

        applied_count = 0
        p_map = policies_by_id or {}

        for cert in self._committed_certificates:
            if cert.registry_version_before == node.registry.version:
                policy = p_map.get(cert.policy_id)
                node.apply_certificate(cert, policy=policy)
                applied_count += 1

        return applied_count
