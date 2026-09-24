"""Execution of certified materialized orchestration UoWs."""
from __future__ import annotations

from typing import Mapping, Optional, Tuple

from ..application import DEFAULT_APPLICATION_SPINE, CursorPolicy
from ..contracts import UoW
from ..state import WorldState
from ..transactions import DeterministicSequencer
from .materialization import UoWMaterializer, certify_materialization
from .scheduler import COMPLETION_PREFIX, CompletionMaterializer, SCHEDULER_ID, SchedulerMaterializer


def execute_materialized(
    materializer: UoWMaterializer,
    sequencer: DeterministicSequencer,
) -> WorldState:
    """Execute one materialized UoW through both certification boundaries."""
    before = sequencer.current_state
    materialized = materializer.materialize(before)
    if not certify_materialization(materializer, before, materialized):
        raise ValueError("Derived UoW materialization failed independent certification.")

    result = DEFAULT_APPLICATION_SPINE.execute(
        materialized.uow,
        sequencer,
        cursor_policy=CursorPolicy.OWNED,
    )
    return result.state


def execute_domain_task(uow: UoW, sequencer: DeterministicSequencer) -> WorldState:
    """Execute one ordinary domain UoW through the common application spine."""
    result = DEFAULT_APPLICATION_SPINE.execute(
        uow,
        sequencer,
        cursor_policy=CursorPolicy.OWNED,
    )
    return result.state


def run_orchestration(
    tasks: Mapping[str, UoW],
    initial_state: WorldState,
    *,
    max_steps: int = 10_000,
    sequencer: Optional[DeterministicSequencer] = None,
) -> Tuple[WorldState, DeterministicSequencer]:
    """Run scheduler, domain work, and completions with no privileged state mutation."""
    sequencer = sequencer or DeterministicSequencer(initial_state)
    scheduler = SchedulerMaterializer()

    for _ in range(max_steps):
        state = sequencer.current_state
        if state.status != "RUNNING" or state.cursor is None:
            return state, sequencer

        cursor = state.cursor
        if cursor == SCHEDULER_ID:
            execute_materialized(scheduler, sequencer)
            continue

        if cursor.startswith(COMPLETION_PREFIX):
            task_id = cursor[len(COMPLETION_PREFIX):]
            execute_materialized(CompletionMaterializer(task_id), sequencer)
            continue

        if cursor not in tasks:
            raise KeyError(f"Orchestration cursor references unknown task {cursor!r}.")
        execute_domain_task(tasks[cursor], sequencer)

    raise RuntimeError(f"Orchestration step budget {max_steps} exceeded.")
