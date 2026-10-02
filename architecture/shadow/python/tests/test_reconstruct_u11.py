from __future__ import annotations

from dataclasses import replace

import pytest

from uow.compat.v2 import (
    Contract,
    Guard,
    GuardOp,
    Header,
    Mutation,
    MutationOp,
    ORCH_TERMINATION_KEY,
    Route,
    SCHEDULER_CELL,
    SchedulerMaterializer,
    Successor,
    UoW,
    create_initial_orchestration_state,
    make_domain_task,
)
from uow.orchestration.materialization import certify_materialization, uow_fingerprint

from uow_shadow.reconstruction import run_orchestration_reconstructed


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


def test_r4_u11_diamond_self_hosted_orchestration_reconstructs():
    dependencies, tasks = _diamond()
    initial = create_initial_orchestration_state(
        ["A", "B", "C", "D"],
        dependencies,
        attributes={"r0": 0, "r1": 0},
    )

    result = run_orchestration_reconstructed(tasks, initial)

    assert result.final_state.require("r0") == 35
    assert result.final_state.require("r1") == 35
    assert tuple(result.final_state.get("__completed__")) == ("A", "B", "C", "D")
    assert result.final_state.status == "HALTED"
    assert result.steps == 13
    assert result.final_state.sequence == 13
    assert len(result.evidence) == 13


def test_r4_u11_replay_is_deterministic():
    dependencies, tasks = _diamond()
    initial = create_initial_orchestration_state(
        ["A", "B", "C", "D"],
        dependencies,
        attributes={"r0": 0, "r1": 0},
    )

    a = run_orchestration_reconstructed(tasks, initial)
    b = run_orchestration_reconstructed(tasks, initial)

    assert a.final_state.state_hash == b.final_state.state_hash
    assert a.evidence_root() == b.evidence_root()
    assert tuple(e.entry_identity for e in a.evidence) == tuple(
        e.entry_identity for e in b.evidence
    )


def test_r4_u11_deadlock_remains_certified_terminal_transition():
    initial = create_initial_orchestration_state(
        ["X", "Y"],
        {"X": ("Y",), "Y": ("X",)},
    )

    result = run_orchestration_reconstructed({}, initial)

    assert result.final_state.status == "HALTED"
    assert result.final_state.get(ORCH_TERMINATION_KEY) == "DEADLOCKED"
    assert result.steps == 1
    assert len(result.evidence) == 1


def test_r4_u11_tampered_scheduler_materialization_remains_rejected():
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


def test_r4_u11_runner_does_not_use_canonical_orchestration_runtime(monkeypatch):
    import uow.orchestration.runtime as canonical_runtime

    def forbidden(*args, **kwargs):
        raise AssertionError("canonical orchestration runtime must not be used")

    monkeypatch.setattr(canonical_runtime, "run_orchestration", forbidden)

    dependencies, tasks = _diamond()
    initial = create_initial_orchestration_state(
        ["A", "B", "C", "D"],
        dependencies,
        attributes={"r0": 0, "r1": 0},
    )

    result = run_orchestration_reconstructed(tasks, initial)
    assert result.final_state.status == "HALTED"
