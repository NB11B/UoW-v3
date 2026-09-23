from __future__ import annotations

from uow.composition.actor import ActorDescriptor, ActorRegistry, AuthorityClass
from uow.composition.binding import ActorBinding
from uow.composition.contract import ParentContract
from uow.composition.delegation import AuthorityScope, DelegationCertificate
from uow.composition.graph import RealizationGraph, RealizationNode

from uow_shadow.adapters import (
    actor_binding_adapter,
    delegation_adapter,
    semantic_projection_adapter,
)


def test_actor_binding_adapter_preserves_capability_decision():
    node = RealizationNode(
        node_id="worker",
        role="worker",
        required_capabilities=("cpu_compute",),
    )
    graph = RealizationGraph("g-bind", {"worker": node}, ())

    good_registry = ActorRegistry(
        [
            ActorDescriptor(
                actor_id="actor-good",
                capabilities=("cpu_compute",),
                substrate="cpu_x86",
                authority_class=AuthorityClass.PROPOSER_ONLY,
            )
        ]
    )
    good_binding = ActorBinding("b-good", graph.graph_id, {"worker": "actor-good"})
    assert actor_binding_adapter(graph, good_binding, good_registry).accepted

    bad_registry = ActorRegistry(
        [
            ActorDescriptor(
                actor_id="actor-bad",
                capabilities=("storage",),
                substrate="cpu_x86",
                authority_class=AuthorityClass.PROPOSER_ONLY,
            )
        ]
    )
    bad_binding = ActorBinding("b-bad", graph.graph_id, {"worker": "actor-bad"})
    result = actor_binding_adapter(graph, bad_binding, bad_registry)
    assert not result.accepted
    assert any("ACTOR_CAPABILITY_DEFICIT" in v for v in result.violations)


def _projection_graph(with_authority_edge: bool) -> RealizationGraph:
    authority = RealizationNode(
        node_id="authority",
        role="authority",
        authority_tier="deterministic_judge",
        outputs=(),
    )
    commit = RealizationNode(
        node_id="commit",
        role="commit",
        outputs=("result",),
        authority_tier="untrusted",
    )
    edges = (("authority", "commit"),) if with_authority_edge else ()
    return RealizationGraph(
        "g-proj-ok" if with_authority_edge else "g-proj-bad",
        {"authority": authority, "commit": commit},
        edges,
    )


def test_semantic_projection_adapter_preserves_authority_bypass_rejection():
    contract = ParentContract(
        contract_id="u-proj",
        description="projection parity",
        required_outputs=("result",),
    )

    accepted = semantic_projection_adapter(_projection_graph(True), contract)
    rejected = semantic_projection_adapter(_projection_graph(False), contract)

    assert accepted.accepted
    assert not rejected.accepted
    assert any("A_COMMIT_BYPASSES_AUTHORITY" in v for v in rejected.violations)


def _delegation_certificate(scope: AuthorityScope, cert_id: str) -> DelegationCertificate:
    return DelegationCertificate(
        cert_id=cert_id,
        parent_contract_id="parent",
        parent_contract_hash="parent-hash",
        child_uow_id="child",
        projection_hash="projection",
        issuer_actor_id="issuer",
        delegate_actor_id="delegate",
        authority_scope=scope,
        generation=1,
        granted_at_ts=1.0,
        expires_at_ts=20.0,
        nonce=cert_id,
    )


def test_delegation_adapter_preserves_authority_attenuation():
    parent_scope = AuthorityScope.compute()

    valid = delegation_adapter(
        parent_scope,
        _delegation_certificate(AuthorityScope.compute(), "cert-ok"),
        current_ts=10.0,
    )
    inflated = delegation_adapter(
        parent_scope,
        _delegation_certificate(AuthorityScope.full(), "cert-inflated"),
        current_ts=10.0,
    )

    assert valid.accepted
    assert not inflated.accepted
    assert any("AUTHORITY_INFLATION_REJECTED" in v for v in inflated.violations)
