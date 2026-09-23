"""R3 shadow closure experiments.

This module tests whether selected meta-runtime state transitions can be lowered
into ordinary canonical UoWs after an independent authorization or validation
artifact already exists. It deliberately does NOT claim closure of
authorization/attestation formation itself.
"""
from __future__ import annotations

from typing import Tuple

from uow.composition.mutation import RuntimeMutationQC
from uow.composition.substitution import GraphReplacementCertificate
from uow.contracts import Guard, GuardOp, Mutation, MutationOp, Route, Successor, UoW, make_uow
from uow.engine import CertificateResult, EvidenceRecord, commit, certify, propose
from uow.state import WorldState

from .types import ConformanceResult


META_ACTIVE_GRAPH_HASH = "__runtime_active_graph_hash__"
META_ACTIVE_BINDING_HASH = "__runtime_active_binding_hash__"
META_GENERATION = "__runtime_generation__"
META_SUBSTITUTION_EPOCH = "__runtime_substitution_epoch__"
META_HISTORY_PARENT = "__runtime_history_parent__"
META_AUTHORIZATION_HASH = "__runtime_authorization_hash__"
META_LAST_QC_HASH = "__runtime_last_mutation_qc_hash__"
META_LAST_SUBSTITUTION_CERT_HASH = "__runtime_last_substitution_certificate_hash__"
META_LAST_BINDING_CONFORMANCE = "__runtime_last_binding_conformance__"


def make_runtime_meta_state(
    *,
    active_graph_hash: str,
    active_binding_hash: str = "",
    generation: int = 0,
    substitution_epoch: int = 0,
    history_head: str = "",
    authorization_hash: str,
    cursor: str,
) -> WorldState:
    return WorldState(
        attributes={
            META_ACTIVE_GRAPH_HASH: active_graph_hash,
            META_ACTIVE_BINDING_HASH: active_binding_hash,
            META_GENERATION: generation,
            META_SUBSTITUTION_EPOCH: substitution_epoch,
            META_HISTORY_PARENT: history_head,
            META_AUTHORIZATION_HASH: authorization_hash,
        },
        cursor=cursor,
        status="RUNNING",
    )


def _execute_meta_uow(
    state: WorldState,
    uow: UoW,
    *,
    prev_evidence_hash: str,
    step_number: int,
) -> Tuple[WorldState, EvidenceRecord, CertificateResult]:
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
    return _execute_meta_uow(
        state,
        make_qc_authorized_runtime_mutation_uow(qc),
        prev_evidence_hash=prev_evidence_hash,
        step_number=step_number,
    )


def make_certified_graph_substitution_uow(cert: GraphReplacementCertificate) -> UoW:
    """Lower application of an accepted A2.1 graph-replacement certificate.

    The current A2.1 runtime treats an accepted GraphReplacementCertificate as
    sufficient authority for atomic active-graph substitution. This shadow
    lowering models only that application step, not certificate formation.
    """
    if not cert.is_accepted:
        raise ValueError("Rejected GraphReplacementCertificate cannot authorize substitution.")

    identity = f"shadow::apply-graph-substitution::{cert.certificate_id}"
    mutations = [
        Mutation(MutationOp.SET, META_ACTIVE_GRAPH_HASH, cert.candidate_graph_hash),
        Mutation(MutationOp.SET, META_SUBSTITUTION_EPOCH, cert.epoch),
        Mutation(MutationOp.SET, META_LAST_SUBSTITUTION_CERT_HASH, cert.compute_hash()),
    ]
    if cert.actor_binding_hash:
        mutations.append(
            Mutation(MutationOp.SET, META_ACTIVE_BINDING_HASH, cert.actor_binding_hash)
        )

    return make_uow(
        identity,
        [
            Route(
                guard=Guard(
                    GuardOp.EQ,
                    META_AUTHORIZATION_HASH,
                    cert.compute_hash(),
                ),
                mutations=tuple(mutations),
                successor=Successor.halt(),
            )
        ],
        layer="shadow-meta",
        parent_context="A2.1-graph-substitution-closure",
    )


def execute_certified_graph_substitution(
    state: WorldState,
    cert: GraphReplacementCertificate,
    *,
    prev_evidence_hash: str = "0" * 64,
    step_number: int = 1,
) -> Tuple[WorldState, EvidenceRecord, CertificateResult]:
    return _execute_meta_uow(
        state,
        make_certified_graph_substitution_uow(cert),
        prev_evidence_hash=prev_evidence_hash,
        step_number=step_number,
    )


def make_validated_rebinding_uow(
    *,
    active_graph_hash: str,
    candidate_binding_hash: str,
    conformance: ConformanceResult,
) -> UoW:
    """Lower tier-1 actor rebinding application into an ordinary UoW.

    Canonical A2 rebinding validates against the live active graph and applies
    the binding immediately. The shadow lowering therefore binds the native UoW
    guard to the exact graph hash that the accepted ConformanceResult evaluated.

    The conformance identity is recorded in the resulting state/evidence, but
    this still does NOT create a standalone authority artifact where the
    canonical runtime has none. The result is behavioral/causal closure, not
    full authority-equivalence.
    """
    if not conformance.accepted:
        raise ValueError("Rejected binding conformance cannot permit shadow rebinding.")
    if conformance.context_id != active_graph_hash:
        raise ValueError(
            "Binding conformance is not bound to the active graph hash supplied for rebinding."
        )

    identity = (
        f"shadow::apply-rebinding::{candidate_binding_hash[:12]}::"
        f"{conformance.conformance_id[:12]}"
    )
    return make_uow(
        identity,
        [
            Route(
                guard=Guard(
                    GuardOp.EQ,
                    META_ACTIVE_GRAPH_HASH,
                    active_graph_hash,
                ),
                mutations=(
                    Mutation(MutationOp.SET, META_ACTIVE_BINDING_HASH, candidate_binding_hash),
                    Mutation(
                        MutationOp.SET,
                        META_LAST_BINDING_CONFORMANCE,
                        conformance.conformance_id,
                    ),
                ),
                successor=Successor.halt(),
            )
        ],
        layer="shadow-meta",
        parent_context=f"A2.2-A2.3-rebinding-closure::{conformance.conformance_id}",
    )


def execute_validated_rebinding(
    state: WorldState,
    *,
    active_graph_hash: str,
    candidate_binding_hash: str,
    conformance: ConformanceResult,
    prev_evidence_hash: str = "0" * 64,
    step_number: int = 1,
) -> Tuple[WorldState, EvidenceRecord, CertificateResult]:
    return _execute_meta_uow(
        state,
        make_validated_rebinding_uow(
            active_graph_hash=active_graph_hash,
            candidate_binding_hash=candidate_binding_hash,
            conformance=conformance,
        ),
        prev_evidence_hash=prev_evidence_hash,
        step_number=step_number,
    )
