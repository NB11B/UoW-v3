"""Certified resource-aware self-hosted orchestration runtime and materializers."""
from __future__ import annotations

from typing import Mapping, Optional, Sequence, Tuple

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
from ..engine import certify, propose
from ..ontology import MatrixCell, WorkCategory
from ..orchestration import (
    COMPLETION_PREFIX,
    ORCH_ACTIVE_KEY,
    ORCH_COMPLETED_KEY,
    ORCH_DEPS_KEY,
    ORCH_QUEUE_KEY,
    ORCH_TERMINATION_KEY,
    SCHEDULER_CELL,
    SCHEDULER_ID,
    TASK_CELL,
    MaterializedUoW,
    OrchestrationState,
    bind_materialization,
    certify_materialization,
)
from ..state import WorldState
from ..transactions import DeterministicSequencer, create_transaction_descriptor
from .policies import BaseSchedulingPolicy
from .requirement import ResourceBoundTask, ResourceRequirement, verify_requirement_binding
from .state import (
    ORCH_RESOURCES_KEY,
    ResourceState,
    get_authoritative_resource_state,
    set_authoritative_resource_state,
)


class ResourceAwareSchedulerMaterializer:
    """Lowers the current ready frontier into a certified scheduler UoW with atomic resource lease acquisition.

    Invariants:
    1. Recomputes requirement binding: verify_requirement_binding(task) must pass for every candidate.
    2. Recomputes resource legality: res_state.can_accommodate(req) before dispatching.
    3. Certified atomicity: (Q, A, R) -> (Q', A', R') in a single UoW transition.
    """

    def __init__(
        self,
        task_registry: Mapping[str, ResourceBoundTask],
        policy: BaseSchedulingPolicy,
    ) -> None:
        self.task_registry = task_registry
        self.policy = policy

    @property
    def materializer_id(self) -> str:
        return SCHEDULER_ID

    def materialize(self, state: WorldState) -> MaterializedUoW:
        orch = OrchestrationState(state)
        res_state = get_authoritative_resource_state(state)
        ready = orch.get_ready_tasks()

        if ready:
            # Verify requirement cryptographic binding for every ready task
            def get_req(tid: str) -> ResourceRequirement:
                if tid not in self.task_registry:
                    raise KeyError(f"Unknown task {tid!r} in resource registry.")
                bound = self.task_registry[tid]
                if not verify_requirement_binding(bound):
                    raise ValueError(f"Requirement cryptographic binding violated for task {tid!r}.")
                return bound.requirement

            # Policy proposes execution schedule
            selected = self.policy.select_schedule(ready, get_req, res_state)

            if selected:
                task_id = selected[0]
                task_bound = self.task_registry[task_id]
                # Direct invariant verification
                if not verify_requirement_binding(task_bound):
                    raise ValueError(f"Requirement cryptographic binding violated for task {task_id!r}.")

                req = task_bound.requirement

                # Independent Resource Certification: Verify capacity can accommodate
                if not res_state.can_accommodate(req):
                    raise ValueError(f"Resource certifier rejected proposal: cannot accommodate {task_id}")

                # Atomically acquire lease and debit consumable budgets
                new_res_state, lease = res_state.acquire_lease(
                    task_id, req, sequence=state.sequence + 1
                )

                new_queue = tuple(t for t in orch.queue if t != task_id)
                new_active = tuple(sorted(set(orch.active) | {task_id}))

                # Materialize UoW updating Q, A, and R simultaneously
                uow = UoW(
                    H=Header(
                        identity=SCHEDULER_ID,
                        source_category=SCHEDULER_CELL.source,
                        target_category=SCHEDULER_CELL.target,
                        layer="orchestration",
                        parent_context="resource-scheduler-materialization",
                    ),
                    Gamma=Contract(
                        (
                            Route(
                                guard=Guard(GuardOp.ALWAYS),
                                mutations=(
                                    Mutation(MutationOp.SET, ORCH_QUEUE_KEY, new_queue),
                                    Mutation(MutationOp.SET, ORCH_ACTIVE_KEY, new_active),
                                    Mutation(MutationOp.SET, ORCH_RESOURCES_KEY, new_res_state.to_dict()),
                                ),
                                successor=Successor.static(task_id),
                            ),
                        )
                    ),
                )
                uow.validate()
                return bind_materialization(self.materializer_id, state, uow)

            # Ready tasks exist, but none fit available resources -> advance anti-starvation aging
            starved_res = res_state.record_starvation(ready)
            uow = UoW(
                H=Header(
                    identity=SCHEDULER_ID,
                    source_category=SCHEDULER_CELL.source,
                    target_category=SCHEDULER_CELL.target,
                    layer="orchestration",
                    parent_context="resource-starvation-aging",
                ),
                Gamma=Contract(
                    (
                        Route(
                            guard=Guard(GuardOp.ALWAYS),
                            mutations=(
                                Mutation(MutationOp.SET, ORCH_RESOURCES_KEY, starved_res.to_dict()),
                                Mutation(MutationOp.SET, ORCH_TERMINATION_KEY, "RESOURCES_BLOCKED"),
                            ),
                            successor=Successor.halt(),
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
                    parent_context="resource-scheduler-materialization",
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
                    parent_context="resource-scheduler-materialization",
                ),
                Gamma=Contract(
                    (
                        Route(
                            guard=Guard(GuardOp.ALWAYS),
                            mutations=(
                                Mutation(MutationOp.SET, ORCH_TERMINATION_KEY, "DEADLOCKED"),
                            ),
                            successor=Successor.halt(),
                        ),
                    )
                ),
            )
            uow.validate()
            return bind_materialization(self.materializer_id, state, uow)

        # Active tasks still executing
        uow = UoW(
            H=Header(
                identity=SCHEDULER_ID,
                source_category=SCHEDULER_CELL.source,
                target_category=SCHEDULER_CELL.target,
                layer="orchestration",
                parent_context="resource-scheduler-materialization",
            ),
            Gamma=Contract(
                (
                    Route(
                        guard=Guard(GuardOp.ALWAYS),
                        mutations=(
                            Mutation(MutationOp.SET, ORCH_TERMINATION_KEY, "ACTIVE_WORK_PRESENT"),
                        ),
                        successor=Successor.halt(),
                    ),
                )
            ),
        )
        uow.validate()
        return bind_materialization(self.materializer_id, state, uow)


class ResourceAwareCompletionMaterializer:
    """Materializes certified completion of an active task, atomically releasing its resource lease."""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id

    @property
    def materializer_id(self) -> str:
        return f"{COMPLETION_PREFIX}{self.task_id}"

    def materialize(self, state: WorldState) -> MaterializedUoW:
        orch = OrchestrationState(state)
        res_state = get_authoritative_resource_state(state)

        if self.task_id not in orch.active:
            raise ValueError(f"Cannot complete inactive task {self.task_id!r}.")

        # Verify task has a granted lease in resource state
        matching_leases = [l for l in res_state.leases if l.uow_id == self.task_id]
        if not matching_leases:
            raise ValueError(f"Active task {self.task_id!r} has no authoritative resource lease to release.")

        # Release lease atomically
        new_res_state = res_state.release_lease(self.task_id)
        new_active = tuple(t for t in orch.active if t != self.task_id)
        new_completed = tuple(sorted(set(orch.completed) | {self.task_id}))

        uow = UoW(
            H=Header(
                identity=self.materializer_id,
                source_category=SCHEDULER_CELL.source,
                target_category=SCHEDULER_CELL.target,
                layer="orchestration",
                parent_context="resource-completion-materialization",
            ),
            Gamma=Contract(
                (
                    Route(
                        guard=Guard(GuardOp.ALWAYS),
                        mutations=(
                            Mutation(MutationOp.SET, ORCH_ACTIVE_KEY, new_active),
                            Mutation(MutationOp.SET, ORCH_COMPLETED_KEY, new_completed),
                            Mutation(MutationOp.SET, ORCH_RESOURCES_KEY, new_res_state.to_dict()),
                        ),
                        successor=Successor.static(SCHEDULER_ID),
                    ),
                )
            ),
        )
        uow.validate()
        return bind_materialization(self.materializer_id, state, uow)


def run_resource_orchestration(
    task_registry: Mapping[str, ResourceBoundTask],
    initial_state: WorldState,
    policy: BaseSchedulingPolicy,
    *,
    max_steps: int = 10_000,
    sequencer: Optional[DeterministicSequencer] = None,
) -> Tuple[WorldState, DeterministicSequencer]:
    """Runs resource-aware orchestration through dual certification: materialization cert + core cert."""
    sequencer = sequencer or DeterministicSequencer(initial_state)
    scheduler_mat = ResourceAwareSchedulerMaterializer(task_registry, policy)

    for _ in range(max_steps):
        state = sequencer.current_state
        if state.status != "RUNNING" or state.cursor is None:
            return state, sequencer

        cursor = state.cursor
        if cursor == SCHEDULER_ID:
            before = sequencer.current_state
            materialized = scheduler_mat.materialize(before)
            if not certify_materialization(scheduler_mat, before, materialized):
                raise ValueError("Scheduler materialization failed certification.")

            proposal = propose(materialized.uow, before)
            cert = certify(materialized.uow, before, proposal)
            if not cert.is_valid:
                raise ValueError(f"Core certifier rejected scheduler UoW: {cert.rejection_reason}")

            tx = create_transaction_descriptor(materialized.uow, before)
            sequencer.commit(materialized.uow, proposal, tx, cert)
            continue

        if cursor.startswith(COMPLETION_PREFIX):
            task_id = cursor[len(COMPLETION_PREFIX):]
            comp_mat = ResourceAwareCompletionMaterializer(task_id)
            before = sequencer.current_state
            materialized = comp_mat.materialize(before)
            if not certify_materialization(comp_mat, before, materialized):
                raise ValueError("Completion materialization failed certification.")

            proposal = propose(materialized.uow, before)
            cert = certify(materialized.uow, before, proposal)
            if not cert.is_valid:
                raise ValueError(f"Core certifier rejected completion UoW: {cert.rejection_reason}")

            tx = create_transaction_descriptor(materialized.uow, before)
            sequencer.commit(materialized.uow, proposal, tx, cert)
            continue

        if cursor not in task_registry:
            raise KeyError(f"Cursor references unknown domain task {cursor!r}.")

        # Execute ordinary domain task
        bound_task = task_registry[cursor]
        if not verify_requirement_binding(bound_task):
            raise ValueError(f"Requirement binding violation for domain task {cursor!r}.")

        before = sequencer.current_state
        proposal = propose(bound_task.uow, before)
        cert = certify(bound_task.uow, before, proposal)
        if not cert.is_valid:
            raise ValueError(f"Core certifier rejected domain task {cursor!r}: {cert.rejection_reason}")

        tx = create_transaction_descriptor(bound_task.uow, before)
        sequencer.commit(bound_task.uow, proposal, tx, cert)

    raise RuntimeError(f"Step budget {max_steps} exceeded.")
