"""Comprehensive canonical tests for Resource Governance, atomic leases, and pluggable scheduling policies."""
import copy
import pytest

from uow import (
    COMPLETION_PREFIX,
    Contract,
    CostEnergySchedulingPolicy,
    DEFAULT_HOST_CAPACITIES,
    DeterministicSequencer,
    FIFOSchedulingPolicy,
    GreedyCapacitySchedulingPolicy,
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    ORCH_ACTIVE_KEY,
    ORCH_COMPLETED_KEY,
    ORCH_QUEUE_KEY,
    ORCH_RESOURCES_KEY,
    ORCH_TERMINATION_KEY,
    PriorityDeadlineSchedulingPolicy,
    ResourceAwareCompletionMaterializer,
    ResourceAwareSchedulerMaterializer,
    ResourceBoundTask,
    ResourceLease,
    ResourceRequirement,
    ResourceState,
    Route,
    SCHEDULER_ID,
    Successor,
    SuccessorKind,
    UoW,
    WorldState,
    certify,
    certify_materialization,
    create_initial_orchestration_state,
    create_transaction_descriptor,
    filter_feasible_candidates,
    get_authoritative_resource_state,
    make_resource_domain_task,
    make_uow,
    propose,
    run_resource_orchestration,
    set_authoritative_resource_state,
    verify_requirement_binding,
)


def _build_competing_resource_dag():
    """Builds a Diamond DAG A -> (B, C) -> D with competing resource footprints."""
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

    task_a = make_resource_domain_task(
        "A",
        [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 10),))],
        req_a,
    )
    task_b = make_resource_domain_task(
        "B",
        [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 20),))],
        req_b,
    )
    task_c = make_resource_domain_task(
        "C",
        [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r1", 30),))],
        req_c,
    )
    task_d = make_resource_domain_task(
        "D",
        [
            Route(
                Guard(GuardOp.ALWAYS),
                (Mutation(MutationOp.ADD, "r0", 5), Mutation(MutationOp.ADD, "r1", 5)),
            )
        ],
        req_d,
    )

    registry = {"A": task_a, "B": task_b, "C": task_c, "D": task_d}
    dependencies = {"B": ["A"], "C": ["A"], "D": ["B", "C"]}
    queue = ["A", "B", "C", "D"]

    initial_base = create_initial_orchestration_state(
        queue=queue,
        dependencies=dependencies,
        attributes={"r0": 0, "r1": 0},
    )
    initial_state = set_authoritative_resource_state(initial_base, res_state)

    return registry, initial_state


# ===========================================================================
# 1. State Binding & Invariant Tests
# ===========================================================================

def test_resource_state_is_hash_bound_in_world_state():
    """Mutating capacities, allocations, or leases directly alters state_hash."""
    base = WorldState(attributes={"x": 1})
    res_1 = ResourceState(capacities={"cpu_cores": 4, "ram_units": 8})
    res_2 = ResourceState(capacities={"cpu_cores": 8, "ram_units": 8})

    s1 = set_authoritative_resource_state(base, res_1)
    s2 = set_authoritative_resource_state(base, res_2)

    assert s1.state_hash != s2.state_hash
    assert get_authoritative_resource_state(s1).capacities["cpu_cores"] == 4
    assert get_authoritative_resource_state(s2).capacities["cpu_cores"] == 8


def test_work_bound_resource_requirement_integrity():
    """Task Header.parent_context binds requirement hash, verified by verify_requirement_binding."""
    req = ResourceRequirement(cpu_cores=4, ram_units=8)
    task = make_resource_domain_task(
        "task_x",
        [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 1),))],
        req,
    )
    assert task.uow.H.parent_context == f"req:{task.requirement_hash}"
    assert verify_requirement_binding(task) is True

    # Forged task with mismatching requirement
    forged_req = ResourceRequirement(cpu_cores=1, ram_units=1)
    forged_task = ResourceBoundTask(uow=task.uow, requirement=forged_req)
    assert verify_requirement_binding(forged_task) is False


# ===========================================================================
# 2. Strict Falsification Tests
# ===========================================================================

def test_falsification_1_dispatch_without_lease_is_rejected():
    """If a scheduler attempts to dispatch a task without granting a lease in __resources__, certification fails."""
    registry, initial_state = _build_competing_resource_dag()
    scheduler_mat = ResourceAwareSchedulerMaterializer(registry, FIFOSchedulingPolicy())

    valid_mat = scheduler_mat.materialize(initial_state)
    assert certify_materialization(scheduler_mat, initial_state, valid_mat)

    # Malicious materialization: dispatches task 'A' into active, but omits resource lease mutation
    tampered_routes = [
        Route(
            guard=Guard(GuardOp.ALWAYS),
            mutations=(
                Mutation(MutationOp.SET, ORCH_QUEUE_KEY, ("B", "C", "D")),
                Mutation(MutationOp.SET, ORCH_ACTIVE_KEY, ("A",)),
            ),
            successor=Successor.static("A"),
        )
    ]
    tampered_uow = copy.deepcopy(valid_mat.uow)
    object.__setattr__(tampered_uow, "Gamma", Contract(tuple(tampered_routes)))
    tampered_mat = copy.deepcopy(valid_mat)
    object.__setattr__(tampered_mat, "uow", tampered_uow)

    assert not certify_materialization(scheduler_mat, initial_state, tampered_mat)


def test_falsification_2_lease_without_dispatch_is_rejected():
    """If a scheduler mutates resource allocations without dispatching the task, certification fails."""
    registry, initial_state = _build_competing_resource_dag()
    scheduler_mat = ResourceAwareSchedulerMaterializer(registry, FIFOSchedulingPolicy())
    valid_mat = scheduler_mat.materialize(initial_state)

    res_state = get_authoritative_resource_state(initial_state)
    res_tampered, _ = res_state.acquire_lease("A", registry["A"].requirement, sequence=1)

    # Malicious: updates resources, but leaves active set empty
    tampered_routes = [
        Route(
            guard=Guard(GuardOp.ALWAYS),
            mutations=(
                Mutation(MutationOp.SET, ORCH_QUEUE_KEY, ("A", "B", "C", "D")),
                Mutation(MutationOp.SET, ORCH_ACTIVE_KEY, ()),
                Mutation(MutationOp.SET, ORCH_RESOURCES_KEY, res_tampered.to_dict()),
            ),
            successor=Successor.static(SCHEDULER_ID),
        )
    ]
    tampered_uow = copy.deepcopy(valid_mat.uow)
    object.__setattr__(tampered_uow, "Gamma", Contract(tuple(tampered_routes)))
    tampered_mat = copy.deepcopy(valid_mat)
    object.__setattr__(tampered_mat, "uow", tampered_uow)

    assert not certify_materialization(scheduler_mat, initial_state, tampered_mat)


def test_falsification_3_overallocation_rejection():
    """Scheduler materializer strictly refuses to materialize dispatch for tasks exceeding capacity."""
    host_caps = {"cpu_cores": 2, "ram_units": 4}
    res_state = ResourceState(capacities=host_caps)
    req_heavy = ResourceRequirement(cpu_cores=4, ram_units=4)
    task_heavy = make_resource_domain_task(
        "heavy",
        [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 1),))],
        req_heavy,
    )
    registry = {"heavy": task_heavy}
    init_base = create_initial_orchestration_state(["heavy"], {})
    init_state = set_authoritative_resource_state(init_base, res_state)

    scheduler_mat = ResourceAwareSchedulerMaterializer(registry, FIFOSchedulingPolicy())
    mat = scheduler_mat.materialize(init_state)
    proposal = propose(mat.uow, init_state)
    assert proposal.proposed_state.get(ORCH_TERMINATION_KEY) == "RESOURCES_BLOCKED"
    assert proposal.halted is True


def test_falsification_4_forged_resource_requirement_rejection():
    """Direct invariant check rejects forged requirements immediately before scheduling."""
    registry, initial_state = _build_competing_resource_dag()

    # Create an imposter registry entry where 'A' has an unverified forged requirement
    imposter_registry = dict(registry)
    forged_req = ResourceRequirement(cpu_cores=0, ram_units=0)
    imposter_registry["A"] = ResourceBoundTask(uow=registry["A"].uow, requirement=forged_req)

    # Invariant failure must trigger directly inside materialize
    scheduler_mat = ResourceAwareSchedulerMaterializer(imposter_registry, FIFOSchedulingPolicy())
    with pytest.raises(ValueError, match="Requirement cryptographic binding violated"):
        scheduler_mat.materialize(initial_state)


def test_falsification_5_stale_resource_state_rejection():
    """Attempting to certify a materialization bound to a stale pre_state_hash fails."""
    registry, initial_state = _build_competing_resource_dag()
    scheduler_mat = ResourceAwareSchedulerMaterializer(registry, FIFOSchedulingPolicy())
    mat = scheduler_mat.materialize(initial_state)

    evolved_state = initial_state.advance_sequence()
    assert not certify_materialization(scheduler_mat, evolved_state, mat)


def test_falsification_6_incorrect_lease_release_rejection():
    """Completion materialization must release the exact matching lease; tampering is rejected."""
    registry, initial_state = _build_competing_resource_dag()
    scheduler_mat = ResourceAwareSchedulerMaterializer(registry, FIFOSchedulingPolicy())
    mat_sched = scheduler_mat.materialize(initial_state)
    prop = propose(mat_sched.uow, initial_state)
    cert = certify(mat_sched.uow, initial_state, prop)
    seq = DeterministicSequencer(initial_state)
    tx = create_transaction_descriptor(mat_sched.uow, initial_state)
    state_after_dispatch, _ = seq.commit(mat_sched.uow, prop, tx, cert)

    comp_mat = ResourceAwareCompletionMaterializer("A")
    valid_comp = comp_mat.materialize(state_after_dispatch)
    assert certify_materialization(comp_mat, state_after_dispatch, valid_comp)

    # Tampered completion: marks A completed, but forgets to release lease in __resources__
    tampered_routes = [
        Route(
            guard=Guard(GuardOp.ALWAYS),
            mutations=(
                Mutation(MutationOp.SET, ORCH_ACTIVE_KEY, ()),
                Mutation(MutationOp.SET, ORCH_COMPLETED_KEY, ("A",)),
            ),
            successor=Successor.static(SCHEDULER_ID),
        )
    ]
    tampered_uow = copy.deepcopy(valid_comp.uow)
    object.__setattr__(tampered_uow, "Gamma", Contract(tuple(tampered_routes)))
    tampered_comp = copy.deepcopy(valid_comp)
    object.__setattr__(tampered_comp, "uow", tampered_uow)

    assert not certify_materialization(comp_mat, state_after_dispatch, tampered_comp)


# ===========================================================================
# 3. Execution, Determinism, and Policy Discrepancy Tests
# ===========================================================================

def test_full_resource_orchestration_execution():
    """Full execution of Diamond DAG under resource governance with leased and consumable accounting."""
    registry, initial_state = _build_competing_resource_dag()
    final_state, seq = run_resource_orchestration(registry, initial_state, FIFOSchedulingPolicy())

    assert final_state.status == "HALTED"
    assert final_state.require("r0") == 35  # A(+10) + B(+20) + D(+5)
    assert final_state.require("r1") == 35  # C(+30) + D(+5)
    assert seq.ledger.verify_integrity()

    final_res = get_authoritative_resource_state(final_state)
    # Leased capacities return cleanly
    assert len(final_res.leases) == 0
    assert final_res.available("cpu_cores") == 8
    assert final_res.available("ram_units") == 16
    assert final_res.available("gpu_slots") == 1

    # Consumable energy budget was debited permanently: 1000 - 500 = 500
    assert final_res.capacities["energy_budget"] == 500


def test_gate_u13_replay_determinism_same_policy():
    """Same initial state + same policy -> byte-for-byte identical evidence root hash."""
    registry, initial_state = _build_competing_resource_dag()

    final_1, seq_1 = run_resource_orchestration(registry, initial_state, FIFOSchedulingPolicy())
    final_2, seq_2 = run_resource_orchestration(registry, initial_state, FIFOSchedulingPolicy())

    assert final_1.state_hash == final_2.state_hash
    assert seq_1.ledger.root_hash() == seq_2.ledger.root_hash()


def test_gate_u13_policy_discrepancy_different_legal_histories():
    """Different scheduling heuristics produce distinct valid certified histories."""
    registry, initial_state = _build_competing_resource_dag()

    final_fifo, seq_fifo = run_resource_orchestration(registry, initial_state, FIFOSchedulingPolicy())
    final_cost, seq_cost = run_resource_orchestration(registry, initial_state, CostEnergySchedulingPolicy())

    assert final_fifo.status == "HALTED"
    assert final_cost.status == "HALTED"
    assert final_fifo.require("r0") == 35
    assert final_cost.require("r0") == 35
    assert seq_fifo.ledger.verify_integrity()
    assert seq_cost.ledger.verify_integrity()

    # Evidence roots must differ because dispatch order differed
    assert seq_fifo.ledger.root_hash() != seq_cost.ledger.root_hash()
