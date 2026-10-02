from __future__ import annotations

import pytest

from uow.compat.v2 import (
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    ResourceRequirement,
    ResourceState,
    Route,
    Successor,
    WorldState,
    make_uow,
)
from uow.composition.actor import ActorDescriptor, ActorRegistry, AuthorityClass
from uow.composition.binding import ActorBinding
from uow.composition.contract import AuthorityObligation, ParentContract
from uow.composition.delegation import AuthorityScope, ChildUoWSpec, DistributedDelegationNode
from uow.composition.graph import RealizationGraph, RealizationNode
from uow.transactions.descriptor import create_transaction_descriptor

from uow_shadow.adapters import (
    actor_binding_adapter,
    delegation_adapter,
    occ_adapter,
    resource_capacity_adapter,
    semantic_projection_adapter,
)
from uow_shadow.conformance_registry import DEFAULT_CONFORMANCE_REGISTRY
from uow_shadow.requirements import MatcherKind


def test_r6_conformance_registry_declares_typed_specializations():
    manifest = DEFAULT_CONFORMANCE_REGISTRY.manifest()

    assert manifest["resource_capacity"]["matcher_kind"] == MatcherKind.QUANTITATIVE_MINIMUM.value
    assert manifest["occ_compatibility"]["matcher_kind"] == MatcherKind.RELATIONAL_COMPATIBILITY.value
    assert manifest["actor_binding"]["matcher_kind"] == MatcherKind.QUALIFIED_CAPABILITY.value
    assert manifest["semantic_projection"]["matcher_kind"] == MatcherKind.RELATIONAL_COMPATIBILITY.value
    assert manifest["mutation_qc"]["matcher_kind"] == MatcherKind.QUORUM_K_OF_N.value
    assert all(item["preserves_specialized_predicate"] for item in manifest.values())


def test_r6_registry_resource_adapter_matches_specialized_validator():
    resources = ResourceState(
        capacities={
            "cpu_cores": 4,
            "ram_units": 8,
            "gpu_slots": 0,
            "npu_slots": 0,
            "energy_budget": 100,
            "cost": 100,
        }
    )
    good = ResourceRequirement(cpu_cores=2, ram_units=4)
    bad = ResourceRequirement(cpu_cores=5, ram_units=4)

    direct_good = resource_capacity_adapter(good, resources)
    via_good = DEFAULT_CONFORMANCE_REGISTRY.evaluate("resource_capacity", good, resources)
    direct_bad = resource_capacity_adapter(bad, resources)
    via_bad = DEFAULT_CONFORMANCE_REGISTRY.evaluate("resource_capacity", bad, resources)

    assert via_good.decision == direct_good.decision
    assert via_bad.decision == direct_bad.decision
    assert via_bad.violations == direct_bad.violations


def test_r6_registry_occ_adapter_preserves_relational_hidden_coupling():
    uow = make_uow(
        "write-x",
        [
            Route(
                Guard(GuardOp.ALWAYS),
                (Mutation(MutationOp.SET, "x", 1),),
                Successor.preserve(),
            )
        ],
    )
    base = WorldState(
        attributes={
            "x": 0,
            "z": 0,
            "__versions__": {"x": 0, "z": 0},
            "__couplings__": {"x": ("z",)},
        },
        cursor="write-x",
    )
    tx = create_transaction_descriptor(uow, base)
    concurrent = base.with_attribute(
        "__versions__",
        {"x": 0, "z": 1},
    )

    direct = occ_adapter(concurrent, tx)
    via = DEFAULT_CONFORMANCE_REGISTRY.evaluate("occ_compatibility", concurrent, tx)

    assert not via.accepted
    assert via.decision == direct.decision
    assert via.violations == direct.violations == ("HIDDEN_COUPLING_HAZARD",)


def _graph():
    return RealizationGraph(
        "g",
        {
            "worker": RealizationNode(
                "worker",
                role="worker",
                required_capabilities=("role:worker",),
            ),
            "verify": RealizationNode(
                "verify",
                role="verifier",
                authority_tier="verifier",
                outputs=("result",),
            ),
        },
        (("worker", "verify"),),
    )


def test_r6_registry_actor_binding_preserves_qualification_semantics():
    graph = _graph()
    good_actor = ActorDescriptor(
        "good",
        ("role:worker", "role:verifier"),
        "cpu",
        authority_class=AuthorityClass.VERIFIER,
    )
    registry = ActorRegistry((good_actor,))
    good_binding = ActorBinding("b-good", "g", {"worker": "good", "verify": "good"})

    direct = actor_binding_adapter(graph, good_binding, registry)
    via = DEFAULT_CONFORMANCE_REGISTRY.evaluate(
        "actor_binding",
        graph,
        good_binding,
        registry,
    )
    assert via.decision == direct.decision
    assert via.accepted

    weak_actor = ActorDescriptor(
        "weak",
        ("role:worker", "role:verifier"),
        "cpu",
        authority_class=AuthorityClass.PROPOSER_ONLY,
    )
    weak_registry = ActorRegistry((weak_actor,))
    bad_binding = ActorBinding("b-bad", "g", {"worker": "weak", "verify": "weak"})
    direct_rejected = actor_binding_adapter(graph, bad_binding, weak_registry)
    rejected = DEFAULT_CONFORMANCE_REGISTRY.evaluate(
        "actor_binding",
        graph,
        bad_binding,
        weak_registry,
    )
    assert not rejected.accepted
    assert rejected.decision == direct_rejected.decision
    assert rejected.violations == direct_rejected.violations
    assert any("ACTOR_AUTHORITY_INSUFFICIENT" in v for v in rejected.violations)


def test_r6_registry_semantic_projection_preserves_output_and_authority_rules():
    contract = ParentContract(
        contract_id="parent",
        description="result requires verifier",
        required_outputs=("result",),
        authority=AuthorityObligation(required_role="verifier"),
    )
    graph = _graph()

    direct = semantic_projection_adapter(graph, contract)
    via = DEFAULT_CONFORMANCE_REGISTRY.evaluate("semantic_projection", graph, contract)
    assert via.decision == direct.decision
    assert via.accepted

    bad = RealizationGraph(
        "bad",
        {"worker": RealizationNode("worker", role="worker", outputs=("result",))},
        (),
    )
    rejected = DEFAULT_CONFORMANCE_REGISTRY.evaluate(
        "semantic_projection",
        bad,
        contract,
    )
    assert not rejected.accepted


def test_r6_registry_delegation_preserves_authority_attenuation():
    contract = ParentContract(
        contract_id="parent",
        description="delegation",
        required_outputs=("result",),
    )
    node = DistributedDelegationNode("issuer", AuthorityScope.compute(), generation=1)

    good_spec = ChildUoWSpec(
        child_uow_id="child-good",
        sub_contract=contract,
        input_keys=(),
        expected_outputs=("result",),
        assigned_actor_id="delegate",
        authority_scope=AuthorityScope.read_only(),
    )
    good_cert = node.issue_certificate(contract, good_spec, current_ts=10.0)
    direct = delegation_adapter(node.authority_scope, good_cert, current_ts=11.0)
    via = DEFAULT_CONFORMANCE_REGISTRY.evaluate(
        "delegation",
        node.authority_scope,
        good_cert,
        current_ts=11.0,
    )
    assert via.decision == direct.decision
    assert via.accepted

    bad_spec = ChildUoWSpec(
        child_uow_id="child-bad",
        sub_contract=contract,
        input_keys=(),
        expected_outputs=("result",),
        assigned_actor_id="delegate",
        authority_scope=AuthorityScope.full(),
    )
    bad_cert = node.issue_certificate(contract, bad_spec, current_ts=10.0)
    rejected = DEFAULT_CONFORMANCE_REGISTRY.evaluate(
        "delegation",
        node.authority_scope,
        bad_cert,
        current_ts=11.0,
    )
    assert not rejected.accepted
    assert any("AUTHORITY_INFLATION_REJECTED" in v for v in rejected.violations)


def test_r6_registry_unknown_domain_fails_closed():
    with pytest.raises(KeyError, match="Unknown conformance domain"):
        DEFAULT_CONFORMANCE_REGISTRY.evaluate("not-a-domain")
