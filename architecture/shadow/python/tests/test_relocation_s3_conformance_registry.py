from __future__ import annotations

from dataclasses import replace
import hashlib

from uow.composition.actor import ActorDescriptor, ActorRegistry, AuthorityClass
from uow.composition.binding import ActorBinding
from uow.composition.contract import AuthorityObligation, ParentContract
from uow.composition.convergence import AuthoritativeHistory
from uow.composition.delegation import AuthorityScope, ChildUoWSpec, DistributedDelegationNode
from uow.composition.graph import RealizationGraph, RealizationNode
from uow.composition.mutation import QuorumMutationCoordinator, assemble_mutation_qc
from uow.conformance import DEFAULT_CONFORMANCE_REGISTRY as PROD
from uow.effects.descriptor import EffectReceipt, create_effect_descriptor
from uow.resources.requirement import ResourceRequirement, make_resource_domain_task
from uow.resources.state import ResourceState
from uow.state import WorldState, canonical_json
from uow.transactions.descriptor import create_transaction_descriptor
from uow import Guard, GuardOp, Mutation, MutationOp, Route, Successor, make_uow

from uow_shadow.conformance_registry import DEFAULT_CONFORMANCE_REGISTRY as SHADOW


def _eq(prod, shadow):
    assert prod.accepted == shadow.accepted
    assert prod.decision.value == shadow.decision.value
    assert prod.violations == shadow.violations
    assert prod.source_validator == shadow.source_validator


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


def test_s3_manifest_matches_validated_shadow_registry():
    assert PROD.manifest() == SHADOW.manifest()
    assert len(PROD.domains()) == 9


def test_s3_resource_capacity_parity():
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
    for req in (
        ResourceRequirement(cpu_cores=2, ram_units=4),
        ResourceRequirement(cpu_cores=5, ram_units=4),
    ):
        _eq(
            PROD.evaluate("resource_capacity", req, resources),
            SHADOW.evaluate("resource_capacity", req, resources),
        )


def test_s3_resource_binding_and_occ_parity():
    bound_uow = make_uow(
        "resource-task",
        [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.SET, "x", 1),), Successor.preserve())],
    )
    good_bound = make_resource_domain_task(
        "resource-bound",
        [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.SET, "x", 1),), Successor.preserve())],
        ResourceRequirement(cpu_cores=1, ram_units=1),
    )
    _eq(
        PROD.evaluate("resource_binding", good_bound),
        SHADOW.evaluate("resource_binding", good_bound),
    )

    base = WorldState(
        attributes={
            "x": 0,
            "z": 0,
            "__versions__": {"x": 0, "z": 0},
            "__couplings__": {"x": ("z",)},
        },
        cursor="resource-task",
    )
    tx = create_transaction_descriptor(bound_uow, base)
    concurrent = base.with_attribute("__versions__", {"x": 0, "z": 1})
    _eq(
        PROD.evaluate("occ_compatibility", concurrent, tx),
        SHADOW.evaluate("occ_compatibility", concurrent, tx),
    )


def test_s3_actor_binding_and_projection_parity():
    graph = _graph()
    actor = ActorDescriptor(
        "good",
        ("role:worker", "role:verifier"),
        "cpu",
        authority_class=AuthorityClass.VERIFIER,
    )
    registry = ActorRegistry((actor,))
    binding = ActorBinding("b-good", "g", {"worker": "good", "verify": "good"})

    _eq(
        PROD.evaluate("actor_binding", graph, binding, registry),
        SHADOW.evaluate("actor_binding", graph, binding, registry),
    )

    contract = ParentContract(
        contract_id="parent",
        description="result requires verifier",
        required_outputs=("result",),
        authority=AuthorityObligation(required_role="verifier"),
    )
    _eq(
        PROD.evaluate("semantic_projection", graph, contract),
        SHADOW.evaluate("semantic_projection", graph, contract),
    )


def test_s3_delegation_parity():
    contract = ParentContract(
        contract_id="parent",
        description="delegation",
        required_outputs=("result",),
    )
    node = DistributedDelegationNode("issuer", AuthorityScope.compute(), generation=1)
    spec = ChildUoWSpec(
        child_uow_id="child",
        sub_contract=contract,
        input_keys=(),
        expected_outputs=("result",),
        assigned_actor_id="delegate",
        authority_scope=AuthorityScope.read_only(),
    )
    cert = node.issue_certificate(contract, spec, current_ts=10.0)
    _eq(
        PROD.evaluate("delegation", node.authority_scope, cert, current_ts=11.0),
        SHADOW.evaluate("delegation", node.authority_scope, cert, current_ts=11.0),
    )


def test_s3_external_receipt_parity():
    state = WorldState(attributes={}, cursor="effect")
    effect = create_effect_descriptor("effect", state.state_hash, "send", {"amount": 1})
    payload = {"status": "SUCCESS"}
    response_hash = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    receipt = EffectReceipt(
        receipt_id="r1",
        effect_id=effect.effect_id,
        idempotency_key=effect.idempotency_key,
        response_payload=payload,
        response_hash=response_hash,
        timestamp="1",
        signature="sig::test-signer::ok",
    )
    _eq(
        PROD.evaluate("external_receipt", effect, receipt, expected_signer="test-signer"),
        SHADOW.evaluate("external_receipt", effect, receipt, expected_signer="test-signer"),
    )

    wrong = replace(receipt, effect_id="wrong", receipt_hash="")
    _eq(
        PROD.evaluate("external_receipt", effect, wrong, expected_signer="test-signer"),
        SHADOW.evaluate("external_receipt", effect, wrong, expected_signer="test-signer"),
    )


def test_s3_mutation_vote_and_qc_parity():
    contract = ParentContract(
        contract_id="mut-parent",
        description="mutation parity",
        required_outputs=("result",),
        authority=AuthorityObligation(required_role="verifier"),
    )
    graph = RealizationGraph(
        "g0",
        {
            "verify": RealizationNode("verify", role="verifier", authority_tier="verifier"),
            "commit": RealizationNode("commit", role="commit", outputs=("result",)),
        },
        (("verify", "commit"),),
    )
    candidate = RealizationGraph(
        "g1",
        {
            "verify": RealizationNode("verify", role="verifier", authority_tier="verifier"),
            "commit": RealizationNode("commit", role="commit", outputs=("result",)),
        },
        (("verify", "commit"),),
    )
    binding0 = ActorBinding("b0", graph.graph_id, {})
    binding1 = ActorBinding("b1", candidate.graph_id, {})
    keys = {"A": "key-a", "B": "key-b", "C": "key-c"}
    history = AuthoritativeHistory()
    coordinator = QuorumMutationCoordinator(
        contract,
        graph,
        binding0,
        history,
        keys,
        generation=0,
        quorum_threshold=2,
    )
    proposal = coordinator.propose_mutation("proposer", candidate, binding1)
    votes = coordinator.collect_votes(proposal)
    vote = votes[0]

    _eq(
        PROD.evaluate("mutation_vote", vote, keys[vote.voter_id]),
        SHADOW.evaluate("mutation_vote", vote, keys[vote.voter_id]),
    )

    qc, reason = assemble_mutation_qc(proposal, votes, threshold=2)
    assert qc is not None, reason
    _eq(
        PROD.evaluate(
            "mutation_qc",
            qc,
            contract,
            history.tip_hash(),
            0,
            keys,
            threshold=2,
        ),
        SHADOW.evaluate(
            "mutation_qc",
            qc,
            contract,
            history.tip_hash(),
            0,
            keys,
            threshold=2,
        ),
    )


def test_s3_target_facade_points_to_production_registry():
    from pathlib import Path
    import sys

    repo = Path(__file__).resolve().parents[4]
    facade_root = repo / "implementations" / "python"
    if str(facade_root) not in sys.path:
        sys.path.insert(0, str(facade_root))

    from uow_architecture_facade.conformance import DEFAULT_CONFORMANCE_REGISTRY

    assert DEFAULT_CONFORMANCE_REGISTRY is PROD
