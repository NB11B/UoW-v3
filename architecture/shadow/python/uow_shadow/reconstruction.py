"""R4 experiment reconstruction helpers using the R3 minimal authority kernel.

The native UoW contract, pure proposal computation, and deterministic certifier
remain the initial semantic oracle. The canonical commit implementation is NOT
used. Accepted transitions are applied by the shadow authority kernel.

This is the first step toward reconstructing the experiment set from the minimal
invariant architecture without prematurely replacing proven proposal/certifier logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Tuple

from uow.contracts import UoW
from uow.engine import validate_graph
from uow.state import WorldState

from .identity import shadow_identity
from .spine import CursorPolicy, DEFAULT_APPLICATION_SPINE
from .types import EvidenceEntryRef


@dataclass(frozen=True)
class ReconstructionResult:
    final_state: WorldState
    evidence: Tuple[EvidenceEntryRef, ...]
    steps: int

    def evidence_root(self) -> str:
        return shadow_identity(
            "reconstruction-evidence-root",
            tuple(entry.entry_identity for entry in self.evidence),
        )


def execute_explicit_uow_reconstructed(
    uow: UoW,
    state: WorldState,
) -> tuple[WorldState, EvidenceEntryRef]:
    """Apply an explicitly supplied UoW through the common R6 application spine."""
    result = DEFAULT_APPLICATION_SPINE.execute(
        uow,
        state,
        cursor_policy=CursorPolicy.DETACHED,
    )
    return result.state, result.evidence


def execute_one_reconstructed(
    graph: Mapping[str, UoW],
    state: WorldState,
) -> tuple[WorldState, EvidenceEntryRef]:
    if state.cursor is None or state.status != "RUNNING":
        raise ValueError("Reconstruction step requires a RUNNING state with an active cursor.")
    if state.cursor not in graph:
        raise KeyError(f"Current UoW cursor {state.cursor!r} does not exist in graph.")

    result = DEFAULT_APPLICATION_SPINE.execute(
        graph[state.cursor],
        state,
        cursor_policy=CursorPolicy.OWNED,
    )
    return result.state, result.evidence

def run_reconstructed(
    graph: Mapping[str, UoW],
    initial_state: WorldState,
    *,
    max_steps: int = 1_000_000,
) -> ReconstructionResult:
    validate_graph(dict(graph))
    state = initial_state
    evidence = []

    for step in range(max_steps):
        if state.cursor is None or state.status != "RUNNING":
            return ReconstructionResult(state, tuple(evidence), step)
        state, entry = execute_one_reconstructed(graph, state)
        evidence.append(entry)

    raise RuntimeError(f"Reconstruction step budget {max_steps} exceeded.")


def run_reconstructed_steps(
    graph: Mapping[str, UoW],
    initial_state: WorldState,
    *,
    steps: int,
) -> ReconstructionResult:
    validate_graph(dict(graph))
    state = initial_state
    evidence = []

    for _ in range(steps):
        if state.cursor is None or state.status != "RUNNING":
            break
        state, entry = execute_one_reconstructed(graph, state)
        evidence.append(entry)

    return ReconstructionResult(state, tuple(evidence), len(evidence))



def run_orchestration_reconstructed(
    tasks: Mapping[str, UoW],
    initial_state: WorldState,
    *,
    max_steps: int = 10_000,
) -> ReconstructionResult:
    """Reconstruct U11 self-hosted orchestration through the minimal authority kernel.

    Scheduler and completion decisions are dynamically materialized and must pass
    independent materialization certification before their resulting ordinary UoW
    is allowed into the shadow authority path. No DeterministicSequencer or
    canonical commit function is used.
    """
    from uow.orchestration.materialization import certify_materialization
    from uow.orchestration.scheduler import (
        COMPLETION_PREFIX,
        SCHEDULER_ID,
        CompletionMaterializer,
        SchedulerMaterializer,
    )

    state = initial_state
    evidence = []
    scheduler = SchedulerMaterializer()

    for step in range(max_steps):
        if state.cursor is None or state.status != "RUNNING":
            return ReconstructionResult(state, tuple(evidence), step)

        cursor = state.cursor
        if cursor == SCHEDULER_ID:
            materialized = scheduler.materialize(state)
            if not certify_materialization(scheduler, state, materialized):
                raise ValueError("Scheduler materialization failed independent certification.")
            active_uow = materialized.uow

        elif cursor.startswith(COMPLETION_PREFIX):
            task_id = cursor[len(COMPLETION_PREFIX):]
            completion = CompletionMaterializer(task_id)
            materialized = completion.materialize(state)
            if not certify_materialization(completion, state, materialized):
                raise ValueError("Completion materialization failed independent certification.")
            active_uow = materialized.uow

        else:
            if cursor not in tasks:
                raise KeyError(f"Orchestration cursor references unknown task {cursor!r}.")
            active_uow = tasks[cursor]

        # execute_one_reconstructed intentionally uses proposal/certifier oracle
        # plus the independent minimal shadow authority/transition/evidence path.
        state, entry = execute_one_reconstructed({active_uow.H.identity: active_uow}, state)
        evidence.append(entry)

    raise RuntimeError(f"Orchestration reconstruction step budget {max_steps} exceeded.")



def run_resource_orchestration_reconstructed(
    task_registry,
    initial_state: WorldState,
    policy,
    *,
    max_steps: int = 10_000,
) -> ReconstructionResult:
    """Reconstruct U13 resource-aware orchestration through shadow authority.

    Resource scheduler/completion materializers remain the canonical semantic
    oracle for lease/budget state transitions. Their accepted ordinary UoWs are
    applied by the minimal shadow authority kernel; no canonical sequencer is used.
    """
    from uow.orchestration.materialization import certify_materialization
    from uow.orchestration.scheduler import COMPLETION_PREFIX, SCHEDULER_ID
    from uow.resources.requirement import verify_requirement_binding
    from uow.resources.runtime import (
        ResourceAwareCompletionMaterializer,
        ResourceAwareSchedulerMaterializer,
    )

    state = initial_state
    evidence = []
    scheduler = ResourceAwareSchedulerMaterializer(task_registry, policy)

    for step in range(max_steps):
        if state.cursor is None or state.status != "RUNNING":
            return ReconstructionResult(state, tuple(evidence), step)

        cursor = state.cursor
        if cursor == SCHEDULER_ID:
            materialized = scheduler.materialize(state)
            if not certify_materialization(scheduler, state, materialized):
                raise ValueError("Resource scheduler materialization failed certification.")
            active_uow = materialized.uow

        elif cursor.startswith(COMPLETION_PREFIX):
            task_id = cursor[len(COMPLETION_PREFIX):]
            completion = ResourceAwareCompletionMaterializer(task_id)
            materialized = completion.materialize(state)
            if not certify_materialization(completion, state, materialized):
                raise ValueError("Resource completion materialization failed certification.")
            active_uow = materialized.uow

        else:
            if cursor not in task_registry:
                raise KeyError(f"Resource orchestration cursor references unknown task {cursor!r}.")
            bound = task_registry[cursor]
            if not verify_requirement_binding(bound):
                raise ValueError(f"Requirement binding violation for domain task {cursor!r}.")
            active_uow = bound.uow

        state, entry = execute_one_reconstructed({active_uow.H.identity: active_uow}, state)
        evidence.append(entry)

    raise RuntimeError(f"Resource orchestration reconstruction step budget {max_steps} exceeded.")
