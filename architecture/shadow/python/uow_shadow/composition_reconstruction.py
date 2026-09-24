"""R4 A2 composition reconstruction helpers.

R3 closure helpers build ordinary UoWs for accepted meta-runtime changes. This
module applies those UoWs through the R3 minimal authority kernel rather than
through canonical uow.engine.commit.
"""
from __future__ import annotations

from typing import Tuple

from uow.composition.convergence import AuthoritativeHistory
from uow.composition.delegation import DelegationCertificate
from uow.composition.mutation import RuntimeMutationQC
from uow.composition.substitution import GraphReplacementCertificate
from uow.state import WorldState

from .closure import (
    make_certified_graph_substitution_uow,
    make_qc_authorized_runtime_mutation_uow,
    make_validated_delegation_registration_uow,
    make_validated_rebinding_uow,
    make_verified_history_reconciliation_uow,
)
from .reconstruction import execute_explicit_uow_reconstructed
from .types import ConformanceResult, EvidenceEntryRef


def apply_graph_substitution_reconstructed(
    state: WorldState,
    certificate: GraphReplacementCertificate,
) -> Tuple[WorldState, EvidenceEntryRef]:
    return execute_explicit_uow_reconstructed(
        make_certified_graph_substitution_uow(certificate),
        state,
    )


def apply_rebinding_reconstructed(
    state: WorldState,
    *,
    active_graph_hash: str,
    candidate_binding_hash: str,
    conformance: ConformanceResult,
) -> Tuple[WorldState, EvidenceEntryRef]:
    return execute_explicit_uow_reconstructed(
        make_validated_rebinding_uow(
            active_graph_hash=active_graph_hash,
            candidate_binding_hash=candidate_binding_hash,
            conformance=conformance,
        ),
        state,
    )


def apply_delegation_reconstructed(
    state: WorldState,
    certificate: DelegationCertificate,
    conformance: ConformanceResult,
) -> Tuple[WorldState, EvidenceEntryRef]:
    return execute_explicit_uow_reconstructed(
        make_validated_delegation_registration_uow(certificate, conformance),
        state,
    )


def apply_history_reconciliation_reconstructed(
    state: WorldState,
    canonical_history: AuthoritativeHistory,
) -> Tuple[WorldState, EvidenceEntryRef]:
    return execute_explicit_uow_reconstructed(
        make_verified_history_reconciliation_uow(canonical_history),
        state,
    )


def apply_runtime_mutation_reconstructed(
    state: WorldState,
    qc: RuntimeMutationQC,
) -> Tuple[WorldState, EvidenceEntryRef]:
    return execute_explicit_uow_reconstructed(
        make_qc_authorized_runtime_mutation_uow(qc),
        state,
    )
