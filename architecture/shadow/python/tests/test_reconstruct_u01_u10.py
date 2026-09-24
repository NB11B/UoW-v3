from __future__ import annotations

import pytest

from foundations.universal_computation.bounded_control import BoundedWorldState
from foundations.universal_computation.reference_minsky import (
    MachineState,
    NON_HALTING_GROWTH,
    PRIMITIVE_DECJZ_NONZERO,
    PRIMITIVE_DECJZ_ZERO,
    PRIMITIVE_HALT,
    PRIMITIVE_INC,
    TRANSFER_R0_TO_R1,
    run as run_reference,
)
from foundations.universal_computation.uow_minsky_compiler import (
    compile_minsky,
    create_initial_world_state,
)
from uow import ALL_MATRIX_CELLS, MatrixCell, WorkCategory

from uow_shadow.reconstruction import (
    run_reconstructed,
    run_reconstructed_steps,
)


def test_r4_u1_u4_reconstruct_primitive_transition_algebra():
    cases = [
        (PRIMITIVE_HALT, 10, 20, 10, 20),
        (PRIMITIVE_INC, 5, 10, 6, 10),
        (PRIMITIVE_DECJZ_ZERO, 0, 42, 0, 42),
        (PRIMITIVE_DECJZ_NONZERO, 5, 42, 4, 42),
    ]

    for program, r0, r1, expected_r0, expected_r1 in cases:
        graph = compile_minsky(program)
        result = run_reconstructed(
            graph,
            create_initial_world_state(pc=0, r0=r0, r1=r1),
        )
        assert result.final_state.status == "HALTED"
        assert result.final_state.get("r0") == expected_r0
        assert result.final_state.get("r1") == expected_r1
        assert result.steps == len(result.evidence)


def test_r4_u6_transfer_matches_independent_minsky_oracle():
    for r0, r1 in [(0, 0), (1, 4), (7, 3), (25, 11)]:
        graph = compile_minsky(TRANSFER_R0_TO_R1)
        reconstructed = run_reconstructed(
            graph,
            create_initial_world_state(pc=0, r0=r0, r1=r1),
        )
        reference = run_reference(
            TRANSFER_R0_TO_R1,
            MachineState(pc=0, r0=r0, r1=r1),
        )
        assert reconstructed.final_state.get("r0") == reference.r0
        assert reconstructed.final_state.get("r1") == reference.r1
        assert reconstructed.final_state.status == ("HALTED" if reference.halted else "RUNNING")
        assert reconstructed.steps == reference.steps


def test_r4_u5_bounded_state_negative_control_is_preserved():
    graph = compile_minsky(NON_HALTING_GROWTH)
    period = 1 << 8

    bounded = BoundedWorldState(
        attributes={"r0": 0, "r1": 0},
        cursor="uow_0",
        status="RUNNING",
        bit_width=8,
    )
    extensible = create_initial_world_state(pc=0, r0=0, r1=0)

    bounded_result = run_reconstructed_steps(graph, bounded, steps=period)
    extensible_result = run_reconstructed_steps(graph, extensible, steps=period)

    assert bounded_result.final_state.get("r0") == 0
    assert bounded_result.final_state.cursor == "uow_0"
    assert extensible_result.final_state.get("r0") == period
    assert extensible_result.final_state.cursor == "uow_0"


def test_r4_u5_extensible_state_preserves_arithmetic_beyond_1024_bits():
    huge = (1 << 1024) + 17
    graph = compile_minsky(PRIMITIVE_INC)
    result = run_reconstructed(
        graph,
        create_initial_world_state(pc=0, r0=huge, r1=0),
    )
    assert result.final_state.get("r0") == huge + 1


def test_r4_u9_semantic_matrix_orthogonality_is_preserved():
    cell_a = MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA)
    cell_b = MatrixCell(WorkCategory.PEOPLE, WorkCategory.DEVICES)
    cell_dynamic = lambda pc: ALL_MATRIX_CELLS[pc % len(ALL_MATRIX_CELLS)]

    s0 = create_initial_world_state(pc=0, r0=8, r1=2)
    a = run_reconstructed(compile_minsky(TRANSFER_R0_TO_R1, cell_a), s0)
    b = run_reconstructed(compile_minsky(TRANSFER_R0_TO_R1, cell_b), s0)
    d = run_reconstructed(compile_minsky(TRANSFER_R0_TO_R1, cell_dynamic), s0)

    assert a.final_state.get("r0") == b.final_state.get("r0") == d.final_state.get("r0") == 0
    assert a.final_state.get("r1") == b.final_state.get("r1") == d.final_state.get("r1") == 10
    assert a.final_state.sequence == b.final_state.sequence == d.final_state.sequence == 18


def test_r4_u8_replay_determinism_is_preserved():
    graph = compile_minsky(TRANSFER_R0_TO_R1)
    first = run_reconstructed(
        graph,
        create_initial_world_state(pc=0, r0=12, r1=7),
    )
    second = run_reconstructed(
        graph,
        create_initial_world_state(pc=0, r0=12, r1=7),
    )

    assert first.final_state.state_hash == second.final_state.state_hash
    assert first.evidence_root() == second.evidence_root()
    assert tuple(e.entry_identity for e in first.evidence) == tuple(
        e.entry_identity for e in second.evidence
    )


def test_r4_non_halting_growth_obeys_external_step_budget():
    graph = compile_minsky(NON_HALTING_GROWTH)
    result = run_reconstructed_steps(
        graph,
        create_initial_world_state(pc=0, r0=0, r1=0),
        steps=1000,
    )
    assert result.final_state.status == "RUNNING"
    assert result.final_state.get("r0") == 1000
    assert result.steps == 1000


def test_r4_runner_does_not_use_canonical_commit(monkeypatch):
    import uow.engine as canonical_engine

    def forbidden(*args, **kwargs):
        raise AssertionError("canonical commit must not be used by R4 reconstruction")

    monkeypatch.setattr(canonical_engine, "commit", forbidden)

    graph = compile_minsky(PRIMITIVE_INC)
    result = run_reconstructed(
        graph,
        create_initial_world_state(pc=0, r0=2, r1=0),
    )
    assert result.final_state.get("r0") == 3


def test_r4_invalid_graph_still_fails_before_execution():
    graph = compile_minsky(PRIMITIVE_INC)
    graph["uow_0"] = graph["uow_0"]

    # Sanity guard: an impossible initial cursor remains invalid.
    with pytest.raises(KeyError):
        run_reconstructed(
            graph,
            create_initial_world_state(pc=99, r0=0, r1=0),
        )
