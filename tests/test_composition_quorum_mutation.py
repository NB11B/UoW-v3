"""Tests for Gate A2.7: Distributed Quorum-Certified Runtime Mutation.

Validates:
1. Proposer Zero Authority: Proposals cannot mutate runtime topology directly.
2. Quorum Certification: Mutations require multi-party threshold signatures (RuntimeMutationQC).
3. Cryptographic Binding: Bound to Parent Contract U, G_{t+1}, B_{t+1}, generation, and history head.
4. Physical Host Node Integration: Durable WAL fsync and crash-restart persistence of mutation entries.
5. Negative Controls NC-1 to NC-5:
   - NC-1: Proposer self-sign attempt rejected.
   - NC-2: Insufficient quorum votes rejected.
   - NC-3: Stale history head rejected.
   - NC-4: Tampered candidate payload rejected.
   - NC-5: Semantic projection violation rejected.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from uow.composition.actor import ActorDescriptor, ActorRegistry, AuthorityClass
from uow.composition.binding import ActorBinding
from uow.composition.contract import (
    AuthorityObligation,
    CausalConstraint,
    EvidenceObligation,
    FailureSemantics,
    ParentContract,
    ResourceConstraint,
    TemporalConstraint,
)
from uow.composition.convergence import AuthoritativeHistory, HistoryEntry, HistoryEntryKind
from uow.composition.graph import RealizationGraph, RealizationNode
from uow.composition.host_node import DurableWAL, PhysicalHostNode
from uow.composition.mutation import (
    AuthorityMutationVote,
    QuorumMutationCoordinator,
    RuntimeMutationProposal,
    RuntimeMutationQC,
    assemble_mutation_qc,
    sign_mutation_vote,
    verify_mutation_qc,
    verify_mutation_vote,
)


@pytest.fixture
def parent_contract() -> ParentContract:
    return ParentContract(
        contract_id="contract_uow_a27_canonical",
        description="A2.7 Canonical Parent Contract",
        required_outputs=("certified_result_R",),
        causal_constraints=(
            CausalConstraint("parser", "worker"),
            CausalConstraint("worker", "verifier"),
            CausalConstraint("verifier", "commit"),
        ),
        authority=AuthorityObligation(
            required_role="verifier",
            min_evidence_level="portable",
            quorum_threshold=1,
        ),
        evidence=EvidenceObligation(
            require_provenance=True,
            require_hash_chain=True,
            min_evidence_level="portable",
            verifier_id="deterministic-judge",
        ),
        temporal=TemporalConstraint(max_duration_ms=1000.0),
        resources=ResourceConstraint(
            max_cpu_cores=8,
            max_ram_units=16,
            max_gpu_slots=2,
            max_npu_slots=2,
            max_cost_units=100.0,
        ),
        failure_semantics=FailureSemantics.ROLLBACK,
    )


@pytest.fixture
def baseline_graph() -> RealizationGraph:
    nodes = {
        "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
        "n_work": RealizationNode("n_work", role="worker", actor_class="cpu", duration_ms=80.0),
        "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
        "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
    }
    edges = (
        ("n_parse", "n_work"),
        ("n_work", "n_verify"),
        ("n_verify", "n_commit"),
    )
    return RealizationGraph("G0_baseline", nodes, edges)


@pytest.fixture
def candidate_graph() -> RealizationGraph:
    nodes = {
        "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
        "n_npu_work": RealizationNode("n_npu_work", role="worker", actor_class="npu", npu_slots=1, duration_ms=15.0),
        "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
        "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
    }
    edges = (
        ("n_parse", "n_npu_work"),
        ("n_npu_work", "n_verify"),
        ("n_verify", "n_commit"),
    )
    return RealizationGraph("G1_accelerated", nodes, edges)


@pytest.fixture
def invalid_candidate_graph() -> RealizationGraph:
    """Missing required output 'certified_result_R' required by parent contract."""
    nodes = {
        "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
        "n_work": RealizationNode("n_work", role="worker", actor_class="cpu", duration_ms=80.0),
        "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
        "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("wrong_output",), duration_ms=10.0),
    }
    edges = (
        ("n_parse", "n_work"),
        ("n_work", "n_verify"),
        ("n_verify", "n_commit"),
    )
    return RealizationGraph("G_invalid_outputs", nodes, edges)


@pytest.fixture
def actor_registry() -> ActorRegistry:
    registry = ActorRegistry()
    registry.register(ActorDescriptor(
        actor_id="actor_cpu",
        substrate="host_cpu",
        capabilities=("cpu", "role:parser", "role:worker", "role:verifier", "role:commit"),
        authority_class=AuthorityClass.VERIFIER,
    ))
    registry.register(ActorDescriptor(
        actor_id="actor_npu",
        substrate="intel_npu",
        capabilities=("npu", "role:worker", "npu_inference", "accelerator"),
        authority_class=AuthorityClass.PROPOSER_ONLY,
    ))
    return registry


@pytest.fixture
def baseline_binding() -> ActorBinding:
    return ActorBinding(
        binding_id="bind_cpu_baseline",
        graph_id="G0_baseline",
        node_to_actor={
            "n_parse": "actor_cpu",
            "n_work": "actor_cpu",
            "n_verify": "actor_cpu",
            "n_commit": "actor_cpu",
        },
    )


@pytest.fixture
def candidate_binding() -> ActorBinding:
    return ActorBinding(
        binding_id="bind_npu_optimized",
        graph_id="G1_accelerated",
        node_to_actor={
            "n_parse": "actor_cpu",
            "n_npu_work": "actor_npu",
            "n_verify": "actor_cpu",
            "n_commit": "actor_cpu",
        },
    )


@pytest.fixture
def authority_cluster_keys() -> dict[str, str]:
    return {
        "auth_node_esp32": "secret_key_esp32_hw",
        "auth_node_stm32": "secret_key_stm32_hw",
        "auth_node_cpu": "secret_key_laptop_cpu",
    }


def test_proposer_zero_authority(
    parent_contract: ParentContract,
    baseline_graph: RealizationGraph,
    candidate_graph: RealizationGraph,
    baseline_binding: ActorBinding,
    candidate_binding: ActorBinding,
    authority_cluster_keys: dict[str, str],
) -> None:
    history = AuthoritativeHistory()
    coordinator = QuorumMutationCoordinator(
        parent_contract=parent_contract,
        active_graph=baseline_graph,
        active_binding=baseline_binding,
        history=history,
        authority_keys=authority_cluster_keys,
        generation=0,
    )

    # Proposer produces a proposal
    proposal = coordinator.propose_mutation(
        proposer_id="npu_adaptive_proposer",
        candidate_graph=candidate_graph,
        candidate_binding=candidate_binding,
        strategy="accelerator_offload",
    )

    # Proposal has 0 authority: active graph is still baseline
    assert coordinator.active_graph.graph_id == "G0_baseline"
    assert coordinator.active_binding.binding_id == "bind_cpu_baseline"
    assert coordinator.generation == 0
    assert len(coordinator.history.entries) == 0


def test_authority_voting_and_signatures(
    parent_contract: ParentContract,
    baseline_graph: RealizationGraph,
    candidate_graph: RealizationGraph,
    baseline_binding: ActorBinding,
    candidate_binding: ActorBinding,
    authority_cluster_keys: dict[str, str],
    actor_registry: ActorRegistry,
) -> None:
    history = AuthoritativeHistory()
    coordinator = QuorumMutationCoordinator(
        parent_contract=parent_contract,
        active_graph=baseline_graph,
        active_binding=baseline_binding,
        history=history,
        authority_keys=authority_cluster_keys,
        actor_registry=actor_registry,
        generation=0,
    )

    proposal = coordinator.propose_mutation(
        proposer_id="npu_proposer",
        candidate_graph=candidate_graph,
        candidate_binding=candidate_binding,
    )

    votes = coordinator.collect_votes(proposal)
    assert len(votes) == 3
    for v in votes:
        assert v.accepted is True
        assert v.conformance_verified is True
        assert v.signature != ""
        # Verify vote signature
        valid, msg = verify_mutation_vote(v, authority_cluster_keys[v.voter_id])
        assert valid is True
        assert msg == "VALID_VOTE"

        # Tampered signature fails
        bad_valid, bad_msg = verify_mutation_vote(v, "wrong_secret_key")
        assert bad_valid is False
        assert bad_msg == "INVALID_VOTE_SIGNATURE"


def test_qc_assembly_and_threshold(
    parent_contract: ParentContract,
    baseline_graph: RealizationGraph,
    candidate_graph: RealizationGraph,
    baseline_binding: ActorBinding,
    candidate_binding: ActorBinding,
    authority_cluster_keys: dict[str, str],
) -> None:
    history = AuthoritativeHistory()
    coordinator = QuorumMutationCoordinator(
        parent_contract=parent_contract,
        active_graph=baseline_graph,
        active_binding=baseline_binding,
        history=history,
        authority_keys=authority_cluster_keys,
        generation=0,
    )

    proposal = coordinator.propose_mutation(
        proposer_id="npu_proposer",
        candidate_graph=candidate_graph,
        candidate_binding=candidate_binding,
    )
    votes = coordinator.collect_votes(proposal)

    # 1. 2-of-3 votes -> Valid QC
    qc_2of3, msg = assemble_mutation_qc(proposal, votes[:2], threshold=2)
    assert qc_2of3 is not None
    assert len(qc_2of3.signers) == 2
    assert msg == "QUORUM_CERTIFICATE_ASSEMBLED"

    # 2. 1-of-3 votes when threshold=2 -> Fails threshold
    qc_1of3, err_msg = assemble_mutation_qc(proposal, votes[:1], threshold=2)
    assert qc_1of3 is None
    assert "QUORUM_THRESHOLD_NOT_MET" in err_msg


def test_live_atomic_mutation_success(
    parent_contract: ParentContract,
    baseline_graph: RealizationGraph,
    candidate_graph: RealizationGraph,
    baseline_binding: ActorBinding,
    candidate_binding: ActorBinding,
    authority_cluster_keys: dict[str, str],
) -> None:
    history = AuthoritativeHistory()
    coordinator = QuorumMutationCoordinator(
        parent_contract=parent_contract,
        active_graph=baseline_graph,
        active_binding=baseline_binding,
        history=history,
        authority_keys=authority_cluster_keys,
        generation=0,
        quorum_threshold=2,
    )

    proposal = coordinator.propose_mutation(
        proposer_id="npu_proposer",
        candidate_graph=candidate_graph,
        candidate_binding=candidate_binding,
    )
    votes = coordinator.collect_votes(proposal)
    qc, _ = assemble_mutation_qc(proposal, votes, threshold=2)
    assert qc is not None

    # Apply mutation atomically
    ok, status = coordinator.apply_mutation(qc, candidate_graph, candidate_binding)
    assert ok is True
    assert status == "MUTATION_COMMITTED"

    # State updated
    assert coordinator.active_graph.graph_id == "G1_accelerated"
    assert coordinator.active_binding.binding_id == "bind_npu_optimized"
    assert coordinator.generation == 1
    assert len(coordinator.history.entries) == 1
    assert coordinator.history.entries[0].kind == HistoryEntryKind.GRAPH_SUBSTITUTION
    assert coordinator.history.verify_integrity() is True


def test_physical_host_node_mutation_qc(
    parent_contract: ParentContract,
    baseline_graph: RealizationGraph,
    candidate_graph: RealizationGraph,
    baseline_binding: ActorBinding,
    candidate_binding: ActorBinding,
    authority_cluster_keys: dict[str, str],
) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        node = PhysicalHostNode(
            node_id="host_node_1",
            working_dir=Path(tmpdir),
            secret_key="host_node_wire_secret",
            generation=0,
            active_graph=baseline_graph,
            active_binding=baseline_binding,
        )
        node.startup()

        coordinator = QuorumMutationCoordinator(
            parent_contract=parent_contract,
            active_graph=baseline_graph,
            active_binding=baseline_binding,
            history=node.history,
            authority_keys=authority_cluster_keys,
            wal=node.wal,
            generation=0,
            quorum_threshold=2,
        )

        proposal = coordinator.propose_mutation(
            proposer_id="npu_proposer",
            candidate_graph=candidate_graph,
            candidate_binding=candidate_binding,
        )
        votes = coordinator.collect_votes(proposal)
        qc, _ = assemble_mutation_qc(proposal, votes, threshold=2)
        assert qc is not None

        # Apply through host node
        ok, msg = node.apply_mutation_qc(
            qc=qc,
            candidate_graph=candidate_graph,
            candidate_binding=candidate_binding,
            parent_contract=parent_contract,
            authority_keys=authority_cluster_keys,
            threshold=2,
        )
        assert ok is True
        assert msg == "MUTATION_COMMITTED"
        assert node.generation == 1
        assert node.active_graph.graph_id == "G1_accelerated"

        # Crash node and reboot from durable WAL
        node.crash()
        assert not node.is_alive
        replayed = node.restart()
        assert replayed == 1
        assert node.history.tip_sequence() == 0
        assert node.history.entries[0].kind == HistoryEntryKind.GRAPH_SUBSTITUTION
        assert node.history.verify_integrity() is True


# =========================================================================
# Adversarial Negative Controls NC-1 to NC-5
# =========================================================================

def test_nc1_proposer_self_sign_rejection(
    parent_contract: ParentContract,
    baseline_graph: RealizationGraph,
    candidate_graph: RealizationGraph,
    baseline_binding: ActorBinding,
    candidate_binding: ActorBinding,
    authority_cluster_keys: dict[str, str],
) -> None:
    """NC-1: Proposer attempts to sign its own mutation QC without authority node keys."""
    history = AuthoritativeHistory()
    coordinator = QuorumMutationCoordinator(
        parent_contract=parent_contract,
        active_graph=baseline_graph,
        active_binding=baseline_binding,
        history=history,
        authority_keys=authority_cluster_keys,
        generation=0,
    )

    proposal = coordinator.propose_mutation(
        proposer_id="unauthorized_proposer",
        candidate_graph=candidate_graph,
        candidate_binding=candidate_binding,
    )

    # Proposer crafts fake votes signed with unauthorized keys
    fake_vote_1 = AuthorityMutationVote(
        vote_id="vote_fake_proposer_1",
        voter_id="unauthorized_proposer_1",
        proposal_id=proposal.proposal_id,
        proposal_hash=proposal.compute_hash(),
        parent_contract_hash=proposal.parent_contract_hash,
        candidate_graph_hash=candidate_graph.compute_hash(),
        candidate_binding_hash=candidate_binding.compute_hash(),
        generation=0,
        history_head=history.tip_hash(),
        conformance_verified=True,
        accepted=True,
        signature="fake_sig_12345",
    )
    fake_vote_2 = AuthorityMutationVote(
        vote_id="vote_fake_proposer_2",
        voter_id="unauthorized_proposer_2",
        proposal_id=proposal.proposal_id,
        proposal_hash=proposal.compute_hash(),
        parent_contract_hash=proposal.parent_contract_hash,
        candidate_graph_hash=candidate_graph.compute_hash(),
        candidate_binding_hash=candidate_binding.compute_hash(),
        generation=0,
        history_head=history.tip_hash(),
        conformance_verified=True,
        accepted=True,
        signature="fake_sig_67890",
    )

    fake_qc, msg = assemble_mutation_qc(proposal, [fake_vote_1, fake_vote_2], threshold=2)
    assert fake_qc is not None

    ok, reason = coordinator.apply_mutation(fake_qc, candidate_graph, candidate_binding)
    assert ok is False
    assert "UNKNOWN_AUTHORITY_VOTER" in reason


def test_nc2_insufficient_quorum_rejection(
    parent_contract: ParentContract,
    baseline_graph: RealizationGraph,
    candidate_graph: RealizationGraph,
    baseline_binding: ActorBinding,
    candidate_binding: ActorBinding,
    authority_cluster_keys: dict[str, str],
) -> None:
    """NC-2: Mutation attempted with fewer votes than the required threshold (1 < 2)."""
    history = AuthoritativeHistory()
    coordinator = QuorumMutationCoordinator(
        parent_contract=parent_contract,
        active_graph=baseline_graph,
        active_binding=baseline_binding,
        history=history,
        authority_keys=authority_cluster_keys,
        generation=0,
        quorum_threshold=2,
    )

    proposal = coordinator.propose_mutation(
        proposer_id="npu_proposer",
        candidate_graph=candidate_graph,
        candidate_binding=candidate_binding,
    )
    votes = coordinator.collect_votes(proposal)

    # Assemble QC with threshold=1, but coordinator requires threshold=2
    qc_1vote, _ = assemble_mutation_qc(proposal, votes[:1], threshold=1)
    assert qc_1vote is not None

    ok, reason = coordinator.apply_mutation(qc_1vote, candidate_graph, candidate_binding)
    assert ok is False
    assert "QUORUM_THRESHOLD_NOT_MET" in reason


def test_nc3_stale_history_head_rejection(
    parent_contract: ParentContract,
    baseline_graph: RealizationGraph,
    candidate_graph: RealizationGraph,
    baseline_binding: ActorBinding,
    candidate_binding: ActorBinding,
    authority_cluster_keys: dict[str, str],
) -> None:
    """NC-3: Proposal or QC constructed against history head H_0 after history advanced to H_1."""
    history = AuthoritativeHistory()
    coordinator = QuorumMutationCoordinator(
        parent_contract=parent_contract,
        active_graph=baseline_graph,
        active_binding=baseline_binding,
        history=history,
        authority_keys=authority_cluster_keys,
        generation=0,
        quorum_threshold=2,
    )

    proposal = coordinator.propose_mutation(
        proposer_id="npu_proposer",
        candidate_graph=candidate_graph,
        candidate_binding=candidate_binding,
    )
    votes = coordinator.collect_votes(proposal)
    qc, _ = assemble_mutation_qc(proposal, votes, threshold=2)
    assert qc is not None

    # Concurrently advance history with another entry
    dummy_entry = HistoryEntry(
        entry_id="concurrent_task_commit",
        sequence_number=0,
        prev_hash=history.tip_hash(),
        kind=HistoryEntryKind.IDEMPOTENT_TASK,
        author_node_id="concurrent_node",
        generation=0,
        payload={"task": "concurrent_work"},
    )
    appended, _ = history.append(dummy_entry)
    assert appended is True

    # Now applying QC that was constructed against genesis tip_hash must fail
    ok, reason = coordinator.apply_mutation(qc, candidate_graph, candidate_binding)
    assert ok is False
    assert "STALE_HISTORY_HEAD" in reason


def test_nc4_tampered_candidate_payload_rejection(
    parent_contract: ParentContract,
    baseline_graph: RealizationGraph,
    candidate_graph: RealizationGraph,
    baseline_binding: ActorBinding,
    candidate_binding: ActorBinding,
    authority_cluster_keys: dict[str, str],
) -> None:
    """NC-4: Graph or binding modified after QC was issued."""
    history = AuthoritativeHistory()
    coordinator = QuorumMutationCoordinator(
        parent_contract=parent_contract,
        active_graph=baseline_graph,
        active_binding=baseline_binding,
        history=history,
        authority_keys=authority_cluster_keys,
        generation=0,
        quorum_threshold=2,
    )

    proposal = coordinator.propose_mutation(
        proposer_id="npu_proposer",
        candidate_graph=candidate_graph,
        candidate_binding=candidate_binding,
    )
    votes = coordinator.collect_votes(proposal)
    qc, _ = assemble_mutation_qc(proposal, votes, threshold=2)
    assert qc is not None

    # Tampered candidate graph with different ID
    tampered_graph = RealizationGraph(
        graph_id="G_tampered",
        nodes=candidate_graph.nodes,
        edges=candidate_graph.edges,
    )

    ok, reason = coordinator.apply_mutation(qc, tampered_graph, candidate_binding)
    assert ok is False
    assert "CANDIDATE_GRAPH_HASH_MISMATCH" in reason


def test_nc5_semantic_projection_violation_rejection(
    parent_contract: ParentContract,
    baseline_graph: RealizationGraph,
    invalid_candidate_graph: RealizationGraph,
    baseline_binding: ActorBinding,
    candidate_binding: ActorBinding,
    authority_cluster_keys: dict[str, str],
) -> None:
    """NC-5: Candidate graph violates parent contract semantics -> Authority nodes reject."""
    history = AuthoritativeHistory()
    coordinator = QuorumMutationCoordinator(
        parent_contract=parent_contract,
        active_graph=baseline_graph,
        active_binding=baseline_binding,
        history=history,
        authority_keys=authority_cluster_keys,
        generation=0,
    )

    proposal = coordinator.propose_mutation(
        proposer_id="npu_proposer",
        candidate_graph=invalid_candidate_graph,
        candidate_binding=candidate_binding,
    )

    votes = coordinator.collect_votes(proposal)
    for v in votes:
        assert v.accepted is False
        assert v.conformance_verified is False
        assert "SEMANTIC_PROJECTION_MISMATCH" in (v.rejection_reason or "")

    qc, reason = assemble_mutation_qc(proposal, votes, threshold=2)
    assert qc is None
    assert "QUORUM_THRESHOLD_NOT_MET" in reason
