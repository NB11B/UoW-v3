"""Qualification tests for Gate U15.8: Heterogeneous Adaptive Quorum Orchestration."""
from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any, Dict, List, Mapping, Sequence, Tuple
import numpy as np
import openvino as ov
import pytest

from integrations.openvino_npu import (
    EPOCH_CONFIGS,
    IntelNPUAdaptiveProposer,
    generate_epoch_workload,
)
from qualification.distributed_authority.authority import (
    AuthorityNode,
    DistributedAuthorityCluster,
    NodeMode,
)
from qualification.distributed_authority.network import NetworkFabric
from uow.compat.v2 import (
    OrchestrationState,
    PortableAdaptiveProposer,
    ProposerOrchestrationEngine,
    QuorumCommitError,
    QuorumCommitSequencer,
    ResourceBoundTask,
    WorldState,
)


def make_test_cluster(
    initial_state: WorldState,
    threshold: int = 2,
    isolated_nodes: Sequence[str] = (),
) -> Tuple[DistributedAuthorityCluster, NetworkFabric]:
    """Constructs a 3-node independent authority cluster connected via network fabric."""
    nodes = [
        AuthorityNode("authority_a", initial_state),
        AuthorityNode("authority_b", initial_state),
        AuthorityNode("authority_c", initial_state),
    ]
    fabric = NetworkFabric(("P", "authority_a", "authority_b", "authority_c"))
    for nid in ("authority_a", "authority_b", "authority_c"):
        fabric.connect("P", nid)
    fabric.connect("authority_a", "authority_b")
    fabric.connect("authority_b", "authority_c")
    fabric.connect("authority_a", "authority_c")

    for iso in isolated_nodes:
        fabric.isolate_node(iso)

    cluster = DistributedAuthorityCluster(nodes, fabric, threshold=threshold, ingress="P")
    return cluster, fabric


def test_gate_u15_8_proposer_driven_quorum_orchestration_portable():
    """Validates that a learned/adaptive proposer drives execution where all commits require 2-of-3 quorum."""
    cfg = EPOCH_CONFIGS[0]
    tasks, s0 = generate_epoch_workload(cfg)
    cluster, _ = make_test_cluster(s0, threshold=2)
    seq = QuorumCommitSequencer(cluster)

    proposer = PortableAdaptiveProposer()
    engine = ProposerOrchestrationEngine(proposer=proposer)

    out_state, final_seq, telemetry = engine.run_dag(tasks, s0, sequencer=seq)

    assert out_state.status == "HALTED"
    assert len(OrchestrationState(out_state).completed) == cfg.num_tasks
    assert seq.is_converged()

    # Verify that every step was committed via a 2-of-3 Quorum Certificate
    assert len(seq.qc_history) > 0
    for qc in seq.qc_history:
        assert len(qc.voters) >= 2
        assert len(qc.vote_hashes) >= 2
        assert qc.threshold == 2

    # Verify all 3 authority nodes reached identical cryptographic state & ledger root
    roots = {node.ledger.root_hash() for node in cluster.nodes.values()}
    states = {node.state.state_hash for node in cluster.nodes.values()}
    assert len(roots) == 1
    assert len(states) == 1
    assert cluster.verify_journal()


def test_gate_u15_8_single_node_partition_resilience():
    """Tolerates single-node partition (1 failure in 3-node cluster); remaining 2 nodes maintain quorum."""
    cfg = EPOCH_CONFIGS[0]
    tasks, s0 = generate_epoch_workload(cfg)
    # Isolate Node A
    cluster, fabric = make_test_cluster(s0, threshold=2, isolated_nodes=("authority_a",))
    seq = QuorumCommitSequencer(cluster, primary_node_id="authority_b")

    proposer = PortableAdaptiveProposer()
    engine = ProposerOrchestrationEngine(proposer=proposer)

    out_state, final_seq, telemetry = engine.run_dag(tasks, s0, sequencer=seq)

    assert out_state.status == "HALTED"
    assert len(OrchestrationState(out_state).completed) == cfg.num_tasks

    # Voters must be B and C only; Node A never voted
    for qc in seq.qc_history:
        assert "authority_a" not in qc.voters
        assert set(qc.voters) == {"authority_b", "authority_c"}

    # Node A remained untouched in initial state; B and C converged
    assert cluster.nodes["authority_a"].state.state_hash == s0.state_hash
    assert cluster.nodes["authority_a"].ledger.root_hash() == "0" * 64
    assert cluster.nodes["authority_b"].state.state_hash == cluster.nodes["authority_c"].state.state_hash
    assert cluster.nodes["authority_b"].ledger.root_hash() == cluster.nodes["authority_c"].ledger.root_hash()


def test_gate_u15_8_minority_partition_halts_safely_no_commit():
    """Minority partition (2 of 3 nodes isolated) cannot form quorum; fails closed with zero commits."""
    cfg = EPOCH_CONFIGS[0]
    tasks, s0 = generate_epoch_workload(cfg)
    # Isolate both Node B and Node C
    cluster, fabric = make_test_cluster(s0, threshold=2, isolated_nodes=("authority_b", "authority_c"))
    seq = QuorumCommitSequencer(cluster, primary_node_id="authority_a")

    proposer = PortableAdaptiveProposer()
    engine = ProposerOrchestrationEngine(proposer=proposer)

    with pytest.raises(QuorumCommitError, match="Quorum commit rejected: reason='NO_QUORUM'"):
        engine.run_dag(tasks, s0, sequencer=seq)

    # Invariant: Zero commits permitted without quorum
    assert len(seq.qc_history) == 0
    assert cluster.nodes["authority_a"].state.state_hash == s0.state_hash
    assert cluster.nodes["authority_a"].ledger.root_hash() == "0" * 64
    assert len(cluster.journal) == 0


def test_gate_u15_8_corrupt_proposer_rejected_by_all_quorum_nodes():
    """Byzantine proposal injection is rejected by the Judge/nodes and cannot obtain quorum."""
    cfg = EPOCH_CONFIGS[4]  # OCC epoch
    tasks, s0 = generate_epoch_workload(cfg)
    cluster, _ = make_test_cluster(s0, threshold=2)
    seq = QuorumCommitSequencer(cluster)

    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="CPU", model_dir=Path(tmp_dir))
        proposer.inject_corrupt_schedule = True  # Injects illegal candidate schedule

        engine = ProposerOrchestrationEngine(proposer=proposer)
        ready = OrchestrationState(s0).ready_frontier()
        bad_prop = proposer.propose(ready, tasks, s0)

        # 1. Deterministic Judge rejects
        cert = engine.certify_proposal(bad_prop, ready, tasks, s0)
        assert not cert.is_valid
        assert cert.fallback_triggered

        # 2. When run_dag executes, fallback schedule ensures safety and progress
        out_state, _, _ = engine.run_dag(tasks, s0, sequencer=seq)
        assert out_state.status == "HALTED"
        assert len(OrchestrationState(out_state).completed) == cfg.num_tasks
        assert seq.is_converged()


def test_gate_u15_8_closed_loop_adaptation_from_qc_evidence():
    """Adaptive proposer receives feedback generated from quorum commits and adapts parameters."""
    cfg = EPOCH_CONFIGS[0]
    tasks, s0 = generate_epoch_workload(cfg)
    cluster, _ = make_test_cluster(s0, threshold=2)
    seq = QuorumCommitSequencer(cluster)

    proposer = PortableAdaptiveProposer()
    engine = ProposerOrchestrationEngine(proposer=proposer)

    out_state, _, _ = engine.run_dag(tasks, s0, sequencer=seq)
    assert out_state.status == "HALTED"

    # Feedback was observed from quorum-committed steps
    assert len(proposer.observation_buffer) > 0
    initial_ident = proposer.model_identity()

    # Adaptation update produces next generation
    new_ident = proposer.update()
    assert new_ident.training_generation == initial_ident.training_generation + 1
    assert new_ident.parent_model_hash == initial_ident.identity_hash


def test_gate_u15_8_physical_npu_adaptive_proposer_under_quorum():
    """Physical Intel AI Boost NPU drives execution under 2-of-3 quorum sequencer."""
    core = ov.Core()
    if "NPU" not in core.available_devices:
        pytest.skip("Physical OpenVINO NPU device is not available on host")

    cfg = EPOCH_CONFIGS[0]
    tasks, s0 = generate_epoch_workload(cfg)
    cluster, _ = make_test_cluster(s0, threshold=2)
    seq = QuorumCommitSequencer(cluster)

    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="NPU", model_dir=Path(tmp_dir), fail_closed=True)
        engine = ProposerOrchestrationEngine(proposer=proposer)

        out_state, _, telemetry = engine.run_dag(tasks, s0, sequencer=seq)

        assert out_state.status == "HALTED"
        assert len(OrchestrationState(out_state).completed) == cfg.num_tasks
        assert seq.is_converged()

        # Physical NPU latency must be recorded while commits are authorized by quorum
        npu_lats = [
            t.proposal.predicted_metrics.get("npu_latency_us", 0.0)
            for t in telemetry
            if t.proposal and t.proposal.candidate_schedule
        ]
        assert len(npu_lats) > 0
        assert all(lat > 0 for lat in npu_lats)

        # Quorum certificates verified
        assert len(seq.qc_history) > 0
        assert all(len(qc.voters) >= 2 for qc in seq.qc_history)
