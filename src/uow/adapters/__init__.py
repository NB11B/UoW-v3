"""UoW hardware, neural, and external model adapters."""
from __future__ import annotations

from typing import Any

__all__ = ["IntelNPUAdaptiveProposer"]


def __getattr__(name: str) -> Any:
    if name == "IntelNPUAdaptiveProposer":
        from integrations.openvino_npu import IntelNPUAdaptiveProposer
        return IntelNPUAdaptiveProposer
    raise AttributeError(f"module 'uow.adapters' has no attribute {name!r}")
