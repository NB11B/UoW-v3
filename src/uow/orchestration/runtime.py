"""Execution of certified materialized orchestration UoWs."""
from __future__ import annotations

from typing import Mapping, Optional, Tuple

from ..contracts import UoW
from ..engine import certify, propose
from ..state import WorldState
from ..transactions import DeterministicSequencer, create_transaction_descriptor
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

    proposal = propose(materialized.uow, before)
    certificate = certify(materialized.uow, before, proposal)
    if not certificate.is_valid:
        raise ValueError(
            f"Materialized UoW failed core certification: {certificate.rejection_reason}"
        )
    transaction = create_transaction_descriptor(materialized.uow, before)
    committed, _evidence = sequencer.commit(
        materialized.uow,
        proposal,
        transaction,
        certificate,
    )
    return committed


def execute_domain_task(uow: UoW, sequencer: DeterministicSequencer) -> WorldState:
    """Execute one ordinary domain UoW through core certification and OCC commit."""
    before = sequencer.current_state
    proposal = propose(uow, before)
    certificate = certify(uow, before, proposal)
    if not certificate.is_valid:
        raise ValueError(f"Domain UoW failed certification: {certificate.rejection_reason}")
    transaction = create_transaction_descriptor(uow, before)
    committed, _evidence = sequencer.commit(uow, proposal, transaction, certificate)
    return committed


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
