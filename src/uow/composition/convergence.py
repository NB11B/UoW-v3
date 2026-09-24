"""Compatibility surface for A2 authoritative history and cluster convergence."""

from .history import AuthoritativeHistory, HistoryEntry, HistoryEntryKind
from ..implementations.distributed.convergence import MultiOrchestratorCluster

__all__ = [
    "AuthoritativeHistory",
    "HistoryEntry",
    "HistoryEntryKind",
    "MultiOrchestratorCluster",
]
