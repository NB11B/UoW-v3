from __future__ import annotations

import pytest

from uow.composition.actor import ActorDescriptor, ActorRegistry, AuthorityClass
from uow.composition.binding import ActorBinding
from uow.composition.contract import ParentContract
from uow.composition.graph import RealizationGraph, RealizationNode
from uow.composition.runtime import AdaptiveCompositionRuntime

from uow_shadow.adapters import actor_binding_adapter
from uow_shadow.closure import (
    META_ACTIVE_BINDING_HASH,
    META_ACTIVE_GRAPH_HASH,
    META_GENERATION,
    META_LAST_BINDING_CONFORMANCE,
    execute_validated_rebinding,
    make_runtime_meta_state,
    make_validated_rebinding_uow,
)


def _graph() -> RealizationGraph:
    return RealizationGraph(
        "g-rebind",
        {
            "worker": RealizationNode(
                node_id="worker",
                role="worker",
                required_capabilities=("role:worker",),
                required_authority_class="PROPOSER_ONLY",
            )
        },
        (),
    )


def _actor(actor_id: str, capabilities=("role:worker",)) -> ActorDescriptor:
    return ActorDescriptor(
        actor_id=actor_id,
        capabilities=tuple(capabilities),
        substrate="cpu_x86",
        authority_class=AuthorityClass.PROPOSER_ONLY,
    )


def test_validated_actor_rebinding_application_closes_over_native_uow():
    graph = _graph()
    contract = ParentContract(
        contract_id="u-rebind",
        description="rebind closure",
        required_outputs=(),
    )
    registry = ActorRegistry([_actor("actor-A"), _actor("actor-B")])
    b0 = ActorBinding("b0", graph.graph_id, {"worker": "actor-A"})
    b1 = ActorBinding("b1", graph.graph_id, {"worker": "actor-B"})

    runtime = AdaptiveCompositionRuntime(
        contract,
        graph,
        registry=registry,
        baseline_binding=b0,
    )
    canonical_ok, canonical_violations = runtime.rebind_active_graph(b1)
    assert canonical_ok, canonical_violations

    conformance = actor_binding_adapter(graph, b1, registry)
    assert conformance.accepted

    uow = make_validated_rebinding_uow(
        active_graph_hash=graph.compute_hash(),
        candidate_binding_hash=b1.compute_hash(),
        conformance=conformance,
    )
    shadow_state = make_runtime_meta_state(
        active_graph_hash=graph.compute_hash(),
        active_binding_hash=b0.compute_hash(),
        generation=0,
        history_head="rebind-history",
        authorization_hash=conformance.conformance_id,
        cursor=uow.H.identity,
    )
    committed, evidence, certificate = execute_validated_rebinding(
        shadow_state,
        active_graph_hash=graph.compute_hash(),
        candidate_binding_hash=b1.compute_hash(),
        conformance=conformance,
    )

    assert certificate.is_valid
    assert committed.get(META_ACTIVE_GRAPH_HASH) == graph.compute_hash()
    assert committed.get(META_ACTIVE_BINDING_HASH) == runtime.active_binding.compute_hash()
    assert committed.get(META_GENERATION) == 0
    assert committed.get(META_LAST_BINDING_CONFORMANCE) == conformance.conformance_id
    assert evidence.certificate_hash == certificate.certificate_hash


def test_rejected_binding_conformance_cannot_be_lowered_as_rebinding():
    graph = _graph()
    bad_registry = ActorRegistry([_actor("actor-bad", capabilities=("storage",))])
    bad_binding = ActorBinding("bad", graph.graph_id, {"worker": "actor-bad"})

    conformance = actor_binding_adapter(graph, bad_binding, bad_registry)
    assert not conformance.accepted

    with pytest.raises(ValueError, match="Rejected binding conformance"):
        make_validated_rebinding_uow(
            active_graph_hash=graph.compute_hash(),
            candidate_binding_hash=bad_binding.compute_hash(),
            conformance=conformance,
        )


def test_validated_rebinding_fails_closed_if_active_graph_context_does_not_match():
    graph = _graph()
    registry = ActorRegistry([_actor("actor-A"), _actor("actor-B")])
    b0 = ActorBinding("b0", graph.graph_id, {"worker": "actor-A"})
    b1 = ActorBinding("b1", graph.graph_id, {"worker": "actor-B"})
    conformance = actor_binding_adapter(graph, b1, registry)
    assert conformance.accepted

    uow = make_validated_rebinding_uow(
        active_graph_hash=graph.compute_hash(),
        candidate_binding_hash=b1.compute_hash(),
        conformance=conformance,
    )
    shadow_state = make_runtime_meta_state(
        active_graph_hash="different-live-graph-hash",
        active_binding_hash=b0.compute_hash(),
        generation=0,
        history_head="rebind-history",
        authorization_hash=conformance.conformance_id,
        cursor=uow.H.identity,
    )

    with pytest.raises(RuntimeError, match="No applicable route"):
        execute_validated_rebinding(
            shadow_state,
            active_graph_hash=graph.compute_hash(),
            candidate_binding_hash=b1.compute_hash(),
            conformance=conformance,
        )

    assert shadow_state.get(META_ACTIVE_BINDING_HASH) == b0.compute_hash()
