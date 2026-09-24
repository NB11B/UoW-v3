from __future__ import annotations

import pytest

from uow import (
    CostEnergySchedulingPolicy,
    FIFOSchedulingPolicy,
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    ORCH_TERMINATION_KEY,
    ResourceBoundTask,
    ResourceRequirement,
    ResourceState,
    Route,
    create_initial_orchestration_state,
    get_authoritative_resource_state,
    make_resource_domain_task,
    set_authoritative_resource_state,
)

from uow_shadow.reconstruction import run_resource_orchestration_reconstructed


def _build():
    host_caps = {
        "cpu_cores": 8,
        "ram_units": 16,
        "gpu_slots": 1,
        "npu_slots": 0,
        "energy_budget": 1000,
        "cost": 100,
    }
    res_state = ResourceState(capacities=host_caps)

    req_a = ResourceRequirement(cpu_cores=4, ram_units=8, priority=1, energy_budget=100)
    req_b = ResourceRequirement(cpu_cores=6, ram_units=8, priority=2, cost=10.0, energy_budget=200)
    req_c = ResourceRequirement(cpu_cores=4, ram_units=8, gpu_slots=1, priority=3, cost=5.0, energy_budget=150)
    req_d = ResourceRequirement(cpu_cores=2, ram_units=4, priority=1, energy_budget=50)

    registry = {
        "A": make_resource_domain_task(
            "A",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 10),))],
            req_a,
        ),
        "B": make_resource_domain_task(
            "B",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 20),))],
            req_b,
        ),
        "C": make_resource_domain_task(
            "C",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r1", 30),))],
            req_c,
        ),
        "D": make_resource_domain_task(
            "D",
            [
                Route(
                    Guard(GuardOp.ALWAYS),
                    (
                        Mutation(MutationOp.ADD, "r0", 5),
                        Mutation(MutationOp.ADD, "r1", 5),
                    ),
                )
            ],
            req_d,
        ),
    }
    dependencies = {"B": ["A"], "C": ["A"], "D": ["B", "C"]}
    base = create_initial_orchestration_state(
        ["A", "B", "C", "D"],
        dependencies,
        attributes={"r0": 0, "r1": 0},
    )
    return registry, set_authoritative_resource_state(base, res_state)


def test_r4_u13_full_resource_orchestration_reconstructs():
    registry, initial = _build()
    result = run_resource_orchestration_reconstructed(
        registry,
        initial,
        FIFOSchedulingPolicy(),
    )

    assert result.final_state.status == "HALTED"
    assert result.final_state.require("r0") == 35
    assert result.final_state.require("r1") == 35

    final_res = get_authoritative_resource_state(result.final_state)
    assert len(final_res.leases) == 0
    assert final_res.available("cpu_cores") == 8
    assert final_res.available("ram_units") == 16
    assert final_res.available("gpu_slots") == 1
    assert final_res.capacities["energy_budget"] == 500


def test_r4_u13_overallocation_fails_closed_as_resources_blocked():
    res = ResourceState(capacities={"cpu_cores": 2, "ram_units": 4})
    heavy = make_resource_domain_task(
        "heavy",
        [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 1),))],
        ResourceRequirement(cpu_cores=4, ram_units=4),
    )
    base = create_initial_orchestration_state(["heavy"], {}, attributes={"r0": 0})
    initial = set_authoritative_resource_state(base, res)

    result = run_resource_orchestration_reconstructed(
        {"heavy": heavy},
        initial,
        FIFOSchedulingPolicy(),
    )

    assert result.final_state.status == "HALTED"
    assert result.final_state.get(ORCH_TERMINATION_KEY) == "RESOURCES_BLOCKED"
    assert result.final_state.get("r0") == 0


def test_r4_u13_forged_requirement_is_rejected_before_execution():
    registry, initial = _build()
    forged = dict(registry)
    forged["A"] = ResourceBoundTask(
        uow=registry["A"].uow,
        requirement=ResourceRequirement(cpu_cores=0, ram_units=0),
    )

    with pytest.raises(ValueError, match="Requirement cryptographic binding violated"):
        run_resource_orchestration_reconstructed(
            forged,
            initial,
            FIFOSchedulingPolicy(),
        )


def test_r4_u13_policy_diversity_preserves_result_but_changes_evidence_history():
    registry, initial = _build()

    fifo = run_resource_orchestration_reconstructed(
        registry,
        initial,
        FIFOSchedulingPolicy(),
    )
    cost = run_resource_orchestration_reconstructed(
        registry,
        initial,
        CostEnergySchedulingPolicy(),
    )

    assert fifo.final_state.status == "HALTED"
    assert cost.final_state.status == "HALTED"
    assert fifo.final_state.require("r0") == cost.final_state.require("r0") == 35
    assert fifo.final_state.require("r1") == cost.final_state.require("r1") == 35
    assert fifo.evidence_root() != cost.evidence_root()


def test_r4_u13_same_policy_replays_deterministically():
    registry, initial = _build()
    a = run_resource_orchestration_reconstructed(
        registry,
        initial,
        FIFOSchedulingPolicy(),
    )
    b = run_resource_orchestration_reconstructed(
        registry,
        initial,
        FIFOSchedulingPolicy(),
    )

    assert a.final_state.state_hash == b.final_state.state_hash
    assert a.evidence_root() == b.evidence_root()
