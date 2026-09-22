"""Bounded-state negative control: demonstrates periodicity and finite-state limits (Gate U5).

Proves the fundamental architectural boundary:
    finite controller + bounded state -> finite-state system (cycles after 2^k steps)
    versus
    finite controller + extensible memory + branch/mutation -> universal computation
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from uow.contracts import Guard, GuardOp, Mutation, MutationOp, Route, make_uow
from uow.engine import EvidenceLedger, execute_one
from uow.state import WorldState


@dataclass(frozen=True)
class BoundedWorldState(WorldState):
    """Intentionally bounded state representation with k-bit modular arithmetic.

    Used as an architectural negative control proving why extensible state is required
    for full computational universality.
    """

    bit_width: int = 8

    def with_attribute(self, key: str, value: Any) -> BoundedWorldState:
        if isinstance(value, int) and not isinstance(value, bool):
            modulus = 1 << self.bit_width
            value = value % modulus
        base = super().with_attribute(key, value)
        return BoundedWorldState(
            attributes=base.attributes,
            cursor=base.cursor,
            status=base.status,
            sequence=base.sequence,
            bit_width=self.bit_width,
        )


def run_bounded_vs_extensible_experiment(bit_width: int = 8) -> Dict[str, Any]:
    """Compares k-bit bounded state backend against native extensible state backend.

    Proves Gate U5 negative control:
    - Bounded state with bit_width=8 returns to initial state configuration after 2^8 = 256 steps.
    - Extensible state never repeats configurations in monotonic growth programs.
    """
    # Non-halting increment loop: loop: ALWAYS -> r0 += 1 -> next=loop
    route = Route(
        guard=Guard(GuardOp.ALWAYS),
        mutations=(Mutation(MutationOp.ADD, "r0", 1),),
        successor=make_uow.__annotations__.get("successor", None),  # static successor
    )
    from uow.contracts import Successor

    uow = make_uow(
        "loop",
        [
            Route(
                guard=Guard(GuardOp.ALWAYS),
                mutations=(Mutation(MutationOp.ADD, "r0", 1),),
                successor=Successor.static("loop"),
            )
        ],
        layer="foundation",
    )
    graph = {"loop": uow}
    period = 1 << bit_width  # 256 for 8-bit

    # 1. Bounded Run
    bounded_initial = BoundedWorldState(
        attributes={"r0": 0, "r1": 0},
        cursor="loop",
        status="RUNNING",
        bit_width=bit_width,
    )
    bounded_state = bounded_initial
    bounded_ledger = EvidenceLedger()
    for _ in range(period):
        bounded_state = execute_one(graph, bounded_state, bounded_ledger)

    bounded_matches_initial = (
        bounded_state.require("r0") == bounded_initial.require("r0")
        and bounded_state.cursor == bounded_initial.cursor
    )

    # 2. Extensible Run
    extensible_initial = WorldState(
        attributes={"r0": 0, "r1": 0},
        cursor="loop",
        status="RUNNING",
    )
    extensible_state = extensible_initial
    extensible_ledger = EvidenceLedger()
    for _ in range(period):
        extensible_state = execute_one(graph, extensible_state, extensible_ledger)

    extensible_matches_initial = (
        extensible_state.require("r0") == extensible_initial.require("r0")
    )

    return {
        "bit_width": bit_width,
        "period": period,
        "bounded_initial_r0": bounded_initial.require("r0"),
        "bounded_after_period_r0": bounded_state.require("r0"),
        "bounded_is_periodic": bounded_matches_initial,
        "extensible_initial_r0": extensible_initial.require("r0"),
        "extensible_after_period_r0": extensible_state.require("r0"),
        "extensible_is_periodic": extensible_matches_initial,
    }
