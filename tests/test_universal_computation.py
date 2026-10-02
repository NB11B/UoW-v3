r"""Canonical qualification tests for Foundational Universal Computation (Minsky 2-Counter Construction).

Validates:
    1. Universal Kernel \subset UoW Transition Algebra
    2. Semantic Classification \perp Computational Semantics (Orthogonality)
    3. Bounded-State Negative Control (Gate U5 Periodicity)
    4. State magnitude scaling past 2^1024 + 17
    5. Bitwise replay determinism
    6. Deterministic tamper rejection
"""
from __future__ import annotations

import copy
import pytest

from foundations.universal_computation.bounded_control import (
    BoundedWorldState,
    run_bounded_vs_extensible_experiment,
)
from foundations.universal_computation.differential_campaign import (
    run_differential_step_campaign,
    run_terminating_run_campaign,
)
from foundations.universal_computation.reference_minsky import (
    COUNTDOWN_R0,
    NESTED_LOOP_GROWTH,
    NON_HALTING_GROWTH,
    PRIMITIVE_DECJZ_NONZERO,
    PRIMITIVE_DECJZ_ZERO,
    PRIMITIVE_HALT,
    PRIMITIVE_INC,
    SUBTRACTION_R0_MINUS_R1,
    TRANSFER_R0_TO_R1,
)
from foundations.universal_computation.uow_minsky_compiler import (
    compile_minsky,
    create_initial_world_state,
)
from uow.compat.v2 import (
    ALL_MATRIX_CELLS,
    EvidenceLedger,
    MatrixCell,
    Proposal,
    WorkCategory,
    WorldState,
    certify,
    execute_one,
    propose,
    run,
)


# ===========================================================================
# 1. Primitive Opcode Qualification
# ===========================================================================

def test_primitive_halt():
    """HALT opcode compiles into unconditional halt route."""
    graph = compile_minsky(PRIMITIVE_HALT)
    state = create_initial_world_state(pc=0, r0=10, r1=20)
    out, ledger = run(graph, state)
    assert out.status == "HALTED"
    assert out.get("r0") == 10
    assert out.get("r1") == 20
    assert len(ledger.records) == 1
    assert ledger.records[0].selected_route_index == 0


def test_primitive_inc():
    """INC opcode executes atomic increment and static successor transition."""
    graph = compile_minsky(PRIMITIVE_INC)
    state = create_initial_world_state(pc=0, r0=5, r1=10)
    out, ledger = run(graph, state)
    assert out.status == "HALTED"
    assert out.get("r0") == 6
    assert out.get("r1") == 10
    assert len(ledger.records) == 2


def test_primitive_decjz_zero_branch():
    """DECJZ executes zero-test branch when register is 0 without mutation."""
    graph = compile_minsky(PRIMITIVE_DECJZ_ZERO)
    # r0 = 0 -> zero branch to pc 1 (HALT)
    state = create_initial_world_state(pc=0, r0=0, r1=42)
    out, ledger = run(graph, state)
    assert out.status == "HALTED"
    assert out.get("r0") == 0
    assert out.get("r1") == 42
    assert len(ledger.records) == 2


def test_primitive_decjz_nonzero_branch():
    """DECJZ decrements register and takes non-zero branch when register > 0."""
    graph = compile_minsky(PRIMITIVE_DECJZ_NONZERO)
    # r0 = 5 -> nonzero branch to pc 1 (HALT), r0 should become 4
    state = create_initial_world_state(pc=0, r0=5, r1=42)
    out, ledger = run(graph, state)
    assert out.status == "HALTED"
    assert out.get("r0") == 4
    assert out.get("r1") == 42
    assert len(ledger.records) == 2


# ===========================================================================
# 2. Algorithmic Programs & Exact Counting
# ===========================================================================

def test_algorithmic_transfer():
    """R0 -> R1 transfer executes with exactly 2N + 2 transitions."""
    graph = compile_minsky(TRANSFER_R0_TO_R1)
    state = create_initial_world_state(pc=0, r0=10, r1=5)
    out, ledger = run(graph, state)
    assert out.status == "HALTED"
    assert out.get("r0") == 0
    assert out.get("r1") == 15
    # 10 decjz-nonzero + 10 inc + 1 decjz-zero + 1 halt = 22 transitions
    assert len(ledger.records) == 10 * 2 + 2
    assert ledger.verify_integrity()


def test_algorithmic_countdown():
    """Countdown loop terminates with R0 = 0."""
    graph = compile_minsky(COUNTDOWN_R0)
    state = create_initial_world_state(pc=0, r0=25, r1=99)
    out, ledger = run(graph, state)
    assert out.status == "HALTED"
    assert out.get("r0") == 0
    assert out.get("r1") == 99
    assert ledger.verify_integrity()


def test_algorithmic_subtraction_with_underflow():
    """Subtraction clamping: max(0, R0 - R1)."""
    graph = compile_minsky(SUBTRACTION_R0_MINUS_R1)
    # Case 1: 15 - 6 = 9
    s1 = create_initial_world_state(pc=0, r0=15, r1=6)
    out1, _ = run(graph, s1)
    assert out1.get("r0") == 9
    assert out1.get("r1") == 0

    # Case 2: 4 - 10 = 0 (underflow clamping)
    s2 = create_initial_world_state(pc=0, r0=4, r1=10)
    out2, _ = run(graph, s2)
    assert out2.get("r0") == 0
    assert out2.get("r1") == 0


def test_nested_loop_growth():
    """Nested loop execution: R1 = R0 * 2."""
    graph = compile_minsky(NESTED_LOOP_GROWTH)
    state = create_initial_world_state(pc=0, r0=3, r1=0)
    out, ledger = run(graph, state)
    assert out.status == "HALTED"
    assert out.get("r0") == 0
    assert out.get("r1") == 6  # 3 * 2 = 6
    assert ledger.verify_integrity()


def test_non_halting_growth_with_budget():
    """Non-halting program executes monotonically without failure under external budget."""
    graph = compile_minsky(NON_HALTING_GROWTH)
    state = create_initial_world_state(pc=0, r0=0, r1=0)
    ledger = EvidenceLedger()

    for _ in range(1000):
        state = execute_one(graph, state, ledger)

    assert state.status == "RUNNING"
    assert state.get("r0") == 1000
    assert len(ledger.records) == 1000
    assert ledger.verify_integrity()


# ===========================================================================
# 3. Orthogonality Theorem: Semantic Matrix Cell Independence
# ===========================================================================

def test_semantic_matrix_cell_orthogonality():
    """Assigning different matrix cells produces bitwise identical computational execution."""
    cell_a = MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA)
    cell_b = MatrixCell(WorkCategory.PEOPLE, WorkCategory.DEVICES)
    cell_dynamic = lambda pc: ALL_MATRIX_CELLS[pc % len(ALL_MATRIX_CELLS)]

    graph_a = compile_minsky(TRANSFER_R0_TO_R1, matrix_cell=cell_a)
    graph_b = compile_minsky(TRANSFER_R0_TO_R1, matrix_cell=cell_b)
    graph_dyn = compile_minsky(TRANSFER_R0_TO_R1, matrix_cell=cell_dynamic)

    s0 = create_initial_world_state(pc=0, r0=8, r1=2)
    out_a, _ = run(graph_a, s0)
    out_b, _ = run(graph_b, s0)
    out_dyn, _ = run(graph_dyn, s0)

    # Computational state outputs are strictly identical
    assert out_a.get("r0") == out_b.get("r0") == out_dyn.get("r0") == 0
    assert out_a.get("r1") == out_b.get("r1") == out_dyn.get("r1") == 10
    assert out_a.sequence == out_b.sequence == out_dyn.sequence == 18


# ===========================================================================
# 4. Bounded-State Negative Control (Gate U5)
# ===========================================================================

def test_bounded_state_negative_control():
    """8-bit bounded state cycles after 2^8=256 steps; extensible state scales monotonically."""
    result = run_bounded_vs_extensible_experiment(bit_width=8)

    assert result["period"] == 256
    # Bounded state returned to initial configuration (periodic)
    assert result["bounded_initial_r0"] == 0
    assert result["bounded_after_period_r0"] == 0
    assert result["bounded_is_periodic"] is True

    # Extensible state grew monotonically to 256 (non-periodic)
    assert result["extensible_initial_r0"] == 0
    assert result["extensible_after_period_r0"] == 256
    assert result["extensible_is_periodic"] is False


# ===========================================================================
# 5. State Magnitude Scaling Past 1024 Bits
# ===========================================================================

def test_extensible_memory_state_magnitude_beyond_1024_bits():
    """Native UoW state maintains exact integer arithmetic beyond 2^1024 + 17."""
    huge_val = (1 << 1024) + 17
    graph = compile_minsky(PRIMITIVE_INC)
    state = create_initial_world_state(pc=0, r0=huge_val, r1=0)
    out, ledger = run(graph, state)

    expected = (1 << 1024) + 18
    assert out.get("r0") == expected
    assert ledger.verify_integrity()


# ===========================================================================
# 6. Replay Determinism & Falsification
# ===========================================================================

def test_replay_determinism_minsky():
    """Replaying Minsky UoWs against identical initial state yields bitwise identical evidence root."""
    graph = compile_minsky(TRANSFER_R0_TO_R1)
    s1 = create_initial_world_state(pc=0, r0=12, r1=7)
    s2 = create_initial_world_state(pc=0, r0=12, r1=7)

    out1, led1 = run(graph, s1)
    out2, led2 = run(graph, s2)

    assert out1.state_hash == out2.state_hash
    assert led1.root_hash() == led2.root_hash()


def test_tampered_proposal_rejection():
    """Core certifier rejects forged proposed state during Minsky UoW step."""
    graph = compile_minsky(PRIMITIVE_INC)
    uow = graph["uow_0"]
    state = create_initial_world_state(pc=0, r0=5, r1=0)

    prop = propose(uow, state)
    # Tamper with the proposed state (simulate Byzantine executor)
    tampered_state = prop.proposed_state.with_attribute("r0", 999)
    tampered_prop = Proposal(
        uow_id=prop.uow_id,
        selected_route_index=prop.selected_route_index,
        proposed_state=tampered_state,
        selected_successor=prop.selected_successor,
        halted=prop.halted,
        pre_state_hash=prop.pre_state_hash,
    )
    cert = certify(uow, state, tampered_prop)
    assert not cert.is_valid
    assert cert.rejection_reason == "STATE_DIVERGENCE"


def test_randomized_differential_sample():
    """Executes a sample of the differential verification campaign in pytest."""
    stats = run_differential_step_campaign(n_programs=20, steps_per_program=10, seed=42)
    assert stats.total_single_step_checks == 200
    assert stats.matched_single_steps == 200
    assert stats.failed_checks == 0
