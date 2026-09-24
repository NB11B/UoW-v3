from __future__ import annotations

from uow import Guard, GuardOp, Mutation, MutationOp, Route, Successor, WorldState, make_uow
from uow.engine import propose

from uow_shadow.distributed_authority_reconstruction import (
    ShadowAuthorityReplica,
    ShadowDistributedAuthorityCluster,
    ShadowNetworkFabric,
    ShadowNodeMode,
    form_quorum_certificate,
    make_shadow_authority_cluster,
)


def _initial():
    return WorldState(
        attributes={"counter": 0},
        cursor="dist.increment",
        status="RUNNING",
        sequence=0,
    )


def _inc(identity="dist.increment", amount=1):
    return make_uow(
        identity,
        [
            Route(
                Guard(GuardOp.ALWAYS),
                (Mutation(MutationOp.ADD, "counter", amount),),
                Successor.preserve(),
            )
        ],
    )


def test_r4_distributed_authority_replicas_are_independent_and_clock_observational():
    cluster = make_shadow_authority_cluster(_initial())
    assert len({id(n.state) for n in cluster.nodes.values()}) == 3
    assert len({id(n.ledger) for n in cluster.nodes.values()}) == 3

    uow = _inc()
    proposal = propose(uow, cluster.nodes["A"].state)
    votes = cluster.collect_votes(uow, proposal)

    assert len(votes) == 3
    assert all(v.accepted for v in votes)
    assert len({v.certificate_hash for v in votes}) == 1
    assert len({v.local_clock for v in votes}) > 1


def test_r4_distributed_authority_two_of_three_qc_converges_via_shadow_authority():
    cluster = make_shadow_authority_cluster(_initial())
    uow = _inc()
    proposal = propose(uow, cluster.nodes["A"].state)

    committed, qc, votes, results = cluster.submit(uow, proposal)

    assert committed
    assert qc is not None
    assert len(qc.voters) >= 2
    assert all(v.accepted for v in votes)
    assert all(r.applied for r in results.values())
    assert len({n.state.state_hash for n in cluster.nodes.values()}) == 1
    assert len({n.ledger.root_hash() for n in cluster.nodes.values()}) == 1
    assert cluster.nodes["A"].state.get("counter") == 1


def test_r4_distributed_authority_single_reachable_node_cannot_commit():
    cluster = make_shadow_authority_cluster(_initial())
    uow = _inc()
    initial_hash = cluster.nodes["A"].state.state_hash
    cluster.network.isolate_node("B")
    cluster.network.isolate_node("C")

    committed, qc, votes, results = cluster.submit(
        uow,
        propose(uow, cluster.nodes["A"].state),
    )

    assert not committed
    assert qc is None
    assert len(votes) == 1
    assert results == {}
    assert all(n.state.state_hash == initial_hash for n in cluster.nodes.values())


def test_r4_distributed_authority_isolated_replica_catches_up_from_verified_journal():
    cluster = make_shadow_authority_cluster(_initial())
    uow = _inc()
    cluster.network.isolate_node("C")

    committed, qc, _, _ = cluster.submit(
        uow,
        propose(uow, cluster.nodes["A"].state),
    )
    assert committed and qc is not None
    assert cluster.nodes["C"].state.state_hash != qc.committed_state_hash

    cluster.network.restore_link("A", "C")
    cluster.network.restore_link("B", "C")
    ok, reason = cluster.catch_up("C")

    assert ok, reason
    assert cluster.nodes["C"].state.state_hash == qc.committed_state_hash
    assert cluster.nodes["C"].ledger.root_hash() == qc.expected_evidence_root


def test_r4_distributed_authority_divergent_replica_is_quarantined_not_overwritten():
    cluster = make_shadow_authority_cluster(_initial())
    uow = _inc()
    committed, qc, _, _ = cluster.submit(
        uow,
        propose(uow, cluster.nodes["A"].state),
    )
    assert committed and qc is not None

    cluster.nodes["C"].state = cluster.nodes["C"].state.with_attribute("counter", 999999)
    divergent_hash = cluster.nodes["C"].state.state_hash

    ok, reason = cluster.catch_up("C")

    assert not ok
    assert reason == "QUARANTINED_DIVERGENCE"
    assert cluster.nodes["C"].mode is ShadowNodeMode.QUARANTINED
    assert cluster.nodes["C"].state.state_hash == divergent_hash


def test_r4_distributed_authority_duplicate_qc_delivery_is_idempotent():
    cluster = make_shadow_authority_cluster(_initial())
    uow = _inc()
    proposal = propose(uow, cluster.nodes["A"].state)
    committed, qc, _, _ = cluster.submit(uow, proposal)
    assert committed and qc is not None

    before = cluster.nodes["A"].snapshot()
    duplicate = cluster.nodes["A"].apply_qc(uow, proposal, qc)

    assert duplicate.idempotent
    assert duplicate.reason == "ALREADY_APPLIED"
    assert cluster.nodes["A"].snapshot() == before


def test_r4_distributed_authority_conflicting_valid_transitions_cannot_both_get_quorum():
    cluster = make_shadow_authority_cluster(_initial())
    one = _inc("dist.increment.one", 1)
    ten = _inc("dist.increment.ten", 10)
    p_one = propose(one, cluster.nodes["A"].state)
    p_ten = propose(ten, cluster.nodes["A"].state)

    cluster.network.isolate_node("C")
    votes_one = cluster.collect_votes(one, p_one)
    qc_one = form_quorum_certificate(one, p_one, votes_one, 2)
    assert qc_one is not None

    cluster.network.restore_link("A", "C")
    cluster.network.restore_link("B", "C")
    votes_ten = cluster.collect_votes(ten, p_ten)
    qc_ten = form_quorum_certificate(ten, p_ten, votes_ten, 2)

    assert qc_ten is None
    assert sum(v.accepted for v in votes_ten) <= 1


def test_r4_distributed_authority_ruleset_mismatch_excluded_from_quorum_application():
    initial = _initial()
    nodes = [
        ShadowAuthorityReplica("A", initial, clock_start=1),
        ShadowAuthorityReplica("B", initial, clock_start=2),
        ShadowAuthorityReplica("C", initial, ruleset_version="uow-authority-v2", clock_start=3),
    ]
    fabric = ShadowNetworkFabric(("P", "A", "B", "C"))
    fabric.connect("P", "A")
    fabric.connect("P", "B")
    fabric.connect("A", "B")
    fabric.connect("A", "C")
    fabric.connect("B", "C")
    cluster = ShadowDistributedAuthorityCluster(nodes, fabric, threshold=2)

    uow = _inc()
    proposal = propose(uow, cluster.nodes["A"].state)
    committed, qc, votes, results = cluster.submit(uow, proposal)

    assert committed and qc is not None
    assert set(qc.voters) == {"A", "B"}
    assert results["C"].reason == "RULESET_VERSION_MISMATCH"
    assert cluster.nodes["C"].state.get("counter") == 0


def test_r4_distributed_authority_reconstruction_does_not_depend_on_qualification_package():
    import sys

    assert "qualification.distributed_authority.authority" not in sys.modules
    cluster = make_shadow_authority_cluster(_initial())
    uow = _inc()
    committed, qc, _, _ = cluster.submit(
        uow,
        propose(uow, cluster.nodes["A"].state),
    )
    assert committed and qc is not None
