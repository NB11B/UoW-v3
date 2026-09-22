"""Comprehensive tests for DAG Orchestration, self-hosted scheduling, and deadlock detection."""
import pytest

from uow import (
    DeterministicSequencer,
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    OrchestrationState,
    Route,
    Successor,
    WorldState,
    certify,
    create_initial_orchestration_state,
    create_transaction_descriptor,
    evaluate_scheduler_step,
    make_domain_task,
    make_uow,
    propose,
)


def test_orchestration_state_dag_dependencies_and_readiness():
    """Validates readiness logic for DAG: A -> (B, C) -> D."""
    queue = ["task_A", "task_B", "task_C", "task_D"]
    deps = {
        "task_B": ["task_A"],
        "task_C": ["task_A"],
        "task_D": ["task_B", "task_C"],
    }
    s = create_initial_orchestration_state(queue, deps)
    orch = OrchestrationState(s)

    # Initially, only A is ready
    assert orch.get_ready_tasks() == ("task_A",)

    # Dispatch A
    orch = orch.dispatch_tasks(["task_A"])
    assert orch.active == ("task_A",)
    assert orch.get_ready_tasks() == ()

    # Complete A -> now B and C are ready
    orch = orch.complete_task("task_A")
    assert orch.completed == ("task_A",)
    assert set(orch.get_ready_tasks()) == {"task_B", "task_C"}

    # Dispatch B and C concurrently
    orch = orch.dispatch_tasks(["task_B", "task_C"])
    assert set(orch.active) == {"task_B", "task_C"}
    assert orch.get_ready_tasks() == ()

    # Complete B -> D is still NOT ready (waiting on C)
    orch = orch.complete_task("task_B")
    assert orch.get_ready_tasks() == ()

    # Complete C -> now D is ready
    orch = orch.complete_task("task_C")
    assert orch.get_ready_tasks() == ("task_D",)

    # Complete D -> queue empty
    orch = orch.dispatch_tasks(["task_D"]).complete_task("task_D")
    assert orch.is_queue_empty()


def test_deadlock_detection_on_cyclic_dependencies():
    """Detects deadlock when pending work has cyclic prerequisites."""
    queue = ["task_X", "task_Y"]
    deps = {
        "task_X": ["task_Y"],
        "task_Y": ["task_X"],
    }
    s = create_initial_orchestration_state(queue, deps)
    orch = OrchestrationState(s)

    assert orch.get_ready_tasks() == ()
    assert not orch.is_queue_empty()
    assert orch.is_deadlocked()

    evaluated = evaluate_scheduler_step(s)
    assert evaluated.status == "DEADLOCKED"
    assert evaluated.cursor is None


def test_full_diamond_dag_execution_with_transactional_sequencer():
    """Executes full diamond DAG (A -> B, C -> D) under deterministic transactional sequencer."""
    queue = ["task_A", "task_B", "task_C", "task_D"]
    deps = {
        "task_B": ["task_A"],
        "task_C": ["task_A"],
        "task_D": ["task_B", "task_C"],
    }
    init_state = create_initial_orchestration_state(
        queue,
        deps,
        attributes={"r0": 0, "r1": 0},
    )

    # Build domain tasks:
    # A: r0 += 10
    # B: r0 += 20 (reads/writes r0)
    # C: r1 += 30 (reads/writes r1 - disjoint from B!)
    # D: r0 += 5, r1 += 5
    tasks = {
        "task_A": make_domain_task(
            "task_A",
            [Route(guard=Guard(GuardOp.ALWAYS), mutations=(Mutation(MutationOp.ADD, "r0", 10),))],
        ),
        "task_B": make_domain_task(
            "task_B",
            [Route(guard=Guard(GuardOp.ALWAYS), mutations=(Mutation(MutationOp.ADD, "r0", 20),))],
        ),
        "task_C": make_domain_task(
            "task_C",
            [Route(guard=Guard(GuardOp.ALWAYS), mutations=(Mutation(MutationOp.ADD, "r1", 30),))],
        ),
        "task_D": make_domain_task(
            "task_D",
            [
                Route(
                    guard=Guard(GuardOp.ALWAYS),
                    mutations=(
                        Mutation(MutationOp.ADD, "r0", 5),
                        Mutation(MutationOp.ADD, "r1", 5),
                    ),
                )
            ],
        ),
    }

    sequencer = DeterministicSequencer(init_state)

    # Step loop
    max_steps = 20
    for _ in range(max_steps):
        s = sequencer.current_state
        orch = OrchestrationState(s)
        if orch.is_queue_empty():
            break

        ready = orch.get_ready_tasks()
        if not ready:
            break

        # Dispatch next ready task
        task_id = ready[0]
        # Move task to active
        dispatched_state = orch.dispatch_tasks([task_id]).state
        sequencer._state = dispatched_state

        uow = tasks[task_id]
        prop = propose(uow, sequencer.current_state)
        tx = create_transaction_descriptor(uow, sequencer.current_state)
        cert = certify(uow, sequencer.current_state, prop)

        # Commit task mutations
        sequencer.commit(uow, prop, tx, cert)

        # Mark completed in orchestration state
        orch = OrchestrationState(sequencer.current_state)
        sequencer._state = orch.complete_task(task_id).state

    final_state = sequencer.current_state
    final_orch = OrchestrationState(final_state)

    assert final_orch.is_queue_empty()
    assert final_state.require("r0") == 35  # A(+10) + B(+20) + D(+5)
    assert final_state.require("r1") == 35  # C(+30) + D(+5)
    assert set(final_orch.completed) == {"task_A", "task_B", "task_C", "task_D"}
    assert sequencer.ledger.verify_integrity()
