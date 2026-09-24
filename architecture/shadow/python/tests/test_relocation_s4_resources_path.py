from __future__ import annotations

import inspect

import uow
from uow import (
    Contract,
    DeterministicSequencer,
    FIFOSchedulingPolicy,
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    ResourceRequirement,
    ResourceState,
    Route,
    create_initial_orchestration_state,
    create_transaction_descriptor,
    make_resource_domain_task,
    propose,
    certify,
    certify_materialization,
    set_authoritative_resource_state,
)
from uow.implementations.resources.runtime import (
    ResourceAwareCompletionMaterializer as ImplCompletion,
    ResourceAwareSchedulerMaterializer as ImplScheduler,
    run_resource_orchestration as impl_run,
)
from uow.resources import (
    ResourceAwareCompletionMaterializer,
    ResourceAwareSchedulerMaterializer,
    run_resource_orchestration,
)
from uow.orchestration import COMPLETION_PREFIX, SCHEDULER_ID


def _fixture():
    registry = {
        "A": make_resource_domain_task(
            "A",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 10),))],
            ResourceRequirement(cpu_cores=2, ram_units=2, energy_budget=5),
        ),
        "B": make_resource_domain_task(
            "B",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r1", 20),))],
            ResourceRequirement(cpu_cores=1, ram_units=2, energy_budget=7),
        ),
    }
    base = create_initial_orchestration_state(
        ["A", "B"],
        {},
        attributes={"r0": 0, "r1": 0},
    )
    state = set_authoritative_resource_state(
        base,
        ResourceState(
            capacities={
                "cpu_cores": 4,
                "ram_units": 8,
                "gpu_slots": 0,
                "npu_slots": 0,
                "energy_budget": 100,
                "cost": 100,
            }
        ),
    )
    return registry, state


def _reference_run(registry, initial, policy):
    seq = DeterministicSequencer(initial)
    scheduler = ImplScheduler(registry, policy)

    for _ in range(1000):
        state = seq.current_state
        if state.status != "RUNNING" or state.cursor is None:
            return state, seq

        cursor = state.cursor
        if cursor == SCHEDULER_ID:
            before = seq.current_state
            materialized = scheduler.materialize(before)
            assert certify_materialization(scheduler, before, materialized)
            proposal = propose(materialized.uow, before)
            cert = certify(materialized.uow, before, proposal)
            assert cert.is_valid
            tx = create_transaction_descriptor(materialized.uow, before)
            seq.commit(materialized.uow, proposal, tx, cert)
            continue

        if cursor.startswith(COMPLETION_PREFIX):
            task_id = cursor[len(COMPLETION_PREFIX):]
            completion = ImplCompletion(task_id)
            before = seq.current_state
            materialized = completion.materialize(before)
            assert certify_materialization(completion, before, materialized)
            proposal = propose(materialized.uow, before)
            cert = certify(materialized.uow, before, proposal)
            assert cert.is_valid
            tx = create_transaction_descriptor(materialized.uow, before)
            seq.commit(materialized.uow, proposal, tx, cert)
            continue

        bound = registry[cursor]
        before = seq.current_state
        proposal = propose(bound.uow, before)
        cert = certify(bound.uow, before, proposal)
        assert cert.is_valid
        tx = create_transaction_descriptor(bound.uow, before)
        seq.commit(bound.uow, proposal, tx, cert)

    raise RuntimeError("reference resource step budget exceeded")


def test_s4_resource_import_paths_remain_identity_compatible():
    assert ResourceAwareSchedulerMaterializer is ImplScheduler
    assert ResourceAwareCompletionMaterializer is ImplCompletion
    assert run_resource_orchestration is impl_run

    assert uow.ResourceAwareSchedulerMaterializer is ImplScheduler
    assert uow.ResourceAwareCompletionMaterializer is ImplCompletion
    assert uow.run_resource_orchestration is impl_run


def test_s4_historical_resource_runtime_is_only_shim():
    import uow.resources.runtime as shim

    source = inspect.getsource(shim)
    assert "class ResourceAwareSchedulerMaterializer" not in source
    assert "class ResourceAwareCompletionMaterializer" not in source
    assert "def run_resource_orchestration" not in source
    assert "implementations.resources.runtime" in source


def test_s4_resource_implementation_uses_common_spine_not_manual_commit_loop():
    import uow.implementations.resources.runtime as implementation

    source = inspect.getsource(implementation)
    assert "DEFAULT_APPLICATION_SPINE.execute" in source
    assert "propose(" not in source
    assert "certify(" not in source
    assert "create_transaction_descriptor(" not in source
    assert "sequencer.commit(" not in source


def test_s4_resource_runtime_matches_pre_move_manual_algorithm_exactly():
    registry, initial = _fixture()

    moved_state, moved_seq = run_resource_orchestration(
        registry,
        initial,
        FIFOSchedulingPolicy(),
    )
    reference_state, reference_seq = _reference_run(
        registry,
        initial,
        FIFOSchedulingPolicy(),
    )

    assert moved_state.to_dict() == reference_state.to_dict()
    assert moved_state.state_hash == reference_state.state_hash
    assert moved_seq.ledger.records == reference_seq.ledger.records
    assert moved_seq.ledger.verify_integrity()
