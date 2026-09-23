"""Actor descriptors and registry for Campaign A2.

Decouples logical graph nodes from physical execution substrates, enabling
dynamic binding and qualification across heterogeneous local and networked actors.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Dict, List, Mapping, Optional, Sequence, Tuple


class AuthorityClass(str, Enum):
    """Authority privilege level of an executing actor."""
    PROPOSER_ONLY = "PROPOSER_ONLY"
    VERIFIER = "VERIFIER"
    AUTHORITY_SUBSTRATE = "AUTHORITY_SUBSTRATE"

    def satisfies(self, required: AuthorityClass) -> bool:
        """Determines if this actor's authority class satisfies the required level."""
        hierarchy = {
            AuthorityClass.PROPOSER_ONLY: 0,
            AuthorityClass.VERIFIER: 1,
            AuthorityClass.AUTHORITY_SUBSTRATE: 2,
        }
        return hierarchy[self] >= hierarchy[required]


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ActorDescriptor:
    """Advertised descriptor of a physical or logical execution actor."""

    actor_id: str
    capabilities: Tuple[str, ...]
    substrate: str  # e.g. "intel_npu", "cpu_x86", "esp32_xtensa", "unoq_stm32", "cloud_server"
    authority_class: AuthorityClass = AuthorityClass.PROPOSER_ONLY
    endpoint: str = "local"  # "local", "127.0.0.1:9527", "COM10", "192.168.1.104"
    availability: bool = True
    load: float = 0.0  # 0.0 (idle) to 1.0 (saturated)
    latency_ms: float = 1.0
    recent_failures: int = 0
    cost_per_ms: float = 0.0
    descriptor_hash: str = ""

    def __post_init__(self) -> None:
        if not self.descriptor_hash:
            payload = {
                "actor_id": self.actor_id,
                "capabilities": sorted(self.capabilities),
                "substrate": self.substrate,
                "authority_class": self.authority_class.value,
                "endpoint": self.endpoint,
            }
            digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
            object.__setattr__(self, "descriptor_hash", digest)

    def compute_hash(self) -> str:
        return self.descriptor_hash

    def has_capabilities(self, required: Sequence[str]) -> bool:
        cap_set = set(self.capabilities)
        return all(req in cap_set for req in required)


class ActorRegistry:
    """In-memory registry of active actors across local and networked substrates."""

    def __init__(self, initial_actors: Optional[Sequence[ActorDescriptor]] = None) -> None:
        self._actors: Dict[str, ActorDescriptor] = {}
        if initial_actors:
            for act in initial_actors:
                self.register(act)

    def register(self, actor: ActorDescriptor) -> None:
        self._actors[actor.actor_id] = actor

    def unregister(self, actor_id: str) -> Optional[ActorDescriptor]:
        return self._actors.pop(actor_id, None)

    def get(self, actor_id: str) -> Optional[ActorDescriptor]:
        return self._actors.get(actor_id)

    def all_actors(self) -> Tuple[ActorDescriptor, ...]:
        return tuple(self._actors.values())

    def find_capable_actors(
        self,
        required_capabilities: Sequence[str],
        min_authority: AuthorityClass = AuthorityClass.PROPOSER_ONLY,
        require_available: bool = True,
        max_load: float = 1.0,
    ) -> List[ActorDescriptor]:
        """Finds all registered actors meeting capability, authority, and load thresholds."""
        candidates = []
        for actor in self._actors.values():
            if require_available and not actor.availability:
                continue
            if actor.load > max_load:
                continue
            if not actor.authority_class.satisfies(min_authority):
                continue
            if not actor.has_capabilities(required_capabilities):
                continue
            candidates.append(actor)

        # Sort by load and latency ascending
        candidates.sort(key=lambda a: (a.load, a.latency_ms))
        return candidates

    def update_status(
        self,
        actor_id: str,
        availability: Optional[bool] = None,
        load: Optional[float] = None,
        latency_ms: Optional[float] = None,
        increment_failures: bool = False,
    ) -> None:
        """Updates runtime telemetry for an existing actor descriptor."""
        if actor_id not in self._actors:
            return
        curr = self._actors[actor_id]
        updated = ActorDescriptor(
            actor_id=curr.actor_id,
            capabilities=curr.capabilities,
            substrate=curr.substrate,
            authority_class=curr.authority_class,
            endpoint=curr.endpoint,
            availability=curr.availability if availability is None else availability,
            load=curr.load if load is None else max(0.0, min(1.0, load)),
            latency_ms=curr.latency_ms if latency_ms is None else max(0.0, latency_ms),
            recent_failures=curr.recent_failures + 1 if increment_failures else curr.recent_failures,
            cost_per_ms=curr.cost_per_ms,
            descriptor_hash=curr.descriptor_hash,
        )
        self._actors[actor_id] = updated
