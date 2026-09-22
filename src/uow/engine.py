"""Deterministic PROPOSE -> CERTIFY -> COMMIT kernel."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Dict, List, Optional, Tuple

from .contracts import SuccessorKind, UoW
from .state import WorldState, canonical_json

UoWGraph = Dict[str, UoW]


@dataclass(frozen=True)
class Proposal:
    uow_id: str
    pre_state_hash: str
    selected_route_index: int
    proposed_state: WorldState
    selected_successor: Optional[str]
    halted: bool


@dataclass(frozen=True)
class CertificateResult:
    is_valid: bool
    certificate_hash: str
    uow_id: str
    pre_state_hash: str
    proposed_state_hash: str
    selected_route_index: int
    selected_successor: Optional[str]
    halted: bool
    rejection_reason: Optional[str] = None


def _certificate_hash(
    *,
    uow_id: str,
    pre_state_hash: str,
    proposed_state_hash: str,
    selected_route_index: int,
    selected_successor: Optional[str],
    halted: bool,
) -> str:
    payload = {
        "uow_id": uow_id,
        "pre_state_hash": pre_state_hash,
        "proposed_state_hash": proposed_state_hash,
        "selected_route_index": selected_route_index,
        "selected_successor": selected_successor,
        "halted": halted,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidenceRecord:
    step_number: int
    uow_id: str
    source_category: str
    target_category: str
    pre_state_hash: str
    selected_route_index: int
    proposed_state_hash: str
    certificate_hash: str
    post_state_hash: str
    next_uow_pointer: Optional[str]
    prev_evidence_hash: str
    record_hash: str = ""

    def __post_init__(self) -> None:
        expected = self.calculate_hash(
            step_number=self.step_number,
            uow_id=self.uow_id,
            source_category=self.source_category,
            target_category=self.target_category,
            pre_state_hash=self.pre_state_hash,
            selected_route_index=self.selected_route_index,
            proposed_state_hash=self.proposed_state_hash,
            certificate_hash=self.certificate_hash,
            post_state_hash=self.post_state_hash,
            next_uow_pointer=self.next_uow_pointer,
            prev_evidence_hash=self.prev_evidence_hash,
        )
        if self.record_hash and self.record_hash != expected:
            raise ValueError("Evidence record hash does not match its contents.")
        object.__setattr__(self, "record_hash", expected)

    @staticmethod
    def calculate_hash(**payload: object) -> str:
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class EvidenceLedger:
    """Append-only hash chain of committed transitions."""

    def __init__(self) -> None:
        self._records: List[EvidenceRecord] = []

    @property
    def records(self) -> Tuple[EvidenceRecord, ...]:
        return tuple(self._records)

    def root_hash(self) -> str:
        return self._records[-1].record_hash if self._records else "0" * 64

    def append(self, record: EvidenceRecord) -> None:
        if record.prev_evidence_hash != self.root_hash():
            raise ValueError("Evidence record does not extend the current ledger root.")
        if record.step_number != len(self._records) + 1:
            raise ValueError("Evidence step number is not contiguous.")
        self._records.append(record)

    def verify_integrity(self) -> bool:
        previous = "0" * 64
        for index, record in enumerate(self._records, start=1):
            if record.step_number != index or record.prev_evidence_hash != previous:
                return False
            expected = EvidenceRecord.calculate_hash(
                step_number=record.step_number,
                uow_id=record.uow_id,
                source_category=record.source_category,
                target_category=record.target_category,
                pre_state_hash=record.pre_state_hash,
                selected_route_index=record.selected_route_index,
                proposed_state_hash=record.proposed_state_hash,
                certificate_hash=record.certificate_hash,
                post_state_hash=record.post_state_hash,
                next_uow_pointer=record.next_uow_pointer,
                prev_evidence_hash=record.prev_evidence_hash,
            )
            if record.record_hash != expected:
                return False
            previous = record.record_hash
        return True


def validate_graph(graph: UoWGraph) -> None:
    for identity, uow in graph.items():
        if identity != uow.H.identity:
            raise ValueError(
                f"Graph identity mismatch: key {identity!r} != UoW identity {uow.H.identity!r}."
            )
        uow.validate()
        for route in uow.Gamma.routes:
            if route.successor.kind is SuccessorKind.STATIC:
                target = route.successor.value
                if target not in graph:
                    raise ValueError(
                        f"Dangling static successor {target!r} referenced by {identity!r}."
                    )


def propose(uow: UoW, state: WorldState) -> Proposal:
    """Purely compute a candidate transition."""
    route_index, route = uow.Gamma.select_route(state)
    mutated = route.apply_mutations(state)
    successor = route.successor.resolve(mutated)
    halted = route.successor.kind is SuccessorKind.HALT

    if halted:
        status = mutated.status if mutated.status != "RUNNING" else "HALTED"
        proposed_state = mutated.with_status(status).with_cursor(None)
    elif route.successor.kind is SuccessorKind.PRESERVE:
        proposed_state = mutated.with_status(state.status).with_cursor(state.cursor)
    else:
        proposed_state = mutated.with_cursor(successor)

    return Proposal(
        uow_id=uow.H.identity,
        pre_state_hash=state.state_hash,
        selected_route_index=route_index,
        proposed_state=proposed_state,
        selected_successor=successor,
        halted=halted,
    )


def _reject(uow: UoW, before: WorldState, proposal: Proposal, reason: str) -> CertificateResult:
    return CertificateResult(
        is_valid=False,
        certificate_hash="",
        uow_id=uow.H.identity,
        pre_state_hash=before.state_hash,
        proposed_state_hash=proposal.proposed_state.state_hash,
        selected_route_index=proposal.selected_route_index,
        selected_successor=proposal.selected_successor,
        halted=proposal.halted,
        rejection_reason=reason,
    )


def certify(uow: UoW, before: WorldState, proposal: Proposal) -> CertificateResult:
    """Independently recompute a proposal and certify only exact agreement."""
    if proposal.uow_id != uow.H.identity:
        return _reject(uow, before, proposal, "UOW_IDENTITY_MISMATCH")
    if proposal.pre_state_hash != before.state_hash:
        return _reject(uow, before, proposal, "PRE_STATE_HASH_MISMATCH")

    try:
        expected = propose(uow, before)
    except Exception as exc:
        return _reject(uow, before, proposal, f"RECOMPUTATION_FAILED:{type(exc).__name__}")

    checks = (
        (proposal.selected_route_index == expected.selected_route_index, "ROUTE_DIVERGENCE"),
        (proposal.proposed_state.state_hash == expected.proposed_state.state_hash, "STATE_DIVERGENCE"),
        (proposal.selected_successor == expected.selected_successor, "SUCCESSOR_DIVERGENCE"),
        (proposal.halted == expected.halted, "HALT_DIVERGENCE"),
    )
    for valid, reason in checks:
        if not valid:
            return _reject(uow, before, proposal, reason)

    cert_hash = _certificate_hash(
        uow_id=uow.H.identity,
        pre_state_hash=before.state_hash,
        proposed_state_hash=proposal.proposed_state.state_hash,
        selected_route_index=proposal.selected_route_index,
        selected_successor=proposal.selected_successor,
        halted=proposal.halted,
    )
    return CertificateResult(
        is_valid=True,
        certificate_hash=cert_hash,
        uow_id=uow.H.identity,
        pre_state_hash=before.state_hash,
        proposed_state_hash=proposal.proposed_state.state_hash,
        selected_route_index=proposal.selected_route_index,
        selected_successor=proposal.selected_successor,
        halted=proposal.halted,
    )


def commit(
    uow: UoW,
    before: WorldState,
    proposal: Proposal,
    certificate: CertificateResult,
    *,
    prev_evidence_hash: str,
    step_number: int,
) -> tuple[WorldState, EvidenceRecord]:
    """Commit a certified proposal and emit its evidence record."""
    if not certificate.is_valid:
        raise ValueError(f"Cannot commit rejected proposal: {certificate.rejection_reason}")
    expected_cert_hash = _certificate_hash(
        uow_id=uow.H.identity,
        pre_state_hash=before.state_hash,
        proposed_state_hash=proposal.proposed_state.state_hash,
        selected_route_index=proposal.selected_route_index,
        selected_successor=proposal.selected_successor,
        halted=proposal.halted,
    )
    if certificate.certificate_hash != expected_cert_hash:
        raise ValueError("Certificate hash is not authentic for this transition.")
    if certificate.pre_state_hash != before.state_hash:
        raise ValueError("Certificate is not bound to the current pre-state.")
    if certificate.proposed_state_hash != proposal.proposed_state.state_hash:
        raise ValueError("Certificate is not bound to the proposed state.")

    committed = proposal.proposed_state.advance_sequence()
    evidence = EvidenceRecord(
        step_number=step_number,
        uow_id=uow.H.identity,
        source_category=uow.H.source_category.value,
        target_category=uow.H.target_category.value,
        pre_state_hash=before.state_hash,
        selected_route_index=proposal.selected_route_index,
        proposed_state_hash=proposal.proposed_state.state_hash,
        certificate_hash=certificate.certificate_hash,
        post_state_hash=committed.state_hash,
        next_uow_pointer=proposal.selected_successor,
        prev_evidence_hash=prev_evidence_hash,
    )
    return committed, evidence


def execute_one(graph: UoWGraph, state: WorldState, ledger: EvidenceLedger) -> WorldState:
    if state.cursor is None or state.status != "RUNNING":
        return state
    if state.cursor not in graph:
        raise KeyError(f"Current UoW cursor {state.cursor!r} does not exist in the graph.")

    uow = graph[state.cursor]
    proposal = propose(uow, state)
    certificate = certify(uow, state, proposal)
    committed, evidence = commit(
        uow,
        state,
        proposal,
        certificate,
        prev_evidence_hash=ledger.root_hash(),
        step_number=len(ledger.records) + 1,
    )
    ledger.append(evidence)
    return committed


def run(
    graph: UoWGraph,
    initial_state: WorldState,
    *,
    max_steps: int = 1_000_000,
    ledger: Optional[EvidenceLedger] = None,
) -> tuple[WorldState, EvidenceLedger]:
    validate_graph(graph)
    ledger = ledger or EvidenceLedger()
    state = initial_state

    for _ in range(max_steps):
        if state.cursor is None or state.status != "RUNNING":
            return state, ledger
        state = execute_one(graph, state, ledger)

    raise RuntimeError(f"Step budget {max_steps} exceeded.")
