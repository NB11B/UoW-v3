"""Compatibility shim for the historical composition host-node path."""

from ..implementations.distributed.host_node import DurableWAL, PhysicalHostNode

__all__ = ["DurableWAL", "PhysicalHostNode"]
