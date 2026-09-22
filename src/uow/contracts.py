"""Declarative Unit-of-Work contracts.

Core contracts contain only general transition semantics. Scheduler, transaction,
resource, external-effect, and model-specific behavior belongs in derived layers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from numbers import Number
from typing import Any, Iterable, Optional, Tuple

from .ontology import ALL_MATRIX_CELLS, MatrixCell, WorkCategory
from .state import WorldState


class LifecyclePhase(str, Enum):
    READY = "READY"
    PROPOSED = "PROPOSED"
    CERTIFIED = "CERTIFIED"
    COMMITTED = "COMMITTED"
    HALTED = "HALTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class Header:
    """Header H: identity and semantic work classification."""

    identity: str
    source_category: WorkCategory
    target_category: WorkCategory
    layer: str = "uow"
    parent_context: str = "native"

    @property
    def matrix_cell(self) -> MatrixCell:
        return MatrixCell(self.source_category, self.target_category)


@dataclass(frozen=True)
class Lifecycle:
    """Lifecycle descriptor M."""

    phase: LifecyclePhase = LifecyclePhase.READY


@dataclass(frozen=True)
class Realization:
    """Realization descriptor R.

    The core records realization identity but does not import an execution backend.
    """

    implementation: str = "state-transition"


@dataclass(frozen=True)
class Boundary:
    """Boundary descriptor B."""

    input_type: str = "WorldState"
    output_type: str = "WorldState"
    schema_version: str = "1.0.0"


@dataclass(frozen=True)
class EvidenceSpec:
    """Evidence descriptor E."""

    verifier: str = "deterministic-transition-judge"
    require_hash_chain: bool = True


@dataclass(frozen=True)
class Timing:
    """Timing descriptor T."""

    clock_owner: str = "uow"
    causal_epoch: int = 0


class GuardOp(str, Enum):
    ALWAYS = "ALWAYS"
    EXISTS = "EXISTS"
    NOT_EXISTS = "NOT_EXISTS"
    EQ = "EQ"
    NE = "NE"
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"


@dataclass(frozen=True)
class Guard:
    """Pure predicate over a WorldState attribute."""

    op: GuardOp = GuardOp.ALWAYS
    key: Optional[str] = None
    operand: Any = None

    def evaluate(self, state: WorldState) -> bool:
        if self.op is GuardOp.ALWAYS:
            return True
        if self.key is None:
            raise ValueError(f"Guard {self.op.value} requires a state key.")
        exists = self.key in state.attributes
        if self.op is GuardOp.EXISTS:
            return exists
        if self.op is GuardOp.NOT_EXISTS:
            return not exists
        if not exists:
            return False

        value = state.require(self.key)
        if self.op is GuardOp.EQ:
            return value == self.operand
        if self.op is GuardOp.NE:
            return value != self.operand
        if self.op is GuardOp.GT:
            return value > self.operand
        if self.op is GuardOp.GTE:
            return value >= self.operand
        if self.op is GuardOp.LT:
            return value < self.operand
        if self.op is GuardOp.LTE:
            return value <= self.operand
        raise ValueError(f"Unsupported guard operation: {self.op.value}")


class MutationOp(str, Enum):
    NOOP = "NOOP"
    SET = "SET"
    ADD = "ADD"
    SUB = "SUB"
    DELETE = "DELETE"


@dataclass(frozen=True)
class Mutation:
    """Deterministic mutation over a WorldState attribute."""

    op: MutationOp = MutationOp.NOOP
    key: Optional[str] = None
    operand: Any = None

    def apply(self, state: WorldState) -> WorldState:
        if self.op is MutationOp.NOOP:
            return state
        if self.key is None:
            raise ValueError(f"Mutation {self.op.value} requires a state key.")
        if self.op is MutationOp.SET:
            return state.with_attribute(self.key, self.operand)
        if self.op is MutationOp.DELETE:
            return state.without_attribute(self.key)

        current = state.require(self.key)
        if not isinstance(current, Number) or isinstance(current, bool):
            raise TypeError(f"Mutation {self.op.value} requires numeric state.")
        if not isinstance(self.operand, Number) or isinstance(self.operand, bool):
            raise TypeError(f"Mutation {self.op.value} requires a numeric operand.")

        if self.op is MutationOp.ADD:
            return state.with_attribute(self.key, current + self.operand)
        if self.op is MutationOp.SUB:
            return state.with_attribute(self.key, current - self.operand)
        raise ValueError(f"Unsupported mutation operation: {self.op.value}")


class SuccessorKind(str, Enum):
    STATIC = "STATIC"
    FROM_ATTRIBUTE = "FROM_ATTRIBUTE"
    HALT = "HALT"
    PRESERVE = "PRESERVE"


@dataclass(frozen=True)
class Successor:
    """First-class successor reference.

    FROM_ATTRIBUTE replaces the research runtime's magic '@DISPATCHED' sentinel.
    PRESERVE preserves enclosing orchestration cursor and status without halting.
    """

    kind: SuccessorKind
    value: Optional[str] = None

    @classmethod
    def static(cls, uow_id: str) -> "Successor":
        return cls(SuccessorKind.STATIC, uow_id)

    @classmethod
    def from_attribute(cls, key: str) -> "Successor":
        return cls(SuccessorKind.FROM_ATTRIBUTE, key)

    @classmethod
    def halt(cls) -> "Successor":
        return cls(SuccessorKind.HALT, None)

    @classmethod
    def preserve(cls) -> "Successor":
        return cls(SuccessorKind.PRESERVE, None)

    def resolve(self, state: WorldState) -> Optional[str]:
        if self.kind is SuccessorKind.HALT:
            return None
        if self.kind is SuccessorKind.PRESERVE:
            return state.cursor
        if not self.value:
            raise ValueError(f"Successor {self.kind.value} requires a value.")
        if self.kind is SuccessorKind.STATIC:
            return self.value
        if self.kind is SuccessorKind.FROM_ATTRIBUTE:
            resolved = state.require(self.value)
            if not isinstance(resolved, str) or not resolved:
                raise TypeError(
                    f"Dynamic successor attribute {self.value!r} must contain a non-empty string."
                )
            return resolved
        raise ValueError(f"Unsupported successor kind: {self.kind.value}")


@dataclass(frozen=True)
class Route:
    guard: Guard
    mutations: Tuple[Mutation, ...] = ()
    successor: Successor = field(default_factory=Successor.halt)

    def is_applicable(self, state: WorldState) -> bool:
        return self.guard.evaluate(state)

    def apply_mutations(self, state: WorldState) -> WorldState:
        result = state
        for mutation in self.mutations:
            result = mutation.apply(result)
        return result


@dataclass(frozen=True)
class Contract:
    """Contract Gamma: ordered conditional transition routes."""

    routes: Tuple[Route, ...]

    def select_route(self, state: WorldState) -> tuple[int, Route]:
        for index, route in enumerate(self.routes):
            if route.is_applicable(state):
                return index, route
        raise RuntimeError("No applicable route exists for the current state.")


@dataclass(frozen=True)
class UoW:
    """Unit of Work U = (H, Gamma, M, R, B, E, T)."""

    H: Header
    Gamma: Contract
    M: Lifecycle = field(default_factory=Lifecycle)
    R: Realization = field(default_factory=Realization)
    B: Boundary = field(default_factory=Boundary)
    E: EvidenceSpec = field(default_factory=EvidenceSpec)
    T: Timing = field(default_factory=Timing)

    def validate(self) -> None:
        if self.H.matrix_cell not in ALL_MATRIX_CELLS:
            raise ValueError(f"Invalid work-category pairing: {self.H.matrix_cell}")
        if not self.H.identity:
            raise ValueError("UoW identity must be non-empty.")
        if not self.Gamma.routes:
            raise ValueError("Contract must contain at least one route.")
        for route in self.Gamma.routes:
            if (
                route.successor.kind not in (SuccessorKind.HALT, SuccessorKind.PRESERVE)
                and not route.successor.value
            ):
                raise ValueError("Non-halting successor must declare a target.")


def make_uow(
    identity: str,
    routes: Iterable[Route],
    matrix_cell: MatrixCell = MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA),
    *,
    layer: str = "uow",
    parent_context: str = "native",
) -> UoW:
    uow = UoW(
        H=Header(
            identity=identity,
            source_category=matrix_cell.source,
            target_category=matrix_cell.target,
            layer=layer,
            parent_context=parent_context,
        ),
        Gamma=Contract(tuple(routes)),
    )
    uow.validate()
    return uow
