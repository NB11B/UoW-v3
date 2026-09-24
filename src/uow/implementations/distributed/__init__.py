"""Distributed implementation package with lazy compatibility exports.

Submodules are loaded only when their symbols are requested. This avoids
creating package-initialization cycles between fabric, convergence/delegation,
and host durability implementations.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "ActorLease",
    "AgentMessage",
    "AgentMessageKind",
    "DistributedActorFabric",
    "NetworkAgent",
    "canonical_json",
    "DurableWAL",
    "PhysicalHostNode",
    "MultiOrchestratorCluster",
]

_FABRIC = {
    "ActorLease",
    "AgentMessage",
    "AgentMessageKind",
    "DistributedActorFabric",
    "NetworkAgent",
    "canonical_json",
}
_HOST = {"DurableWAL", "PhysicalHostNode"}
_CONVERGENCE = {"MultiOrchestratorCluster"}


def __getattr__(name: str) -> Any:
    if name in _FABRIC:
        return getattr(import_module(".fabric", __name__), name)
    if name in _HOST:
        return getattr(import_module(".host_node", __name__), name)
    if name in _CONVERGENCE:
        return getattr(import_module(".convergence", __name__), name)
    raise AttributeError(name)
