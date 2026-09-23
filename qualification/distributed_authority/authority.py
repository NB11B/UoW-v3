"""Independent replicated authority and quorum certification.

The cluster object is a qualification harness and transport coordinator. It has
no power to fabricate an authority vote. A transition becomes authoritative
only when independently produced authority votes form a valid quorum
certificate.

Clocks are observational. No authority decision/hash depends on local clock
values.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
from typing import Iterable, Mapping, Optional

from uow.contracts import UoW
from uow.engine import (
    CertificateResult,
    EvidenceLedger,
    EvidenceRecord,
    Proposal,
    certify,
    commit,
)
from uow.state import WorldState, canonical_json

from .network import NetworkFabric


def _clone_state(state: WorldState) -> WorldState:
    data = state.to_dict()
    return WorldState(
        attributes=data["attributes"],
        cursor=data["cursor"],
        status=data["status"],
        sequence=data["sequence"],
    )


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


class NodeMode(str, Enum):
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    QUARANTINED = "QUARANTINED"


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
        expected = self.calculate_hash(
            node_id=self.node_id,
            accepted=self.accepted,
            proposal_hash=self.proposal_hash,
            pre_state_hash=self.pre_state_hash,
            proposed_state_hash=self.proposed_state_hash,
            certificate_hash=self.certificate_hash,
            pre_evidence_root=self.pre_evidence_root,
            evidence_step=self.evidence_step,
            ruleset_version=self.ruleset_version,
            rejection_reason=self.rejection_reason,
        )
        if self.vote_hash and self.vote_hash != expected:
            raise ValueError("Authority vote hash does not match vote contents.")
        object.__setattr__(self, "vote_hash", expected)

    @staticmethod
    def calculate_hash(**payload: object) -> str:
        # local_clock is intentionally absent: clock observations carry no authority.
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


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
    voters: tuple[str, ...]
    vote_hashes: tuple[str, ...]
    qc_hash: str = ""

    def __post_init__(self) -> None:
        expected = self.calculate_hash(
            proposal_hash=self.proposal_hash,
            uow_id=self.uow_id,
            pre_state_hash=self.pre_state_hash,
            proposed_state_hash=self.proposed_state_hash,
            committed_state_hash=self.committed_state_hash,
            certificate_hash=self.certificate_hash,
            pre_evidence_root=self.pre_evidence_root,
            evidence_step=self.evidence_step,
            expected_evidence_root=self.expected_evidence_root,
            ruleset_version=self.ruleset_version,
            threshold=self.threshold,
            voters=self.voters,
            vote_hashes=self.vote_hashes,
        )
        if self.qc_hash and self.qc_hash != expected:
            raise ValueError("Quorum certificate hash does not match certificate contents.")
        object.__setattr__(self, "qc_hash", expected)

    @staticmethod
    def calculate_hash(**payload: object) -> str:
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ApplyResult:
    node_id: str
    applied: bool
    idempotent: bool
    reason: str
    state_hash: str
    evidence_root: str


@dataclass(frozen=True)
class JournalEntry:
    index: int
    uow: UoW
    proposal: Proposal
    quorum_certificate: QuorumCertificate
    prev_entry_hash: str
    entry_hash: str = ""

    def __post_init__(self) -> None:
        expected = self.calculate_hash(
            index=self.index,
            uow_id=self.uow.H.identity,
            proposal_hash=proposal_digest(self.proposal),
            qc_hash=self.quorum_certificate.qc_hash,
            pre_state_hash=self.quorum_certificate.pre_state_hash,
            post_state_hash=self.quorum_certificate.committed_state_hash,
            pre_evidence_root=self.quorum_certificate.pre_evidence_root,
            post_evidence_root=self.quorum_certificate.expected_evidence_root,
            prev_entry_hash=self.prev_entry_hash,
        )
        if self.entry_hash and self.entry_hash != expected:
            raise ValueError("Journal entry hash does not match entry contents.")
        object.__setattr__(self, "entry_hash", expected)

    @staticmethod
    def calculate_hash(**payload: object) -> str:
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RoundResult:
    committed: bool
    reason: str
    votes: tuple[AuthorityVote, ...]
    quorum_certificate: Optional[QuorumCertificate]
    apply_results: Mapping[str, ApplyResult]
    reachable_nodes: tuple[str, ...]


class AuthorityNode:
    """One independent authority replica.

    Each node owns its own immutable WorldState reference, EvidenceLedger, vote
    locks, ruleset version, and local clock. Nodes never share a mutable ledger
    or vote map.
    """

    def __init__(
        self,
        node_id: str,
        initial_state: WorldState,
        *,
        ruleset_version: str = "uow-authority-v1",
        clock_start: int = 0,
        clock_stride: int = 1,
        clock_frozen: bool = False,
    ) -> None:
        self.node_id = node_id
        self.initial_state = _clone_state(initial_state)
        self.state = _clone_state(initial_state)
        self.ledger = EvidenceLedger()
        self.ruleset_version = ruleset_version
        self.mode = NodeMode.ACTIVE
        self.clock_ticks = int(clock_start)
        self.clock_stride = int(clock_stride)
        self.clock_frozen = bool(clock_frozen)
        self._vote_locks: dict[str, str] = {}
        self._applied_qcs: set[str] = set()

    def _tick(self) -> int:
        if not self.clock_frozen:
            self.clock_ticks += self.clock_stride
        return self.clock_ticks

    def set_clock(self, *, stride: Optional[int] = None, frozen: Optional[bool] = None) -> None:
        if stride is not None:
            self.clock_stride = int(stride)
        if frozen is not None:
            self.clock_frozen = bool(frozen)

    def quarantine(self) -> None:
        self.mode = NodeMode.QUARANTINED

    def activate(self) -> None:
        self.mode = NodeMode.ACTIVE

    def snapshot(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "mode": self.mode.value,
            "state_hash": self.state.state_hash,
            "sequence": self.state.sequence,
            "evidence_root": self.ledger.root_hash(),
            "evidence_steps": len(self.ledger.records),
            "ruleset_version": self.ruleset_version,
            "local_clock": self.clock_ticks,
        }

    def evaluate(self, uow: UoW, proposal: Proposal) -> AuthorityVote:
        now = self._tick()
        digest = proposal_digest(proposal)
        root = self.ledger.root_hash()
        evidence_step = len(self.ledger.records)

        def reject(reason: str) -> AuthorityVote:
            return AuthorityVote(
                node_id=self.node_id,
                accepted=False,
                proposal_hash=digest,
                pre_state_hash=self.state.state_hash,
                proposed_state_hash=proposal.proposed_state.state_hash,
                certificate_hash="",
                pre_evidence_root=root,
                evidence_step=evidence_step,
                ruleset_version=self.ruleset_version,
                rejection_reason=reason,
                local_clock=now,
            )

        if self.mode is NodeMode.QUARANTINED:
            return reject("NODE_QUARANTINED")
        if proposal.pre_state_hash != self.state.state_hash:
            self.mode = NodeMode.STALE
            return reject("STALE_REPLICA")

        existing = self._vote_locks.get(self.state.state_hash)
        if existing is not None and existing != digest:
            return reject("CONFLICTING_VOTE_LOCK")

        certificate = certify(uow, self.state, proposal)
        if not certificate.is_valid:
            return reject(certificate.rejection_reason or "CERTIFICATION_REJECTED")

        self._vote_locks[self.state.state_hash] = digest
        return AuthorityVote(
            node_id=self.node_id,
            accepted=True,
            proposal_hash=digest,
            pre_state_hash=self.state.state_hash,
            proposed_state_hash=proposal.proposed_state.state_hash,
            certificate_hash=certificate.certificate_hash,
            pre_evidence_root=root,
            evidence_step=evidence_step,
            ruleset_version=self.ruleset_version,
            local_clock=now,
        )

    def verify_quorum_certificate(
        self,
        uow: UoW,
        proposal: Proposal,
        qc: QuorumCertificate,
    ) -> tuple[bool, str]:
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

        committed_state = proposal.proposed_state.advance_sequence()
        if committed_state.state_hash != qc.committed_state_hash:
            return False, "COMMITTED_STATE_HASH_MISMATCH"

        expected_evidence = EvidenceRecord(
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
        if expected_evidence.record_hash != qc.expected_evidence_root:
            return False, "EVIDENCE_ROOT_MISMATCH"

        expected_hash = QuorumCertificate.calculate_hash(
            proposal_hash=qc.proposal_hash,
            uow_id=qc.uow_id,
            pre_state_hash=qc.pre_state_hash,
            proposed_state_hash=qc.proposed_state_hash,
            committed_state_hash=qc.committed_state_hash,
            certificate_hash=qc.certificate_hash,
            pre_evidence_root=qc.pre_evidence_root,
            evidence_step=qc.evidence_step,
            expected_evidence_root=qc.expected_evidence_root,
            ruleset_version=qc.ruleset_version,
            threshold=qc.threshold,
            voters=qc.voters,
            vote_hashes=qc.vote_hashes,
        )
        if expected_hash != qc.qc_hash:
            return False, "QUORUM_CERTIFICATE_HASH_MISMATCH"
        return True, "OK"

    def apply_quorum_certificate(
        self,
        uow: UoW,
        proposal: Proposal,
        qc: QuorumCertificate,
    ) -> ApplyResult:
        if self.mode is NodeMode.QUARANTINED:
            return ApplyResult(
                self.node_id, False, False, "NODE_QUARANTINED",
                self.state.state_hash, self.ledger.root_hash(),
            )

        if qc.qc_hash in self._applied_qcs:
            return ApplyResult(
                self.node_id, False, True, "ALREADY_APPLIED",
                self.state.state_hash, self.ledger.root_hash(),
            )

        valid, reason = self.verify_quorum_certificate(uow, proposal, qc)
        if not valid:
            return ApplyResult(
                self.node_id, False, False, reason,
                self.state.state_hash, self.ledger.root_hash(),
            )

        if (
            self.state.state_hash == qc.committed_state_hash
            and self.ledger.root_hash() == qc.expected_evidence_root
        ):
            self._applied_qcs.add(qc.qc_hash)
            self.mode = NodeMode.ACTIVE
            return ApplyResult(
                self.node_id, False, True, "STATE_ALREADY_AT_QUORUM_TIP",
                self.state.state_hash, self.ledger.root_hash(),
            )

        if self.state.state_hash != qc.pre_state_hash:
            self.mode = NodeMode.STALE
            return ApplyResult(
                self.node_id, False, False, "PRE_STATE_MISMATCH",
                self.state.state_hash, self.ledger.root_hash(),
            )
        if self.ledger.root_hash() != qc.pre_evidence_root:
            self.mode = NodeMode.QUARANTINED
            return ApplyResult(
                self.node_id, False, False, "PRE_EVIDENCE_ROOT_MISMATCH",
                self.state.state_hash, self.ledger.root_hash(),
            )
        if len(self.ledger.records) != qc.evidence_step:
            self.mode = NodeMode.QUARANTINED
            return ApplyResult(
                self.node_id, False, False, "EVIDENCE_STEP_MISMATCH",
                self.state.state_hash, self.ledger.root_hash(),
            )

        certificate = certify(uow, self.state, proposal)
        if not certificate.is_valid or certificate.certificate_hash != qc.certificate_hash:
            return ApplyResult(
                self.node_id, False, False, "LOCAL_RECERTIFICATION_FAILED",
                self.state.state_hash, self.ledger.root_hash(),
            )

        committed, evidence = commit(
            uow,
            self.state,
            proposal,
            certificate,
            prev_evidence_hash=self.ledger.root_hash(),
            step_number=len(self.ledger.records) + 1,
        )
        if committed.state_hash != qc.committed_state_hash:
            raise AssertionError("Local deterministic commit disagrees with quorum certificate.")
        if evidence.record_hash != qc.expected_evidence_root:
            raise AssertionError("Local deterministic evidence disagrees with quorum certificate.")

        self.ledger.append(evidence)
        self.state = committed
        self._applied_qcs.add(qc.qc_hash)
        self.mode = NodeMode.ACTIVE
        return ApplyResult(
            self.node_id, True, False, "APPLIED",
            self.state.state_hash, self.ledger.root_hash(),
        )


def _vote_group_key(vote: AuthorityVote) -> tuple[object, ...]:
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
    accepted = [vote for vote in votes if vote.accepted]
    groups: dict[tuple[object, ...], list[AuthorityVote]] = {}
    for vote in accepted:
        groups.setdefault(_vote_group_key(vote), []).append(vote)
    if not groups:
        return None

    matching = max(groups.values(), key=lambda group: (len(group), tuple(sorted(v.node_id for v in group))))
    unique = {vote.node_id: vote for vote in matching}
    if len(unique) < threshold:
        return None

    selected = [unique[node_id] for node_id in sorted(unique)]
    first = selected[0]
    if first.proposal_hash != proposal_digest(proposal):
        return None

    committed_state = proposal.proposed_state.advance_sequence()
    expected_evidence = EvidenceRecord(
        step_number=first.evidence_step + 1,
        uow_id=uow.H.identity,
        source_category=uow.H.source_category.value,
        target_category=uow.H.target_category.value,
        pre_state_hash=first.pre_state_hash,
        selected_route_index=proposal.selected_route_index,
        proposed_state_hash=proposal.proposed_state.state_hash,
        certificate_hash=first.certificate_hash,
        post_state_hash=committed_state.state_hash,
        next_uow_pointer=proposal.selected_successor,
        prev_evidence_hash=first.pre_evidence_root,
    )
    return QuorumCertificate(
        proposal_hash=first.proposal_hash,
        uow_id=uow.H.identity,
        pre_state_hash=first.pre_state_hash,
        proposed_state_hash=first.proposed_state_hash,
        committed_state_hash=committed_state.state_hash,
        certificate_hash=first.certificate_hash,
        pre_evidence_root=first.pre_evidence_root,
        evidence_step=first.evidence_step,
        expected_evidence_root=expected_evidence.record_hash,
        ruleset_version=first.ruleset_version,
        threshold=threshold,
        voters=tuple(v.node_id for v in selected),
        vote_hashes=tuple(v.vote_hash for v in selected),
    )


class DistributedAuthorityCluster:
    """Qualification harness around independent authority nodes and network fabric."""

    def __init__(
        self,
        nodes: Iterable[AuthorityNode],
        network: NetworkFabric,
        *,
        threshold: int,
        ingress: str = "P",
    ) -> None:
        self.nodes = {node.node_id: node for node in nodes}
        if threshold < 1 or threshold > len(self.nodes):
            raise ValueError("Invalid quorum threshold.")
        self.threshold = threshold
        self.network = network
        self.ingress = ingress
        self.journal: list[JournalEntry] = []
        self._initial_states = {
            node_id: _clone_state(node.initial_state)
            for node_id, node in self.nodes.items()
        }

    def reachable_nodes(self, ingress: Optional[str] = None) -> tuple[str, ...]:
        source = ingress or self.ingress
        return tuple(
            node_id
            for node_id in sorted(self.nodes)
            if self.network.route(source, node_id) is not None
        )

    def collect_votes(
        self,
        uow: UoW,
        proposal: Proposal,
        *,
        ingress: Optional[str] = None,
    ) -> tuple[AuthorityVote, ...]:
        return tuple(
            self.nodes[node_id].evaluate(uow, proposal)
            for node_id in self.reachable_nodes(ingress)
        )

    def submit(
        self,
        uow: UoW,
        proposal: Proposal,
        *,
        ingress: Optional[str] = None,
    ) -> RoundResult:
        reachable = self.reachable_nodes(ingress)
        votes = tuple(self.nodes[node_id].evaluate(uow, proposal) for node_id in reachable)
        qc = form_quorum_certificate(uow, proposal, votes, self.threshold)
        if qc is None:
            return RoundResult(
                committed=False,
                reason="NO_QUORUM",
                votes=votes,
                quorum_certificate=None,
                apply_results={},
                reachable_nodes=reachable,
            )

        apply_results: dict[str, ApplyResult] = {}
        for node_id in reachable:
            apply_results[node_id] = self.nodes[node_id].apply_quorum_certificate(uow, proposal, qc)

        entry = JournalEntry(
            index=len(self.journal) + 1,
            uow=uow,
            proposal=proposal,
            quorum_certificate=qc,
            prev_entry_hash=self.journal_root(),
        )
        self.journal.append(entry)
        return RoundResult(
            committed=True,
            reason="QUORUM_CERTIFIED",
            votes=votes,
            quorum_certificate=qc,
            apply_results=apply_results,
            reachable_nodes=reachable,
        )

    def journal_root(self) -> str:
        return self.journal[-1].entry_hash if self.journal else "0" * 64

    def verify_journal(self) -> bool:
        previous = "0" * 64
        for index, entry in enumerate(self.journal, start=1):
            if entry.index != index or entry.prev_entry_hash != previous:
                return False
            expected = JournalEntry.calculate_hash(
                index=entry.index,
                uow_id=entry.uow.H.identity,
                proposal_hash=proposal_digest(entry.proposal),
                qc_hash=entry.quorum_certificate.qc_hash,
                pre_state_hash=entry.quorum_certificate.pre_state_hash,
                post_state_hash=entry.quorum_certificate.committed_state_hash,
                pre_evidence_root=entry.quorum_certificate.pre_evidence_root,
                post_evidence_root=entry.quorum_certificate.expected_evidence_root,
                prev_entry_hash=entry.prev_entry_hash,
            )
            if expected != entry.entry_hash:
                return False
            previous = entry.entry_hash
        return True

    def expected_tip(self) -> tuple[str, str, int]:
        if not self.journal:
            node_id = sorted(self.nodes)[0]
            initial = self._initial_states[node_id]
            return initial.state_hash, "0" * 64, 0
        qc = self.journal[-1].quorum_certificate
        return qc.committed_state_hash, qc.expected_evidence_root, qc.evidence_step + 1

    def prefix_index_for(self, node: AuthorityNode) -> Optional[int]:
        initial = self._initial_states[node.node_id]
        if (
            node.state.state_hash == initial.state_hash
            and node.ledger.root_hash() == "0" * 64
            and len(node.ledger.records) == 0
        ):
            return 0
        for index, entry in enumerate(self.journal, start=1):
            qc = entry.quorum_certificate
            if (
                node.state.state_hash == qc.committed_state_hash
                and node.ledger.root_hash() == qc.expected_evidence_root
                and len(node.ledger.records) == qc.evidence_step + 1
            ):
                return index
        return None

    def replace_node(self, node_id: str, replacement: AuthorityNode) -> None:
        if node_id != replacement.node_id:
            raise ValueError("Replacement node identity mismatch.")
        self.nodes[node_id] = replacement
