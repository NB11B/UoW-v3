"""Milestone P4 Qualification Test Suite: Distributed Policy Authority Across Physical Nodes.

Verifies the 8 core P4 distributed authority invariants and 4-tier cryptographic audit chain:
1. P4.1 - Distributed Promotion via Quorum Q(A1, A2, A3, ΔΠ) = 1
2. P4.2 - Distributed Invalidation vs Emergency Fail-Closed Containment
3. P4.3 - Registry-Version Agreement across Physical Nodes
4. P4.4 - Conflicting Proposal Rejection (N_{double_commits} = 0)
5. P4.5 - Node Loss Fault Tolerance (2-of-3 threshold vs 3-of-3 unanimity)
6. P4.6 - Partition & Certificate-Chain Reconciliation (Truth determined by cert chain)
7. P4.7 - Malformed / Unauthorized Vote Rejection
8. P4.8 - In-Flight UoW Execution Isolation During Distributed Transitions
9. P4.9 - 4-Tier Cryptographic Audit Chain Provenance Verification
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, Tuple

import pytest

from uow.policy import (
    AuthorityError,
    AuthorityRule,
    AuthorityVote,
    ConflictingProposalError,
    DecisionSource,
    DistributedAuthorityNode,
    DistributedPolicyCertificate,
    DistributedPolicyGovernor,
    ExecutionCertificate,
    GraphExecutionError,
    Policy,
    PolicyDecisionRecord,
    PolicyEvidence,
    PolicyLifecycleEvent,
    PolicyLifecycleRecord,
    PolicyRegion,
    PolicyRegistry,
    PolicyResolver,
    PolicyState,
    PolicyTransitionProposal,
    PolicyTransitionType,
    QuorumNotSatisfiedError,
    RealizationGraph,
    RealizationGraphExecutor,
    RealizationStage,
    ResourceCapability,
    StaleProposalError,
    WorkRequirement,
    WorldConditions,
)


def _canonical_meaning_for(workload_class: str = "dense_matrix", required_authority: str = "AUTHORIZED_CONTRACT_VERIFIED") -> str:
    raw = f"REQ_SEMANTICS:{workload_class}:{required_authority}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _make_dummy_graph(graph_id: str = "graph_hetero") -> RealizationGraph:
    stages = (
        RealizationStage(
            stage_id="s1_preprocess",
            capability=ResourceCapability.GENERAL_COMPUTE,
            nominal_energy_wh=0.0001,
            nominal_latency_ms=2.0,
        ),
        RealizationStage(
            stage_id="s2_compute",
            capability=ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR,
            nominal_energy_wh=0.0002,
            nominal_latency_ms=1.5,
            dependencies=("s1_preprocess",),
        ),
    )
    return RealizationGraph(
        graph_id=graph_id,
        stages=stages,
        inter_stage_transfer_energy_wh=0.00001,
        inter_stage_transfer_latency_ms=0.5,
        meaning_digest=_canonical_meaning_for(),
    )


def _make_dummy_policy(
    policy_id: str = "pol_hetero_001",
    version: int = 1,
    correctness_breaches: int = 0,
) -> Policy:
    evidence = PolicyEvidence(
        evidence_digest=f"digest_evidence_{policy_id}_v{version}",
        observations_count=10,
        expected_energy_wh=0.00031,
        energy_ci95_lower=0.00029,
        energy_ci95_upper=0.00033,
        expected_latency_ms=4.0,
        break_even_uows=5,
        correctness_breaches=correctness_breaches,
    )
    region = PolicyRegion(
        workload_class="dense_matrix",
        min_scale=16,
        max_scale=256,
        min_power_budget_w=0.0,
        max_power_budget_w=200.0,
        max_concurrency=4,
        required_capabilities=frozenset([
            ResourceCapability.GENERAL_COMPUTE,
            ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR,
        ]),
    )
    return Policy(
        policy_id=policy_id,
        policy_version=version,
        region=region,
        realization_graph=_make_dummy_graph(f"graph_{policy_id}_v{version}"),
        evidence=evidence,
        state=PolicyState.ACTIVE,
    )


def _make_world(snapshot_id: str = "snap_01", power_budget_w: float = 120.0) -> WorldConditions:
    return WorldConditions.create(
        available_capabilities=[
            ResourceCapability.GENERAL_COMPUTE,
            ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR,
            ResourceCapability.LOW_POWER_ACCELERATOR,
            ResourceCapability.DETERMINISTIC_AUTHORITY,
        ],
        power_budget_w=power_budget_w,
        max_concurrency=4,
        snapshot_id=snapshot_id,
        timestamp=1000.0,
    )


def _create_three_node_cluster() -> Tuple[DistributedPolicyGovernor, DistributedAuthorityNode, DistributedAuthorityNode, DistributedAuthorityNode]:
    node_a1 = DistributedAuthorityNode(
        authority_id="A1_HOST",
        node_id="host_x86_01",
        domain="control_plane",
    )
    node_a2 = DistributedAuthorityNode(
        authority_id="A2_ESP32",
        node_id="esp32s3_node_02",
        domain="edge_realtime",
    )
    node_a3 = DistributedAuthorityNode(
        authority_id="A3_STM32",
        node_id="stm32u5_node_03",
        domain="secure_element",
    )
    governor = DistributedPolicyGovernor(
        nodes=[node_a1, node_a2, node_a3],
        default_rule=AuthorityRule(
            rule_id="quorum_2_of_3",
            required_authorities=frozenset(["A1_HOST", "A2_ESP32", "A3_STM32"]),
            threshold=2,
        ),
    )
    return governor, node_a1, node_a2, node_a3


class TestDistributedPolicyAuthority:
    """Milestone P4 Qualification Suite."""

    def test_p4_1_distributed_promotion_quorum(self):
        """P4.1: Candidate proposal voted across physical authorities and committed upon 2-of-3 quorum."""
        governor, a1, a2, a3 = _create_three_node_cluster()
        world = _make_world("snap_01")
        policy = _make_dummy_policy("pol_fft_01", version=1)

        # 1. Propose promotion
        proposal = governor.create_proposal(
            transition_type=PolicyTransitionType.PROMOTE,
            policy_id=policy.policy_id,
            candidate_policy_version=policy.policy_version,
            world_snapshot=world,
            candidate_policy=policy,
            proposer_id="A1_HOST",
        )
        assert proposal.registry_version_expected == 1
        assert proposal.previous_registry_digest == a1.registry.compute_digest()

        # 2. Collect votes
        votes = governor.collect_votes(proposal, candidate_policy=policy)
        assert len(votes) == 3
        assert all(v.vote for v in votes)

        # 3. Certify and Commit
        cert = governor.certify_and_commit(proposal, votes, candidate_policy=policy)
        assert cert.quorum_satisfied is True
        assert cert.registry_version_before == 1
        assert cert.registry_version_after == 2
        assert len(cert.authority_votes) == 3

        # 4. Invariant: Registry version agreement across all nodes
        assert a1.registry.version == 2
        assert a2.registry.version == 2
        assert a3.registry.version == 2
        assert a1.registry.compute_digest() == a2.registry.compute_digest() == a3.registry.compute_digest() == cert.new_registry_digest

        # 5. Promoted policy is active and certified in registries
        p_a1 = a1.registry.get_policy("pol_fft_01")
        assert p_a1 is not None
        assert p_a1.is_active is True
        assert p_a1.state == PolicyState.ACTIVE

    def test_p4_2a_distributed_invalidation_quorum(self):
        """P4.2a: Performance drift requires quorum vote to invalidate."""
        governor, a1, a2, a3 = _create_three_node_cluster()
        world = _make_world("snap_01")
        policy = _make_dummy_policy("pol_gemm_01", version=1)

        # Promote initial policy
        p_prom = governor.create_proposal(
            transition_type=PolicyTransitionType.PROMOTE,
            policy_id=policy.policy_id,
            candidate_policy_version=policy.policy_version,
            world_snapshot=world,
            candidate_policy=policy,
        )
        votes_prom = governor.collect_votes(p_prom, candidate_policy=policy)
        governor.certify_and_commit(p_prom, votes_prom, candidate_policy=policy)

        assert a1.registry.version == 2

        # Now propose invalidation due to 28% energy drift
        p_inval = governor.create_proposal(
            transition_type=PolicyTransitionType.INVALIDATE,
            policy_id="pol_gemm_01",
            candidate_policy_version=policy.policy_version,
            world_snapshot=world,
            details={"drift_dimension": "energy", "drift_magnitude_pct": 28.5},
        )
        assert p_inval.registry_version_expected == 2

        votes_inval = governor.collect_votes(p_inval)
        assert len(votes_inval) == 3
        assert all(v.vote for v in votes_inval)

        cert_inval = governor.certify_and_commit(p_inval, votes_inval)
        assert cert_inval.registry_version_before == 2
        assert cert_inval.registry_version_after == 3

        # Registries agree on invalidation
        assert a1.registry.version == 3
        assert a2.registry.version == 3
        assert a3.registry.version == 3
        assert a1.registry.compute_digest() == a2.registry.compute_digest()

        # Policy is marked INVALIDATED
        p_now = a1.registry.get_policy("pol_gemm_01")
        assert p_now.is_active is False
        assert p_now.state == PolicyState.INVALIDATED

    def test_p4_2b_emergency_fail_closed_containment(self):
        """P4.2b: Emergency hard gate breach triggers immediate local containment without waiting for quorum."""
        governor, a1, a2, a3 = _create_three_node_cluster()
        world = _make_world("snap_01")
        policy = _make_dummy_policy("pol_safety_crit", version=1)

        p_prom = governor.create_proposal(
            transition_type=PolicyTransitionType.PROMOTE,
            policy_id=policy.policy_id,
            candidate_policy_version=policy.policy_version,
            world_snapshot=world,
            candidate_policy=policy,
        )
        governor.certify_and_commit(p_prom, governor.collect_votes(p_prom, candidate_policy=policy), candidate_policy=policy)
        assert a1.registry.get_policy("pol_safety_crit").is_active is True

        # Trigger emergency fail-closed containment
        governor.emergency_fail_closed_containment(
            policy_id="pol_safety_crit",
            reason="Uncertified hardware fault / correctness breach",
            triggering_node_id="A3_STM32",
        )

        # Immediate containment: active flag revoked across all reachable nodes
        assert a1.registry.get_policy("pol_safety_crit").is_active is False
        assert a2.registry.get_policy("pol_safety_crit").is_active is False
        assert a3.registry.get_policy("pol_safety_crit").is_active is False
        assert "EMERGENCY_FAIL_CLOSED" in a1.registry.lifecycle_history[-1].details.get("reason", "")

    def test_p4_3_registry_version_agreement_and_stale_rejection(self):
        """P4.3: Nodes reject proposals with stale parent registry version or mismatched digest."""
        governor, a1, a2, a3 = _create_three_node_cluster()
        world = _make_world("snap_01")
        policy1 = _make_dummy_policy("pol_v1", version=1)
        policy2 = _make_dummy_policy("pol_v2", version=1)

        # Advance to version 2
        p1 = governor.create_proposal(PolicyTransitionType.PROMOTE, "pol_v1", 1, world, candidate_policy=policy1)
        governor.certify_and_commit(p1, governor.collect_votes(p1, candidate_policy=policy1), candidate_policy=policy1)
        assert a1.registry.version == 2

        # Intentionally craft a stale proposal expecting version 1
        stale_proposal = PolicyTransitionProposal(
            proposal_id="stale_prop_01",
            transition_type=PolicyTransitionType.PROMOTE,
            policy_id="pol_v2",
            candidate_policy_version=1,
            registry_version_expected=1,  # Stale! Cluster is at 2
            previous_registry_digest=p1.previous_registry_digest,
            candidate_policy_digest=policy2.compute_digest(),
            evidence_digest=policy2.evidence.evidence_digest,
            qualification_digest="",
            world_snapshot_id="snap_01",
            proposer_id="A1_HOST",
            timestamp=time.time(),
        )

        votes = governor.collect_votes(stale_proposal, candidate_policy=policy2)
        # All online nodes reject due to version mismatch
        assert all(not v.vote for v in votes)
        assert "Stale registry version" in votes[0].reason

        # Committing stale proposal fails (double commit prevention or quorum failure)
        with pytest.raises(AuthorityError):
            governor.certify_and_commit(stale_proposal, votes, candidate_policy=policy2)

        # Mismatched parent digest fails quorum check
        bad_digest_proposal = PolicyTransitionProposal(
            proposal_id="bad_digest_prop_01",
            transition_type=PolicyTransitionType.PROMOTE,
            policy_id="pol_v2",
            candidate_policy_version=1,
            registry_version_expected=2,
            previous_registry_digest="mismatched_parent_digest_xyz",
            candidate_policy_digest=policy2.compute_digest(),
            evidence_digest=policy2.evidence.evidence_digest,
            qualification_digest="",
            world_snapshot_id="snap_01",
            proposer_id="A1_HOST",
            timestamp=time.time(),
        )
        votes_bad = governor.collect_votes(bad_digest_proposal, candidate_policy=policy2)
        assert all(not v.vote for v in votes_bad)
        assert "Registry digest mismatch" in votes_bad[0].reason
        with pytest.raises(QuorumNotSatisfiedError):
            governor.certify_and_commit(bad_digest_proposal, votes_bad, candidate_policy=policy2)

    def test_p4_4_conflicting_proposals_rejection(self):
        """P4.4: Two conflicting proposals claiming same parent version - second must fail (N_{double_commits} = 0)."""
        governor, a1, a2, a3 = _create_three_node_cluster()
        world = _make_world("snap_01")
        policy_a = _make_dummy_policy("pol_branch_a", version=1)
        policy_b = _make_dummy_policy("pol_branch_b", version=1)

        # Both proposals created against version 1
        prop_a = governor.create_proposal(PolicyTransitionType.PROMOTE, "pol_branch_a", 1, world, candidate_policy=policy_a)
        prop_b = governor.create_proposal(PolicyTransitionType.PROMOTE, "pol_branch_b", 1, world, candidate_policy=policy_b)

        assert prop_a.registry_version_expected == 1
        assert prop_b.registry_version_expected == 1

        # Commit Proposal A first
        votes_a = governor.collect_votes(prop_a, candidate_policy=policy_a)
        governor.certify_and_commit(prop_a, votes_a, candidate_policy=policy_a)
        assert a1.registry.version == 2

        # Attempting to commit Proposal B fails with ConflictingProposalError
        votes_b = [
            AuthorityVote(
                authority_id=n.authority_id,
                node_id=n.node_id,
                proposal_id=prop_b.proposal_id,
                proposal_digest=prop_b.proposal_digest,
                vote=True,
                pre_state_hash=prop_b.previous_registry_digest,
                post_state_hash="dummy",
                reason="vote",
                timestamp=time.time(),
            )
            for n in [a1, a2, a3]
        ]

        with pytest.raises(ConflictingProposalError):
            governor.certify_and_commit(prop_b, votes_b, candidate_policy=policy_b)

    def test_p4_5_node_loss_fault_tolerance(self):
        """P4.5: 2-of-3 threshold survives node failure; 3-of-3 unanimity halts safely without crashing."""
        governor, a1, a2, a3 = _create_three_node_cluster()
        world = _make_world("snap_01")
        policy = _make_dummy_policy("pol_survivor", version=1)

        # Node A2 (ESP32-S3) fails / goes offline
        a2.is_online = False

        prop = governor.create_proposal(PolicyTransitionType.PROMOTE, "pol_survivor", 1, world, candidate_policy=policy)
        votes = governor.collect_votes(prop, candidate_policy=policy)

        # Only A1 and A3 cast votes
        assert len(votes) == 2
        assert {v.authority_id for v in votes} == {"A1_HOST", "A3_STM32"}
        assert all(v.vote for v in votes)

        # Scenario 1: 2-of-3 threshold quorum succeeds
        cert = governor.certify_and_commit(prop, votes, candidate_policy=policy)
        assert cert.quorum_satisfied is True
        assert a1.registry.version == 2
        assert a3.registry.version == 2
        assert a2.registry.version == 1  # A2 is still at 1 because it was offline

        # Scenario 2: Under strict 3-of-3 unanimity rule, node loss halts transition safely
        unanimity_rule = AuthorityRule(
            rule_id="unanimity_3_of_3",
            required_authorities=frozenset(["A1_HOST", "A2_ESP32", "A3_STM32"]),
            threshold=3,
        )
        prop_halt = governor.create_proposal(PolicyTransitionType.INVALIDATE, "pol_survivor", 1, world)
        votes_halt = governor.collect_votes(prop_halt)
        assert len(votes_halt) == 2

        with pytest.raises(QuorumNotSatisfiedError):
            governor.certify_and_commit(prop_halt, votes_halt, rule=unanimity_rule)

        # Existing qualified policy execution remains intact
        assert a1.registry.get_policy("pol_survivor").is_active is True

    def test_p4_6_partition_and_certificate_chain_reconciliation(self):
        """P4.6: Isolated node catches up via certified transition chain upon reconnection (no last-writer-wins)."""
        governor, a1, a2, a3 = _create_three_node_cluster()
        world = _make_world("snap_01")
        policy_a = _make_dummy_policy("pol_part_a", version=1)
        policy_b = _make_dummy_policy("pol_part_b", version=1)

        # A3 is partitioned / offline during two transitions
        a3.is_online = False

        # Transition 1: Promote A
        p1 = governor.create_proposal(PolicyTransitionType.PROMOTE, "pol_part_a", 1, world, candidate_policy=policy_a)
        governor.certify_and_commit(p1, governor.collect_votes(p1, candidate_policy=policy_a), candidate_policy=policy_a)

        # Transition 2: Promote B
        p2 = governor.create_proposal(PolicyTransitionType.PROMOTE, "pol_part_b", 1, world, candidate_policy=policy_b)
        governor.certify_and_commit(p2, governor.collect_votes(p2, candidate_policy=policy_b), candidate_policy=policy_b)

        assert a1.registry.version == 3
        assert a2.registry.version == 3
        assert a3.registry.version == 1  # Lagging behind at 1

        # A3 reconnects
        a3.is_online = True

        # Reconcile A3 via certificate chain
        policies_catalog = {"pol_part_a": policy_a, "pol_part_b": policy_b}
        reconciled_transitions = governor.reconcile_node("A3_STM32", policies_by_id=policies_catalog)

        assert reconciled_transitions == 2
        assert a3.registry.version == 3
        # Deterministic agreement verified
        assert a3.registry.compute_digest() == a1.registry.compute_digest() == a2.registry.compute_digest()
        assert a3.registry.get_policy("pol_part_a").is_active is True
        assert a3.registry.get_policy("pol_part_b").is_active is True

    def test_p4_7_malformed_and_unauthorized_vote_rejection(self):
        """P4.7: Reject unknown authorities, tampered proposal digests, wrong hashes, duplicate votes."""
        governor, a1, a2, a3 = _create_three_node_cluster()
        world = _make_world("snap_01")
        policy = _make_dummy_policy("pol_test_sec", version=1)

        prop = governor.create_proposal(PolicyTransitionType.PROMOTE, "pol_test_sec", 1, world, candidate_policy=policy)

        # 1. Unauthorized node vote (Rogue Node)
        rogue_vote = AuthorityVote(
            authority_id="A4_ROGUE",
            node_id="rogue_node",
            proposal_id=prop.proposal_id,
            proposal_digest=prop.proposal_digest,
            vote=True,
            pre_state_hash=prop.previous_registry_digest,
            post_state_hash="dummy",
            reason="rogue",
            timestamp=time.time(),
        )

        # 2. Tampered proposal digest vote
        tampered_vote = AuthorityVote(
            authority_id="A2_ESP32",
            node_id="esp32s3_node_02",
            proposal_id=prop.proposal_id,
            proposal_digest="tampered_proposal_digest_0000",
            vote=True,
            pre_state_hash=prop.previous_registry_digest,
            post_state_hash="dummy",
            reason="tampered",
            timestamp=time.time(),
        )

        # 3. Duplicate votes from A1
        a1_vote = AuthorityVote(
            authority_id="A1_HOST",
            node_id="host_x86_01",
            proposal_id=prop.proposal_id,
            proposal_digest=prop.proposal_digest,
            vote=True,
            pre_state_hash=prop.previous_registry_digest,
            post_state_hash="dummy",
            reason="ok",
            timestamp=time.time(),
        )

        votes = [rogue_vote, tampered_vote, a1_vote, a1_vote]  # Contains duplicate and invalid

        # Only 1 legitimate vote (A1_HOST). With threshold=2, quorum must fail
        with pytest.raises(QuorumNotSatisfiedError):
            governor.certify_and_commit(prop, votes, candidate_policy=policy)

    def test_p4_8_inflight_uow_isolation_during_distributed_transition(self):
        """P4.8: In-flight executions retain their bound registry context; new work sees the committed transition."""
        governor, a1, a2, a3 = _create_three_node_cluster()
        world = _make_world("snap_01")
        executor = RealizationGraphExecutor()

        # Step 1: Promote initial policy P_v1
        policy_v1 = _make_dummy_policy("pol_stream_01", version=1)
        prop_v1 = governor.create_proposal(PolicyTransitionType.PROMOTE, "pol_stream_01", 1, world, candidate_policy=policy_v1)
        cert_v1 = governor.certify_and_commit(prop_v1, governor.collect_votes(prop_v1, candidate_policy=policy_v1), candidate_policy=policy_v1)
        assert a1.registry.version == 2

        # Step 2: In-flight workload U1 begins on A1. Resolves against registry v2.
        req1 = WorkRequirement(workload_class="dense_matrix", scale=64, uow_id="uow_inflight_01")
        resolver_node1 = PolicyResolver(a1.registry)
        resolution_u1 = resolver_node1.resolve(req1, world)

        assert resolution_u1.decision_record.decision_source == DecisionSource.QUALIFIED_POLICY
        assert resolution_u1.policy.policy_version == 1
        assert resolution_u1.decision_record.registry_version == 2

        # Step 3: Concurrent distributed transition commits invalidation of P_v1 across cluster
        prop_inval = governor.create_proposal(PolicyTransitionType.INVALIDATE, "pol_stream_01", 1, world)
        cert_inval = governor.certify_and_commit(prop_inval, governor.collect_votes(prop_inval))
        assert a1.registry.version == 3
        assert a1.registry.get_policy("pol_stream_01").is_active is False

        # Step 4: U1 completes execution using its pre-bound decision context
        exec_cert_u1 = executor.execute_graph(
            graph=resolution_u1.graph,
            requirement=req1,
            world=world,
            decision=resolution_u1.decision_record,
        )

        assert exec_cert_u1.is_certified is True
        assert exec_cert_u1.decision_id == resolution_u1.decision_record.decision_id
        # U1's certificate correctly points to registry v2 context
        assert resolution_u1.decision_record.registry_version == 2

        # Step 5: New workload U2 arrives after the transition. Resolves against registry v3.
        req2 = WorkRequirement(workload_class="dense_matrix", scale=64, uow_id="uow_subsequent_02")
        resolution_u2 = resolver_node1.resolve(req2, world)

        # Since P_v1 is now invalidated, resolution falls back to discovery
        assert resolution_u2.policy is None
        assert resolution_u2.mode == "BOUNDED_DISCOVERY"
        assert resolution_u2.decision_record.registry_version == 3

    def test_p4_9_four_tier_cryptographic_audit_chain(self):
        """P4.9: DistributedPolicyCertificate -> PolicyLifecycleRecord -> PolicyDecisionRecord -> ExecutionCertificate."""
        governor, a1, a2, a3 = _create_three_node_cluster()
        world = _make_world("snap_01")
        executor = RealizationGraphExecutor()
        policy = _make_dummy_policy("pol_audit_01", version=1)

        # Tier 1: Distributed Authority Quorum and Certificate
        prop = governor.create_proposal(PolicyTransitionType.PROMOTE, "pol_audit_01", 1, world, candidate_policy=policy)
        dist_cert = governor.certify_and_commit(prop, governor.collect_votes(prop, candidate_policy=policy), candidate_policy=policy)

        # Tier 2: Policy Lifecycle Record in Registry
        lifecycle_records = a1.registry.lifecycle_history
        assert len(lifecycle_records) == 1
        lifecycle_rec = lifecycle_records[0]

        assert lifecycle_rec.event_type == PolicyLifecycleEvent.PROMOTED
        assert lifecycle_rec.policy_id == policy.policy_id
        assert lifecycle_rec.policy_version == policy.policy_version
        # Causal Link 1: Lifecycle record binds the distributed authority certificate
        assert lifecycle_rec.authority_certificate_digest == dist_cert.certificate_digest

        # Tier 3: Policy Decision Record during UoW Resolution
        resolver = PolicyResolver(a1.registry)
        req = WorkRequirement(workload_class="dense_matrix", scale=32, uow_id="uow_chain_01")
        resolution = resolver.resolve(req, world)

        decision_rec = resolution.decision_record
        assert decision_rec.decision_source == DecisionSource.QUALIFIED_POLICY
        assert decision_rec.selected_policy_id == policy.policy_id
        # Causal Link 2: Decision record binds exact policy digest & lifecycle record
        assert decision_rec.registry_version == dist_cert.registry_version_after
        assert decision_rec.lifecycle_digest == lifecycle_rec.lifecycle_digest

        # Tier 4: Execution Certificate during Workload Dispatch
        exec_cert = executor.execute_graph(
            graph=resolution.graph,
            requirement=req,
            world=world,
            decision=decision_rec,
        )

        assert exec_cert.is_certified is True
        # Causal Link 3: Execution certificate binds policy decision record
        assert exec_cert.decision_id == decision_rec.decision_id
        assert exec_cert.decision_digest == decision_rec.decision_digest

        # Audit Chain Verification (Forward & Backward)
        # 1. Start from ExecutionCertificate:
        assert exec_cert.decision_digest == decision_rec.decision_digest
        # 2. Trace to PolicyDecisionRecord:
        assert decision_rec.selected_policy_id == lifecycle_rec.policy_id
        assert decision_rec.registry_version == lifecycle_rec.registry_version_after
        assert decision_rec.lifecycle_digest == lifecycle_rec.lifecycle_digest
        # 3. Trace to PolicyLifecycleRecord:
        assert lifecycle_rec.authority_certificate_digest == dist_cert.certificate_digest
        # 4. Trace to DistributedPolicyCertificate:
        assert dist_cert.quorum_satisfied is True
        assert len(dist_cert.authority_votes) >= 2
