"""R4 portable distributed-authority reconstruction.

This module intentionally does NOT import qualification.distributed_authority.
R1 found that src/uow/proposer/quorum_sequencer.py imports that qualification
package, creating a derived-runtime -> qualification dependency inversion and a
circular import when qualification is treated as a reusable runtime primitive.

The shadow layer therefore reconstructs the portable semantics directly from
the language-neutral attestation model:

independent replica evaluation -> AuthorityVote -> threshold QuorumCertificate
-> QC verification -> minimal shadow authorization -> AuthorizedTransition
-> independent evidence lineage.

No canonical AuthorityNode.apply_quorum_certificate and no uow.engine.commit
are used.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
from collections import deque
from typing import Dict, Iterable, Mapping, Optional, Tuple

from uow.contracts import UoW
from uow.engine import EvidenceLedger, EvidenceRecord, Proposal, certify
from uow.state import WorldState, canonical_json

from .adapters import adapt_world_state
from .identity import shadow_identity
from .kernel import LocalAuthorization, apply_authorized_transition
from .types import CausalCoordinate, ConformanceDecision, ConformanceResult, ProposalEnvelope


def proposal_digest(proposal: Proposal) -> str:
    payload = {
        "uow_id": proposal.uow_id,
        "pre_state_hash": proposal.pre_state_hash,
        "selected_route_index": proposal.selected_route_index,
        "proposed_state_hash": proposal.proposed_state.state_hash,
        "selected_successor": proposal.selected_successor,
        "halted": proposal.halted,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuthorityVote:
    node_id: str
    accepted: bool
    proposal_hash: str
    pre_state_hash: str
    proposed_state_hash: str
    certificate_hash: str
    pre_evidence_root: str
    evidence_step: int
    ruleset_version: str
    rejection_reason: Optional[str] = None
    local_clock: int = 0
    vote_hash: str = ""

    def __post_init__(self) -> None:
        payload = {
            "node_id": self.node_id,
            "accepted": self.accepted,
            "proposal_hash": self.proposal_hash,
            "pre_state_hash": self.pre_state_hash,
            "proposed_state_hash": self.proposed_state_hash,
            "certificate_hash": self.certificate_hash,
            "pre_evidence_root": self.pre_evidence_root,
            "evidence_step": self.evidence_step,
            "ruleset_version": self.ruleset_version,
            "rejection_reason": self.rejection_reason,
        }
        expected = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        if self.vote_hash and self.vote_hash != expected:
            raise ValueError("Authority vote hash mismatch.")
        object.__setattr__(self, "vote_hash", expected)


@dataclass(frozen=True)
class QuorumCertificate:
    proposal_hash: str
    uow_id: str
    pre_state_hash: str
    proposed_state_hash: str
    committed_state_hash: str
    certificate_hash: str
    pre_evidence_root: str
    evidence_step: int
    expected_evidence_root: str
    ruleset_version: str
    threshold: int
    voters: Tuple[str, ...]
    vote_hashes: Tuple[str, ...]
    qc_hash: str = ""

    def __post_init__(self) -> None:
        payload = {
            "proposal_hash": self.proposal_hash,
            "uow_id": self.uow_id,
            "pre_state_hash": self.pre_state_hash,
            "proposed_state_hash": self.proposed_state_hash,
            "committed_state_hash": self.committed_state_hash,
            "certificate_hash": self.certificate_hash,
            "pre_evidence_root": self.pre_evidence_root,
            "evidence_step": self.evidence_step,
            "expected_evidence_root": self.expected_evidence_root,
            "ruleset_version": self.ruleset_version,
            "threshold": self.threshold,
            "voters": self.voters,
            "vote_hashes": self.vote_hashes,
        }
        expected = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        if self.qc_hash and self.qc_hash != expected:
            raise ValueError("Quorum certificate hash mismatch.")
        object.__setattr__(self, "qc_hash", expected)


def _vote_group_key(vote: AuthorityVote) -> tuple:
    return (
        vote.proposal_hash,
        vote.pre_state_hash,
        vote.proposed_state_hash,
        vote.certificate_hash,
        vote.pre_evidence_root,
        vote.evidence_step,
        vote.ruleset_version,
    )


def form_quorum_certificate(
    uow: UoW,
    proposal: Proposal,
    votes: Iterable[AuthorityVote],
    threshold: int,
) -> Optional[QuorumCertificate]:
    accepted = [v for v in votes if v.accepted]
    groups: Dict[tuple, list[AuthorityVote]] = {}
    for vote in accepted:
        groups.setdefault(_vote_group_key(vote), []).append(vote)
    if not groups:
        return None

    matching = max(
        groups.values(),
        key=lambda group: (len(group), tuple(sorted(v.node_id for v in group))),
    )
    unique = {v.node_id: v for v in matching}
    if len(unique) < threshold:
        return None

    selected = [unique[node_id] for node_id in sorted(unique)]
    first = selected[0]
    if first.proposal_hash != proposal_digest(proposal):
        return None

    committed = proposal.proposed_state.advance_sequence()
    expected_evidence = EvidenceRecord(
        step_number=first.evidence_step + 1,
        uow_id=uow.H.identity,
        source_category=uow.H.source_category.value,
        target_category=uow.H.target_category.value,
        pre_state_hash=first.pre_state_hash,
        selected_route_index=proposal.selected_route_index,
        proposed_state_hash=proposal.proposed_state.state_hash,
        certificate_hash=first.certificate_hash,
        post_state_hash=committed.state_hash,
        next_uow_pointer=proposal.selected_successor,
        prev_evidence_hash=first.pre_evidence_root,
    )
    return QuorumCertificate(
        proposal_hash=first.proposal_hash,
        uow_id=uow.H.identity,
        pre_state_hash=first.pre_state_hash,
        proposed_state_hash=first.proposed_state_hash,
        committed_state_hash=committed.state_hash,
        certificate_hash=first.certificate_hash,
        pre_evidence_root=first.pre_evidence_root,
        evidence_step=first.evidence_step,
        expected_evidence_root=expected_evidence.record_hash,
        ruleset_version=first.ruleset_version,
        threshold=threshold,
        voters=tuple(v.node_id for v in selected),
        vote_hashes=tuple(v.vote_hash for v in selected),
    )


class ShadowNetworkFabric:
    def __init__(self, nodes: Iterable[str]) -> None:
        self.nodes = tuple(nodes)
        self.links: Dict[tuple[str, str], bool] = {}

    def connect(self, a: str, b: str) -> None:
        self.links[tuple(sorted((a, b)))] = True

    def set_link(self, a: str, b: str, active: bool) -> None:
        self.links[tuple(sorted((a, b)))] = active

    def isolate_node(self, node: str) -> None:
        for edge in list(self.links):
            if node in edge:
                self.links[edge] = False

    def restore_link(self, a: str, b: str) -> None:
        self.set_link(a, b, True)

    def route(self, source: str, target: str) -> Optional[Tuple[str, ...]]:
        if source == target:
            return (source,)
        adjacency: Dict[str, list[str]] = {n: [] for n in self.nodes}
        for (a, b), active in self.links.items():
            if active:
                adjacency.setdefault(a, []).append(b)
                adjacency.setdefault(b, []).append(a)
        q = deque([(source, (source,))])
        seen = {source}
        while q:
            node, path = q.popleft()
            for nxt in sorted(adjacency.get(node, ())):
                if nxt in seen:
                    continue
                new_path = path + (nxt,)
                if nxt == target:
                    return new_path
                seen.add(nxt)
                q.append((nxt, new_path))
        return None


class ShadowNodeMode(str, Enum):
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True)
class ShadowApplyResult:
    node_id: str
    applied: bool
    idempotent: bool
    reason: str
    state_hash: str
    evidence_root: str


@dataclass(frozen=True)
class ShadowJournalEntry:
    index: int
    uow: UoW
    proposal: Proposal
    qc: QuorumCertificate


class ShadowAuthorityReplica:
    def __init__(
        self,
        node_id: str,
        initial_state: WorldState,
        *,
        ruleset_version: str = "uow-authority-v1",
        clock_start: int = 0,
        clock_stride: int = 1,
    ) -> None:
        data = initial_state.to_dict()
        self.node_id = node_id
        self.initial_state = WorldState(
            attributes=data["attributes"],
            cursor=data["cursor"],
            status=data["status"],
            sequence=data["sequence"],
        )
        self.state = self.initial_state
        self.ledger = EvidenceLedger()
        self.ruleset_version = ruleset_version
        self.mode = ShadowNodeMode.ACTIVE
        self.clock = int(clock_start)
        self.clock_stride = int(clock_stride)
        self._vote_locks: Dict[str, str] = {}
        self._applied_qcs: set[str] = set()

    def _tick(self) -> int:
        self.clock += self.clock_stride
        return self.clock

    def snapshot(self) -> dict:
        return {
            "node_id": self.node_id,
            "mode": self.mode.value,
            "state_hash": self.state.state_hash,
            "sequence": self.state.sequence,
            "evidence_root": self.ledger.root_hash(),
            "evidence_steps": len(self.ledger.records),
            "local_clock": self.clock,
        }

    def evaluate(self, uow: UoW, proposal: Proposal) -> AuthorityVote:
        now = self._tick()
        digest = proposal_digest(proposal)
        root = self.ledger.root_hash()
        step = len(self.ledger.records)

        def reject(reason: str) -> AuthorityVote:
            return AuthorityVote(
                node_id=self.node_id,
                accepted=False,
                proposal_hash=digest,
                pre_state_hash=self.state.state_hash,
                proposed_state_hash=proposal.proposed_state.state_hash,
                certificate_hash="",
                pre_evidence_root=root,
                evidence_step=step,
                ruleset_version=self.ruleset_version,
                rejection_reason=reason,
                local_clock=now,
            )

        if self.mode is ShadowNodeMode.QUARANTINED:
            return reject("NODE_QUARANTINED")
        if proposal.pre_state_hash != self.state.state_hash:
            return reject("PRE_STATE_MISMATCH")

        locked = self._vote_locks.get(self.state.state_hash)
        if locked is not None and locked != digest:
            return reject("CONFLICTING_VOTE_LOCK")

        cert = certify(uow, self.state, proposal)
        if not cert.is_valid:
            return reject(cert.rejection_reason or "CERTIFICATION_REJECTED")

        self._vote_locks[self.state.state_hash] = digest
        return AuthorityVote(
            node_id=self.node_id,
            accepted=True,
            proposal_hash=digest,
            pre_state_hash=self.state.state_hash,
            proposed_state_hash=proposal.proposed_state.state_hash,
            certificate_hash=cert.certificate_hash,
            pre_evidence_root=root,
            evidence_step=step,
            ruleset_version=self.ruleset_version,
            local_clock=now,
        )

    def verify_qc(self, uow: UoW, proposal: Proposal, qc: QuorumCertificate) -> tuple[bool, str]:
        if len(set(qc.voters)) != len(qc.voters):
            return False, "DUPLICATE_VOTER"
        if len(qc.voters) < qc.threshold:
            return False, "INSUFFICIENT_QUORUM"
        if len(qc.vote_hashes) != len(qc.voters):
            return False, "VOTE_HASH_COUNT_MISMATCH"
        if qc.proposal_hash != proposal_digest(proposal):
            return False, "PROPOSAL_HASH_MISMATCH"
        if qc.uow_id != uow.H.identity or proposal.uow_id != uow.H.identity:
            return False, "UOW_IDENTITY_MISMATCH"
        if qc.pre_state_hash != proposal.pre_state_hash:
            return False, "PRE_STATE_HASH_MISMATCH"
        if qc.proposed_state_hash != proposal.proposed_state.state_hash:
            return False, "PROPOSED_STATE_HASH_MISMATCH"
        if qc.ruleset_version != self.ruleset_version:
            return False, "RULESET_VERSION_MISMATCH"

        committed = proposal.proposed_state.advance_sequence()
        if committed.state_hash != qc.committed_state_hash:
            return False, "COMMITTED_STATE_HASH_MISMATCH"

        expected = EvidenceRecord(
            step_number=qc.evidence_step + 1,
            uow_id=uow.H.identity,
            source_category=uow.H.source_category.value,
            target_category=uow.H.target_category.value,
            pre_state_hash=qc.pre_state_hash,
            selected_route_index=proposal.selected_route_index,
            proposed_state_hash=proposal.proposed_state.state_hash,
            certificate_hash=qc.certificate_hash,
            post_state_hash=qc.committed_state_hash,
            next_uow_pointer=proposal.selected_successor,
            prev_evidence_hash=qc.pre_evidence_root,
        )
        if expected.record_hash != qc.expected_evidence_root:
            return False, "EVIDENCE_ROOT_MISMATCH"
        return True, "OK"

    def apply_qc(self, uow: UoW, proposal: Proposal, qc: QuorumCertificate) -> ShadowApplyResult:
        if self.mode is ShadowNodeMode.QUARANTINED:
            return ShadowApplyResult(
                self.node_id, False, False, "NODE_QUARANTINED",
                self.state.state_hash, self.ledger.root_hash(),
            )
        if qc.qc_hash in self._applied_qcs:
            return ShadowApplyResult(
                self.node_id, False, True, "ALREADY_APPLIED",
                self.state.state_hash, self.ledger.root_hash(),
            )

        valid, reason = self.verify_qc(uow, proposal, qc)
        if not valid:
            return ShadowApplyResult(
                self.node_id, False, False, reason,
                self.state.state_hash, self.ledger.root_hash(),
            )
        if self.state.state_hash != qc.pre_state_hash:
            self.mode = ShadowNodeMode.STALE
            return ShadowApplyResult(
                self.node_id, False, False, "PRE_STATE_MISMATCH",
                self.state.state_hash, self.ledger.root_hash(),
            )
        if self.ledger.root_hash() != qc.pre_evidence_root or len(self.ledger.records) != qc.evidence_step:
            self.mode = ShadowNodeMode.QUARANTINED
            return ShadowApplyResult(
                self.node_id, False, False, "PRE_EVIDENCE_CONTEXT_MISMATCH",
                self.state.state_hash, self.ledger.root_hash(),
            )

        local_cert = certify(uow, self.state, proposal)
        if not local_cert.is_valid or local_cert.certificate_hash != qc.certificate_hash:
            return ShadowApplyResult(
                self.node_id, False, False, "LOCAL_RECERTIFICATION_FAILED",
                self.state.state_hash, self.ledger.root_hash(),
            )

        committed_mirror = proposal.proposed_state.advance_sequence()
        conformance_id = shadow_identity(
            "distributed-quorum-conformance",
            {
                "qc_hash": qc.qc_hash,
                "local_certificate_hash": local_cert.certificate_hash,
                "node_id": self.node_id,
                "pre_state_hash": self.state.state_hash,
            },
        )
        conformance = ConformanceResult(
            conformance_id=conformance_id,
            subject_id=proposal.proposed_state.state_hash,
            contract_id=uow.H.identity,
            context_id=self.state.state_hash,
            decision=ConformanceDecision.ACCEPT,
            violations=(),
            evidence={
                "qc_hash": qc.qc_hash,
                "voters": qc.voters,
                "threshold": qc.threshold,
                "canonical_certificate_hash": qc.certificate_hash,
            },
            source_validator="shadow.distributed_authority.qc",
        )
        authorization = LocalAuthorization(
            authorization_id=qc.qc_hash,
            authority_id="distributed-quorum",
            profile="DISTRIBUTED_QUORUM",
            conformance_id=conformance.conformance_id,
            contract_id=uow.H.identity,
            context_id=self.state.state_hash,
        )
        envelope = ProposalEnvelope(
            proposal_id=proposal_digest(proposal),
            proposal_kind="DISTRIBUTED_AUTHORITY_TRANSITION",
            proposer_id="external-proposer",
            subject_contract_id=uow.H.identity,
            precondition_context_id=self.state.state_hash,
            causal_coordinate=CausalCoordinate("quorum_pre_state_hash", self.state.state_hash),
            candidate_payload={
                "proposed_state_id": proposal.proposed_state.state_hash,
                "committed_state_id": committed_mirror.state_hash,
                "next_semantic_payload": dict(committed_mirror.attributes),
                "next_status": committed_mirror.status,
                "next_cursor": committed_mirror.cursor,
            },
            proposal_identity=proposal_digest(proposal),
            metadata={"qc_hash": qc.qc_hash},
            source_type="r4.distributed_authority",
        )

        after_ref, _shadow_evidence = apply_authorized_transition(
            adapt_world_state(self.state),
            envelope,
            conformance,
            authorization,
            evidence_profile="SHADOW-DISTRIBUTED-QUORUM-L2",
        )
        if after_ref.state_id != qc.committed_state_hash:
            raise AssertionError("Shadow quorum application diverged from QC committed state.")

        canonical_evidence = EvidenceRecord(
            step_number=qc.evidence_step + 1,
            uow_id=uow.H.identity,
            source_category=uow.H.source_category.value,
            target_category=uow.H.target_category.value,
            pre_state_hash=qc.pre_state_hash,
            selected_route_index=proposal.selected_route_index,
            proposed_state_hash=proposal.proposed_state.state_hash,
            certificate_hash=qc.certificate_hash,
            post_state_hash=qc.committed_state_hash,
            next_uow_pointer=proposal.selected_successor,
            prev_evidence_hash=qc.pre_evidence_root,
        )
        self.ledger.append(canonical_evidence)
        self.state = committed_mirror
        self._applied_qcs.add(qc.qc_hash)
        self.mode = ShadowNodeMode.ACTIVE
        return ShadowApplyResult(
            self.node_id, True, False, "APPLIED",
            self.state.state_hash, self.ledger.root_hash(),
        )


class ShadowDistributedAuthorityCluster:
    def __init__(
        self,
        nodes: Iterable[ShadowAuthorityReplica],
        network: ShadowNetworkFabric,
        *,
        threshold: int = 2,
        ingress: str = "P",
    ) -> None:
        self.nodes = {n.node_id: n for n in nodes}
        self.network = network
        self.threshold = threshold
        self.ingress = ingress
        self.journal: list[ShadowJournalEntry] = []

    def reachable_nodes(self) -> Tuple[str, ...]:
        return tuple(
            node_id for node_id in sorted(self.nodes)
            if self.network.route(self.ingress, node_id) is not None
        )

    def collect_votes(self, uow: UoW, proposal: Proposal) -> Tuple[AuthorityVote, ...]:
        return tuple(self.nodes[n].evaluate(uow, proposal) for n in self.reachable_nodes())

    def submit(self, uow: UoW, proposal: Proposal):
        votes = self.collect_votes(uow, proposal)
        qc = form_quorum_certificate(uow, proposal, votes, self.threshold)
        if qc is None:
            return False, None, votes, {}
        results = {
            n: self.nodes[n].apply_qc(uow, proposal, qc)
            for n in self.reachable_nodes()
        }
        self.journal.append(ShadowJournalEntry(len(self.journal) + 1, uow, proposal, qc))
        return True, qc, votes, results

    def catch_up(self, node_id: str) -> tuple[bool, str]:
        node = self.nodes[node_id]
        if (
            node.state.state_hash == node.initial_state.state_hash
            and node.ledger.root_hash() == "0" * 64
            and len(node.ledger.records) == 0
        ):
            start = 0
        else:
            start = None
            for idx, entry in enumerate(self.journal, start=1):
                qc = entry.qc
                if (
                    node.state.state_hash == qc.committed_state_hash
                    and node.ledger.root_hash() == qc.expected_evidence_root
                    and len(node.ledger.records) == qc.evidence_step + 1
                ):
                    start = idx
                    break
            if start is None:
                node.mode = ShadowNodeMode.QUARANTINED
                return False, "QUARANTINED_DIVERGENCE"

        for entry in self.journal[start:]:
            res = node.apply_qc(entry.uow, entry.proposal, entry.qc)
            if not (res.applied or res.idempotent):
                node.mode = ShadowNodeMode.QUARANTINED
                return False, f"REPLAY_FAILED:{res.reason}"
        return True, "CAUGHT_UP"


def make_shadow_authority_cluster(initial: WorldState) -> ShadowDistributedAuthorityCluster:
    nodes = [
        ShadowAuthorityReplica("A", initial, clock_start=1, clock_stride=1),
        ShadowAuthorityReplica("B", initial, clock_start=10_000, clock_stride=999_983),
        ShadowAuthorityReplica("C", initial, clock_start=77, clock_stride=17),
    ]
    fabric = ShadowNetworkFabric(("P", "A", "B", "C"))
    fabric.connect("P", "A")
    fabric.connect("P", "B")
    fabric.connect("A", "B")
    fabric.connect("A", "C")
    fabric.connect("B", "C")
    return ShadowDistributedAuthorityCluster(nodes, fabric, threshold=2)
