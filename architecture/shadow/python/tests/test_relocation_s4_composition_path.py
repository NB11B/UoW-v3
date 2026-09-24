from __future__ import annotations

import inspect

import uow
from uow.composition import AdaptiveCompositionRuntime, ExecutionRecord, NodeExecutionResult
from uow.implementations.composition.runtime import (
    AdaptiveCompositionRuntime as ImplRuntime,
    ExecutionRecord as ImplRecord,
    NodeExecutionResult as ImplNodeResult,
)


def test_s4_composition_runtime_imports_remain_identity_compatible():
    assert AdaptiveCompositionRuntime is ImplRuntime
    assert ExecutionRecord is ImplRecord
    assert NodeExecutionResult is ImplNodeResult

    assert uow.AdaptiveCompositionRuntime is ImplRuntime
    assert uow.ExecutionRecord is ImplRecord
    assert uow.NodeExecutionResult is ImplNodeResult


def test_s4_historical_composition_runtime_is_only_compatibility_shim():
    import uow.composition.runtime as shim

    source = inspect.getsource(shim)
    assert "class AdaptiveCompositionRuntime" not in source
    assert "class ExecutionRecord" not in source
    assert "class NodeExecutionResult" not in source
    assert "implementations.composition.runtime" in source


def test_s4_relocated_composition_runtime_keeps_semantic_dependencies():
    import uow.implementations.composition.runtime as implementation

    source = inspect.getsource(implementation)
    assert "uow.composition.contract" in source
    assert "uow.composition.substitution" in source
    assert "uow.composition.binding" in source
