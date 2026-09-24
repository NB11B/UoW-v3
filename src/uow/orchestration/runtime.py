"""Compatibility shim for the historical orchestration runtime path."""

from ..implementations.orchestration.runtime import (
    execute_domain_task,
    execute_materialized,
    run_orchestration,
)

__all__ = ["execute_domain_task", "execute_materialized", "run_orchestration"]
