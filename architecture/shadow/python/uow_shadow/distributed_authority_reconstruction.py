"""R4 portable distributed-authority reconstruction.

Independent replicas form AuthorityVote and QuorumCertificate objects using the
qualified attestation semantics, but authoritative application does not call
AuthorityNode.apply_quorum_certificate or uow.engine.commit.

Each replica applies a verified QC through the R3 minimal authority kernel and
maintains an independent canonical EvidenceLedger for subsequent quorum rounds.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, Mapping, Optional, Tuple

from qualification.distributed_authority.authority import (
    AuthorityVote,
    QuorumCertificate,
    form_quorum_certificate,
    proposal_digest,
)
from qualification.distributed_authority.network import NetworkFabric
from uow.contracts import UoW
from uow.engine import EvidenceLedger, EvidenceRecord, Proposal, certify
from uow.state import WorldState

from .adapters import adapt_world_state
from .identity import shadow_identity
from .kernel import LocalAuthorization, apply_authorized_transition
from .types import CausalCoordinate, ConformanceDecision, ConformanceResult, ProposalEnvelope


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
        self.node_id = node_id
        self.initial_state = WorldState(
            attributes=initial_state.to_dict()["attributes"],
            cursor=initial_state.cursor,
            status=initial_state.status,
            sequence=initial_state.sequence,
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
        network: NetworkFabric,
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
        # Determine whether node matches a valid journal prefix.
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
    fabric = NetworkFabric(("P", "A", "B", "C"))
    fabric.connect("P", "A")
    fabric.connect("P", "B")
    fabric.connect("A", "B")
    fabric.connect("A", "C")
    fabric.connect("B", "C")
    return ShadowDistributedAuthorityCluster(nodes, fabric, threshold=2)
