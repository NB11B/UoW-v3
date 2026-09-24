from __future__ import annotations

from uow import (
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    Route,
    Successor,
    WorldState,
    make_uow,
)

from uow_shadow.concurrency import run_parallel_transaction_batch_reconstructed


def _write_task(task_id: str, key: str, value: int):
    return make_uow(
        task_id,
        [
            Route(
                Guard(GuardOp.ALWAYS),
                (Mutation(MutationOp.SET, key, value),),
                Successor.preserve(),
            )
        ],
    )


def _read_x_write_y(task_id: str, y_value: int):
    return make_uow(
        task_id,
        [
            Route(
                Guard(GuardOp.GTE, "x", 0),
                (Mutation(MutationOp.SET, "y", y_value),),
                Successor.preserve(),
            )
        ],
    )


def _state(*, couplings=None):
    return WorldState(
        attributes={
            "x": 0,
            "y": 0,
            "z": 0,
            "__versions__": {"x": 0, "y": 0, "z": 0},
            "__couplings__": couplings or {},
        },
        cursor="controller",
        status="RUNNING",
    )


def test_r4_u12_disjoint_transactions_prepare_in_parallel_and_both_commit():
    graph = {
        "A_x": _write_task("A_x", "x", 1),
        "B_y": _write_task("B_y", "y", 2),
    }
    result = run_parallel_transaction_batch_reconstructed(
        graph,
        ("A_x", "B_y"),
        _state(),
        inject_entropy=True,
        seed=1,
    )

    assert len(set(result.worker_thread_ids)) == 2
    assert result.committed == ("A_x", "B_y")
    assert result.conflicts == ()
    assert result.final_state.get("x") == 1
    assert result.final_state.get("y") == 2
    versions = result.final_state.get("__versions__")
    assert versions["x"] == 1
    assert versions["y"] == 1
    assert len(result.evidence) == 2


def test_r4_u12_write_write_conflict_aborts_without_dirty_second_mutation():
    graph = {
        "A_x": _write_task("A_x", "x", 1),
        "B_x": _write_task("B_x", "x", 2),
    }
    result = run_parallel_transaction_batch_reconstructed(
        graph,
        ("A_x", "B_x"),
        _state(),
        inject_entropy=True,
        seed=2,
    )

    assert result.committed == ("A_x",)
    assert len(result.conflicts) == 1
    assert result.conflicts[0][0] == "B_x"
    assert result.conflicts[0][1] == "WRITE_WRITE_HAZARD"
    assert result.final_state.get("x") == 1
    assert result.final_state.get("y") == 0
    assert len(result.evidence) == 1


def test_r4_u12_read_write_hazard_rejects_stale_read():
    graph = {
        "A_x": _write_task("A_x", "x", 1),
        "B_read_x_write_y": _read_x_write_y("B_read_x_write_y", 9),
    }
    result = run_parallel_transaction_batch_reconstructed(
        graph,
        ("A_x", "B_read_x_write_y"),
        _state(),
    )

    assert result.committed == ("A_x",)
    assert result.conflicts == (("B_read_x_write_y", "READ_WRITE_HAZARD"),)
    assert result.final_state.get("x") == 1
    assert result.final_state.get("y") == 0


def test_r4_u12_hidden_coupling_rejects_semantically_conflicting_write():
    graph = {
        "A_z": _write_task("A_z", "z", 1),
        "B_x": _write_task("B_x", "x", 1),
    }
    result = run_parallel_transaction_batch_reconstructed(
        graph,
        ("A_z", "B_x"),
        _state(couplings={"x": ("z",)}),
    )

    assert result.committed == ("A_z",)
    assert result.conflicts == (("B_x", "HIDDEN_COUPLING_HAZARD"),)
    assert result.final_state.get("z") == 1
    assert result.final_state.get("x") == 0


def test_r4_u12_host_timing_entropy_does_not_change_serialized_result_or_evidence():
    graph = {
        "A_x": _write_task("A_x", "x", 1),
        "B_y": _write_task("B_y", "y", 2),
    }

    roots = set()
    states = set()
    for seed in range(8):
        result = run_parallel_transaction_batch_reconstructed(
            graph,
            ("A_x", "B_y"),
            _state(),
            inject_entropy=True,
            seed=seed,
        )
        roots.add(result.evidence_root())
        states.add(result.final_state.state_hash)
        assert len(set(result.worker_thread_ids)) == 2

    assert len(roots) == 1
    assert len(states) == 1


def test_r4_u12_whole_state_hash_can_advance_while_disjoint_occ_context_remains_valid():
    graph = {
        "A_x": _write_task("A_x", "x", 1),
        "B_y": _write_task("B_y", "y", 2),
    }
    initial = _state()
    result = run_parallel_transaction_batch_reconstructed(
        graph,
        ("A_x", "B_y"),
        initial,
    )

    # B_y was proposed from the original state, but is still valid after A_x
    # because OCC establishes disjoint typed compatibility.
    assert result.committed == ("A_x", "B_y")
    assert result.final_state.sequence == initial.sequence + 2


def test_r4_u12_replay_is_deterministic():
    graph = {
        "A_x": _write_task("A_x", "x", 1),
        "B_y": _write_task("B_y", "y", 2),
    }
    a = run_parallel_transaction_batch_reconstructed(graph, ("A_x", "B_y"), _state())
    b = run_parallel_transaction_batch_reconstructed(graph, ("A_x", "B_y"), _state())

    assert a.final_state.state_hash == b.final_state.state_hash
    assert a.evidence_root() == b.evidence_root()
