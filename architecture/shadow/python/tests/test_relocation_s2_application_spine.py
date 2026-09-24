from __future__ import annotations

import inspect

from uow import (
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    Route,
    Successor,
    create_initial_orchestration_state,
    make_domain_task,
)
from uow.engine import certify, propose
from uow.orchestration.materialization import certify_materialization
from uow.orchestration.runtime import run_orchestration
from uow.orchestration.scheduler import (
    COMPLETION_PREFIX,
    CompletionMaterializer,
    SCHEDULER_ID,
    SchedulerMaterializer,
)
from uow.transactions import DeterministicSequencer, create_transaction_descriptor
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


def _reference_apply(uow, sequencer):
    before = sequencer.current_state
    proposal = propose(uow, before)
    certificate = certify(uow, before, proposal)
    assert certificate.is_valid
    transaction = create_transaction_descriptor(uow, before)
    committed, _ = sequencer.commit(uow, proposal, transaction, certificate)
    return committed


def _reference_run(tasks, initial, max_steps=10_000):
    sequencer = DeterministicSequencer(initial)
    scheduler = SchedulerMaterializer()

    for _ in range(max_steps):
        state = sequencer.current_state
        if state.status != "RUNNING" or state.cursor is None:
            return state, sequencer

        cursor = state.cursor
        if cursor == SCHEDULER_ID:
            before = sequencer.current_state
            materialized = scheduler.materialize(before)
            assert certify_materialization(scheduler, before, materialized)
            _reference_apply(materialized.uow, sequencer)
            continue

        if cursor.startswith(COMPLETION_PREFIX):
            task_id = cursor[len(COMPLETION_PREFIX):]
            completion = CompletionMaterializer(task_id)
            before = sequencer.current_state
            materialized = completion.materialize(before)
            assert certify_materialization(completion, before, materialized)
            _reference_apply(materialized.uow, sequencer)
            continue

        _reference_apply(tasks[cursor], sequencer)

    raise RuntimeError("reference orchestration step budget exceeded")


def _without_occ_versions(state):
    attrs = dict(state.attributes)
    attrs.pop("__versions__", None)
    return {
        "attributes": attrs,
        "cursor": state.cursor,
        "status": state.status,
        "sequence": state.sequence,
    }


def test_s2_orchestration_runtime_uses_common_application_spine():
    import uow.orchestration.runtime as runtime

    source = inspect.getsource(runtime)
    assert "DEFAULT_APPLICATION_SPINE.execute" in source
    assert "propose(" not in source
    assert "certify(" not in source
    assert "create_transaction_descriptor(" not in source
    assert "sequencer.commit(" not in source


def test_s2_orchestration_runtime_is_exactly_compatible_with_pre_move_algorithm():
    dependencies, tasks = _diamond()
    initial = create_initial_orchestration_state(
        ["A", "B", "C", "D"],
        dependencies,
        attributes={"r0": 0, "r1": 0},
    )

    moved_state, moved_seq = run_orchestration(tasks, initial)
    reference_state, reference_seq = _reference_run(tasks, initial)

    assert moved_state.to_dict() == reference_state.to_dict()
    assert moved_state.state_hash == reference_state.state_hash
    assert tuple(r.to_dict() for r in moved_seq.ledger.records) == tuple(
        r.to_dict() for r in reference_seq.ledger.records
    )


def test_s2_orchestration_preserves_reconstructed_u11_semantics():
    dependencies, tasks = _diamond()
    initial = create_initial_orchestration_state(
        ["A", "B", "C", "D"],
        dependencies,
        attributes={"r0": 0, "r1": 0},
    )

    moved_state, moved_seq = run_orchestration(tasks, initial)
    reconstructed = run_orchestration_reconstructed(tasks, initial)

    assert _without_occ_versions(moved_state) == _without_occ_versions(reconstructed.final_state)
    assert moved_state.sequence == reconstructed.final_state.sequence == 13
    assert moved_seq.ledger.verify_chain()


def test_s2_target_layout_facade_points_to_production_spine():
    from pathlib import Path
    import sys

    from uow.application import DEFAULT_APPLICATION_SPINE as production_spine

    repo = Path(__file__).resolve().parents[4]
    facade_root = repo / "implementations" / "python"
    if str(facade_root) not in sys.path:
        sys.path.insert(0, str(facade_root))

    from uow_architecture_facade.application import DEFAULT_APPLICATION_SPINE

    assert DEFAULT_APPLICATION_SPINE is production_spine
