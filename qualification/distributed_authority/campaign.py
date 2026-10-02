"""D1 portable qualification campaign: quorum authority + self-healing fabric."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from qualification.claim_registry import get_claim
from qualification.evidence import ClaimRequirement, EvidenceContext, EvidenceLevel, evaluate_claim
from uow.compat.v2 import Guard, GuardOp, Mutation, MutationOp, Route, Successor, WorldState, make_uow
from uow.engine import propose

from .authority import (
    AuthorityNode,
    DistributedAuthorityCluster,
    form_quorum_certificate,
)
from .network import HealingAction, NetworkFabric, SelfHealingController


def make_uow_increment(identity: str = "dist.increment", amount: int = 1):
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


def make_cluster(
    *,
    c_ruleset: str = "uow-authority-v1",
) -> tuple[DistributedAuthorityCluster, SelfHealingController]:
    initial = WorldState(
        attributes={"counter": 0},
        cursor="dist.increment",
        status="RUNNING",
        sequence=0,
    )
    nodes = [
        AuthorityNode("A", initial, clock_start=1, clock_stride=1),
        AuthorityNode("B", initial, clock_start=10_000, clock_stride=999_983),
        AuthorityNode("C", initial, ruleset_version=c_ruleset, clock_start=77, clock_stride=17),
    ]

    fabric = NetworkFabric(("P", "A", "B", "C"))
    fabric.connect("P", "A")
    fabric.connect("P", "B")
    fabric.connect("A", "B")
    fabric.connect("A", "C")
    fabric.connect("B", "C")

    cluster = DistributedAuthorityCluster(nodes, fabric, threshold=2, ingress="P")
    return cluster, SelfHealingController(cluster)


def _req(claim_id: str) -> ClaimRequirement:
    spec = get_claim(claim_id)
    return ClaimRequirement(spec.required_level, spec.required_components)


def _context() -> EvidenceContext:
    return EvidenceContext(
        EvidenceLevel.PORTABLE,
        "D1 in-process independent authority replicas + deterministic faultable fabric",
        {
            "authority_a": "AuthorityNode:A",
            "authority_b": "AuthorityNode:B",
            "authority_c": "AuthorityNode:C",
            "network_fabric": "NetworkFabric",
            "self_healing_controller": "SelfHealingController",
        },
        {},
    )


def run_campaign() -> dict[str, Any]:
    context = _context()
    gates: dict[str, Any] = {}

    # D1.0 — independent replicas, identical certification, clocks observational.
    cluster, _ = make_cluster()
    uow = make_uow_increment()
    p = propose(uow, cluster.nodes["A"].state)
    votes = cluster.collect_votes(uow, p)
    distinct_state_objects = len({id(cluster.nodes[n].state) for n in cluster.nodes}) == 3
    distinct_ledgers = len({id(cluster.nodes[n].ledger) for n in cluster.nodes}) == 3
    cert_hashes = {v.certificate_hash for v in votes if v.accepted}
    d0 = (
        len(votes) == 3
        and all(v.accepted for v in votes)
        and len(cert_hashes) == 1
        and distinct_state_objects
        and distinct_ledgers
    )
    gates["D0_independent_authority_agreement"] = evaluate_claim(
        d0,
        context,
        _req("DIST.AUTHORITY.AGREEMENT.PORTABLE"),
        certificate_hash=next(iter(cert_hashes)) if cert_hashes else "",
        local_clocks={v.node_id: v.local_clock for v in votes},
        independent_state_objects=distinct_state_objects,
        independent_ledgers=distinct_ledgers,
    )

    # D1.1 — quorum commit produces identical state/evidence on all reachable replicas.
    cluster, _ = make_cluster()
    p = propose(uow, cluster.nodes["A"].state)
    result = cluster.submit(uow, p)
    snapshots = [cluster.nodes[n].snapshot() for n in sorted(cluster.nodes)]
    d1 = (
        result.committed
        and result.quorum_certificate is not None
        and len({s["state_hash"] for s in snapshots}) == 1
        and len({s["evidence_root"] for s in snapshots}) == 1
        and cluster.verify_journal()
    )
    gates["D1_quorum_commit_convergence"] = evaluate_claim(
        d1,
        context,
        _req("DIST.AUTHORITY.QUORUM_SAFETY.PORTABLE"),
        voters=list(result.quorum_certificate.voters) if result.quorum_certificate else [],
        journal_root=cluster.journal_root(),
    )

    # D1.2 — one reachable authority cannot commit.
    cluster, _ = make_cluster()
    initial_hash = cluster.nodes["A"].state.state_hash
    cluster.network.isolate_node("B")
    cluster.network.isolate_node("C")
    p = propose(uow, cluster.nodes["A"].state)
    no_quorum = cluster.submit(uow, p)
    d2 = (
        not no_quorum.committed
        and no_quorum.reason == "NO_QUORUM"
        and all(node.state.state_hash == initial_hash for node in cluster.nodes.values())
        and len(cluster.journal) == 0
    )
    gates["D2_no_quorum_no_commit"] = evaluate_claim(
        d2,
        context,
        _req("DIST.AUTHORITY.QUORUM_SAFETY.PORTABLE"),
        reachable_nodes=list(no_quorum.reachable_nodes),
        negative_control="only one authority reachable",
    )

    # D1.3 — failed direct link is bypassed over alternate topology.
    cluster, healer = make_cluster()
    cluster.network.set_link("P", "A", False)
    reroute = healer.reroute("A")
    d3 = (
        reroute.success
        and reroute.action is HealingAction.REROUTED
        and reroute.route[0] == "P"
        and reroute.route[-1] == "A"
        and len(reroute.route) >= 3
    )
    gates["D3_network_alternate_route"] = evaluate_claim(
        d3,
        context,
        _req("DIST.NETWORK.SELF_HEAL.PORTABLE"),
        route=list(reroute.route),
        negative_control="direct ingress-to-A link failed",
    )

    # D1.4/D1.5 — majority continues; isolated replica catches up after reconnect.
    cluster, healer = make_cluster()
    cluster.network.isolate_node("C")
    p = propose(uow, cluster.nodes["A"].state)
    majority = cluster.submit(uow, p)
    expected_state, expected_root, _ = cluster.expected_tip()
    d4 = (
        majority.committed
        and cluster.nodes["A"].state.state_hash == expected_state
        and cluster.nodes["B"].state.state_hash == expected_state
        and cluster.nodes["C"].state.state_hash != expected_state
    )
    gates["D4_majority_progress_one_isolated"] = evaluate_claim(
        d4,
        context,
        _req("DIST.AUTHORITY.QUORUM_SAFETY.PORTABLE"),
        reachable_nodes=list(majority.reachable_nodes),
    )

    cluster.network.restore_link("A", "C")
    cluster.network.restore_link("B", "C")
    healed = healer.heal_node("C")
    d5 = (
        healed.success
        and healed.action is HealingAction.CAUGHT_UP
        and cluster.nodes["C"].state.state_hash == expected_state
        and cluster.nodes["C"].ledger.root_hash() == expected_root
    )
    gates["D5_stale_replica_self_heals"] = evaluate_claim(
        d5,
        context,
        _req("DIST.NETWORK.SELF_HEAL.PORTABLE"),
        entries_replayed=healed.entries_replayed,
        route=list(healed.route),
    )

    # D1.6 — divergent history is quarantined, never silently overwritten.
    cluster, healer = make_cluster()
    p = propose(uow, cluster.nodes["A"].state)
    committed = cluster.submit(uow, p)
    assert committed.committed
    corrupt = cluster.nodes["C"].state.with_attribute("counter", 999_999)
    cluster.nodes["C"].state = corrupt
    before_corrupt_hash = corrupt.state_hash
    quarantine = healer.heal_node("C")
    d6 = (
        not quarantine.success
        and quarantine.action is HealingAction.QUARANTINED_DIVERGENCE
        and cluster.nodes["C"].state.state_hash == before_corrupt_hash
        and cluster.nodes["C"].mode.value == "QUARANTINED"
    )
    gates["D6_divergence_quarantined_no_overwrite"] = evaluate_claim(
        d6,
        context,
        _req("DIST.AUTHORITY.DIVERGENCE_CONTAINMENT.PORTABLE"),
        negative_control="validly hashed but non-journal state injected",
        divergent_state_hash=before_corrupt_hash,
    )

    unauthorized_blocked = False
    try:
        healer.explicit_rebuild("C", authorize=False)
    except PermissionError:
        unauthorized_blocked = True
    rebuild = healer.explicit_rebuild("C", authorize=True)
    expected_state, expected_root, _ = cluster.expected_tip()
    d7 = (
        unauthorized_blocked
        and rebuild.success
        and rebuild.action is HealingAction.REBUILT
        and cluster.nodes["C"].state.state_hash == expected_state
        and cluster.nodes["C"].ledger.root_hash() == expected_root
    )
    gates["D7_explicit_verified_rebuild"] = evaluate_claim(
        d7,
        context,
        _req("DIST.AUTHORITY.DIVERGENCE_CONTAINMENT.PORTABLE"),
        unauthorized_rebuild_blocked=unauthorized_blocked,
        entries_replayed=rebuild.entries_replayed,
    )

    # D1.8 — duplicate quorum delivery is idempotent.
    cluster, _ = make_cluster()
    p = propose(uow, cluster.nodes["A"].state)
    committed = cluster.submit(uow, p)
    qc = committed.quorum_certificate
    assert qc is not None
    before = cluster.nodes["A"].snapshot()
    duplicate = cluster.nodes["A"].apply_quorum_certificate(uow, p, qc)
    after = cluster.nodes["A"].snapshot()
    d8 = duplicate.idempotent and before == after
    gates["D8_duplicate_quorum_idempotent"] = evaluate_claim(
        d8,
        context,
        _req("DIST.AUTHORITY.QUORUM_SAFETY.PORTABLE"),
        apply_reason=duplicate.reason,
    )

    # D1.9 — a proposal against an obsolete pre-state cannot obtain a vote.
    cluster, _ = make_cluster()
    stale = propose(uow, cluster.nodes["A"].state)
    first = cluster.submit(uow, stale)
    assert first.committed
    stale_votes = cluster.collect_votes(uow, stale)
    d9 = (
        stale_votes
        and all(not v.accepted for v in stale_votes)
        and all(v.rejection_reason == "PRE_STATE_MISMATCH" for v in stale_votes)
    )
    gates["D9_stale_proposal_rejected"] = evaluate_claim(
        d9,
        context,
        _req("DIST.AUTHORITY.QUORUM_SAFETY.PORTABLE"),
        rejection_reasons=[v.rejection_reason for v in stale_votes],
        negative_control="replay prior proposal after authoritative state advanced",
    )

    # D1.10 — quorum intersection + one-vote-per-pre-state blocks split decision.
    cluster, _ = make_cluster()
    uow_one = make_uow_increment("dist.increment", 1)
    uow_ten = make_uow_increment("dist.increment10", 10)
    p_one = propose(uow_one, cluster.nodes["A"].state)
    p_ten = propose(uow_ten, cluster.nodes["A"].state)

    cluster.network.isolate_node("C")
    votes_one = cluster.collect_votes(uow_one, p_one)
    qc_one = form_quorum_certificate(uow_one, p_one, votes_one, 2)

    cluster.network.restore_link("A", "C")
    cluster.network.restore_link("B", "C")
    votes_ten = cluster.collect_votes(uow_ten, p_ten)
    qc_ten = form_quorum_certificate(uow_ten, p_ten, votes_ten, 2)
    d10 = (
        qc_one is not None
        and qc_ten is None
        and sum(1 for v in votes_ten if v.accepted) <= 1
        and any(v.rejection_reason == "CONFLICTING_VOTE_LOCK" for v in votes_ten)
    )
    gates["D10_conflicting_quorums_blocked"] = evaluate_claim(
        d10,
        context,
        _req("DIST.AUTHORITY.QUORUM_SAFETY.PORTABLE"),
        first_quorum_voters=list(qc_one.voters) if qc_one else [],
        second_accepts=sum(1 for v in votes_ten if v.accepted),
        negative_control="competing valid UoW transitions from same pre-state",
    )

    # D1.11 — local clocks can vary/freeze without changing authority vote content.
    cluster, _ = make_cluster()
    node = cluster.nodes["A"]
    p = propose(uow, node.state)
    vote_before = node.evaluate(uow, p)
    node.set_clock(stride=99_999_937, frozen=False)
    node.clock_ticks += 10**12
    vote_after = node.evaluate(uow, p)
    node.set_clock(frozen=True)
    vote_frozen = node.evaluate(uow, p)
    d11 = (
        vote_before.accepted
        and vote_after.accepted
        and vote_frozen.accepted
        and vote_before.certificate_hash == vote_after.certificate_hash == vote_frozen.certificate_hash
        and vote_before.vote_hash == vote_after.vote_hash == vote_frozen.vote_hash
        and len({vote_before.local_clock, vote_after.local_clock, vote_frozen.local_clock}) >= 2
    )
    gates["D11_clock_independent_authority_vote"] = evaluate_claim(
        d11,
        context,
        _req("DIST.AUTHORITY.AGREEMENT.PORTABLE"),
        local_clocks=[vote_before.local_clock, vote_after.local_clock, vote_frozen.local_clock],
    )

    # D1.12 — ruleset mismatch cannot be self-healed across silently.
    cluster, healer = make_cluster(c_ruleset="uow-authority-v2")
    p = propose(uow, cluster.nodes["A"].state)
    mixed = cluster.submit(uow, p)
    c_apply = mixed.apply_results.get("C")
    heal = healer.heal_node("C")
    d12 = (
        mixed.committed
        and mixed.quorum_certificate is not None
        and set(mixed.quorum_certificate.voters) == {"A", "B"}
        and c_apply is not None
        and c_apply.reason == "RULESET_VERSION_MISMATCH"
        and not heal.success
        and heal.action is HealingAction.QUARANTINED_REPLAY_FAILURE
    )
    gates["D12_ruleset_mismatch_contained"] = evaluate_claim(
        d12,
        context,
        _req("DIST.AUTHORITY.DIVERGENCE_CONTAINMENT.PORTABLE"),
        quorum_voters=list(mixed.quorum_certificate.voters) if mixed.quorum_certificate else [],
        c_apply_reason=c_apply.reason if c_apply else None,
        healing_action=heal.action.value,
        negative_control="authority C runs incompatible ruleset version",
    )

    all_passed = all(gate["passed"] for gate in gates.values())
    return {
        "schema_version": "uow-distributed-authority-d1-v0.1",
        "evidence_level": "portable",
        "claim_scope": "in-process independent replicas with simulated network faults",
        "physical_distributed_authority_qualified": False,
        "gates": gates,
        "all_gates_passed": all_passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("qualification/distributed_authority/artifacts/d1_report.json"),
    )
    args = parser.parse_args()

    report = run_campaign()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["all_gates_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
