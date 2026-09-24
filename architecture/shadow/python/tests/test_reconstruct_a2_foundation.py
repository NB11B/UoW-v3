from __future__ import annotations

import pytest

from uow.composition.actor import ActorDescriptor, ActorRegistry, AuthorityClass
from uow.composition.binding import ActorBinding
from uow.composition.contract import (
    AuthorityObligation,
    CausalConstraint,
    EvidenceObligation,
    ParentContract,
)
from uow.composition.convergence import AuthoritativeHistory, HistoryEntry, HistoryEntryKind
from uow.composition.delegation import AuthorityScope, DistributedDelegationNode
from uow.composition.fabric import DistributedActorFabric, NetworkAgent
from uow.composition.graph import RealizationGraph, RealizationNode
from uow.composition.policy import AdaptiveGraphProposer, CompositionRuntimeState
from uow.composition.projection import are_equivalent, project_semantics
from uow.composition.substitution import (
    CompositionCertifier,
    GraphReplacementProposal,
    SubstitutionStrategy,
)
from uow.state import WorldState

from uow_shadow.adapters import actor_binding_adapter, delegation_adapter
from uow_shadow.composition_reconstruction import (
    apply_delegation_reconstructed,
    apply_graph_substitution_reconstructed,
    apply_history_reconciliation_reconstructed,
    apply_rebinding_reconstructed,
)
from uow_shadow.closure import (
    META_ACTIVE_BINDING_HASH,
    META_ACTIVE_GRAPH_HASH,
    META_AUTHORIZATION_HASH,
    META_CANONICAL_HISTORY_DIGEST,
    META_DELEGATION_ACTOR_PREFIX,
    META_DELEGATION_CERT_PREFIX,
    make_runtime_meta_state,
)


def _contract() -> ParentContract:
    return ParentContract(
        contract_id="a2-reconstruction-contract",
        description="A2 reconstruction parent intent",
        required_outputs=("result",),
        causal_constraints=(
            CausalConstraint("parser", "worker"),
            CausalConstraint("worker", "verifier"),
            CausalConstraint("verifier", "commit"),
        ),
        authority=AuthorityObligation(
            required_role="verifier",
            min_evidence_level="portable",
            quorum_threshold=1,
        ),
        evidence=EvidenceObligation(
            require_provenance=True,
            require_hash_chain=True,
            min_evidence_level="portable",
            verifier_id="deterministic-judge",
        ),
    )


def _g0() -> RealizationGraph:
    return RealizationGraph(
        "G0_sequential",
        {
            "parse": RealizationNode("parse", role="parser", actor_class="cpu"),
            "work": RealizationNode("work", role="worker", actor_class="cpu"),
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
                outputs=("result",),
            ),
        },
        (
            ("parse", "work"),
            ("work", "verify"),
            ("verify", "commit"),
        ),
    )


def _g1() -> RealizationGraph:
    return RealizationGraph(
        "G1_npu",
        {
            "parse": RealizationNode("parse", role="parser", actor_class="cpu"),
            "work": RealizationNode(
                "work",
                role="worker",
                actor_class="npu",
                npu_slots=1,
            ),
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
                outputs=("result",),
            ),
        },
        (
            ("parse", "work"),
            ("work", "verify"),
            ("verify", "commit"),
        ),
    )


def _registry():
    return ActorRegistry(
        [
            ActorDescriptor(
                actor_id="cpu",
                capabilities=("role:parser", "role:worker", "role:verifier", "role:commit"),
                substrate="cpu_x86",
                authority_class=AuthorityClass.VERIFIER,
                load=0.20,
                latency_ms=2.0,
            ),
            ActorDescriptor(
                actor_id="npu",
                capabilities=("role:worker", "npu_inference"),
                substrate="intel_npu",
                authority_class=AuthorityClass.PROPOSER_ONLY,
                load=0.05,
                latency_ms=1.0,
            ),
            ActorDescriptor(
                actor_id="cpu2",
                capabilities=("role:worker",),
                substrate="cpu_x86",
                authority_class=AuthorityClass.PROPOSER_ONLY,
                load=0.10,
                latency_ms=3.0,
            ),
        ]
    )


def _binding(graph: RealizationGraph, binding_id: str, worker_actor: str) -> ActorBinding:
    return ActorBinding(
        binding_id=binding_id,
        graph_id=graph.graph_id,
        node_to_actor={
            "parse": "cpu",
            "work": worker_actor,
            "verify": "cpu",
            "commit": "cpu",
        },
    )


def test_r4_a2_0_semantic_projection_preserves_realization_invariance():
    contract = _contract()
    g0 = _g0()
    g1 = _g1()

    p0 = project_semantics(g0, contract)
    p1 = project_semantics(g1, contract)

    assert p0.conforms
    assert p1.conforms
    assert p0.projection_hash == p1.projection_hash
    assert are_equivalent(g0, g1, contract)

    bad = RealizationGraph(
        "G_bad_authority",
        {
            "parse": RealizationNode("parse", role="parser"),
            "work": RealizationNode("work", role="worker"),
            "commit": RealizationNode("commit", role="commit", outputs=("result",)),
        },
        (("parse", "work"), ("work", "commit")),
    )
    rejected = project_semantics(bad, contract)
    assert not rejected.conforms
    assert any("AUTHORITY" in v for v in rejected.violations)


def test_r4_a2_1_certified_graph_substitution_applies_through_minimal_authority():
    contract = _contract()
    g0 = _g0()
    g1 = _g1()

    proposal = GraphReplacementProposal(
        parent_contract_id=contract.contract_id,
        current_graph_hash=g0.compute_hash(),
        candidate_graph=g1,
        strategy=SubstitutionStrategy.ACCELERATOR_OFFLOAD,
        predicted_speedup=1.5,
        proposal_id="a2-r4-sub",
    )
    cert = CompositionCertifier().certify_proposal(
        proposal,
        g0,
        contract,
        current_epoch=1,
    )
    assert cert.is_accepted

    state = make_runtime_meta_state(
        active_graph_hash=g0.compute_hash(),
        authorization_hash=cert.compute_hash(),
        cursor="runtime-controller",
    )
    after, evidence = apply_graph_substitution_reconstructed(state, cert)

    assert after.get(META_ACTIVE_GRAPH_HASH) == g1.compute_hash()
    assert evidence.authorization_reference
    assert evidence.conformance_reference

    stale = GraphReplacementProposal(
        parent_contract_id=contract.contract_id,
        current_graph_hash="stale",
        candidate_graph=g1,
        strategy=SubstitutionStrategy.ACCELERATOR_OFFLOAD,
        proposal_id="a2-r4-stale",
    )
    stale_cert = CompositionCertifier().certify_proposal(stale, g0, contract)
    assert not stale_cert.is_accepted
    with pytest.raises(ValueError, match="Rejected GraphReplacementCertificate"):
        apply_graph_substitution_reconstructed(state, stale_cert)


def test_r4_a2_2_adaptive_proposer_selects_realization_but_shadow_authority_applies_it():
    contract = _contract()
    g0 = _g0()
    g1 = _g1()
    registry = _registry()

    proposer = AdaptiveGraphProposer()
    runtime_state = CompositionRuntimeState(
        actor_availability={a.actor_id: True for a in registry.all_actors()},
        actor_loads={a.actor_id: a.load for a in registry.all_actors()},
        actor_latencies={a.actor_id: a.latency_ms for a in registry.all_actors()},
        actor_failure_counts={a.actor_id: 0 for a in registry.all_actors()},
        active_graph_id=g0.graph_id,
    )
    proposal = proposer.propose_realization(
        runtime_state,
        contract,
        (g0, g1),
        registry,
        g0.compute_hash(),
        proposal_id="a2-r4-adaptive",
    )
    assert proposal is not None
    assert proposal.candidate_graph.graph_id == "G1_npu"
    assert proposal.actor_binding is not None

    cert = CompositionCertifier().certify_proposal(
        proposal,
        g0,
        contract,
        current_epoch=1,
        actor_registry=registry,
    )
    assert cert.is_accepted

    state = make_runtime_meta_state(
        active_graph_hash=g0.compute_hash(),
        active_binding_hash="baseline",
        authorization_hash=cert.compute_hash(),
        cursor="runtime-controller",
    )
    after, _ = apply_graph_substitution_reconstructed(state, cert)

    assert after.get(META_ACTIVE_GRAPH_HASH) == g1.compute_hash()
    assert after.get(META_ACTIVE_BINDING_HASH) == proposal.actor_binding.compute_hash()


def test_r4_a2_3_discovery_does_not_confer_authority_and_valid_rebinding_closes():
    graph = _g0()
    registry = _registry()
    fabric = DistributedActorFabric(
        registry=registry,
        trusted_authority_keys={"cpu"},
        lease_ttl_sec=10.0,
    )

    untrusted_verifier = ActorDescriptor(
        actor_id="untrusted-verifier",
        capabilities=("role:verifier",),
        substrate="remote",
        authority_class=AuthorityClass.VERIFIER,
    )
    agent = NetworkAgent("untrusted-verifier", untrusted_verifier)
    lease = fabric.register_agent(agent, current_ts=100.0)
    assert lease.is_valid(105.0)
    assert not fabric.qualify_actor("untrusted-verifier", AuthorityClass.VERIFIER)

    b0 = _binding(graph, "b0", "cpu")
    b1 = _binding(graph, "b1", "cpu2")
    conformance = actor_binding_adapter(graph, b1, registry)
    assert conformance.accepted

    state = make_runtime_meta_state(
        active_graph_hash=graph.compute_hash(),
        active_binding_hash=b0.compute_hash(),
        authorization_hash="not-used-by-rebind",
        cursor="runtime-controller",
    )
    after, _ = apply_rebinding_reconstructed(
        state,
        active_graph_hash=graph.compute_hash(),
        candidate_binding_hash=b1.compute_hash(),
        conformance=conformance,
    )

    assert after.get(META_ACTIVE_GRAPH_HASH) == graph.compute_hash()
    assert after.get(META_ACTIVE_BINDING_HASH) == b1.compute_hash()


def test_r4_a2_4_delegation_attenuation_and_registration_reconstruct():
    contract = _contract()
    node = DistributedDelegationNode(
        "issuer",
        AuthorityScope.compute(),
        generation=2,
        delegation_ttl_sec=30.0,
    )

    from uow.composition.delegation import ChildUoWSpec

    child = ChildUoWSpec(
        child_uow_id="child-1",
        sub_contract=contract,
        input_keys=("x",),
        expected_outputs=("result",),
        assigned_actor_id="delegate-A",
        authority_scope=AuthorityScope.read_only(),
        is_idempotent=True,
    )
    cert = node.issue_certificate(contract, child, current_ts=10.0)
    conf = delegation_adapter(node.authority_scope, cert, current_ts=11.0)
    assert conf.accepted

    state = make_runtime_meta_state(
        active_graph_hash="delegation-meta",
        generation=2,
        authorization_hash=cert.compute_hash(),
        cursor="runtime-controller",
    )
    after, _ = apply_delegation_reconstructed(state, cert, conf)

    assert after.get(f"{META_DELEGATION_CERT_PREFIX}child-1") == cert.compute_hash()
    assert after.get(f"{META_DELEGATION_ACTOR_PREFIX}child-1") == "delegate-A"

    inflated = ChildUoWSpec(
        child_uow_id="child-2",
        sub_contract=contract,
        input_keys=("x",),
        expected_outputs=("result",),
        assigned_actor_id="delegate-B",
        authority_scope=AuthorityScope.full(),
        is_idempotent=True,
    )
    bad_cert = node.issue_certificate(contract, inflated, current_ts=10.0)
    bad_conf = delegation_adapter(node.authority_scope, bad_cert, current_ts=11.0)
    assert not bad_conf.accepted


def test_r4_a2_5_verified_history_application_reconstructs_full_lineage_payload():
    history = AuthoritativeHistory()
    entry = HistoryEntry(
        entry_id="e0",
        sequence_number=0,
        prev_hash="GENESIS_0000000000000000000000000000000000000000000000000000000000000000",
        kind=HistoryEntryKind.AUTHORITATIVE_COMMIT,
        author_node_id="A",
        generation=1,
        payload={"result": "ok"},
        quorum_signatures=("A", "B"),
    )
    ok, reason = history.append(entry)
    assert ok, reason
    assert history.verify_integrity()

    state = make_runtime_meta_state(
        active_graph_hash="history-meta",
        history_head="old",
        authorization_hash=history.state_digest(),
        cursor="runtime-controller",
    )
    after, _ = apply_history_reconciliation_reconstructed(state, history)

    assert after.get(META_CANONICAL_HISTORY_DIGEST) == history.state_digest()
