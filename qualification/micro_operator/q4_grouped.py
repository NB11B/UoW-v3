"""Grouped preparation over existing UoW quorum, preserving per-item evidence."""
import hashlib
import json
from dataclasses import dataclass
from qualification.distributed_authority.campaign import make_cluster
from qualification.micro_operator.q2_campaign import FrozenMicroOperator, work_for
from uow.engine import propose

MODEL = FrozenMicroOperator((1, 1, 1), "q3-majority-frozen-v1")

def validate(values):
    if type(values) not in (tuple, list) or not 1 <= len(values) <= 256:
        raise ValueError("invalid length")
    if any(type(v) is not int or v not in (0, 1) for v in values):
        raise ValueError("invalid item")
    return tuple(values)

def hash_group(base, votes):
    payload = json.dumps({"schema":"q4-v1","base":base,"votes":votes},
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()

@dataclass(frozen=True)
class Plan:
    votes: tuple
    base: str
    digest: str

def prepare(cluster, values):
    votes = validate(values)
    base = cluster.nodes["A"].state.state_hash
    return Plan(votes, base, hash_group(base, votes))

def submit(cluster, plan, stop_after=None):
    if not isinstance(plan, Plan) or validate(plan.votes) != plan.votes:
        raise ValueError("invalid plan")
    if hash_group(plan.base, plan.votes) != plan.digest:
        raise ValueError("altered plan")
    if cluster.nodes["A"].state.state_hash != plan.base:
        return "STALE", []
    contracts = {v:work_for(MODEL, 100*v, 100*v) for v in (0,1)}
    receipts = []
    for index, value in enumerate(plan.votes):
        if stop_after is not None and index >= stop_after:
            return "INTERRUPTED", receipts
        work = contracts[value]
        result = cluster.submit(work, propose(work, cluster.nodes["A"].state))
        if not result.committed or result.quorum_certificate is None:
            return "NO_QUORUM", receipts
        receipts.append(result.quorum_certificate.qc_hash)
    return "COMPLETE", receipts

def reference(cluster, values):
    receipts = []
    for value in validate(values):
        work = work_for(MODEL, 100*value, 100*value)
        result = cluster.submit(work, propose(work, cluster.nodes["A"].state))
        if not result.committed or result.quorum_certificate is None:
            return "NO_QUORUM", receipts
        receipts.append(result.quorum_certificate.qc_hash)
    return "COMPLETE", receipts

def equivalent(a, b):
    return (a.verify_journal() and b.verify_journal()
            and a.journal_root() == b.journal_root()
            and all(a.nodes[n].state.state_hash == b.nodes[n].state.state_hash
                    and a.nodes[n].ledger.root_hash() == b.nodes[n].ledger.root_hash()
                    for n in a.nodes))
