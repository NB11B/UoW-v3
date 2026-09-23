"""Distributed Actor Fabric, Network Agents, and Leases for Campaign A2.

Implements network agent discovery, cryptographic leases with expiry, and strict
separation between actor discovery and authority qualification:
    Discover(A) != Qualify(A, U)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from uow.composition.actor import ActorDescriptor, ActorRegistry, AuthorityClass
from uow.composition.contract import ParentContract


def canonical_json(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


class AgentMessageKind(str, Enum):
    ANNOUNCE = "ANNOUNCE"
    HEARTBEAT = "HEARTBEAT"
    DESCRIBE = "DESCRIBE"
    EXECUTE = "EXECUTE"
    RESULT = "RESULT"
    EVIDENCE = "EVIDENCE"


@dataclass(frozen=True)
class AgentMessage:
    """Standardized message exchanged between network runtime agents and the fabric."""

    kind: AgentMessageKind
    sender_id: str
    payload: Mapping[str, Any]
    timestamp_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class ActorLease:
    """Cryptographic, time-bounded lease guaranteeing actor liveness and availability."""

    actor_id: str
    descriptor_hash: str
    epoch: int
    granted_at_ts: float
    expires_at_ts: float
    nonce: str
    lease_hash: str = ""

    def __post_init__(self) -> None:
        if not self.lease_hash:
            payload = {
                "actor_id": self.actor_id,
                "descriptor_hash": self.descriptor_hash,
                "epoch": self.epoch,
                "granted_at_ts": f"{self.granted_at_ts:.4f}",
                "expires_at_ts": f"{self.expires_at_ts:.4f}",
                "nonce": self.nonce,
            }
            digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
            object.__setattr__(self, "lease_hash", digest)

    def compute_hash(self) -> str:
        return self.lease_hash

    def is_valid(self, current_ts: float) -> bool:
        """Determines if this lease has not expired."""
        return current_ts <= self.expires_at_ts


class NetworkAgent:
    """Lightweight independent runtime agent running on a local or remote network endpoint."""

    def __init__(
        self,
        actor_id: str,
        descriptor: ActorDescriptor,
    ) -> None:
        self.actor_id = actor_id
        self.descriptor = descriptor
        self.is_alive = True
        self._nonce_counter = 0

    def announce(self) -> AgentMessage:
        return AgentMessage(
            kind=AgentMessageKind.ANNOUNCE,
            sender_id=self.actor_id,
            payload={
                "descriptor": {
                    "actor_id": self.descriptor.actor_id,
                    "capabilities": list(self.descriptor.capabilities),
                    "substrate": self.descriptor.substrate,
                    "authority_class": self.descriptor.authority_class.value,
                    "endpoint": self.descriptor.endpoint,
                    "availability": self.is_alive,
                    "load": self.descriptor.load,
                    "latency_ms": self.descriptor.latency_ms,
                }
            },
        )

    def heartbeat(self) -> AgentMessage:
        self._nonce_counter += 1
        return AgentMessage(
            kind=AgentMessageKind.HEARTBEAT,
            sender_id=self.actor_id,
            payload={"alive": self.is_alive, "nonce": f"{self.actor_id}_{self._nonce_counter}"},
        )

    def execute_step(
        self,
        node_id: str,
        role: str,
        inputs: Mapping[str, Any],
        duration_ms: float = 10.0,
    ) -> Tuple[Mapping[str, Any], str]:
        """Executes a single node step and returns (outputs, evidence_token)."""
        if not self.is_alive:
            raise RuntimeError(f"Agent {self.actor_id} is terminated/offline")

        outputs: Dict[str, Any] = {}
        for k, v in inputs.items():
            outputs[f"res_{k}"] = f"processed_{v}_by_{self.actor_id}"

        evidence_token = hashlib.sha256(
            f"{self.actor_id}:{node_id}:{role}:{time.time()}".encode("utf-8")
        ).hexdigest()[:16]

        return outputs, evidence_token

    def terminate(self) -> None:
        """Simulates agent disconnection or process crash."""
        self.is_alive = False


class DistributedActorFabric:
    """Central discovery fabric managing network agent registrations, leases, and authority qualification."""

    def __init__(
        self,
        registry: Optional[ActorRegistry] = None,
        trusted_authority_keys: Optional[Set[str]] = None,
        lease_ttl_sec: float = 15.0,
    ) -> None:
        self.registry = registry or ActorRegistry()
        # Explicit trusted authority keys for Qualify(A, U)
        self.trusted_authority_keys: Set[str] = set(trusted_authority_keys or set())
        self.lease_ttl_sec = lease_ttl_sec
        self.active_leases: Dict[str, ActorLease] = {}
        self.registered_agents: Dict[str, NetworkAgent] = {}
        self.current_epoch = 1

    def register_trusted_authority(self, actor_id: str) -> None:
        self.trusted_authority_keys.add(actor_id)

    def register_agent(self, agent: NetworkAgent, current_ts: Optional[float] = None) -> ActorLease:
        """Discovers and registers a network agent, granting an initial lease."""
        ts = current_ts if current_ts is not None else time.time()
        self.registered_agents[agent.actor_id] = agent
        self.registry.register(agent.descriptor)
        return self._grant_lease(agent.actor_id, agent.descriptor.descriptor_hash, ts)

    def handle_heartbeat(self, agent_id: str, current_ts: Optional[float] = None) -> Optional[ActorLease]:
        """Renews an active actor lease upon receiving a heartbeat."""
        ts = current_ts if current_ts is not None else time.time()
        agent = self.registered_agents.get(agent_id)
        if not agent or not agent.is_alive:
            return None

        desc = self.registry.get(agent_id)
        if not desc:
            return None

        return self._grant_lease(agent_id, desc.descriptor_hash, ts)

    def handle_message(self, message: AgentMessage, current_ts: Optional[float] = None) -> Optional[ActorLease]:
        """Dispatches an incoming agent message to the appropriate fabric handler."""
        ts = current_ts if current_ts is not None else time.time()
        if message.kind == AgentMessageKind.HEARTBEAT:
            return self.handle_heartbeat(message.sender_id, ts)
        elif message.kind == AgentMessageKind.ANNOUNCE:
            desc_data = message.payload.get("descriptor")
            if desc_data:
                desc = ActorDescriptor.from_dict(desc_data)
                agent = NetworkAgent(desc.actor_id, desc)
                return self.register_agent(agent, ts)
            return self.handle_heartbeat(message.sender_id, ts)
        return None

    def _grant_lease(self, actor_id: str, descriptor_hash: str, current_ts: float) -> ActorLease:
        lease = ActorLease(
            actor_id=actor_id,
            descriptor_hash=descriptor_hash,
            epoch=self.current_epoch,
            granted_at_ts=current_ts,
            expires_at_ts=current_ts + self.lease_ttl_sec,
            nonce=hashlib.sha256(f"{actor_id}:{self.current_epoch}:{current_ts}".encode("utf-8")).hexdigest()[:12],
        )
        self.active_leases[actor_id] = lease
        self.registry.update_status(actor_id, availability=True)
        return lease

    def reap_expired_leases(self, current_ts: float) -> Tuple[str, ...]:
        """Detects expired actor leases and marks actors offline."""
        expired = []
        for actor_id, lease in list(self.active_leases.items()):
            if not lease.is_valid(current_ts):
                expired.append(actor_id)
                del self.active_leases[actor_id]
                self.registry.update_status(actor_id, availability=False)
        return tuple(expired)

    def get_valid_lease(self, actor_id: str, current_ts: float) -> Optional[ActorLease]:
        lease = self.active_leases.get(actor_id)
        if lease and lease.is_valid(current_ts):
            return lease
        return None

    def has_valid_lease(self, actor_id: str, current_ts: float) -> bool:
        return self.get_valid_lease(actor_id, current_ts) is not None

    def qualify_actor(self, actor_id: str, required_authority: AuthorityClass) -> bool:
        """Strict qualification check separating discovery claims from authoritative trust.

        Discover(A) != Qualify(A, U)
        """
        actor = self.registry.get(actor_id)
        if actor is None or not actor.availability:
            return False

        # If only proposer-level compute is required, any valid leased actor qualifies
        if required_authority == AuthorityClass.PROPOSER_ONLY:
            return True

        # If verifier or authority quorum is required:
        # The actor MUST be explicitly present in the trusted authority keys
        if actor_id not in self.trusted_authority_keys:
            return False

        return actor.authority_class.satisfies(required_authority)
