"""Regression tests for certified scheduler materialization and DAG orchestration."""
from __future__ import annotations

from dataclasses import replace
import random

from uow import (
    CompletionMaterializer,
    Contract,
    Guard,
    GuardOp,
    Header,
    MatrixCell,
    Mutation,
    MutationOp,
    ORCH_TERMINATION_KEY,
    OrchestrationState,
    Route,
    SCHEDULER_CELL,
    SchedulerMaterializer,
    Successor,
    UoW,
    WorkCategory,
    WorldState,
    certify,
    certify_materialization,
    create_initial_orchestration_state,
    evaluate_scheduler_step,
    make_domain_task,
    propose,
    run_orchestration,
    uow_fingerprint,
)


def _diamond():
    dependencies = {
        "A": (),
        "B": ("A",),
        "C": ("A",),
        "D": ("B", "C"),
    }
    tasks = {
        "A": make_domain_task(
            "A",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 10),))],
        ),
        "B": make_domain_task(
            "B",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 20),))],
        ),
        "C": make_domain_task(
            "C",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r1", 30),))],
        ),
        "D": make_domain_task(
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
        ),
    }
    return dependencies, tasks


def test_orchestration_state_dag_dependencies_and_readiness():
    queue = ["A", "B", "C", "D"]
    dependencies, _tasks = _diamond()
    state = create_initial_orchestration_state(queue, dependencies)
    orch = OrchestrationState(state)

    assert orch.get_ready_tasks() == ("A",)

    orch = orch.dispatch_tasks(["A"])
    assert orch.active == ("A",)
    assert orch.get_ready_tasks() == ()

    orch = orch.complete_task("A")
    assert set(orch.get_ready_tasks()) == {"B", "C"}

    orch = orch.dispatch_tasks(["B", "C"])
    assert set(orch.active) == {"B", "C"}

    orch = orch.complete_task("B")
    assert orch.get_ready_tasks() == ()

    orch = orch.complete_task("C")
    assert orch.get_ready_tasks() == ("D",)


def test_diamond_every_authoritative_change_is_certified():
    dependencies, tasks = _diamond()
    initial = create_initial_orchestration_state(
        ["A", "B", "C", "D"],
        dependencies,
        attributes={"r0": 0, "r1": 0},
    )

    final, sequencer = run_orchestration(tasks, initial)

    assert final.require("r0") == 35
    assert final.require("r1") == 35
    assert tuple(final.get("__completed__")) == ("A", "B", "C", "D")
    assert final.status == "HALTED"

    # dispatch + domain task + completion for every task + final scheduler halt
    assert len(sequencer.ledger.records) == 13
    assert final.sequence == len(sequencer.ledger.records)
    assert sequencer.ledger.verify_integrity()

    identities = [record.uow_id for record in sequencer.ledger.records]
    assert identities.count("uow_scheduler") == 5
    assert sum(identity.startswith("complete::") for identity in identities) == 4

    # Every authoritative transition extends the evidence chain.
    assert all(
        sequencer.ledger.records[index].pre_state_hash
        == (
            initial.state_hash
            if index == 0
            else sequencer.ledger.records[index - 1].post_state_hash
        )
        for index in range(len(sequencer.ledger.records))
    )


def test_deterministic_replay_reproduces_final_state_and_evidence_root():
    dependencies, tasks = _diamond()
    initial = create_initial_orchestration_state(
        ["A", "B", "C", "D"],
        dependencies,
        attributes={"r0": 0, "r1": 0},
    )

    final_a, seq_a = run_orchestration(tasks, initial)
    final_b, seq_b = run_orchestration(tasks, initial)

    assert final_a.state_hash == final_b.state_hash
    assert seq_a.ledger.root_hash() == seq_b.ledger.root_hash()
    assert [r.record_hash for r in seq_a.ledger.records] == [
        r.record_hash for r in seq_b.ledger.records
    ]


def test_tampered_scheduler_materialization_is_rejected():
    dependencies, _tasks = _diamond()
    state = create_initial_orchestration_state(
        ["A", "B", "C", "D"],
        dependencies,
        attributes={"r0": 0, "r1": 0},
    )
    materializer = SchedulerMaterializer()
    legitimate = materializer.materialize(state)

    forged_uow = UoW(
        H=Header(
            identity="uow_scheduler",
            source_category=SCHEDULER_CELL.source,
            target_category=SCHEDULER_CELL.target,
            layer="orchestration",
            parent_context="scheduler-materialization",
        ),
        Gamma=Contract(
            (
                Route(
                    Guard(GuardOp.ALWAYS),
                    (
                        Mutation(MutationOp.SET, "__queue__", ("A", "B", "C")),
                        Mutation(MutationOp.SET, "__active__", ("D",)),
                    ),
                    Successor.static("D"),
                ),
            )
        ),
    )
    forged = replace(
        legitimate,
        uow=forged_uow,
        materialization_hash=uow_fingerprint(forged_uow),
    )

    assert not certify_materialization(materializer, state, forged)


def test_corrupted_scheduler_post_state_is_rejected_by_core_certifier():
    dependencies, _tasks = _diamond()
    state = create_initial_orchestration_state(
        ["A", "B", "C", "D"],
        dependencies,
        attributes={"r0": 0, "r1": 0},
    )
    materializer = SchedulerMaterializer()
    materialized = materializer.materialize(state)

    assert certify_materialization(materializer, state, materialized)
    proposal = propose(materialized.uow, state)
    corrupted = replace(
        proposal,
        proposed_state=proposal.proposed_state.with_attribute("__active__", ("D",)),
    )

    assert not certify(materialized.uow, state, corrupted).is_valid


def test_deadlock_is_a_certified_terminal_transition():
    initial = create_initial_orchestration_state(
        ["X", "Y"],
        {"X": ("Y",), "Y": ("X",)},
    )

    final, sequencer = run_orchestration({}, initial)

    assert final.status == "HALTED"
    assert final.get(ORCH_TERMINATION_KEY) == "DEADLOCKED"
    assert len(sequencer.ledger.records) == 1
    assert sequencer.ledger.records[0].uow_id == "uow_scheduler"
    assert sequencer.ledger.verify_integrity()


def _random_dag(rng: random.Random, size: int):
    names = [f"T{i}" for i in range(size)]
    dependencies = {}
    for index, task in enumerate(names):
        dependencies[task] = tuple(
            candidate for candidate in names[:index] if rng.random() < 0.25
        )
    return names, dependencies


def test_250_random_dags_complete_with_every_transition_evidenced():
    rng = random.Random(20260921)

    for _ in range(250):
        size = rng.randint(2, 12)
        names, dependencies = _random_dag(rng, size)
        tasks = {
            task: make_domain_task(
                task,
                [
                    Route(
                        Guard(GuardOp.ALWAYS),
                        (Mutation(MutationOp.ADD, "count", 1),),
                    )
                ],
            )
            for task in names
        }
        initial = create_initial_orchestration_state(
            names,
            dependencies,
            attributes={"count": 0},
        )

        final, sequencer = run_orchestration(
            tasks,
            initial,
            max_steps=4 * size + 10,
        )

        assert final.status == "HALTED"
        assert final.require("count") == size
        assert set(final.get("__completed__")) == set(names)
        assert final.sequence == len(sequencer.ledger.records) == 3 * size + 1
        assert sequencer.ledger.records[-1].uow_id == "uow_scheduler"
        assert sequencer.ledger.verify_integrity()


def test_10000_materializations_match_reference_scheduler_semantics():
    rng = random.Random(7112026)
    materializer = SchedulerMaterializer()

    for _ in range(10_000):
        size = rng.randint(0, 10)
        names = [f"T{i}" for i in range(size)]
        dependencies = {
            task: tuple(
                candidate
                for candidate in names[:index]
                if rng.random() < 0.2
            )
            for index, task in enumerate(names)
        }
        completed_count = rng.randint(0, size)
        completed = tuple(names[:completed_count])
        queue = tuple(names[completed_count:])
        state = WorldState(
            attributes={
                "__queue__": queue,
                "__active__": (),
                "__completed__": completed,
                "__deps__": dependencies,
            },
            cursor="uow_scheduler",
        )

        expected = evaluate_scheduler_step(state)
        materialized = materializer.materialize(state)
        assert certify_materialization(materializer, state, materialized)

        proposal = propose(materialized.uow, state)
        certificate = certify(materialized.uow, state, proposal)
        assert certificate.is_valid

        # Compare at the proposed-state boundary; transactional commit adds versions.
        actual = proposal.proposed_state
        assert actual.attributes == expected.attributes
        assert actual.cursor == expected.cursor
        assert actual.status == expected.status
