"""Q2: trained micro-operator inside the EXISTING UoW distributed-authority protocol.

The classifier supplies a bounded work proposal, never authority. Production
commit/certification is delegated to qualification.distributed_authority.
This is portable in-process qualification, NOT physical transport qualification.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass

from qualification.distributed_authority.campaign import make_cluster
from qualification.distributed_authority.network import HealingAction
from uow.compat.v2 import Guard, GuardOp, Mutation, MutationOp, Route, Successor, make_uow
from uow.engine import propose


def target(x: int, y: int) -> int:
    return int(x + 2 * y >= 150)


def features(x: int, y: int) -> tuple[int, int, int]:
    if type(x) is not int or type(y) is not int or not 0 <= x <= 100 or not 0 <= y <= 100:
        raise ValueError("features must be integers in [0,100]")
    return (x - 50, y - 50, 50)


def split() -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    values = [(x, y) for x in range(101) for y in range(101)]
    random.Random(9151).shuffle(values)
    return values[:7000], values[7000:]


@dataclass(frozen=True)
class FrozenMicroOperator:
    weights: tuple[int, int, int]
    model_id: str

    def predict(self, x: int, y: int) -> int:
        f = features(x, y)
        return int(sum(a * b for a, b in zip(self.weights, f)) >= 0)


def train_model() -> FrozenMicroOperator:
    training, _ = split()
    weights = [0, 0, 0]
    for _ in range(35):
        errors = 0
        for x, y in training:
            f = features(x, y)
            vote = int(sum(a * b for a, b in zip(weights, f)) >= 0)
            correct = target(x, y)
            if vote != correct:
                delta = 1 if correct else -1
                weights = [a + delta * b for a, b in zip(weights, f)]
                errors += 1
        if errors == 0:
            break
    frozen = tuple(weights)
    raw = json.dumps({"algorithm": "integer-perceptron-v1", "weights": frozen}, separators=(",", ":"))
    return FrozenMicroOperator(frozen, hashlib.sha256(raw.encode()).hexdigest())


def work_for(model: FrozenMicroOperator, x: int, y: int):
    """One explicit UoW transition for a bounded inferred action.

    Varying inputs never grant authority. The UoW contract is independently
    evaluated by all authority nodes using the existing certifier.
    """
    vote = model.predict(x, y)
    return make_uow(
        "q2.micro." + model.model_id[:16] + "." + str(vote),
        [Route(Guard(GuardOp.ALWAYS),
               (Mutation(MutationOp.ADD, "counter", vote),),
               Successor.preserve())],
    )


def submit_observation(cluster, model: FrozenMicroOperator, x: int, y: int):
    uow = work_for(model, x, y)
    proposal = propose(uow, cluster.nodes["A"].state)
    return cluster.submit(uow, proposal)


def run_q2() -> dict:
    model = train_model()
    training, heldout = split()
    train_correct = sum(model.predict(x, y) == target(x, y) for x, y in training)
    heldout_correct = sum(model.predict(x, y) == target(x, y) for x, y in heldout)
    gates = {}

    gates["Q2_01_learned_and_frozen"] = (
        model.weights != (0, 0, 0)
        and train_correct >= 6650
        and heldout_correct >= 3041
    )

    cluster, healer = make_cluster()
    decisions = [(10, 40), (100, 100), (0, 0), (65, 45)]
    votes = [model.predict(*xy) for xy in decisions]
    results = [submit_observation(cluster, model, *xy) for xy in decisions]
    gates["Q2_02_real_quorum_commits"] = (
        all(r.committed and r.quorum_certificate is not None for r in results)
        and cluster.verify_journal()
    )
    states = [n.state.state_hash for n in cluster.nodes.values()]
    roots = [n.ledger.root_hash() for n in cluster.nodes.values()]
    gates["Q2_03_evidence_and_state_convergence"] = (
        len(set(states)) == len(set(roots)) == 1
        and cluster.nodes["A"].state.attributes["counter"] == sum(votes)
    )
    gates["Q2_04_no_shared_clock"] = (
        len({n.clock_ticks for n in cluster.nodes.values()}) > 1
        and len(set(states)) == 1
    )

    cluster, healer = make_cluster()
    first_uow = work_for(model, 100, 100)
    stale = propose(first_uow, cluster.nodes["A"].state)
    first = cluster.submit(first_uow, stale)
    replay = cluster.submit(first_uow, stale)
    gates["Q2_05_replay_rejected"] = (
        first.committed and not replay.committed
        and all(not v.accepted for v in replay.votes)
        and len(cluster.journal) == 1
    )

    cluster, healer = make_cluster()
    cluster.network.isolate_node("B")
    cluster.network.isolate_node("C")
    refused = submit_observation(cluster, model, 100, 100)
    gates["Q2_06_no_quorum_no_mutation"] = (
        not refused.committed
        and len(cluster.journal) == 0
        and all(n.state.attributes["counter"] == 0 for n in cluster.nodes.values())
    )

    cluster, healer = make_cluster()
    cluster.network.isolate_node("C")
    majority = submit_observation(cluster, model, 100, 100)
    cluster.network.restore_link("A", "C")
    cluster.network.restore_link("B", "C")
    healed = healer.heal_node("C")
    gates["Q2_07_partition_and_catchup"] = (
        majority.committed and healed.success
        and healed.action == HealingAction.CAUGHT_UP
        and cluster.verify_journal()
        and len({n.state.state_hash for n in cluster.nodes.values()}) == 1
    )

    cluster, healer = make_cluster()
    old_tip = {k: n.state.state_hash for k, n in cluster.nodes.items()}
    invalid_rejected = False
    for pair in [(101, 0), (-1, 3), (True, 1), (2.0, 3), ("12", 5)]:
        try:
            submit_observation(cluster, model, *pair)
        except ValueError:
            invalid_rejected = True
        else:
            invalid_rejected = False
            break
    gates["Q2_08_bad_features_no_commit"] = (
        invalid_rejected and not cluster.journal
        and old_tip == {k: n.state.state_hash for k, n in cluster.nodes.items()}
    )

    cluster, healer = make_cluster()
    alt = FrozenMicroOperator((1, 1, 1), "unqualified-model-version")
    reference_work = work_for(model, 100, 100)
    alternate_work = work_for(alt, 100, 100)
    reference_proposal = propose(reference_work, cluster.nodes["A"].state)
    # Deliberately swap UoW contract while reusing proposal: certification must reject.
    votes_swapped = cluster.collect_votes(alternate_work, reference_proposal)
    gates["Q2_09_cross_model_contract_rejection"] = (
        all(not vote.accepted for vote in votes_swapped) and not cluster.journal
    )

    return {
        "campaign": "Q2-embedded-micro-operator-existing-uow",
        "scope": "portable in-process existing UoW certifier/quorum/evidence; no physical wire transport",
        "model": {"weights": list(model.weights), "model_id": model.model_id,
                  "train_accuracy": train_correct / len(training),
                  "heldout_accuracy": heldout_correct / len(heldout)},
        "gates": gates, "passed": all(gates.values()),
        "physical_transport_qualified": False,
        "rtl_qualified": False,
    }


if __name__ == "__main__":
    report = run_q2()
    print(json.dumps(report, sort_keys=True, indent=2))
    if not report["passed"]:
        raise SystemExit(1)
