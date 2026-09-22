"""Comprehensive tests for Resource Governance, atomic leases, and pluggable scheduling policies."""
import pytest

from uow import (
    DEFAULT_HOST_CAPACITIES,
    CostEnergySchedulingPolicy,
    DeterministicSequencer,
    FIFOSchedulingPolicy,
    GreedyCapacitySchedulingPolicy,
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    PriorityDeadlineSchedulingPolicy,
    ResourceLease,
    ResourceRequirement,
    ResourceState,
    Route,
    Successor,
    WorldState,
    certify,
    create_transaction_descriptor,
    filter_feasible_candidates,
    make_uow,
    propose,
)


def _make_res_workload():
    """Builds a set of competing tasks with distinct resource footprints."""
    reqs = {
        "task_small": ResourceRequirement(cpu_cores=1, ram_units=2, priority=10, deadline=100),
        "task_heavy_cpu": ResourceRequirement(cpu_cores=6, ram_units=4, priority=5, deadline=50),
        "task_heavy_gpu": ResourceRequirement(cpu_cores=2, ram_units=8, gpu_slots=1, priority=2, deadline=20),
        "task_npu": ResourceRequirement(cpu_cores=1, ram_units=2, npu_slots=2, priority=1, deadline=10, cost=0.05, energy_budget=10),
        "task_expensive": ResourceRequirement(cpu_cores=2, ram_units=4, cost=5.0, energy_budget=500),
    }
    return reqs


def test_gate_u13_1_and_u13_2_capacity_tracking_and_overallocation_rejection():
    """Verifies available capacity calculation and strict rejection on overallocation."""
    custom_capacities = {"cpu_cores": 8, "ram_units": 16, "gpu_slots": 1, "npu_slots": 0}
    res = ResourceState(capacities=custom_capacities)

    assert res.available("cpu_cores") == 8
    assert res.available("ram_units") == 16
    assert res.available("gpu_slots") == 1
    assert res.available("npu_slots") == 0

    # Valid lease acquisition
    req_valid = ResourceRequirement(cpu_cores=4, ram_units=8, gpu_slots=1)
    res_after, lease = res.acquire_lease("task_1", req_valid, sequence=1)
    assert res_after.available("cpu_cores") == 4
    assert res_after.available("ram_units") == 8
    assert res_after.available("gpu_slots") == 0
    assert len(res_after.leases) == 1
    assert lease.uow_id == "task_1"

    # Overallocation rejection: attempting to acquire another GPU slot when 0 available
    req_invalid = ResourceRequirement(gpu_slots=1)
    assert not res_after.can_accommodate(req_invalid)
    with pytest.raises(ValueError, match="Resource over-allocation rejected on 'gpu_slots'"):
        res_after.acquire_lease("task_2", req_invalid, sequence=2)


def test_gate_u13_4_atomic_lease_acquisition_and_release():
    """Lease is acquired and released cleanly."""
    res = ResourceState(capacities={"cpu_cores": 4, "ram_units": 8})
    req = ResourceRequirement(cpu_cores=3, ram_units=4)

    res_acquired, lease = res.acquire_lease("task_A", req, sequence=1)
    assert res_acquired.available("cpu_cores") == 1
    assert res_acquired.available("ram_units") == 4
    assert len(res_acquired.leases) == 1

    # Release by uow_id
    res_released = res_acquired.release_lease("task_A")
    assert res_released.available("cpu_cores") == 4
    assert res_released.available("ram_units") == 8
    assert len(res_released.leases) == 0


def test_gate_u13_5_legality_dominance_over_candidates():
    """Policy selection MUST obey capacity bounds even under aggressive greed or priority."""
    capacities = {"cpu_cores": 4, "ram_units": 8, "gpu_slots": 1, "npu_slots": 0}
    res = ResourceState(capacities=capacities)
    reqs = {
        "t1": ResourceRequirement(cpu_cores=3, ram_units=4),
        "t2": ResourceRequirement(cpu_cores=3, ram_units=4),  # Cannot fit concurrently with t1!
    }
    candidates = ["t1", "t2"]

    fifo = FIFOSchedulingPolicy()
    selected = fifo.select_schedule(candidates, lambda cid: reqs[cid], res)

    # Only t1 could fit
    assert selected == ["t1"]

    total_cpu = sum(reqs[t].cpu_cores for t in selected)
    total_ram = sum(reqs[t].ram_units for t in selected)
    assert total_cpu <= capacities["cpu_cores"]
    assert total_ram <= capacities["ram_units"]


def test_gate_u13_6_priority_and_deadline_order():
    """PriorityDeadlinePolicy orders by priority and earlier deadlines."""
    capacities = {"cpu_cores": 10, "ram_units": 20, "gpu_slots": 2, "npu_slots": 2}
    res = ResourceState(capacities=capacities)
    reqs = {
        "low_pri": ResourceRequirement(cpu_cores=1, priority=10, deadline=100),
        "high_pri": ResourceRequirement(cpu_cores=1, priority=2, deadline=50),
        "urgent_deadline": ResourceRequirement(cpu_cores=1, priority=2, deadline=10),
    }
    candidates = ["low_pri", "high_pri", "urgent_deadline"]

    policy = PriorityDeadlineSchedulingPolicy()
    selected = policy.select_schedule(candidates, lambda cid: reqs[cid], res)

    # Both high_pri and urgent_deadline have priority 2, but urgent_deadline has deadline 10 < 50
    assert selected[0] == "urgent_deadline"
    assert selected[1] == "high_pri"
    assert selected[2] == "low_pri"


def test_gate_u13_7_starvation_freedom_via_aging():
    """Starving tasks are boosted to urgency rank 0 after threshold scheduling rounds."""
    capacities = {"cpu_cores": 10, "ram_units": 20, "gpu_slots": 2, "npu_slots": 2}
    res = ResourceState(capacities=capacities)
    reqs = {
        "normal": ResourceRequirement(cpu_cores=1, priority=1),
        "neglected": ResourceRequirement(cpu_cores=1, priority=10),
    }
    candidates = ["normal", "neglected"]

    policy = PriorityDeadlineSchedulingPolicy(starvation_threshold=3)

    # Initially, 'normal' is first
    sel_init = policy.select_schedule(candidates, lambda cid: reqs[cid], res)
    assert sel_init[0] == "normal"

    # Simulate 3 rounds of 'neglected' being ready but starved
    starved_res = res
    for _ in range(3):
        starved_res = starved_res.record_starvation(["neglected"])

    assert starved_res.starvation_counters["neglected"] == 3

    # Now 'neglected' must be boosted to the top
    sel_boosted = policy.select_schedule(candidates, lambda cid: reqs[cid], starved_res)
    assert sel_boosted[0] == "neglected"


def test_gate_u13_10_swappable_policies_different_profiles():
    """Demonstrates all 4 policies choose different optimal subsets based on their objective."""
    capacities = {"cpu_cores": 6, "ram_units": 12, "gpu_slots": 1, "npu_slots": 1, "energy_budget": 1000}
    res = ResourceState(capacities=capacities)
    reqs = {
        "c_heavy": ResourceRequirement(cpu_cores=5, ram_units=10, priority=1, cost=10.0, energy_budget=100),
        "c_light1": ResourceRequirement(cpu_cores=1, ram_units=2, priority=5, cost=1.0, energy_budget=10),
        "c_light2": ResourceRequirement(cpu_cores=1, ram_units=2, priority=6, cost=1.0, energy_budget=10),
    }
    candidates = ["c_heavy", "c_light1", "c_light2"]

    # 1. FIFO: picks c_heavy first (fits 5/6 cpu), then c_light1 fits (5+1 = 6/6 cpu), c_light2 cannot fit!
    fifo = FIFOSchedulingPolicy()
    assert fifo.select_schedule(candidates, lambda c: reqs[c], res) == ["c_heavy", "c_light1"]

    # 2. GreedyCapacity: sorts by smallest footprint first -> picks light1, light2, then heavy doesn't fit!
    greedy = GreedyCapacitySchedulingPolicy()
    assert greedy.select_schedule(candidates, lambda c: reqs[c], res) == ["c_light1", "c_light2"]

    # 3. CostEnergy: sorts by cost ascending -> picks light1, light2
    cost_pol = CostEnergySchedulingPolicy()
    assert cost_pol.select_schedule(candidates, lambda c: reqs[c], res) == ["c_light1", "c_light2"]
