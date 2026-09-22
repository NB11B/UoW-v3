"""Public API for DAG orchestration and certified self-hosted scheduling."""

from .materialization import (
    MaterializedUoW,
    UoWMaterializer,
    bind_materialization,
    canonical_uow_payload,
    certify_materialization,
    uow_fingerprint,
)
from .runtime import (
    execute_domain_task,
    execute_materialized,
    run_orchestration,
)
from .scheduler import (
    COMPLETION_PREFIX,
    ORCH_TERMINATION_KEY,
    SCHEDULER_CELL,
    SCHEDULER_ID,
    TASK_CELL,
    CompletionMaterializer,
    SchedulerMaterializer,
    evaluate_scheduler_step,
    make_domain_task,
)
from .state import (
    ORCH_ACTIVE_KEY,
    ORCH_COMPLETED_KEY,
    ORCH_DEPS_KEY,
    ORCH_QUEUE_KEY,
    OrchestrationState,
    create_initial_orchestration_state,
)

__all__ = [
    "COMPLETION_PREFIX",
    "MaterializedUoW",
    "ORCH_ACTIVE_KEY",
    "ORCH_COMPLETED_KEY",
    "ORCH_DEPS_KEY",
    "ORCH_QUEUE_KEY",
    "ORCH_TERMINATION_KEY",
    "OrchestrationState",
    "SCHEDULER_CELL",
    "SCHEDULER_ID",
    "TASK_CELL",
    "CompletionMaterializer",
    "SchedulerMaterializer",
    "UoWMaterializer",
    "bind_materialization",
    "canonical_uow_payload",
    "certify_materialization",
    "create_initial_orchestration_state",
    "evaluate_scheduler_step",
    "execute_domain_task",
    "execute_materialized",
    "make_domain_task",
    "run_orchestration",
    "uow_fingerprint",
]
