r"""Independent, zero-dependency reference interpreter for Minsky 2-counter register machines.

Acts as the gold-standard mathematical oracle for differential validation of UoW universality:
    Universal Kernel \subset UoW Transition Algebra
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum, auto
from typing import Dict, Mapping, Optional


class Op(Enum):
    INC = auto()
    DECJZ = auto()
    HALT = auto()


@dataclass(frozen=True)
class Instruction:
    op: Op
    register: Optional[int] = None
    next_pc: Optional[int] = None
    zero_pc: Optional[int] = None
    nonzero_pc: Optional[int] = None


@dataclass(frozen=True)
class MachineState:
    pc: int
    r0: int = 0
    r1: int = 0
    halted: bool = False
    steps: int = 0

    def reg(self, idx: int) -> int:
        if idx == 0:
            return self.r0
        if idx == 1:
            return self.r1
        raise ValueError(f"Invalid register index: {idx}")

    def with_reg(self, idx: int, value: int) -> MachineState:
        if value < 0:
            raise ValueError("Counter registers cannot be negative.")
        if idx == 0:
            return replace(self, r0=value)
        if idx == 1:
            return replace(self, r1=value)
        raise ValueError(f"Invalid register index: {idx}")


Program = Mapping[int, Instruction]


def step(program: Program, state: MachineState) -> MachineState:
    """Executes a single atomic transition of the reference Minsky machine."""
    if state.halted:
        return state

    if state.pc not in program:
        raise KeyError(f"Program counter {state.pc} out of bounds.")

    ins = program[state.pc]

    if ins.op is Op.HALT:
        return replace(state, halted=True, steps=state.steps + 1)

    if ins.op is Op.INC:
        assert ins.register in (0, 1), f"Invalid register {ins.register}"
        assert ins.next_pc is not None, "INC missing next_pc"
        next_state = state.with_reg(ins.register, state.reg(ins.register) + 1)
        return replace(next_state, pc=ins.next_pc, steps=state.steps + 1)

    if ins.op is Op.DECJZ:
        assert ins.register in (0, 1), f"Invalid register {ins.register}"
        assert ins.zero_pc is not None and ins.nonzero_pc is not None, "DECJZ missing branch targets"
        value = state.reg(ins.register)
        if value == 0:
            return replace(state, pc=ins.zero_pc, steps=state.steps + 1)
        next_state = state.with_reg(ins.register, value - 1)
        return replace(next_state, pc=ins.nonzero_pc, steps=state.steps + 1)

    raise AssertionError(f"Unreachable opcode: {ins.op}")


def run(program: Program, state: MachineState, max_steps: int = 1_000_000) -> MachineState:
    """Executes the reference machine until HALT or step budget exhaustion."""
    current = state
    for _ in range(max_steps):
        if current.halted:
            return current
        current = step(program, current)
    raise RuntimeError(f"Step budget {max_steps} exceeded in reference Minsky machine.")


# --- Canonical Verification Programs ---

# Program: Transfer all of R0 into R1, leaving R0=0 and R1=R1_orig + R0_orig.
TRANSFER_R0_TO_R1: Program = {
    0: Instruction(Op.DECJZ, register=0, zero_pc=2, nonzero_pc=1),
    1: Instruction(Op.INC, register=1, next_pc=0),
    2: Instruction(Op.HALT),
}

# Program: Countdown R0 to 0 and halt.
COUNTDOWN_R0: Program = {
    0: Instruction(Op.DECJZ, register=0, zero_pc=1, nonzero_pc=0),
    1: Instruction(Op.HALT),
}

# Program: Addition R1 = R0 + R1 (same transition logic as transfer).
ADDITION_R0_INTO_R1: Program = TRANSFER_R0_TO_R1

# Program: Subtraction R0 = max(0, R0 - R1) with non-negative clamping
SUBTRACTION_R0_MINUS_R1: Program = {
    0: Instruction(Op.DECJZ, register=1, zero_pc=3, nonzero_pc=1),
    1: Instruction(Op.DECJZ, register=0, zero_pc=2, nonzero_pc=0),
    2: Instruction(Op.DECJZ, register=1, zero_pc=3, nonzero_pc=2),
    3: Instruction(Op.HALT),
}

# Program: Non-halting monotonic growth on R0
NON_HALTING_GROWTH: Program = {
    0: Instruction(Op.INC, register=0, next_pc=0),
}

# Program: Nested loops (outer decrements R0, inner increments R1 by 2)
NESTED_LOOP_GROWTH: Program = {
    0: Instruction(Op.DECJZ, register=0, zero_pc=3, nonzero_pc=1),
    1: Instruction(Op.INC, register=1, next_pc=2),
    2: Instruction(Op.INC, register=1, next_pc=0),
    3: Instruction(Op.HALT),
}

# Primitives for isolated opcode verification
PRIMITIVE_HALT: Program = {
    0: Instruction(Op.HALT),
}

PRIMITIVE_INC: Program = {
    0: Instruction(Op.INC, register=0, next_pc=1),
    1: Instruction(Op.HALT),
}

PRIMITIVE_DECJZ_ZERO: Program = {
    0: Instruction(Op.DECJZ, register=0, zero_pc=1, nonzero_pc=2),
    1: Instruction(Op.HALT),
    2: Instruction(Op.INC, register=1, next_pc=1),
}

PRIMITIVE_DECJZ_NONZERO: Program = {
    0: Instruction(Op.DECJZ, register=0, zero_pc=2, nonzero_pc=1),
    1: Instruction(Op.HALT),
    2: Instruction(Op.INC, register=1, next_pc=1),
}
