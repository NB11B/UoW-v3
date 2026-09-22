"""Certified self-hosted scheduler materialization."""
from __future__ import annotations

from typing import List, Sequence

from ..contracts import (
    Contract,
    Guard,
    GuardOp,
    Header,
    Mutation,
    MutationOp,
    Route,
    Successor,
    SuccessorKind,
    UoW,
)
from ..ontology import MatrixCell, WorkCategory
from ..state import WorldState
from .materialization import MaterializedUoW, bind_materialization
from .state import (
    ORCH_ACTIVE_KEY,
    ORCH_COMPLETED_KEY,
    ORCH_QUEUE_KEY,
    OrchestrationState,
)

SCHEDULER_CELL: MatrixCell = MatrixCell(WorkCategory.RULES, WorkCategory.PROCESSES)
TASK_CELL: MatrixCell = MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA)
ORCH_TERMINATION_KEY = "__termination__"
SCHEDULER_ID = "uow_scheduler"
COMPLETION_PREFIX = "complete::"


class SchedulerMaterializer:
    """Lower the current ready frontier into an ordinary scheduler UoW.

    The materializer itself never mutates state. Its output must pass independent
    materialization certification and then the normal UoW certification boundary.
    """

    @property
    def materializer_id(self) -> str:
        return SCHEDULER_ID

    def materialize(self, state: WorldState) -> MaterializedUoW:
        orch = OrchestrationState(state)
        ready = orch.get_ready_tasks()

        if ready:
            task_id = ready[0]
            new_queue = tuple(task for task in orch.queue if task != task_id)
            new_active = tuple(sorted(set(orch.active) | {task_id}))
            uow = UoW(
                H=Header(
                    identity=SCHEDULER_ID,
                    source_category=SCHEDULER_CELL.source,
                    target_category=SCHEDULER_CELL.target,
                    layer="orchestration",
                    parent_context="scheduler-materialization",
                ),
                Gamma=Contract(
                    (
                        Route(
                            guard=Guard(GuardOp.ALWAYS),
                            mutations=(
                                Mutation(MutationOp.SET, ORCH_QUEUE_KEY, new_queue),
                                Mutation(MutationOp.SET, ORCH_ACTIVE_KEY, new_active),
                            ),
                            successor=Successor.static(task_id),
                        ),
                    )
                ),
            )
            uow.validate()
            return bind_materialization(self.materializer_id, state, uow)

        if orch.is_queue_empty():
            uow = UoW(
                H=Header(
                    identity=SCHEDULER_ID,
                    source_category=SCHEDULER_CELL.source,
                    target_category=SCHEDULER_CELL.target,
                    layer="orchestration",
                    parent_context="scheduler-materialization",
                ),
                Gamma=Contract(
                    (
                        Route(
                            guard=Guard(GuardOp.ALWAYS),
                            successor=Successor.halt(),
                        ),
                    )
                ),
            )
            uow.validate()
            return bind_materialization(self.materializer_id, state, uow)

        if orch.is_deadlocked():
            uow = UoW(
                H=Header(
                    identity=SCHEDULER_ID,
                    source_category=SCHEDULER_CELL.source,
                    target_category=SCHEDULER_CELL.target,
                    layer="orchestration",
                    parent_context="scheduler-materialization",
                ),
                Gamma=Contract(
                    (
                        Route(
                            guard=Guard(GuardOp.ALWAYS),
                            mutations=(
                                Mutation(
                                    MutationOp.SET,
                                    ORCH_TERMINATION_KEY,
                                    "DEADLOCKED",
                                ),
                            ),
                            successor=Successor.halt(),
                        ),
                    )
                ),
            )
            uow.validate()
            return bind_materialization(self.materializer_id, state, uow)

        # Scheduler execution while work remains active indicates a control-flow error.
        uow = UoW(
            H=Header(
                identity=SCHEDULER_ID,
                source_category=SCHEDULER_CELL.source,
                target_category=SCHEDULER_CELL.target,
                layer="orchestration",
                parent_context="scheduler-materialization",
            ),
            Gamma=Contract(
                (
                    Route(
                        guard=Guard(GuardOp.ALWAYS),
                        mutations=(
                            Mutation(
                                MutationOp.SET,
                                ORCH_TERMINATION_KEY,
                                "ACTIVE_WORK_PRESENT",
                            ),
                        ),
                        successor=Successor.halt(),
                    ),
                )
            ),
        )
        uow.validate()
        return bind_materialization(self.materializer_id, state, uow)


class CompletionMaterializer:
    """Materialize certified completion of one active task."""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id

    @property
    def materializer_id(self) -> str:
        return f"{COMPLETION_PREFIX}{self.task_id}"

    def materialize(self, state: WorldState) -> MaterializedUoW:
        orch = OrchestrationState(state)
        if self.task_id not in orch.active:
            raise ValueError(f"Cannot complete inactive task {self.task_id!r}.")

        new_active = tuple(task for task in orch.active if task != self.task_id)
        new_completed = tuple(sorted(set(orch.completed) | {self.task_id}))
        uow = UoW(
            H=Header(
                identity=self.materializer_id,
                source_category=SCHEDULER_CELL.source,
                target_category=SCHEDULER_CELL.target,
                layer="orchestration",
                parent_context="completion-materialization",
            ),
            Gamma=Contract(
                (
                    Route(
                        guard=Guard(GuardOp.ALWAYS),
                        mutations=(
                            Mutation(MutationOp.SET, ORCH_ACTIVE_KEY, new_active),
                            Mutation(MutationOp.SET, ORCH_COMPLETED_KEY, new_completed),
                        ),
                        successor=Successor.static(SCHEDULER_ID),
                    ),
                )
            ),
        )
        uow.validate()
        return bind_materialization(self.materializer_id, state, uow)


def make_domain_task(
    identity: str,
    routes: Sequence[Route],
    *,
    matrix_cell: MatrixCell = TASK_CELL,
) -> UoW:
    """Create a domain task whose successful route proceeds to certified completion."""
    wrapped_routes: List[Route] = []
    for route in routes:
        successor = (
            Successor.static(f"{COMPLETION_PREFIX}{identity}")
            if route.successor.kind is SuccessorKind.HALT
            else route.successor
        )
        wrapped_routes.append(
            Route(
                guard=route.guard,
                mutations=route.mutations,
                successor=successor,
            )
        )

    uow = UoW(
        H=Header(
            identity=identity,
            source_category=matrix_cell.source,
            target_category=matrix_cell.target,
            layer="domain",
            parent_context="orchestrated-task",
        ),
        Gamma=Contract(tuple(wrapped_routes)),
    )
    uow.validate()
    return uow


def evaluate_scheduler_step(state: WorldState) -> WorldState:
    """Pure compatibility/reference helper.

    This function does not have commit authority. Canonical authoritative execution
    uses SchedulerMaterializer -> materialization certification -> UoW certification
    -> commit. It remains useful for differential testing of scheduler semantics.
    """
    orch = OrchestrationState(state)
    ready = orch.get_ready_tasks()

    if ready:
        task_id = ready[0]
        return orch.dispatch_tasks([task_id]).state.with_cursor(task_id)
    if orch.is_queue_empty():
        return state.with_status("HALTED").with_cursor(None)
    if orch.is_deadlocked():
        return (
            state.with_attribute(ORCH_TERMINATION_KEY, "DEADLOCKED")
            .with_status("HALTED")
            .with_cursor(None)
        )
    return state
