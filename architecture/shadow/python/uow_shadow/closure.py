"""R3 shadow closure experiments.

This module tests whether selected meta-runtime state transitions can be lowered
into ordinary canonical UoWs after an independent authorization artifact already
exists. It deliberately does NOT claim closure of quorum formation itself.
"""
from __future__ import annotations

from typing import Tuple

from uow.composition.mutation import RuntimeMutationQC
from uow.contracts import Guard, GuardOp, Mutation, MutationOp, Route, Successor, UoW, make_uow
from uow.engine import CertificateResult, EvidenceRecord, commit, certify, propose
from uow.state import WorldState


META_ACTIVE_GRAPH_HASH = "__runtime_active_graph_hash__"
META_ACTIVE_BINDING_HASH = "__runtime_active_binding_hash__"
META_GENERATION = "__runtime_generation__"
META_HISTORY_PARENT = "__runtime_history_parent__"
META_AUTHORIZATION_HASH = "__runtime_authorization_hash__"
META_LAST_QC_HASH = "__runtime_last_mutation_qc_hash__"


def make_runtime_meta_state(
    *,
    active_graph_hash: str,
    active_binding_hash: str,
    generation: int,
    history_head: str,
    authorization_hash: str,
    cursor: str,
) -> WorldState:
    return WorldState(
        attributes={
            META_ACTIVE_GRAPH_HASH: active_graph_hash,
            META_ACTIVE_BINDING_HASH: active_binding_hash,
            META_GENERATION: generation,
            META_HISTORY_PARENT: history_head,
            META_AUTHORIZATION_HASH: authorization_hash,
        },
        cursor=cursor,
        status="RUNNING",
    )


def make_qc_authorized_runtime_mutation_uow(qc: RuntimeMutationQC) -> UoW:
    """Lower QC-authorized graph/binding application into an ordinary UoW.

    This tests closure of mutation application only. QC formation, signature
    verification, and distributed-history construction remain outside this
    shadow lowering and must already have produced a valid authorization.
    """
    identity = f"shadow::apply-runtime-mutation::{qc.qc_id}"
    return make_uow(
        identity,
        [
            Route(
                guard=Guard(
                    GuardOp.EQ,
                    META_AUTHORIZATION_HASH,
                    qc.compute_hash(),
                ),
                mutations=(
                    Mutation(MutationOp.SET, META_ACTIVE_GRAPH_HASH, qc.candidate_graph_hash),
                    Mutation(MutationOp.SET, META_ACTIVE_BINDING_HASH, qc.candidate_binding_hash),
                    Mutation(MutationOp.ADD, META_GENERATION, 1),
                    Mutation(MutationOp.SET, META_HISTORY_PARENT, qc.history_head),
                    Mutation(MutationOp.SET, META_LAST_QC_HASH, qc.compute_hash()),
                ),
                successor=Successor.halt(),
            )
        ],
        layer="shadow-meta",
        parent_context="A2.7-runtime-mutation-closure",
    )


def execute_qc_authorized_runtime_mutation(
    state: WorldState,
    qc: RuntimeMutationQC,
    *,
    prev_evidence_hash: str = "0" * 64,
    step_number: int = 1,
) -> Tuple[WorldState, EvidenceRecord, CertificateResult]:
    uow = make_qc_authorized_runtime_mutation_uow(qc)
    proposal = propose(uow, state)
    certificate = certify(uow, state, proposal)
    committed, evidence = commit(
        uow,
        state,
        proposal,
        certificate,
        prev_evidence_hash=prev_evidence_hash,
        step_number=step_number,
    )
    return committed, evidence, certificate
