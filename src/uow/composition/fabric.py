"""Compatibility shim for the historical distributed actor fabric path."""

from ..implementations.distributed.fabric import (
    ActorLease,
    AgentMessage,
    AgentMessageKind,
    DistributedActorFabric,
    NetworkAgent,
    canonical_json,
)

__all__ = [
    "ActorLease",
    "AgentMessage",
    "AgentMessageKind",
    "DistributedActorFabric",
    "NetworkAgent",
    "canonical_json",
]
