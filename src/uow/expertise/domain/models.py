"""Domain Package Schema and Metadata Models (WP04).

Decouples domain knowledge (entities, operations, parameters, safety guards)
from neural weight memorization.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from uow.protocol.v1 import canonical_json, compute_digest


@dataclass(frozen=True)
class EntityDefinition:
    """Authoritative domain entity specification."""
    entity_id: str
    entity_type: str
    allowed_states: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SafetyGuard:
    """Authoritative safety boundary condition."""
    guard_id: str
    parameter: str
    condition: str  # e.g., "max_value:200.0", "min_value:0.0", "regex:^[A-Z0-9_-]+$"
    threshold: Any
    severity: str = "CRITICAL"


@dataclass(frozen=True)
class ActionDefinition:
    """Authoritative operation definition in domain catalog."""
    action_name: str
    required_parameters: List[str]
    optional_parameters: List[str] = field(default_factory=list)
    applicable_entity_types: List[str] = field(default_factory=list)
    safety_guards: List[SafetyGuard] = field(default_factory=list)


@dataclass
class DomainPackage:
    """Complete domain ontology package."""
    domain_id: str
    version: str
    name: str
    description: str
    entities: Dict[str, EntityDefinition] = field(default_factory=dict)
    actions: Dict[str, ActionDefinition] = field(default_factory=dict)
    aliases: Dict[str, str] = field(default_factory=dict)  # alias -> canonical entity_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "entities": {k: v.__dict__ for k, v in self.entities.items()},
            "actions": {
                k: {
                    "action_name": v.action_name,
                    "required_parameters": v.required_parameters,
                    "optional_parameters": v.optional_parameters,
                    "applicable_entity_types": v.applicable_entity_types,
                    "safety_guards": [g.__dict__ for g in v.safety_guards],
                }
                for k, v in self.actions.items()
            },
            "aliases": self.aliases,
        }

    def digest(self) -> str:
        return compute_digest(self.to_dict())

    def resolve_entity(self, ref: str) -> Optional[str]:
        """Resolve entity identifier or alias to canonical ID."""
        if ref in self.entities:
            return ref
        return self.aliases.get(ref)
