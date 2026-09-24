from __future__ import annotations

from dataclasses import replace

import pytest

from uow.composition.binding import ActorBinding
from uow.composition.contract import AuthorityObligation, CausalConstraint, EvidenceObligation, ParentContract
from uow.composition.convergence import AuthoritativeHistory
from uow.composition.graph import RealizationGraph, RealizationNode
from uow.composition.mutation import (
    QuorumMutationCoordinator,
    assemble_mutation_qc,
)
from uow.state import WorldState

from uow_shadow.composition_reconstruction import apply_verified_runtime_mutation_reconstructed


def _contract() -> ParentContract:
    return ParentContract(
        contract_id="a2.7-reconstruct",
        description="A2.7 reconstructed mutation contract",
        required_outputs=("result",),
        causal_constraints=(
            CausalConstraint("parser", "worker"),
            CausalConstraint("worker", "verifier"),
            CausalConstraint("verifier", "commit"),
        ),
        authority=AuthorityObligation(required_role="verifier", min_evidence_level="portable"),
        evidence=EvidenceObligation(
            require_provenance=True,
            require_hash_chain=True,
            min_evidence_level="portable",
            verifier_id="judge",
        ),
    )


def _graph(graph_id: str, actor_class: str = "cpu", output: str = "result") -> RealizationGraph:
    return RealizationGraph(
        graph_id,
        {
            "parse": RealizationNode("parse", role="parser", actor_class="cpu"),
            "work": RealizationNode("work", role="worker", actor_class=actor_class),
            "verify": RealizationNode(
                "verify",
                role="verifier",
                actor_class="cpu",
                authority_tier="verifier",
            ),
            "commit": RealizationNode(
                "commit",
                role="commit",
                actor_class="cpu",
                outputs=(output,),
            ),
        },
        (("parse", "work"), ("work", "verify"), ("verify", "commit")),
    )


def _binding(graph: RealizationGraph, binding_id: str) -> ActorBinding:
    return ActorBinding(
        binding_id,
        graph.graph_id,
        {node_id: f"actor::{node_id}" for node_id in graph.nodes},
    )


def _setup():
    contract = _contract()
    g0 = _graph("G0")
    g1 = _graph("G1_npu", "npu")
    b0 = _binding(g0, "B0")
    b1 = _binding(g1, "B1")
    history = AuthoritativeHistory()
    keys = {"A": "key-A", "B": "key-B", "C": "key-C"}
    coordinator = QuorumMutationCoordinator(
        contract,
        g0,
        b0,
        history,
        keys,
        generation=0,
        quorum_threshold=2,
    )
    meta = WorldState(
        attributes={
            "__runtime_active_graph_hash__": g0.compute_hash(),
            "__runtime_active_binding_hash__": b0.compute_hash(),
            "__runtime_generation__": 0,
            "__runtime_history_parent__": history.tip_hash(),
        },
        cursor="runtime-controller",
        status="RUNNING",
    )
    return contract, g0, b0, g1, b1, history, keys, coordinator, meta


def test_r4_a2_7_proposal_has_zero_authority_then_qc_applies_through_minimal_kernel():
    contract, g0, b0, g1, b1, history, keys, coordinator, meta = _setup()

    proposal = coordinator.propose_mutation("adaptive-proposer", g1, b1)
    assert coordinator.active_graph.compute_hash() == g0.compute_hash()
    assert coordinator.active_binding.compute_hash() == b0.compute_hash()
    assert coordinator.generation == 0

    votes = coordinator.collect_votes(proposal)
    qc, reason = assemble_mutation_qc(proposal, votes, threshold=2)
    assert qc is not None, reason

    after, evidence = apply_verified_runtime_mutation_reconstructed(
        meta,
        qc,
        parent_contract=contract,
        candidate_graph=g1,
        candidate_binding=b1,
        authority_keys=keys,
        current_history_head=history.tip_hash(),
        current_generation=0,
    )

    assert after.get("__runtime_active_graph_hash__") == g1.compute_hash()
    assert after.get("__runtime_active_binding_hash__") == b1.compute_hash()
    assert after.get("__runtime_generation__") == 1
    assert after.cursor == "runtime-controller"
    assert after.status == "RUNNING"
    assert evidence.authorization_reference == qc.compute_hash()


def test_r4_a2_7_insufficient_quorum_has_no_application_artifact():
    contract, _, _, g1, b1, history, keys, coordinator, _ = _setup()
    proposal = coordinator.propose_mutation("adaptive-proposer", g1, b1)
    votes = coordinator.collect_votes(proposal)
    qc, reason = assemble_mutation_qc(proposal, votes[:1], threshold=2)

    assert qc is None
    assert "QUORUM_THRESHOLD_NOT_MET" in reason


def test_r4_a2_7_stale_history_qc_is_rejected_before_shadow_transition():
    contract, _, _, g1, b1, history, keys, coordinator, meta = _setup()
    proposal = coordinator.propose_mutation("adaptive-proposer", g1, b1)
    votes = coordinator.collect_votes(proposal)
    qc, _ = assemble_mutation_qc(proposal, votes, threshold=2)
    assert qc is not None

    with pytest.raises(ValueError, match="STALE_HISTORY_HEAD"):
        apply_verified_runtime_mutation_reconstructed(
            meta,
            qc,
            parent_contract=contract,
            candidate_graph=g1,
            candidate_binding=b1,
            authority_keys=keys,
            current_history_head="different-history-head",
            current_generation=0,
        )


def test_r4_a2_7_candidate_payload_tamper_is_rejected():
    contract, _, _, g1, b1, history, keys, coordinator, meta = _setup()
    proposal = coordinator.propose_mutation("adaptive-proposer", g1, b1)
    votes = coordinator.collect_votes(proposal)
    qc, _ = assemble_mutation_qc(proposal, votes, threshold=2)
    assert qc is not None

    tampered_graph = _graph("G_tampered", "cpu")
    with pytest.raises(ValueError, match="CANDIDATE_GRAPH_HASH_MISMATCH"):
        apply_verified_runtime_mutation_reconstructed(
            meta,
            qc,
            parent_contract=contract,
            candidate_graph=tampered_graph,
            candidate_binding=b1,
            authority_keys=keys,
            current_history_head=history.tip_hash(),
            current_generation=0,
        )


def test_r4_a2_7_semantically_invalid_candidate_never_forms_qc():
    contract, g0, b0, _, _, history, keys, _, _ = _setup()
    invalid = _graph("G_invalid", output="wrong")
    invalid_binding = _binding(invalid, "B_invalid")
    coordinator = QuorumMutationCoordinator(
        contract,
        g0,
        b0,
        history,
        keys,
        generation=0,
    )
    proposal = coordinator.propose_mutation("adaptive-proposer", invalid, invalid_binding)
    votes = coordinator.collect_votes(proposal)

    assert all(not v.accepted for v in votes)
    assert all("SEMANTIC_PROJECTION_MISMATCH" in (v.rejection_reason or "") for v in votes)
    qc, _ = assemble_mutation_qc(proposal, votes, threshold=2)
    assert qc is None
