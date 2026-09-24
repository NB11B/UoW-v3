from __future__ import annotations

import inspect

import uow
from uow.orchestration import (
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
from uow.realizations.scheduling.self_hosted import (
    COMPLETION_PREFIX as impl_completion_prefix,
    ORCH_TERMINATION_KEY as impl_termination_key,
    SCHEDULER_CELL as impl_scheduler_cell,
    SCHEDULER_ID as impl_scheduler_id,
    TASK_CELL as impl_task_cell,
    CompletionMaterializer as ImplCompletionMaterializer,
    SchedulerMaterializer as ImplSchedulerMaterializer,
    evaluate_scheduler_step as impl_evaluate_scheduler_step,
    make_domain_task as impl_make_domain_task,
)


def test_s4_scheduler_imports_remain_identity_compatible():
    assert SchedulerMaterializer is ImplSchedulerMaterializer
    assert CompletionMaterializer is ImplCompletionMaterializer
    assert make_domain_task is impl_make_domain_task
    assert evaluate_scheduler_step is impl_evaluate_scheduler_step

    assert SCHEDULER_CELL is impl_scheduler_cell
    assert TASK_CELL is impl_task_cell
    assert SCHEDULER_ID is impl_scheduler_id
    assert COMPLETION_PREFIX is impl_completion_prefix
    assert ORCH_TERMINATION_KEY is impl_termination_key

    assert uow.SchedulerMaterializer is ImplSchedulerMaterializer
    assert uow.CompletionMaterializer is ImplCompletionMaterializer
    assert uow.make_domain_task is impl_make_domain_task
    assert uow.evaluate_scheduler_step is impl_evaluate_scheduler_step


def test_s4_historical_scheduler_module_is_only_compatibility_shim():
    import uow.orchestration.scheduler as shim

    source = inspect.getsource(shim)
    assert "class SchedulerMaterializer" not in source
    assert "class CompletionMaterializer" not in source
    assert "def make_domain_task" not in source
    assert "def evaluate_scheduler_step" not in source
    assert "realizations.scheduling.self_hosted" in source
