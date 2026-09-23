"""Physical actor binding and validation for Campaign A2.

Binds logical realization graph nodes to qualified physical or logical actors,
verifying capabilities and authority constraints prior to task dispatch.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping, Tuple

from uow.composition.actor import ActorRegistry, AuthorityClass
from uow.composition.graph import RealizationGraph


def canonical_json(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ActorBinding:
    """Explicit mapping from logical graph nodes to physical actor identifiers."""

    binding_id: str
    graph_id: str
    node_to_actor: Mapping[str, str]  # node_id -> actor_id
    binding_hash: str = ""

    def __post_init__(self) -> None:
        if not self.binding_hash:
            payload = {
                "binding_id": self.binding_id,
                "graph_id": self.graph_id,
                "node_to_actor": {k: self.node_to_actor[k] for k in sorted(self.node_to_actor.keys())},
            }
            digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
            object.__setattr__(self, "binding_hash", digest)

    def compute_hash(self) -> str:
        return self.binding_hash


def validate_binding(
    graph: RealizationGraph,
    binding: ActorBinding,
    registry: ActorRegistry,
) -> Tuple[bool, Tuple[str, ...]]:
    """Validates that all nodes in a graph are bound to qualified, available actors."""
    violations = []

    if binding.graph_id != graph.graph_id:
        violations.append(
            f"BINDING_GRAPH_ID_MISMATCH: binding targets {binding.graph_id!r}, graph is {graph.graph_id!r}"
        )

    for node_id, node in graph.nodes.items():
        if node_id not in binding.node_to_actor:
            violations.append(f"UNBOUND_NODE: node {node_id!r} has no assigned actor in binding")
            continue

        actor_id = binding.node_to_actor[node_id]
        actor = registry.get(actor_id)
        if actor is None:
            violations.append(f"UNKNOWN_ACTOR: node {node_id!r} references unregistered actor {actor_id!r}")
            continue

        if not actor.availability:
            violations.append(f"ACTOR_UNAVAILABLE: actor {actor_id!r} bound to node {node_id!r} is offline")

        # Capability check
        if node.required_capabilities:
            if not actor.has_capabilities(node.required_capabilities):
                missing = set(node.required_capabilities) - set(actor.capabilities)
                violations.append(
                    f"ACTOR_CAPABILITY_DEFICIT: actor {actor_id!r} lacks required capabilities {sorted(missing)} for node {node_id!r}"
                )

        # Authority hierarchy check
        try:
            req_auth = AuthorityClass(node.required_authority_class)
            if not actor.authority_class.satisfies(req_auth):
                violations.append(
                    f"ACTOR_AUTHORITY_INSUFFICIENT: actor {actor_id!r} has class {actor.authority_class.value}, but node {node_id!r} requires {req_auth.value}"
                )
        except ValueError:
            violations.append(f"INVALID_NODE_AUTHORITY_CLASS: {node.required_authority_class!r}")

    return len(violations) == 0, tuple(violations)
