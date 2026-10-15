"""Q3B: batch *local inference*; preserve individual UoW authority/evidence.

No batch quorum, no skipped certificates, no global clock. Compare identical
ordered work and independent clusters. Do not claim physical speedup.
"""
from __future__ import annotations
import json
import statistics
import time
from qualification.distributed_authority.campaign import make_cluster
from qualification.micro_operator.q2_campaign import FrozenMicroOperator, work_for
from qualification.micro_operator.q3_cooperation import dataset, train, predict, SEED
from uow.engine import propose


def classify_one(models, views):
    return int(sum(predict(models[j], views, (j,)) for j in range(3)) >= 2)


def classify_batch(models, views_batch):
    """Compute the three local streams, then apply deterministic majority."""
    streams = [[predict(models[j], view, (j,)) for view in views_batch]
               for j in range(3)]
    return [int(a + b + c >= 2) for a, b, c in zip(*streams)]


def commit_votes(votes, *, reuse_contracts):
    cluster, _ = make_cluster()
    model = FrozenMicroOperator((1, 1, 1), "q3-majority-frozen-v1")
    contracts = {v: work_for(model, 100*v, 100*v) for v in (0, 1)} if reuse_contracts else None
    certs = []
    for vote in votes:
        work = contracts[vote] if reuse_contracts else work_for(model, 100*vote, 100*vote)
        proposal = propose(work, cluster.nodes["A"].state)
        result = cluster.submit(work, proposal)
        if not result.committed or result.quorum_certificate is None:
            raise AssertionError("UoW quorum rejected a valid transition")
        certs.append(result.quorum_certificate.qc_hash)
    if not cluster.verify_journal():
        raise AssertionError("journal verification failed")
    return cluster, certs


def comparison(count=96, repetitions=3):
    training = dataset(6000, SEED)
    heldout = dataset(count, SEED+1)
    models = [train(training, (j,)) for j in range(3)]
    views = [v for _, v in heldout]
    original = [classify_one(models, v) for v in views]
    batched = classify_batch(models, views)
    if original != batched:
        raise AssertionError("local batch changed output ordering/values")

    # Commit-path comparison excludes training, includes proposals,
    # independent node votes, certificates and evidence on both sides.
    a, ac = commit_votes(original, reuse_contracts=False)
    b, bc = commit_votes(batched, reuse_contracts=True)
    for key in a.nodes:
        left, right = a.nodes[key], b.nodes[key]
        if left.state.state_hash != right.state.state_hash or left.ledger.root_hash() != right.ledger.root_hash():
            raise AssertionError("batch and original diverged in authoritative state/evidence")
    if ac != bc or a.journal_root() != b.journal_root():
        raise AssertionError("batch changed certificate hashes or journal ordering")

    times = {"reference_ms": [], "batch_ms": []}
    for _ in range(repetitions):
        t = time.perf_counter()
        commit_votes(original, reuse_contracts=False)
        times["reference_ms"].append((time.perf_counter()-t)*1000)
        t = time.perf_counter()
        commit_votes(batched, reuse_contracts=True)
        times["batch_ms"].append((time.perf_counter()-t)*1000)

    return {"status":"PASS","examples":count,"repetitions":repetitions,
            "native_commits_per_arm":count,
            "same_decisions":True,"same_state_evidence_certificates":True,
            "reference_commit_median_ms":statistics.median(times["reference_ms"]),
            "batched_commit_median_ms":statistics.median(times["batch_ms"]),
            "commit_speedup_ratio":statistics.median(times["reference_ms"])/statistics.median(times["batch_ms"]),
            "qualification_scope":"portable in-process; inference batched, quorum remains per transition",
            "caveats":["timings vary across runners","no physical transport","no energy measurement",
                       "no model provenance attestation"]}


if __name__=="__main__":
    print(json.dumps(comparison(),indent=2,sort_keys=True))
