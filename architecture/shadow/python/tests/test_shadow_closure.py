from __future__ import annotations

import pytest

from uow.composition.binding import ActorBinding
from uow.composition.contract import ParentContract
from uow.composition.convergence import AuthoritativeHistory
from uow.composition.graph import RealizationGraph, RealizationNode
from uow.composition.mutation import QuorumMutationCoordinator, assemble_mutation_qc
from uow.composition.runtime import AdaptiveCompositionRuntime
from uow.composition.substitution import GraphReplacementProposal, SubstitutionStrategy

from uow_shadow.closure import (
    META_ACTIVE_BINDING_HASH,
    META_ACTIVE_GRAPH_HASH,
    META_AUTHORIZATION_HASH,
    META_GENERATION,
    META_LAST_QC_HASH,
    META_LAST_SUBSTITUTION_CERT_HASH,
    META_SUBSTITUTION_EPOCH,
    execute_certified_graph_substitution,
    execute_qc_authorized_runtime_mutation,
    make_certified_graph_substitution_uow,
    make_qc_authorized_runtime_mutation_uow,
    make_runtime_meta_state,
)


def _graph(graph_id: str, with_worker: bool) -> RealizationGraph:
    authority = RealizationNode(
        node_id="authority",
        role="authority",
        authority_tier="deterministic_judge",
    )
    commit = RealizationNode(
        node_id="commit",
        role="commit",
        outputs=("result",),
    )
    nodes = {"authority": authority, "commit": commit}
    edges = [("authority", "commit")]

    if with_worker:
        worker = RealizationNode(node_id="worker", role="worker")
        nodes["worker"] = worker
        edges = [("authority", "worker"), ("worker", "commit")]

    return RealizationGraph(graph_id, nodes, tuple(edges))


def _binding(graph: RealizationGraph, binding_id: str) -> ActorBinding:
    return ActorBinding(
        binding_id,
        graph.graph_id,
        {node_id: f"actor::{node_id}" for node_id in graph.nodes},
    )


def _qualified_mutation():
    contract = ParentContract(
        contract_id="u-runtime",
        description="runtime mutation closure",
        required_outputs=("result",),
    )
    g0 = _graph("g0", False)
    g1 = _graph("g1", True)
    b0 = _binding(g0, "b0")
    b1 = _binding(g1, "b1")
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
    proposal = coordinator.propose_mutation("adaptive-proposer", g1, b1)
    votes = coordinator.collect_votes(proposal)
    qc, reason = assemble_mutation_qc(proposal, votes, threshold=2)
    assert qc is not None, reason
    return coordinator, g0, b0, g1, b1, qc


def test_qc_authorized_runtime_mutation_application_closes_over_native_uow():
    coordinator, g0, b0, g1, b1, qc = _qualified_mutation()

    canonical_ok, canonical_reason = coordinator.apply_mutation(qc, g1, b1)
    assert canonical_ok, canonical_reason

    uow = make_qc_authorized_runtime_mutation_uow(qc)
    shadow_state = make_runtime_meta_state(
        active_graph_hash=g0.compute_hash(),
        active_binding_hash=b0.compute_hash(),
        generation=0,
        history_head=qc.history_head,
        authorization_hash=qc.compute_hash(),
        cursor=uow.H.identity,
    )
    committed, evidence, certificate = execute_qc_authorized_runtime_mutation(shadow_state, qc)

    assert certificate.is_valid
    assert committed.get(META_ACTIVE_GRAPH_HASH) == coordinator.active_graph.compute_hash()
    assert committed.get(META_ACTIVE_BINDING_HASH) == coordinator.active_binding.compute_hash()
    assert committed.get(META_GENERATION) == coordinator.generation
    assert committed.get(META_LAST_QC_HASH) == qc.compute_hash()
    assert evidence.certificate_hash == certificate.certificate_hash


def test_runtime_mutation_lowering_fails_closed_on_wrong_authorization_hash():
    _, g0, b0, _, _, qc = _qualified_mutation()
    uow = make_qc_authorized_runtime_mutation_uow(qc)
    shadow_state = make_runtime_meta_state(
        active_graph_hash=g0.compute_hash(),
        active_binding_hash=b0.compute_hash(),
        generation=0,
        history_head=qc.history_head,
        authorization_hash="wrong-qc-hash",
        cursor=uow.H.identity,
    )

    with pytest.raises(RuntimeError, match="No applicable route"):
        execute_qc_authorized_runtime_mutation(shadow_state, qc)

    assert shadow_state.get(META_ACTIVE_GRAPH_HASH) == g0.compute_hash()
    assert shadow_state.get(META_ACTIVE_BINDING_HASH) == b0.compute_hash()
    assert shadow_state.get(META_GENERATION) == 0
    assert shadow_state.get(META_AUTHORIZATION_HASH) == "wrong-qc-hash"


def _certified_substitution(stale: bool = False):
    contract = ParentContract(
        contract_id="u-sub",
        description="graph substitution closure",
        required_outputs=("result",),
    )
    g0 = _graph("g0-sub", False)
    g1 = _graph("g1-sub", True)
    runtime = AdaptiveCompositionRuntime(contract, g0)

    proposal = GraphReplacementProposal(
        parent_contract_id=contract.contract_id,
        current_graph_hash="stale-hash" if stale else g0.compute_hash(),
        candidate_graph=g1,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        proposal_id="sub-1",
    )
    cert = runtime.propose_and_certify(proposal)
    return runtime, g0, g1, cert


def test_accepted_graph_substitution_application_closes_over_native_uow():
    runtime, g0, g1, cert = _certified_substitution(stale=False)
    assert cert.is_accepted
    assert runtime.active_graph.compute_hash() == g1.compute_hash()

    uow = make_certified_graph_substitution_uow(cert)
    shadow_state = make_runtime_meta_state(
        active_graph_hash=g0.compute_hash(),
        authorization_hash=cert.compute_hash(),
        cursor=uow.H.identity,
    )
    committed, evidence, native_cert = execute_certified_graph_substitution(shadow_state, cert)

    assert native_cert.is_valid
    assert committed.get(META_ACTIVE_GRAPH_HASH) == runtime.active_graph.compute_hash()
    assert committed.get(META_SUBSTITUTION_EPOCH) == cert.epoch
    assert committed.get(META_LAST_SUBSTITUTION_CERT_HASH) == cert.compute_hash()
    assert evidence.certificate_hash == native_cert.certificate_hash


def test_rejected_graph_substitution_cannot_be_lowered_as_authorized_uow():
    runtime, g0, _, cert = _certified_substitution(stale=True)

    assert not cert.is_accepted
    assert runtime.active_graph.compute_hash() == g0.compute_hash()

    with pytest.raises(ValueError, match="Rejected GraphReplacementCertificate"):
        make_certified_graph_substitution_uow(cert)
