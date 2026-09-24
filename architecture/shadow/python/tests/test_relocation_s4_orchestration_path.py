from __future__ import annotations

import inspect

import uow
from uow.implementations.orchestration.runtime import (
    execute_domain_task as implementation_execute_domain_task,
    execute_materialized as implementation_execute_materialized,
    run_orchestration as implementation_run_orchestration,
)
from uow.orchestration import (
    execute_domain_task,
    execute_materialized,
    run_orchestration,
)


def test_s4_orchestration_imports_remain_identity_compatible():
    assert execute_domain_task is implementation_execute_domain_task
    assert execute_materialized is implementation_execute_materialized
    assert run_orchestration is implementation_run_orchestration

    assert uow.execute_domain_task is implementation_execute_domain_task
    assert uow.execute_materialized is implementation_execute_materialized
    assert uow.run_orchestration is implementation_run_orchestration


def test_s4_historical_orchestration_runtime_is_only_shim():
    import uow.orchestration.runtime as shim

    source = inspect.getsource(shim)
    assert "def execute_domain_task" not in source
    assert "def execute_materialized" not in source
    assert "def run_orchestration" not in source
    assert "implementations.orchestration.runtime" in source


def test_s4_new_orchestration_implementation_uses_production_application_spine():
    import uow.implementations.orchestration.runtime as implementation

    source = inspect.getsource(implementation)
    assert "DEFAULT_APPLICATION_SPINE.execute" in source
    assert "propose(" not in source
    assert "certify(" not in source
    assert "sequencer.commit(" not in source
