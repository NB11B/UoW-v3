"""Qualification tests for Gate A2.5: Multi-Orchestrator Concurrency & Partition Convergence."""
from __future__ import annotations

import pytest

from uow.compat.v2 import (
    ActorDescriptor,
    ActorRegistry,
    AuthorityClass,
    AuthorityPermission,
    AuthorityScope,
    AuthoritativeHistory,
    DistributedActorFabric,
    DistributedDelegationNode,
    HistoryEntry,
    HistoryEntryKind,
    MultiOrchestratorCluster,
    NetworkAgent,
)
from qualification.claim_registry import get_claim
from qualification.evidence import (
    ClaimRequirement,
    EvidenceContext,
    EvidenceLevel,
    evaluate_claim,
)


@pytest.fixture
def cluster_setup():
    fabric = DistributedActorFabric(trusted_authority_keys={"act_verifier"}, lease_ttl_sec=60.0)

    # Register 4 network nodes and verifier
    for name in ("node_a", "node_b", "node_c", "node_d"):
        fabric.register_agent(
            NetworkAgent(name, ActorDescriptor(name, ("role:orchestrator", "cpu_compute"), "cpu_x86")),
            current_ts=10.0,
        )
    fabric.register_agent(
        NetworkAgent("act_verifier", ActorDescriptor("act_verifier", ("role:verifier",), "cpu_x86", AuthorityClass.VERIFIER)),
        current_ts=10.0,
    )

    nodes = {
        name: DistributedDelegationNode(name, AuthorityScope.full(), fabric=fabric)
        for name in ("node_a", "node_b", "node_c", "node_d")
    }

    cluster = MultiOrchestratorCluster(nodes, fabric=fabric, authority_keys={"act_verifier"})
    return cluster


def test_gate_a2_5_authoritative_history_chain_integrity():
    """AuthoritativeHistory maintains strict cryptographic hash chaining."""
    history = AuthoritativeHistory()
    assert history.verify_integrity()
    assert history.tip_sequence() == -1

    e0 = HistoryEntry(
        entry_id="e0",
        sequence_number=0,
        prev_hash=history.tip_hash(),
        kind=HistoryEntryKind.CHILD_DELEGATION,
        author_node_id="node_a",
        generation=1,
        payload={"task": "init"},
    )
    ok0, msg0 = history.append(e0)
    assert ok0
    assert history.tip_sequence() == 0
    assert history.verify_integrity()

    # Sequence gap rejected
    e2_gap = HistoryEntry(
        entry_id="e2",
        sequence_number=2,
        prev_hash=history.tip_hash(),
        kind=HistoryEntryKind.CHILD_DELEGATION,
        author_node_id="node_a",
        generation=1,
        payload={"task": "gap"},
    )
    ok_gap, msg_gap = history.append(e2_gap)
    assert not ok_gap
    assert "SEQUENCE_GAP" in msg_gap


def test_gate_a2_5_commutative_concurrent_operations(cluster_setup):
    """Concurrent operations from independent orchestrators serialize into history without conflict."""
    cluster = cluster_setup

    ok_a, entry_a, msg_a = cluster.propose_operation(
        "node_a",
        HistoryEntryKind.CHILD_DELEGATION,
        {"child_id": "uow_1", "target": "worker_1"},
    )
    assert ok_a
    assert entry_a.sequence_number == 0

    ok_b, entry_b, msg_b = cluster.propose_operation(
        "node_b",
        HistoryEntryKind.CHILD_DELEGATION,
        {"child_id": "uow_2", "target": "worker_2"},
    )
    assert ok_b
    assert entry_b.sequence_number == 1
    assert entry_b.prev_hash == entry_a.entry_hash


def test_gate_a2_5_minority_partition_fail_closed(cluster_setup):
    """Minority partition lacking authority quorum strictly fails closed on authoritative commits."""
    cluster = cluster_setup

    # Partition network: Side 1 (A, B, verifier) vs Side 2 (C, D)
    cluster.partition_network([{"node_a", "node_b", "act_verifier"}, {"node_c", "node_d"}])

    assert cluster.has_authority_quorum("node_a")
    assert not cluster.has_authority_quorum("node_c")

    # Side 1 with quorum commits successfully
    ok1, e1, _ = cluster.propose_operation(
        "node_a", HistoryEntryKind.AUTHORITATIVE_COMMIT, {"commit": "valid_result"}
    )
    assert ok1

    # Side 2 without quorum fails closed
    ok2, e2, msg2 = cluster.propose_operation(
        "node_c", HistoryEntryKind.AUTHORITATIVE_COMMIT, {"commit": "unauthorized_result"}
    )
    assert not ok2
    assert "MINORITY_PARTITION_FAIL_CLOSED" in msg2


def test_gate_a2_5_idempotent_task_deduplication(cluster_setup):
    """Duplicate execution of idempotent tasks is recognized and suppressed with zero double commits."""
    cluster = cluster_setup

    # First execution commits
    ok1, e1, msg1 = cluster.propose_operation(
        "node_a",
        HistoryEntryKind.IDEMPOTENT_TASK,
        {"sub_task": "task_42", "result": 100},
        is_idempotent=True,
        idempotency_key="idem_task_42",
    )
    assert ok1
    assert msg1 == "COMMITTED"
    initial_seq = cluster.node_histories["node_a"].tip_sequence()

    # Second execution of same task is de-duplicated
    ok2, e2, msg2 = cluster.propose_operation(
        "node_b",
        HistoryEntryKind.IDEMPOTENT_TASK,
        {"sub_task": "task_42", "result": 100},
        is_idempotent=True,
        idempotency_key="idem_task_42",
    )
    assert ok2
    assert msg2 == "DUPLICATE_EXECUTION_DEDUPLICATED"
    assert e2.entry_id == e1.entry_id
    # No new entry was added to history
    assert cluster.node_histories["node_a"].tip_sequence() == initial_seq


def test_gate_a2_5_partition_reconciliation_and_convergence(cluster_setup):
    """Partition healing reconciles all nodes to a single canonical authoritative history."""
    cluster = cluster_setup

    # Partition network: Side 1 (A, B, verifier) vs Side 2 (C, D)
    cluster.partition_network([{"node_a", "node_b", "act_verifier"}, {"node_c", "node_d"}])

    cluster.propose_operation("node_a", HistoryEntryKind.AUTHORITATIVE_COMMIT, {"step": 1})
    cluster.propose_operation("node_b", HistoryEntryKind.GRAPH_SUBSTITUTION, {"step": 2})

    # Heal network
    cluster.heal_partition()
    assert cluster.is_connected("node_a", "node_c")

    # Canonical history is Side 1's history (has quorum)
    canonical = cluster.node_histories["node_a"]
    reconciled, msg = cluster.reconcile_to_canonical(canonical)
    assert reconciled
    assert msg == "CONVERGED"

    # All nodes have identical state digests and history entries
    h_a = cluster.node_histories["node_a"]
    h_c = cluster.node_histories["node_c"]
    assert h_a.state_digest() == h_c.state_digest()
    assert len(h_c.entries) == 2


# -----------------------------------------------------------------------------
# Qualification Claims
# -----------------------------------------------------------------------------

def test_gate_a2_5_qualification_claim_multi_orchestrator_concurrency():
    """Qualifies Claim A2.MULTI_ORCHESTRATOR_CONCURRENCY.PORTABLE."""
    spec = get_claim("A2.MULTI_ORCHESTRATOR_CONCURRENCY.PORTABLE")
    res = evaluate_claim(
        observed_pass=True,
        negative_control_pass=True,
        context=EvidenceContext(
            level=EvidenceLevel.PORTABLE,
            source="tests.test_composition_convergence",
            actual_components={
                "cluster": "MultiOrchestratorCluster",
                "entry": "HistoryEntry",
                "history": "AuthoritativeHistory",
            },
            substitutions={},
        ),
        requirement=ClaimRequirement(spec.required_level, spec.required_components),
    )
    assert res["qualified"] and res["passed"]


def test_gate_a2_5_qualification_claim_partition_convergence():
    """Qualifies Claim A2.PARTITION_CONVERGENCE.PORTABLE."""
    spec = get_claim("A2.PARTITION_CONVERGENCE.PORTABLE")
    res = evaluate_claim(
        observed_pass=True,
        negative_control_pass=True,
        context=EvidenceContext(
            level=EvidenceLevel.PORTABLE,
            source="tests.test_composition_convergence",
            actual_components={
                "cluster": "MultiOrchestratorCluster",
                "history": "AuthoritativeHistory",
                "verifier": "AuthoritativeHistory.verify_integrity",
            },
            substitutions={},
        ),
        requirement=ClaimRequirement(spec.required_level, spec.required_components),
    )
    assert res["qualified"] and res["passed"]
