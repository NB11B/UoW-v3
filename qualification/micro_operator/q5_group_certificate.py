"""Q5 portable grouped-certificate experiment.

One *group vote* per replica, with independent member-by-member certification.
Publication is all-or-none in this in-process coordinator, not crash durable.
Do not use this as a production Byzantine quorum protocol.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
from uow.engine import propose, certify, commit, EvidenceLedger
from uow.state import canonical_json
from qualification.distributed_authority.campaign import make_cluster
from qualification.micro_operator.q4_grouped import validate, MODEL
from qualification.micro_operator.q2_campaign import work_for

def h(payload):
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

@dataclass(frozen=True)
class Ballot:
    voter: str
    digest: str
    member_hashes: tuple[str, ...]
    state_hash: str
    evidence_root: str
    base_hash: str

@dataclass(frozen=True)
class GroupCertificate:
    digest: str
    voters: tuple[str, ...]
    ballots: tuple[str, ...]
    members: tuple[str, ...]
    state_hash: str
    evidence_root: str
    certificate_hash: str

class GroupAuthority:
    def __init__(self, cluster):
        self.cluster = cluster
        self.applied = set()

    def _simulate(self, node, votes):
        state = node.state
        root = node.ledger.root_hash()
        step = len(node.ledger.records)
        records = []
        contracts = {v: work_for(MODEL,100*v,100*v) for v in (0,1)}
        for vote in votes:
            work = contracts[vote]
            proposal = propose(work, state)
            cert = certify(work, state, proposal)
            if not cert.is_valid:
                raise ValueError("invalid member certificate")
            state, record = commit(work, state, proposal, cert,
                                   prev_evidence_hash=root, step_number=step+1)
            root = record.record_hash
            step += 1
            records.append(record)
        return state, tuple(records), root

    def commit(self, values, *, interrupt=False):
        votes = validate(values)
        c = self.cluster
        reachable = c.reachable_nodes()
        if len(reachable) < c.threshold:
            return "NO_QUORUM", None
        nodes = [c.nodes[k] for k in reachable]
        if any(n.mode.value != "ACTIVE" for n in nodes):
            return "INACTIVE", None
        if len({(n.state.state_hash,n.ledger.root_hash(),len(n.ledger.records),n.ruleset_version) for n in nodes}) != 1:
            return "DIVERGED", None
        base = nodes[0].state.state_hash
        root = nodes[0].ledger.root_hash()
        group_hash = h({"schema":"Q5","base":base,"root":root,"votes":votes})
        if group_hash in self.applied:
            return "REPLAY", None
        prepared = []
        for node in nodes:
            state, records, final_root = self._simulate(node, votes)
            item_hashes = tuple(r.record_hash for r in records)
            ballot = Ballot(node.node_id, group_hash, item_hashes,
                            state.state_hash, final_root, base)
            prepared.append((node,state,records,ballot))
        groups={}
        for node,state,records,ballot in prepared:
            key=(ballot.digest,ballot.member_hashes,ballot.state_hash,ballot.evidence_root)
            groups.setdefault(key,[]).append((node,state,records,ballot))
        winning=max(groups.values(),key=len)
        if len(winning)<c.threshold:
            return "NO_AGREEMENT", None
        if len(winning)!=len(prepared):
            return "PARTIAL_REPLICA", None  # never publish only a subset
        members=winning[0][3].member_hashes
        cert=GroupCertificate(group_hash,tuple(sorted(x[0].node_id for x in winning)),
              tuple(h({"node":x[3].voter,"group":x[3].digest,"members":x[3].member_hashes,
                       "state":x[3].state_hash,"root":x[3].evidence_root}) for x in winning),
              members,winning[0][3].state_hash,winning[0][3].evidence_root,"")
        object.__setattr__(cert,"certificate_hash",h({"digest":cert.digest,"voters":cert.voters,
            "ballots":cert.ballots,"members":cert.members,"state":cert.state_hash,
            "root":cert.evidence_root}))
        if interrupt:
            return "INTERRUPTED_PREPUBLISH", None
        # All members verified on each replica, then publish in-process. This is
        # not a durable multi-process atomic transaction.
        for node,state,records,ballot in winning:
            for rec in records:
                node.ledger.append(rec)
            node.state=state
        self.applied.add(group_hash)
        return "COMMITTED",cert
