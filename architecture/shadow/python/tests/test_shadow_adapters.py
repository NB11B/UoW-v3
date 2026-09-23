from __future__ import annotations

import hashlib

from uow.contracts import Guard, GuardOp, Mutation, MutationOp, Route, Successor, make_uow
from uow.effects.descriptor import EffectReceipt, create_effect_descriptor
from uow.engine import Proposal, propose
from uow.resources.requirement import ResourceRequirement
from uow.resources.state import ResourceState
from uow.state import WorldState, canonical_json
from uow.transactions.descriptor import TransactionDescriptor

from uow_shadow.adapters import (
    adapt_transition_contract,
    adapt_world_state,
    core_certify_adapter,
    effect_receipt_adapter,
    occ_adapter,
    resource_capacity_adapter,
)


def test_core_shadow_adapters_preserve_canonical_accept_reject():
    state = WorldState(attributes={"x": 0}, cursor="u1")
    uow = make_uow(
        "u1",
        [
            Route(
                guard=Guard(GuardOp.ALWAYS),
                mutations=(Mutation(MutationOp.SET, "x", 1),),
                successor=Successor.halt(),
            )
        ],
    )

    state_ref = adapt_world_state(state)
    contract_ref = adapt_transition_contract(uow)
    assert state_ref.state_id == state.state_hash
    assert contract_ref.contract_id == "u1"

    proposal = propose(uow, state)
    accepted = core_certify_adapter(uow, state, proposal)
    assert accepted.accepted

    tampered = Proposal(
        uow_id=proposal.uow_id,
        pre_state_hash=proposal.pre_state_hash,
        selected_route_index=proposal.selected_route_index,
        proposed_state=proposal.proposed_state.with_attribute("x", 99),
        selected_successor=proposal.selected_successor,
        halted=proposal.halted,
    )
    rejected = core_certify_adapter(uow, state, tampered)
    assert not rejected.accepted
    assert rejected.violations


def test_resource_adapter_matches_canonical_capacity_decision():
    resources = ResourceState(
        capacities={
            "cpu_cores": 4,
            "ram_units": 8,
            "gpu_slots": 1,
            "npu_slots": 1,
            "energy_budget": 10,
        },
        allocated={
            "cpu_cores": 0,
            "ram_units": 0,
            "gpu_slots": 0,
            "npu_slots": 0,
            "energy_budget": 0,
        },
    )

    fits = ResourceRequirement(cpu_cores=2, ram_units=4)
    too_large = ResourceRequirement(cpu_cores=5, ram_units=4)

    assert resource_capacity_adapter(fits, resources).accepted == resources.can_accommodate(fits)
    assert resource_capacity_adapter(too_large, resources).accepted == resources.can_accommodate(too_large)


def test_occ_adapter_preserves_stale_read_rejection():
    state = WorldState(attributes={"x": 1, "__versions__": {"x": 1}})
    tx = TransactionDescriptor(
        uow_id="u-occ",
        base_sequence=0,
        read_set=("x",),
        read_versions={"x": 0},
        write_set=(),
        write_versions={},
        proposed_state_hash="candidate",
        coupled_set=(),
        coupled_versions={},
    )
    result = occ_adapter(state, tx)
    assert not result.accepted
    assert "READ_WRITE_HAZARD" in result.violations


def test_external_receipt_adapter_preserves_binding_checks():
    state = WorldState(attributes={})
    effect = create_effect_descriptor(
        "u-eff",
        state.state_hash,
        "send",
        {"value": 1},
    )
    response = {"status": "SUCCESS"}
    response_hash = hashlib.sha256(canonical_json(response).encode("utf-8")).hexdigest()

    receipt = EffectReceipt(
        receipt_id="r1",
        effect_id=effect.effect_id,
        idempotency_key=effect.idempotency_key,
        response_payload=response,
        response_hash=response_hash,
        timestamp="1",
        signature="sig::signer::test",
    )
    assert effect_receipt_adapter(effect, receipt, expected_signer="signer").accepted

    wrong = EffectReceipt(
        receipt_id="r2",
        effect_id="wrong-effect",
        idempotency_key=effect.idempotency_key,
        response_payload=response,
        response_hash=response_hash,
        timestamp="1",
        signature="sig::signer::test",
    )
    rejected = effect_receipt_adapter(effect, wrong, expected_signer="signer")
    assert not rejected.accepted
