from __future__ import annotations

import inspect

from qualification.distributed_authority.authority import AuthorityNode, DistributedAuthorityCluster
from qualification.distributed_authority.network import NetworkFabric
from uow.compat.v2 import (
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    Route,
    Successor,
    WorldState,
    make_uow,
)
from uow.authority import QuorumAuthorityProvider
from uow.engine import certify, propose
from uow.proposer import QuorumCommitSequencer
from uow.transactions import create_transaction_descriptor


def _cluster(initial_state: WorldState) -> DistributedAuthorityCluster:
    nodes = [
        AuthorityNode("authority_a", initial_state),
        AuthorityNode("authority_b", initial_state),
        AuthorityNode("authority_c", initial_state),
    ]
    fabric = NetworkFabric(("P", "authority_a", "authority_b", "authority_c"))
    for node_id in ("authority_a", "authority_b", "authority_c"):
        fabric.connect("P", node_id)
    fabric.connect("authority_a", "authority_b")
    fabric.connect("authority_b", "authority_c")
    fabric.connect("authority_a", "authority_c")
    return DistributedAuthorityCluster(nodes, fabric, threshold=2, ingress="P")


def _uow():
    return make_uow(
        "authority-protocol-test",
        [
            Route(
                Guard(GuardOp.ALWAYS),
                (Mutation(MutationOp.SET, "x", 1),),
                Successor.preserve(),
            )
        ],
    )


def test_s1_quorum_sequencer_source_has_no_qualification_dependency():
    import uow.proposer.quorum_sequencer as module

    source = inspect.getsource(module)
    assert "qualification.distributed_authority" not in source
    assert "from qualification" not in source


def test_s1_existing_distributed_authority_cluster_satisfies_provider_protocol():
    cluster = _cluster(WorldState(attributes={"x": 0}, cursor="authority-protocol-test"))
    assert isinstance(cluster, QuorumAuthorityProvider)


def test_s1_existing_cluster_commits_through_unchanged_quorum_sequencer_api():
    state = WorldState(attributes={"x": 0}, cursor="authority-protocol-test")
    cluster = _cluster(state)
    sequencer = QuorumCommitSequencer(cluster)

    uow = _uow()
    proposal = propose(uow, state)
    certificate = certify(uow, state, proposal)
    transaction = create_transaction_descriptor(uow, state)

    committed, evidence = sequencer.commit(uow, proposal, transaction, certificate)

    assert committed.get("x") == 1
    assert evidence.post_state_hash == committed.state_hash
    assert len(sequencer.qc_history) == 1
    assert sequencer.is_converged()
    assert len({n.state.state_hash for n in cluster.nodes.values()}) == 1
    assert len({n.ledger.root_hash() for n in cluster.nodes.values()}) == 1


def test_s1_minority_partition_behavior_is_unchanged():
    state = WorldState(attributes={"x": 0}, cursor="authority-protocol-test")
    cluster = _cluster(state)
    cluster.network.isolate_node("authority_b")
    cluster.network.isolate_node("authority_c")

    sequencer = QuorumCommitSequencer(cluster, primary_node_id="authority_a")
    uow = _uow()
    proposal = propose(uow, state)
    certificate = certify(uow, state, proposal)
    transaction = create_transaction_descriptor(uow, state)

    from uow.proposer import QuorumCommitError

    try:
        sequencer.commit(uow, proposal, transaction, certificate)
    except QuorumCommitError as exc:
        assert "NO_QUORUM" in str(exc)
    else:
        raise AssertionError("Minority partition unexpectedly committed.")

    assert sequencer.qc_history == ()
    assert cluster.nodes["authority_a"].state.state_hash == state.state_hash
