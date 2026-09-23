from __future__ import annotations

from qualification.distributed_authority.authority import (
    AuthorityNode,
    form_quorum_certificate,
)
from qualification.distributed_authority.campaign import (
    make_cluster,
    make_uow_increment,
    run_campaign,
)
from qualification.distributed_authority.network import HealingAction, NetworkFabric
from uow import WorldState
from uow.engine import propose


def test_network_reroutes_deterministically_around_failed_direct_link():
    fabric = NetworkFabric(("P", "A", "B", "C"))
    fabric.connect("P", "A")
    fabric.connect("P", "B")
    fabric.connect("A", "B")
    fabric.connect("B", "C")
    fabric.set_link("P", "A", False)
    assert fabric.route("P", "A") == ("P", "B", "A")


def test_authority_replicas_own_independent_state_and_ledgers():
    cluster, _ = make_cluster()
    assert len({id(node.state) for node in cluster.nodes.values()}) == 3
    assert len({id(node.ledger) for node in cluster.nodes.values()}) == 3


def test_same_transition_certifies_identically_despite_clock_skew():
    cluster, _ = make_cluster()
    uow = make_uow_increment()
    p = propose(uow, cluster.nodes["A"].state)
    votes = cluster.collect_votes(uow, p)
    assert all(v.accepted for v in votes)
    assert len({v.certificate_hash for v in votes}) == 1
    assert len({v.local_clock for v in votes}) > 1


def test_two_of_three_quorum_commits_and_converges():
    cluster, _ = make_cluster()
    uow = make_uow_increment()
    result = cluster.submit(uow, propose(uow, cluster.nodes["A"].state))
    assert result.committed
    assert result.quorum_certificate is not None
    assert len(result.quorum_certificate.voters) >= 2
    assert len({node.state.state_hash for node in cluster.nodes.values()}) == 1
    assert len({node.ledger.root_hash() for node in cluster.nodes.values()}) == 1
    assert cluster.verify_journal()


def test_single_reachable_authority_cannot_commit():
    cluster, _ = make_cluster()
    uow = make_uow_increment()
    initial = cluster.nodes["A"].state.state_hash
    cluster.network.isolate_node("B")
    cluster.network.isolate_node("C")
    result = cluster.submit(uow, propose(uow, cluster.nodes["A"].state))
    assert not result.committed
    assert result.reason == "NO_QUORUM"
    assert all(node.state.state_hash == initial for node in cluster.nodes.values())


def test_isolated_replica_catches_up_only_from_verified_quorum_history():
    cluster, healer = make_cluster()
    uow = make_uow_increment()
    cluster.network.isolate_node("C")
    result = cluster.submit(uow, propose(uow, cluster.nodes["A"].state))
    assert result.committed

    cluster.network.restore_link("A", "C")
    cluster.network.restore_link("B", "C")
    healed = healer.heal_node("C")

    assert healed.success
    assert healed.action is HealingAction.CAUGHT_UP
    expected_state, expected_root, _ = cluster.expected_tip()
    assert cluster.nodes["C"].state.state_hash == expected_state
    assert cluster.nodes["C"].ledger.root_hash() == expected_root


def test_divergent_replica_is_quarantined_without_overwrite():
    cluster, healer = make_cluster()
    uow = make_uow_increment()
    assert cluster.submit(uow, propose(uow, cluster.nodes["A"].state)).committed

    corrupted = cluster.nodes["C"].state.with_attribute("counter", 123456)
    cluster.nodes["C"].state = corrupted
    before = corrupted.state_hash

    healed = healer.heal_node("C")
    assert not healed.success
    assert healed.action is HealingAction.QUARANTINED_DIVERGENCE
    assert cluster.nodes["C"].state.state_hash == before
    assert cluster.nodes["C"].mode.value == "QUARANTINED"


def test_divergent_replica_rebuild_requires_explicit_authorization():
    cluster, healer = make_cluster()
    uow = make_uow_increment()
    assert cluster.submit(uow, propose(uow, cluster.nodes["A"].state)).committed
    cluster.nodes["C"].state = cluster.nodes["C"].state.with_attribute("counter", 999)
    assert healer.heal_node("C").action is HealingAction.QUARANTINED_DIVERGENCE

    try:
        healer.explicit_rebuild("C")
        assert False, "expected PermissionError"
    except PermissionError:
        pass

    rebuilt = healer.explicit_rebuild("C", authorize=True)
    assert rebuilt.success
    assert rebuilt.action is HealingAction.REBUILT


def test_duplicate_quorum_delivery_is_idempotent():
    cluster, _ = make_cluster()
    uow = make_uow_increment()
    p = propose(uow, cluster.nodes["A"].state)
    result = cluster.submit(uow, p)
    assert result.committed and result.quorum_certificate is not None

    before = cluster.nodes["A"].snapshot()
    duplicate = cluster.nodes["A"].apply_quorum_certificate(
        uow, p, result.quorum_certificate
    )
    assert duplicate.idempotent
    assert cluster.nodes["A"].snapshot() == before


def test_conflicting_valid_transitions_cannot_both_obtain_quorum():
    cluster, _ = make_cluster()
    uow_one = make_uow_increment("dist.increment", 1)
    uow_ten = make_uow_increment("dist.increment10", 10)
    p_one = propose(uow_one, cluster.nodes["A"].state)
    p_ten = propose(uow_ten, cluster.nodes["A"].state)

    cluster.network.isolate_node("C")
    votes_one = cluster.collect_votes(uow_one, p_one)
    assert form_quorum_certificate(uow_one, p_one, votes_one, 2) is not None

    cluster.network.restore_link("A", "C")
    cluster.network.restore_link("B", "C")
    votes_ten = cluster.collect_votes(uow_ten, p_ten)
    assert form_quorum_certificate(uow_ten, p_ten, votes_ten, 2) is None
    assert sum(v.accepted for v in votes_ten) <= 1


def test_ruleset_mismatch_cannot_silently_self_heal():
    cluster, healer = make_cluster(c_ruleset="uow-authority-v2")
    uow = make_uow_increment()
    result = cluster.submit(uow, propose(uow, cluster.nodes["A"].state))

    assert result.committed
    assert result.quorum_certificate is not None
    assert set(result.quorum_certificate.voters) == {"A", "B"}
    assert result.apply_results["C"].reason == "RULESET_VERSION_MISMATCH"

    heal = healer.heal_node("C")
    assert not heal.success
    assert heal.action is HealingAction.QUARANTINED_REPLAY_FAILURE


def test_campaign_passes_only_as_portable_not_physical():
    report = run_campaign()
    assert report["all_gates_passed"] is True
    assert report["evidence_level"] == "portable"
    assert report["physical_distributed_authority_qualified"] is False
    assert all(
        gate["evidence_level"] == "portable"
        for gate in report["gates"].values()
    )
