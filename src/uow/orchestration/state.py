"""Orchestration state model and DAG dependency evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ..state import WorldState, _thaw

ORCH_QUEUE_KEY = "__queue__"
ORCH_ACTIVE_KEY = "__active__"
ORCH_COMPLETED_KEY = "__completed__"
ORCH_DEPS_KEY = "__deps__"


@dataclass(frozen=True)
class OrchestrationState:
    """Typed wrapper over WorldState providing DAG queue, active batch, and dependency views.

    WorldState remains authoritative. OrchestrationState maps typed concepts
    to internal state attributes without polluting the foundational kernel.
    """

    state: WorldState

    @property
    def queue(self) -> Tuple[str, ...]:
        return tuple(self.state.get(ORCH_QUEUE_KEY, ()))

    @property
    def active(self) -> Tuple[str, ...]:
        return tuple(self.state.get(ORCH_ACTIVE_KEY, ()))

    @property
    def completed(self) -> Tuple[str, ...]:
        return tuple(self.state.get(ORCH_COMPLETED_KEY, ()))

    @property
    def dependencies(self) -> Mapping[str, Tuple[str, ...]]:
        raw = self.state.get(ORCH_DEPS_KEY, {})
        if not isinstance(raw, Mapping):
            return {}
        return {k: tuple(v) for k, v in raw.items()}

    def get_ready_tasks(self) -> Tuple[str, ...]:
        """Returns pending tasks in queue whose dependencies are all completed."""
        completed_set = set(self.completed)
        deps = self.dependencies
        ready: List[str] = []
        for task_id in self.queue:
            task_deps = deps.get(task_id, ())
            if all(d in completed_set for d in task_deps):
                ready.append(task_id)
        return tuple(ready)

    def is_queue_empty(self) -> bool:
        return len(self.queue) == 0 and len(self.active) == 0

    def is_deadlocked(self) -> bool:
        """Deadlock occurs when queue is non-empty, active is empty, but no tasks are ready."""
        return len(self.queue) > 0 and len(self.active) == 0 and len(self.get_ready_tasks()) == 0

    def dispatch_tasks(self, task_ids: Sequence[str]) -> "OrchestrationState":
        """Dispatches a batch of ready tasks: moves them from queue to active."""
        to_dispatch = set(task_ids)
        new_queue = tuple(t for t in self.queue if t not in to_dispatch)
        new_active = tuple(sorted(set(self.active) | to_dispatch))

        s = self.state.with_attribute(ORCH_QUEUE_KEY, new_queue).with_attribute(
            ORCH_ACTIVE_KEY, new_active
        )
        return OrchestrationState(s)

    def complete_task(self, task_id: str) -> "OrchestrationState":
        """Marks a task completed: removes from active, appends to completed."""
        new_active = tuple(t for t in self.active if t != task_id)
        new_completed = tuple(sorted(set(self.completed) | {task_id}))

        s = self.state.with_attribute(ORCH_ACTIVE_KEY, new_active).with_attribute(
            ORCH_COMPLETED_KEY, new_completed
        )
        return OrchestrationState(s)

    def enqueue_tasks(
        self,
        tasks: Sequence[str],
        dependencies: Optional[Mapping[str, Sequence[str]]] = None,
    ) -> "OrchestrationState":
        """Enqueues new tasks and records their dependencies."""
        new_queue = tuple(self.queue) + tuple(tasks)
        new_deps = dict(self.dependencies)
        if dependencies:
            for k, v in dependencies.items():
                new_deps[k] = tuple(v)

        s = self.state.with_attribute(ORCH_QUEUE_KEY, new_queue).with_attribute(
            ORCH_DEPS_KEY, new_deps
        )
        return OrchestrationState(s)


def create_initial_orchestration_state(
    queue: Sequence[str],
    dependencies: Optional[Mapping[str, Sequence[str]]] = None,
    attributes: Optional[Mapping[str, Any]] = None,
    scheduler_pointer: str = "uow_scheduler",
) -> WorldState:
    """Constructs an initial WorldState configured for DAG orchestration."""
    attrs = dict(attributes or {})
    attrs[ORCH_QUEUE_KEY] = tuple(queue)
    attrs[ORCH_ACTIVE_KEY] = ()
    attrs[ORCH_COMPLETED_KEY] = ()
    attrs[ORCH_DEPS_KEY] = {k: tuple(v) for k, v in (dependencies or {}).items()}

    return WorldState(
        attributes=attrs,
        cursor=scheduler_pointer,
        status="RUNNING",
    )
