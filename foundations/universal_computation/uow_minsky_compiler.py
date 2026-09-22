r"""Compiler lowering Minsky two-counter register programs into canonical native UoWs.

Demonstrates:
    1. Universal Kernel \subset UoW Transition Algebra
    2. Semantic Classification \perp Computational Semantics
"""
from __future__ import annotations

from typing import Callable, Dict, Mapping, Optional, Union

from uow.contracts import (
    Contract,
    Guard,
    GuardOp,
    Header,
    Mutation,
    MutationOp,
    Route,
    Successor,
    UoW,
    make_uow,
)
from uow.ontology import ALL_MATRIX_CELLS, MatrixCell, WorkCategory
from uow.state import WorldState
from .reference_minsky import Instruction, Op, Program

DEFAULT_CELL: MatrixCell = MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA)


def compile_minsky(
    program: Program,
    matrix_cell: Union[MatrixCell, Callable[[int], MatrixCell]] = DEFAULT_CELL,
    prefix: str = "uow_",
) -> Dict[str, UoW]:
    """Compiles an arbitrary two-counter Minsky program into a native UoW graph.

    Every Minsky instruction lowers into an ordinary native UoW with standard guards,
    deterministic mutations, and explicit successor routing:
    - INC(r, next_pc) -> Unconditional ALWAYS, ADD 1 to r, Successor.static(next_pc)
    - DECJZ(r, zero_pc, nonzero_pc) ->
        Route 0: Guard EQ(r, 0), NOOP mutation, Successor.static(zero_pc)
        Route 1: Guard GT(r, 0), SUB 1 from r, Successor.static(nonzero_pc)
    - HALT -> Unconditional ALWAYS, Successor.halt()

    Orthogonality Invariant:
        Any of the 64 matrix cells can be assigned (either uniformly or dynamically
        per PC) without altering computational execution. The 64 pairings remain pure
        semantic typing ("what kind of work is this?"), not an instruction set.
    """
    graph: Dict[str, UoW] = {}

    for pc, ins in program.items():
        uid = f"{prefix}{pc}"
        cell = matrix_cell(pc) if callable(matrix_cell) else matrix_cell

        if ins.op is Op.HALT:
            routes = (
                Route(
                    guard=Guard(GuardOp.ALWAYS),
                    mutations=(),
                    successor=Successor.halt(),
                ),
            )
            graph[uid] = make_uow(
                uid, routes, matrix_cell=cell, layer="foundation", parent_context="universal-minsky-kernel"
            )

        elif ins.op is Op.INC:
            assert ins.register in (0, 1), f"Invalid register: {ins.register}"
            assert ins.next_pc is not None, f"INC at pc={pc} missing next_pc"
            var = f"r{ins.register}"
            target_uid = f"{prefix}{ins.next_pc}"
            routes = (
                Route(
                    guard=Guard(GuardOp.ALWAYS),
                    mutations=(Mutation(MutationOp.ADD, var, 1),),
                    successor=Successor.static(target_uid),
                ),
            )
            graph[uid] = make_uow(
                uid, routes, matrix_cell=cell, layer="foundation", parent_context="universal-minsky-kernel"
            )

        elif ins.op is Op.DECJZ:
            assert ins.register in (0, 1), f"Invalid register: {ins.register}"
            assert ins.zero_pc is not None and ins.nonzero_pc is not None, (
                f"DECJZ at pc={pc} missing branch targets"
            )
            var = f"r{ins.register}"
            zero_uid = f"{prefix}{ins.zero_pc}"
            nonzero_uid = f"{prefix}{ins.nonzero_pc}"

            routes = (
                # Route 0: Zero test branch
                Route(
                    guard=Guard(GuardOp.EQ, var, 0),
                    mutations=(),
                    successor=Successor.static(zero_uid),
                ),
                # Route 1: Non-zero decrement branch
                Route(
                    guard=Guard(GuardOp.GT, var, 0),
                    mutations=(Mutation(MutationOp.SUB, var, 1),),
                    successor=Successor.static(nonzero_uid),
                ),
            )
            graph[uid] = make_uow(
                uid, routes, matrix_cell=cell, layer="foundation", parent_context="universal-minsky-kernel"
            )

        else:
            raise ValueError(f"Unknown Minsky opcode: {ins.op}")

    return graph


def create_initial_world_state(
    pc: int = 0,
    r0: int = 0,
    r1: int = 0,
    prefix: str = "uow_",
) -> WorldState:
    """Constructs the initial WorldState corresponding to a starting Minsky configuration."""
    return WorldState(
        attributes={"r0": r0, "r1": r1},
        cursor=f"{prefix}{pc}",
        status="RUNNING",
    )
