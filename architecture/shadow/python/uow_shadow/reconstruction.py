"""R4 experiment reconstruction helpers using the R3 minimal authority kernel.

The native UoW contract, pure proposal computation, and deterministic certifier
remain the initial semantic oracle. The canonical commit implementation is NOT
used. Accepted transitions are applied by the shadow authority kernel.

This is the first step toward reconstructing the experiment set from the minimal
invariant architecture without prematurely replacing proven proposal/certifier logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Tuple

from uow.contracts import UoW
from uow.engine import Proposal, propose, validate_graph
from uow.state import WorldState

from .adapters import adapt_world_state, core_certify_adapter
from .identity import shadow_identity
from .kernel import apply_authorized_transition, authorize_local_conformance
from .types import CausalCoordinate, EvidenceEntryRef, ProposalEnvelope


@dataclass(frozen=True)
class ReconstructionResult:
    final_state: WorldState
    evidence: Tuple[EvidenceEntryRef, ...]
    steps: int

    def evidence_root(self) -> str:
        return shadow_identity(
            "reconstruction-evidence-root",
            tuple(entry.entry_identity for entry in self.evidence),
        )


def _proposal_envelope(
    before: WorldState,
    proposal: Proposal,
) -> tuple[ProposalEnvelope, WorldState]:
    """Bind canonical proposal semantics into the R2 proposal shape.

    The authoritative post-state identity is computed independently of the
    canonical commit function by applying the canonical sequence advance to the
    pure proposed state.
    """
    committed_mirror = proposal.proposed_state.advance_sequence()
    payload = {
        "proposed_state_id": proposal.proposed_state.state_hash,
        "committed_state_id": committed_mirror.state_hash,
        "next_semantic_payload": dict(committed_mirror.attributes),
        "next_status": committed_mirror.status,
        "next_cursor": committed_mirror.cursor,
    }
    proposal_id = shadow_identity(
        "reconstruction-proposal",
        {
            "uow_id": proposal.uow_id,
            "pre_state_hash": proposal.pre_state_hash,
            "selected_route_index": proposal.selected_route_index,
            "selected_successor": proposal.selected_successor,
            "halted": proposal.halted,
            "payload": payload,
        },
    )
    envelope = ProposalEnvelope(
        proposal_id=proposal_id,
        proposal_kind="STATE_TRANSITION",
        proposer_id="canonical-native-proposer",
        subject_contract_id=proposal.uow_id,
        precondition_context_id=before.state_hash,
        causal_coordinate=CausalCoordinate("pre_state_hash", before.state_hash),
        candidate_payload=payload,
        proposal_identity=proposal_id,
        source_type="r4.reconstruction",
    )
    return envelope, committed_mirror


def execute_one_reconstructed(
    graph: Mapping[str, UoW],
    state: WorldState,
) -> tuple[WorldState, EvidenceEntryRef]:
    if state.cursor is None or state.status != "RUNNING":
        raise ValueError("Reconstruction step requires a RUNNING state with an active cursor.")
    if state.cursor not in graph:
        raise KeyError(f"Current UoW cursor {state.cursor!r} does not exist in graph.")

    uow = graph[state.cursor]
    proposal = propose(uow, state)
    conformance = core_certify_adapter(uow, state, proposal)
    if not conformance.accepted:
        raise ValueError(f"Canonical conformance rejected reconstruction proposal: {conformance.violations}")
    authorization = authorize_local_conformance(conformance)
    envelope, committed_mirror = _proposal_envelope(state, proposal)

    after_ref, evidence = apply_authorized_transition(
        adapt_world_state(state),
        envelope,
        conformance,
        authorization,
    )

    # Semantic parity checks against the independently derived committed mirror.
    if dict(after_ref.semantic_payload) != dict(committed_mirror.attributes):
        raise AssertionError("Shadow kernel payload diverged from native proposed transition semantics.")
    if after_ref.cursor != committed_mirror.cursor:
        raise AssertionError("Shadow kernel cursor diverged from native proposed transition semantics.")
    if after_ref.status != committed_mirror.status:
        raise AssertionError("Shadow kernel status diverged from native proposed transition semantics.")
    if int(after_ref.causal_coordinate.value) != committed_mirror.sequence:
        raise AssertionError("Shadow kernel sequence diverged from native sequence semantics.")
    if after_ref.state_id != committed_mirror.state_hash:
        raise AssertionError("Shadow kernel post-state identity diverged from canonical WorldState identity.")

    return committed_mirror, evidence


def run_reconstructed(
    graph: Mapping[str, UoW],
    initial_state: WorldState,
    *,
    max_steps: int = 1_000_000,
) -> ReconstructionResult:
    validate_graph(dict(graph))
    state = initial_state
    evidence = []

    for step in range(max_steps):
        if state.cursor is None or state.status != "RUNNING":
            return ReconstructionResult(state, tuple(evidence), step)
        state, entry = execute_one_reconstructed(graph, state)
        evidence.append(entry)

    raise RuntimeError(f"Reconstruction step budget {max_steps} exceeded.")


def run_reconstructed_steps(
    graph: Mapping[str, UoW],
    initial_state: WorldState,
    *,
    steps: int,
) -> ReconstructionResult:
    validate_graph(dict(graph))
    state = initial_state
    evidence = []

    for _ in range(steps):
        if state.cursor is None or state.status != "RUNNING":
            break
        state, entry = execute_one_reconstructed(graph, state)
        evidence.append(entry)

    return ReconstructionResult(state, tuple(evidence), len(evidence))
