"""R4 U12 transactional-concurrency reconstruction.

Concurrent workers compute proposals/transaction descriptors from one base snapshot.
Authoritative application is serialized only after core conformance + OCC conformance.
The canonical sequencer commit implementation is not used.

This demonstrates a typed causal context: a proposal may be stale by whole-state
hash yet remain transaction-compatible when its read/write/coupling versions
still satisfy OCC.
"""
from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass
import random
import threading
import time
from typing import Mapping, Sequence, Tuple

from uow.contracts import UoW
from uow.engine import Proposal, propose
from uow.state import WorldState
from uow.transactions.descriptor import TransactionDescriptor, create_transaction_descriptor
from uow.transactions.occ import apply_transaction

from .adapters import adapt_world_state, core_certify_adapter, occ_adapter
from .identity import shadow_identity
from .kernel import apply_authorized_transition, authorize_local_conformance
from .types import (
    CausalCoordinate,
    ConformanceDecision,
    ConformanceResult,
    EvidenceEntryRef,
    ProposalEnvelope,
)


@dataclass(frozen=True)
class PreparedTransaction:
    task_id: str
    uow: UoW
    proposal: Proposal
    tx: TransactionDescriptor
    core_conformance: ConformanceResult
    worker_thread_id: int


@dataclass(frozen=True)
class TransactionBatchResult:
    final_state: WorldState
    evidence: Tuple[EvidenceEntryRef, ...]
    committed: Tuple[str, ...]
    conflicts: Tuple[Tuple[str, str], ...]
    worker_thread_ids: Tuple[int, ...]

    def evidence_root(self) -> str:
        return shadow_identity(
            "transaction-batch-evidence-root",
            tuple(entry.entry_identity for entry in self.evidence),
        )


def _combined_transaction_conformance(
    prepared: PreparedTransaction,
    current_state: WorldState,
    occ: ConformanceResult,
    committed_mirror: WorldState,
) -> ConformanceResult:
    violations = tuple(prepared.core_conformance.violations) + tuple(occ.violations)
    decision = (
        ConformanceDecision.ACCEPT
        if prepared.core_conformance.accepted and occ.accepted
        else ConformanceDecision.REJECT
    )
    cid = shadow_identity(
        "transaction-composite-conformance",
        {
            "task_id": prepared.task_id,
            "base_state_hash": prepared.proposal.pre_state_hash,
            "current_state_hash": current_state.state_hash,
            "core_conformance": prepared.core_conformance.conformance_id,
            "occ_conformance": occ.conformance_id,
            "candidate_committed_state": committed_mirror.state_hash,
            "decision": decision.value,
            "violations": violations,
        },
    )
    return ConformanceResult(
        conformance_id=cid,
        subject_id=committed_mirror.state_hash,
        contract_id=f"transaction::{prepared.uow.H.identity}",
        context_id=current_state.state_hash,
        decision=decision,
        violations=violations,
        evidence={
            "core_conformance_id": prepared.core_conformance.conformance_id,
            "occ_conformance_id": occ.conformance_id,
            "proposal_base_state_hash": prepared.proposal.pre_state_hash,
            "transaction_base_sequence": prepared.tx.base_sequence,
        },
        source_validator="r4.composite(core_certify+OCC)",
    )


def _transaction_application_envelope(
    prepared: PreparedTransaction,
    current_state: WorldState,
    committed_mirror: WorldState,
) -> ProposalEnvelope:
    payload = {
        "proposed_state_id": committed_mirror.state_hash,
        "committed_state_id": committed_mirror.state_hash,
        "next_semantic_payload": dict(committed_mirror.attributes),
        "next_status": committed_mirror.status,
        "next_cursor": committed_mirror.cursor,
    }
    pid = shadow_identity(
        "transaction-application-proposal",
        {
            "task_id": prepared.task_id,
            "current_state_hash": current_state.state_hash,
            "original_base_state_hash": prepared.proposal.pre_state_hash,
            "transaction": {
                "read_set": prepared.tx.read_set,
                "write_set": prepared.tx.write_set,
                "coupled_set": prepared.tx.coupled_set,
            },
            "payload": payload,
        },
    )
    return ProposalEnvelope(
        proposal_id=pid,
        proposal_kind="OCC_TRANSACTION_APPLICATION",
        proposer_id="r4-transaction-application",
        subject_contract_id=f"transaction::{prepared.uow.H.identity}",
        precondition_context_id=current_state.state_hash,
        causal_coordinate=CausalCoordinate("occ_current_state_hash", current_state.state_hash),
        candidate_payload=payload,
        proposal_identity=pid,
        metadata={
            "original_base_state_hash": prepared.proposal.pre_state_hash,
            "transaction_base_sequence": prepared.tx.base_sequence,
        },
        source_type="r4.u12.transaction",
    )


def prepare_parallel_transactions(
    graph: Mapping[str, UoW],
    task_ids: Sequence[str],
    base_state: WorldState,
    *,
    inject_entropy: bool = False,
    seed: int = 0,
) -> Tuple[PreparedTransaction, ...]:
    """Compute candidate transactions concurrently from one authoritative snapshot."""
    if not task_ids:
        return ()

    barrier = threading.Barrier(len(task_ids))
    rng = random.Random(seed)
    delays = {task_id: rng.uniform(0.001, 0.01) for task_id in task_ids}

    def worker(task_id: str) -> PreparedTransaction:
        barrier.wait(timeout=5)
        if inject_entropy:
            time.sleep(delays[task_id])
        uow = graph[task_id]
        proposal = propose(uow, base_state)
        tx = create_transaction_descriptor(uow, base_state)
        core = core_certify_adapter(uow, base_state, proposal)
        return PreparedTransaction(
            task_id=task_id,
            uow=uow,
            proposal=proposal,
            tx=tx,
            core_conformance=core,
            worker_thread_id=threading.get_ident(),
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(task_ids)) as executor:
        futures = {task_id: executor.submit(worker, task_id) for task_id in task_ids}
        # Return in deterministic task order independent of worker completion timing.
        return tuple(futures[task_id].result() for task_id in sorted(task_ids))


def apply_prepared_transactions(
    prepared: Sequence[PreparedTransaction],
    initial_state: WorldState,
) -> TransactionBatchResult:
    state = initial_state
    evidence = []
    committed = []
    conflicts = []

    for item in prepared:
        if not item.core_conformance.accepted:
            conflicts.append((item.task_id, "CORE_CONFORMANCE_REJECTED"))
            continue

        occ = occ_adapter(state, item.tx)
        if not occ.accepted:
            reason = occ.violations[0] if occ.violations else "OCC_REJECTED"
            conflicts.append((item.task_id, reason))
            continue

        committed_mirror = apply_transaction(state, item.proposal, item.tx)
        combined = _combined_transaction_conformance(
            item,
            state,
            occ,
            committed_mirror,
        )
        authorization = authorize_local_conformance(
            combined,
            authority_id="occ-transaction-authority",
        )
        envelope = _transaction_application_envelope(
            item,
            state,
            committed_mirror,
        )
        after_ref, entry = apply_authorized_transition(
            adapt_world_state(state),
            envelope,
            combined,
            authorization,
            evidence_profile="SHADOW-U12-OCC-L2",
        )
        if after_ref.state_id != committed_mirror.state_hash:
            raise AssertionError("Shadow transaction application state identity divergence.")
        if dict(after_ref.semantic_payload) != dict(committed_mirror.attributes):
            raise AssertionError("Shadow transaction application payload divergence.")

        state = committed_mirror
        evidence.append(entry)
        committed.append(item.task_id)

    return TransactionBatchResult(
        final_state=state,
        evidence=tuple(evidence),
        committed=tuple(committed),
        conflicts=tuple(conflicts),
        worker_thread_ids=tuple(item.worker_thread_id for item in prepared),
    )


def run_parallel_transaction_batch_reconstructed(
    graph: Mapping[str, UoW],
    task_ids: Sequence[str],
    initial_state: WorldState,
    *,
    inject_entropy: bool = False,
    seed: int = 0,
) -> TransactionBatchResult:
    prepared = prepare_parallel_transactions(
        graph,
        task_ids,
        initial_state,
        inject_entropy=inject_entropy,
        seed=seed,
    )
    return apply_prepared_transactions(prepared, initial_state)
