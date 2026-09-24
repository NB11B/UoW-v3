r"""Milestone P5 Qualification Test Suite: Durable State, Crash Recovery, and Distributed Reconciliation.

Verifies the 6 core P5 recovery requirements, RecoveryRecord provenance, and hard zero gates:
1. P5.1 - Registry Persistence: Exact restoration on restart (\Pi_k' == \Pi_k) with identical digest.
2. P5.2 - Crash during Policy Transition: Atomic commit boundaries (never half-applied).
3. P5.3 - Authority-Node Reboot: Validates certificate chain (\Pi_k -> \Pi_{k+1} -> ... -> \Pi_n).
4. P5.4 - Whole-Host Restart during Active UoWs: Zero duplicate external effects (N_{duplicate} = 0).
5. P5.5 - Corrupted Persistence: Fails closed on any hash divergence (never guesses).
6. P5.6 - Conflicting Recovery Peers: Authority comes from valid certificate history, not integer freshness.
7. P5.7 - RecoveryRecord & 5-Tier Cryptographic Provenance Chain.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Tuple

import pytest

from uow.policy import (
    AuthorityRule,
    AuthorityVote,
    ConflictingProposalError,
    CorruptedStorageError,
    DecisionSource,
    DistributedAuthorityNode,
    DistributedPolicyCertificate,
    DistributedPolicyGovernor,
    DurablePolicyStore,
    ExecutionCertificate,
    InFlightTransaction,
    NodeRecoveryCoordinator,
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
    RealizationGraph,
    RealizationGraphExecutor,
    RealizationStage,
    RecoveryRecord,
    RecoveryResultStatus,
    ResourceCapability,
    SplitBrainRecoveryError,
    TransactionExecutionStatus,
    WorkRequirement,
    WorldConditions,
)


def _canonical_meaning_for(workload_class: str = "dense_matrix", required_authority: str = "AUTHORIZED_CONTRACT_VERIFIED") -> str:
    raw = f"REQ_SEMANTICS:{workload_class}:{required_authority}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _make_dummy_graph(graph_id: str = "graph_p5") -> RealizationGraph:
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


def _make_dummy_policy(policy_id: str = "pol_p5_01", version: int = 1) -> Policy:
    evidence = PolicyEvidence(
        evidence_digest=f"digest_evidence_{policy_id}_v{version}",
        observations_count=10,
        expected_energy_wh=0.00031,
        energy_ci95_lower=0.00029,
        energy_ci95_upper=0.00033,
        expected_latency_ms=4.0,
        break_even_uows=5,
        correctness_breaches=0,
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


def _make_world(snapshot_id: str = "snap_p5") -> WorldConditions:
    return WorldConditions.create(
        available_capabilities=[
            ResourceCapability.GENERAL_COMPUTE,
            ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR,
            ResourceCapability.LOW_POWER_ACCELERATOR,
            ResourceCapability.DETERMINISTIC_AUTHORITY,
        ],
        power_budget_w=120.0,
        max_concurrency=4,
        snapshot_id=snapshot_id,
        timestamp=1000.0,
    )


def _create_cluster(tmp_path: Path) -> Tuple[DistributedPolicyGovernor, DistributedAuthorityNode, DistributedAuthorityNode, DistributedAuthorityNode, DurablePolicyStore]:
    store = DurablePolicyStore(tmp_path / "authority_store")
    rule = AuthorityRule(
        rule_id="quorum_2_of_3",
        required_authorities=frozenset(["A1_HOST", "A2_ESP32", "A3_STM32"]),
        threshold=2,
    )
    node_a1 = DistributedAuthorityNode("A1_HOST", "host_01", "control", registry=PolicyRegistry())
    node_a2 = DistributedAuthorityNode("A2_ESP32", "esp32_02", "edge", registry=PolicyRegistry())
    node_a3 = DistributedAuthorityNode("A3_STM32", "stm32_03", "secure", registry=PolicyRegistry())

    governor = DistributedPolicyGovernor(
        nodes=[node_a1, node_a2, node_a3],
        default_rule=rule,
    )
    return governor, node_a1, node_a2, node_a3, store


class TestMilestoneP5DurableRecovery:
    """Milestone P5 Qualification Suite."""

    def test_p5_1_registry_persistence_and_exact_restart(self, tmp_path: Path):
        """P5.1: Registry serialized to disk and restored identically (Pi_k' == Pi_k) including digest."""
        store = DurablePolicyStore(tmp_path / "p5_1_store")
        registry = PolicyRegistry()
        policy1 = _make_dummy_policy("pol_fft", version=1)
        policy2 = _make_dummy_policy("pol_gemm", version=1)

        registry.register_policy(policy1)
        registry.register_policy(policy2)
        registry.invalidate("pol_fft", reason="Thermal drift")

        v_before = registry.version
        digest_before = registry.compute_digest()
        rule = AuthorityRule("rule_2of3", frozenset(["A1", "A2", "A3"]), 2)

        # 1. Persist to disk
        store.persist_registry(registry, authority_rule=rule)

        # 2. Simulate process restart: Load fresh from disk
        restored_registry, restored_rule, file_hash = store.load_registry()

        # 3. Invariants: Pi_k' == Pi_k identically
        assert restored_registry.version == v_before
        assert restored_registry.compute_digest() == digest_before
        assert restored_registry.total_policies == 2
        assert restored_registry.active_policies_count == 1
        assert restored_registry.get_policy("pol_fft").is_active is False
        assert restored_registry.get_policy("pol_gemm").is_active is True
        assert len(restored_registry.lifecycle_history) == 3
        assert restored_rule.rule_id == "rule_2of3"
        assert restored_rule.threshold == 2

    def test_p5_2_crash_during_policy_transition(self, tmp_path: Path):
        """P5.2: Crash during policy transition (WAL replay vs mid-commit); transitions are never half-applied."""
        store = DurablePolicyStore(tmp_path / "p5_2_store")
        governor, a1, a2, a3, _ = _create_cluster(tmp_path)
        world = _make_world()
        policy = _make_dummy_policy("pol_atomic", version=1)

        # Propose and form certificate
        proposal = governor.create_proposal(PolicyTransitionType.PROMOTE, "pol_atomic", 1, world, candidate_policy=policy)
        votes = governor.collect_votes(proposal, candidate_policy=policy)

        # Write-ahead log: certificate formed and recorded in journal
        cert = governor.certify_and_commit(proposal, votes, candidate_policy=policy)
        store.log_certificate(cert)

        # Initial snapshot was saved before commit (at version 1)
        snap_registry = PolicyRegistry()
        store.persist_registry(snap_registry)

        # Simulate Crash: Node restarts. Local snapshot is at version 1, but journal has certificate for v1 -> v2
        coordinator = NodeRecoveryCoordinator("host_01", "A1_HOST", store)
        policies_catalog = {"pol_atomic": policy}
        recovered_registry, recovery_record = coordinator.recover_local_state(policies_catalog=policies_catalog)

        # Invariant: WAL replay cleanly completes the transition to version 2 (never half-applied)
        assert recovery_record.recovery_result == RecoveryResultStatus.CLEAN_RECOVERY
        assert len(recovery_record.replayed_certificates) == 1
        assert cert.transition_id in recovery_record.replayed_certificates
        assert recovered_registry.version == 2
        assert recovered_registry.get_policy("pol_atomic").is_active is True
        assert recovered_registry.compute_digest() == cert.new_registry_digest

    def test_p5_3_authority_node_reboot_and_chain_reconciliation(self, tmp_path: Path):
        """P5.3: Authority node reboot lagging behind (Pi_local < Pi_committed) reconciles strictly via certificate chain."""
        store_a2 = DurablePolicyStore(tmp_path / "a2_store")
        governor, a1, a2, a3, _ = _create_cluster(tmp_path)
        world = _make_world()
        policy1 = _make_dummy_policy("pol_chain_1", version=1)
        policy2 = _make_dummy_policy("pol_chain_2", version=1)

        # A2 persists its state at version 1
        store_a2.persist_registry(a2.registry)

        # Cluster advances through two certified transitions while A2 is offline: Pi_1 -> Pi_2 -> Pi_3
        a2.is_online = False
        p1 = governor.create_proposal(PolicyTransitionType.PROMOTE, "pol_chain_1", 1, world, candidate_policy=policy1)
        cert1 = governor.certify_and_commit(p1, governor.collect_votes(p1, candidate_policy=policy1), candidate_policy=policy1)

        p2 = governor.create_proposal(PolicyTransitionType.PROMOTE, "pol_chain_2", 1, world, candidate_policy=policy2)
        cert2 = governor.certify_and_commit(p2, governor.collect_votes(p2, candidate_policy=policy2), candidate_policy=policy2)

        assert a1.registry.version == 3
        assert a3.registry.version == 3

        # A2 reboots from disk at version 1
        coordinator_a2 = NodeRecoveryCoordinator("esp32_02", "A2_ESP32", store_a2, governor.default_rule)
        reg_a2, rec_init = coordinator_a2.recover_local_state()
        assert reg_a2.version == 1

        # Reconcile A2 using candidate peer certificate chain [cert1, cert2]
        catalog = {"pol_chain_1": policy1, "pol_chain_2": policy2}
        recon_rec = coordinator_a2.reconcile_with_peer_chain(reg_a2, [cert1, cert2], policies_catalog=catalog)

        # Invariant: Certificate chain determines state (Pi_1 -> Pi_2 -> Pi_3)
        assert recon_rec.recovery_result == RecoveryResultStatus.RECONCILED_FROM_PEERS
        assert len(recon_rec.replayed_certificates) == 2
        assert reg_a2.version == 3
        assert reg_a2.compute_digest() == a1.registry.compute_digest() == a3.registry.compute_digest()
        assert reg_a2.get_policy("pol_chain_1").is_active is True
        assert reg_a2.get_policy("pol_chain_2").is_active is True

    def test_p5_4_whole_host_restart_active_uows_no_duplicate_effects(self, tmp_path: Path):
        """P5.4: Whole-host restart during active UoWs classifies transactions; zero duplicate effects (N_{dup} = 0)."""
        store = DurablePolicyStore(tmp_path / "p5_4_store")
        registry = PolicyRegistry()
        policy = _make_dummy_policy("pol_effect_safe", version=1)
        registry.register_policy(policy)
        store.persist_registry(registry)

        # Workload states prior to sudden crash:
        # U1: NOT_STARTED
        tx1 = InFlightTransaction("u1", "req_01", "snap_01", 2, "pol_effect_safe", "g1", TransactionExecutionStatus.NOT_STARTED)
        # U2: IN_FLIGHT, no external effects yet
        tx2 = InFlightTransaction("u2", "req_02", "snap_01", 2, "pol_effect_safe", "g1", TransactionExecutionStatus.IN_FLIGHT, executed_stages=("s1",), external_effect_applied=False)
        # U3: IN_FLIGHT, external effect already actuated (e.g. GPIO/stepper triggered)
        tx3 = InFlightTransaction("u3", "req_03", "snap_01", 2, "pol_effect_safe", "g1", TransactionExecutionStatus.IN_FLIGHT, executed_stages=("s1", "s2"), external_effect_applied=True)
        # U4: EXECUTED_UNCOMMITTED, external effect applied
        tx4 = InFlightTransaction("u4", "req_04", "snap_01", 2, "pol_effect_safe", "g1", TransactionExecutionStatus.EXECUTED_UNCOMMITTED, executed_stages=("s1", "s2"), external_effect_applied=True, execution_certificate_id="cert_u4")

        store.record_inflight(tx1)
        store.record_inflight(tx2)
        store.record_inflight(tx3)
        store.record_inflight(tx4)

        # Simulate Whole-Host Crash and Restart
        coordinator = NodeRecoveryCoordinator("host_01", "A1_HOST", store)
        _, recovery_rec = coordinator.recover_local_state()

        # Invariant checks:
        assert recovery_rec.inflight_transactions_found == 4
        # U1 & U2 aborted cleanly (safe to restart without side effects)
        assert recovery_rec.transactions_aborted == 2
        # U3 & U4 already triggered external effect; prevented from executing twice!
        assert recovery_rec.duplicate_effects_prevented == 2

        # Verify active inflight storage has cleaned up aborted transactions
        active_inflight = store.load_inflight_transactions()
        active_ids = {t.uow_id for t in active_inflight}
        assert "u1" not in active_ids
        assert "u2" not in active_ids
        # u3 and u4 marked COMMITTED
        assert active_inflight[0].status == TransactionExecutionStatus.COMMITTED

    def test_p5_5_corrupted_persistence_fail_closed(self, tmp_path: Path):
        """P5.5: Corrupted snapshot or checksum fails closed immediately (never guesses or repairs)."""
        store = DurablePolicyStore(tmp_path / "p5_5_store")
        registry = PolicyRegistry()
        policy = _make_dummy_policy("pol_secure", version=1)
        registry.register_policy(policy)
        store.persist_registry(registry)

        coordinator = NodeRecoveryCoordinator("host_01", "A1_HOST", store)

        # Tampering Case A: Bit flip in snapshot JSON file
        with open(store.snapshot_file, "r+", encoding="utf-8") as f:
            content = f.read()
            f.seek(0)
            f.write(content.replace("pol_secure", "pol_tampered"))
            f.truncate()

        with pytest.raises(CorruptedStorageError) as exc_info:
            coordinator.recover_local_state()

        assert "hash mismatch" in str(exc_info.value)
        assert coordinator.latest_recovery_record.recovery_result == RecoveryResultStatus.FAIL_CLOSED_CORRUPTION

    def test_p5_6_conflicting_recovery_peers_history_over_freshness(self, tmp_path: Path):
        """P5.6: Conflicting recovery peers; state is resolved by valid certificate history, not largest version number."""
        store = DurablePolicyStore(tmp_path / "p5_6_store")
        world = _make_world()
        policy_real = _make_dummy_policy("pol_real_15", version=1)

        # Host is at Pi_14
        host_registry = PolicyRegistry()
        host_registry._version = 14
        host_digest_14 = host_registry.compute_digest()
        store.persist_registry(host_registry)

        rule = AuthorityRule("quorum_2_of_3", frozenset(["A1_HOST", "A2_ESP32", "A3_STM32"]), 2)
        coordinator = NodeRecoveryCoordinator("host_01", "A1_HOST", store, rule)

        # Candidate 1: Stale peer at Pi_12 (certificate for Pi_11 -> Pi_12)
        cert_stale_12 = DistributedPolicyCertificate(
            transition_id="cert_stale_v12",
            transition_type=PolicyTransitionType.PROMOTE,
            policy_id="pol_stale",
            policy_version=1,
            registry_version_before=11,
            registry_version_after=12,
            previous_registry_digest="digest_11",
            new_registry_digest="digest_12",
            proposal_digest="prop_stale",
            qualification_digest="",
            evidence_digest="",
            authority_rule_id="quorum_2_of_3",
            authority_votes=(),
            quorum_satisfied=True,
            commit_timestamp=time.time(),
        )

        # Candidate 2: Legitimate peer advancing Pi_14 -> Pi_15
        expected_post_15 = host_registry.predict_transition_digest(
            PolicyTransitionType.PROMOTE,
            "pol_real_15",
            policy=policy_real,
        )
        prop_14 = PolicyTransitionProposal(
            proposal_id="prop_v14_to_15",
            transition_type=PolicyTransitionType.PROMOTE,
            policy_id="pol_real_15",
            candidate_policy_version=1,
            registry_version_expected=14,
            previous_registry_digest=host_digest_14,
            candidate_policy_digest=policy_real.compute_digest(),
            evidence_digest=policy_real.evidence.evidence_digest,
            qualification_digest="",
            world_snapshot_id=world.snapshot_id,
            proposer_id="A1_HOST",
            timestamp=time.time(),
        )
        votes_14 = (
            AuthorityVote("A1_HOST", "host_01", prop_14.proposal_id, prop_14.proposal_digest, True, host_digest_14, expected_post_15, "ok", time.time()),
            AuthorityVote("A2_ESP32", "esp32_02", prop_14.proposal_id, prop_14.proposal_digest, True, host_digest_14, expected_post_15, "ok", time.time()),
        )
        cert_legit_15 = DistributedPolicyCertificate(
            transition_id="cert_legit_v14_to_15",
            transition_type=PolicyTransitionType.PROMOTE,
            policy_id="pol_real_15",
            policy_version=1,
            registry_version_before=14,
            registry_version_after=15,
            previous_registry_digest=host_digest_14,
            new_registry_digest=expected_post_15,
            proposal_digest=prop_14.proposal_digest,
            qualification_digest="",
            evidence_digest=policy_real.evidence.evidence_digest,
            authority_rule_id="quorum_2_of_3",
            authority_votes=votes_14,
            quorum_satisfied=True,
            commit_timestamp=time.time(),
        )

        # Candidate 3: Unchained/forged peer claiming Pi_18 (has higher integer, but breaks chain from 15)
        cert_bogus_18 = DistributedPolicyCertificate(
            transition_id="cert_bogus_v18",
            transition_type=PolicyTransitionType.PROMOTE,
            policy_id="pol_bogus",
            policy_version=1,
            registry_version_before=17,  # Gap from 15!
            registry_version_after=18,
            previous_registry_digest="fake_digest_17",
            new_registry_digest="fake_digest_18",
            proposal_digest="fake_prop",
            qualification_digest="",
            evidence_digest="",
            authority_rule_id="quorum_2_of_3",
            authority_votes=(),
            quorum_satisfied=True,
            commit_timestamp=time.time(),
        )

        candidates = [cert_stale_12, cert_bogus_18, cert_legit_15]

        rec_record = coordinator.reconcile_with_peer_chain(
            host_registry,
            candidates,
            policies_catalog={"pol_real_15": policy_real},
        )

        # Invariants:
        # 1. Stale cert 12 skipped (<= 14)
        # 2. Bogus cert 18 rejected (gap from 15)
        # 3. Legit cert 15 replayed
        assert cert_legit_15.transition_id in rec_record.replayed_certificates
        assert cert_bogus_18.transition_id in rec_record.rejected_certificates
        # Final state is Pi_15 (determined by unbroken history, NOT the highest integer 18)
        assert host_registry.version == 15
        assert host_registry.get_policy("pol_real_15").is_active is True
        assert host_registry.get_policy("pol_bogus") is None

    def test_p5_7_split_brain_fork_detection(self, tmp_path: Path):
        """P5.7: Split-brain fork detection (two certificates claiming same parent version) fails closed."""
        store = DurablePolicyStore(tmp_path / "p5_7_store")
        governor, a1, a2, a3, _ = _create_cluster(tmp_path)
        world = _make_world()
        policy_a = _make_dummy_policy("pol_fork_a", version=1)
        policy_b = _make_dummy_policy("pol_fork_b", version=1)

        coordinator = NodeRecoveryCoordinator("host_01", "A1_HOST", store, governor.default_rule)

        # Construct two competing valid certificates branching off parent version 1
        prop_a = governor.create_proposal(PolicyTransitionType.PROMOTE, "pol_fork_a", 1, world, candidate_policy=policy_a)
        cert_a = governor.certify_and_commit(prop_a, governor.collect_votes(prop_a, candidate_policy=policy_a), candidate_policy=policy_a)

        # Peer B created conflicting cert_b claiming parent version 1
        cert_b = DistributedPolicyCertificate(
            transition_id="cert_fork_b",
            transition_type=PolicyTransitionType.PROMOTE,
            policy_id="pol_fork_b",
            policy_version=1,
            registry_version_before=1,  # Conflicting parent!
            registry_version_after=2,
            previous_registry_digest=cert_a.previous_registry_digest,
            new_registry_digest="competing_post_digest",
            proposal_digest="prop_b_digest",
            qualification_digest="",
            evidence_digest="",
            authority_rule_id="quorum_2_of_3",
            authority_votes=cert_a.authority_votes,
            quorum_satisfied=True,
            commit_timestamp=time.time(),
        )

        # When presented with forked history claiming same parent version, fails closed
        with pytest.raises(SplitBrainRecoveryError):
            coordinator.reconcile_with_peer_chain(
                PolicyRegistry(),
                [cert_a, cert_b],
                policies_catalog={"pol_fork_a": policy_a, "pol_fork_b": policy_b},
            )

        assert coordinator.latest_recovery_record.recovery_result == RecoveryResultStatus.FAIL_CLOSED_SPLIT_BRAIN

    def test_p5_8_five_tier_cryptographic_provenance_chain(self, tmp_path: Path):
        """P5.8: Full 5-tier cryptographic provenance: DistCert -> RecoveryRecord -> LifecycleRecord -> DecisionRecord -> ExecCert."""
        store = DurablePolicyStore(tmp_path / "p5_8_store")
        governor, a1, a2, a3, _ = _create_cluster(tmp_path)
        world = _make_world()
        executor = RealizationGraphExecutor()
        policy = _make_dummy_policy("pol_provenance", version=1)

        # Tier 1: Distributed Authority Quorum
        prop = governor.create_proposal(PolicyTransitionType.PROMOTE, "pol_provenance", 1, world, candidate_policy=policy)
        dist_cert = governor.certify_and_commit(prop, governor.collect_votes(prop, candidate_policy=policy), candidate_policy=policy)

        # Persist and simulate reboot
        store.persist_registry(a1.registry, authority_rule=governor.default_rule)
        coordinator = NodeRecoveryCoordinator("host_01", "A1_HOST", store, governor.default_rule)

        # Tier 2: Recovery Record on Node Startup
        recovered_reg, recovery_rec = coordinator.recover_local_state(policies_catalog={"pol_provenance": policy})
        assert recovery_rec.recovery_result == RecoveryResultStatus.CLEAN_RECOVERY
        assert recovery_rec.committed_registry_version == dist_cert.registry_version_after

        # Tier 3: Policy Lifecycle Record in Registry
        lifecycle_rec = recovered_reg.lifecycle_history[-1]
        assert lifecycle_rec.authority_certificate_digest == dist_cert.certificate_digest

        # Tier 4: Policy Decision Record during UoW Resolution
        resolver = PolicyResolver(recovered_reg)
        req = WorkRequirement(workload_class="dense_matrix", scale=32, uow_id="uow_provenance_01")
        resolution = resolver.resolve(req, world)
        decision_rec = resolution.decision_record

        assert decision_rec.decision_source == DecisionSource.QUALIFIED_POLICY
        assert decision_rec.selected_policy_id == policy.policy_id
        assert decision_rec.registry_version == recovery_rec.committed_registry_version
        assert decision_rec.lifecycle_digest == lifecycle_rec.lifecycle_digest

        # Tier 5: Execution Certificate during Workload Dispatch
        exec_cert = executor.execute_graph(
            graph=resolution.graph,
            requirement=req,
            world=world,
            decision=decision_rec,
        )

        assert exec_cert.is_certified is True
        assert exec_cert.decision_id == decision_rec.decision_id
        assert exec_cert.decision_digest == decision_rec.decision_digest

        # Verify complete forward and backward audit lineage
        assert exec_cert.decision_digest == decision_rec.decision_digest
        assert decision_rec.lifecycle_digest == lifecycle_rec.lifecycle_digest
        assert decision_rec.registry_version == recovery_rec.committed_registry_version
        assert lifecycle_rec.authority_certificate_digest == dist_cert.certificate_digest
        assert dist_cert.quorum_satisfied is True
