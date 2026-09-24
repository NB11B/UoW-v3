"""Compatibility shim for the historical adaptive composition runtime path."""

from ..implementations.composition.runtime import (
    AdaptiveCompositionRuntime,
    ExecutionRecord,
    NodeExecutionResult,
)

__all__ = ["AdaptiveCompositionRuntime", "ExecutionRecord", "NodeExecutionResult"]
