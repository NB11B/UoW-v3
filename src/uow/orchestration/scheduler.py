"""Native self-hosted scheduler and task UoW construction."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

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
from .state import (
    ORCH_ACTIVE_KEY,
    ORCH_COMPLETED_KEY,
    ORCH_DEPS_KEY,
    ORCH_QUEUE_KEY,
    OrchestrationState,
)

SCHEDULER_CELL: MatrixCell = MatrixCell(WorkCategory.RULES, WorkCategory.PROCESSES)
TASK_CELL: MatrixCell = MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA)


def evaluate_scheduler_step(state: WorldState) -> WorldState:
    """Evaluates one step of native scheduling over the orchestration state attributes.

    - If ready tasks exist in queue, dispatches the first ready task (setting it in active
      and setting state cursor to that task).
    - If queue is empty and active is empty, halts cleanly.
    - If queue has pending tasks but none are ready and active is empty, marks DEADLOCKED.
    """
    orch = OrchestrationState(state)
    ready = orch.get_ready_tasks()

    if ready:
        top_task = ready[0]
        dispatched_orch = orch.dispatch_tasks([top_task])
        # Direct cursor to dispatched task
        return dispatched_orch.state.with_cursor(top_task)

    if orch.is_queue_empty():
        return state.with_status("HALTED").with_cursor(None)

    if orch.is_deadlocked():
        return state.with_status("DEADLOCKED").with_cursor(None)

    # Active tasks are in-flight, waiting for completion
    return state


def make_domain_task(
    identity: str,
    routes: Sequence[Route],
    *,
    matrix_cell: MatrixCell = TASK_CELL,
    return_to: str = "uow_scheduler",
) -> UoW:
    """Creates a domain task UoW that executes its mutations and transitions back to scheduler.

    When the task completes, the scheduler or transaction commit marks it completed.
    """
    wrapped_routes: List[Route] = []
    for r in routes:
        # If route halts, redirect to scheduler return
        succ = Successor.static(return_to) if r.successor.kind == SuccessorKind.HALT else r.successor
        wrapped_routes.append(
            Route(
                guard=r.guard,
                mutations=r.mutations,
                successor=succ,
            )
        )

    return UoW(
        H=Header(
            identity=identity,
            source_category=matrix_cell.source,
            target_category=matrix_cell.target,
            layer="domain",
            parent_context="orchestrated-task",
        ),
        Gamma=Contract(tuple(wrapped_routes)),
    )
