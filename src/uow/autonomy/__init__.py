"""Public API for UoW Autonomy.

Autonomy decides/proposes work; existing UoW machinery governs work.
"""
from __future__ import annotations

from .api import (
    AutonomousRuntime,
    AutonomyRequest,
    AutonomyResult,
    CapabilitySpec,
    GoalSpec,
    TerminalDisposition,
)
from .model import AutonomyBudget
from .ports import ExecutionPort

__all__ = [
    "AutonomousRuntime",
    "AutonomyBudget",
    "AutonomyRequest",
    "AutonomyResult",
    "CapabilitySpec",
    "ExecutionPort",
    "GoalSpec",
    "TerminalDisposition",
]
