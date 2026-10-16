"""Capability Magazine Specification & Schema (uow.magazine.v1).

Defines the immutable manifest data model, lifecycle states, and integrity constraints
for domain-specialist weight adapters within the Unit-of-Work (UoW) ecosystem.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional
import json


class AdapterLifecycleState(str, Enum):
    """Formal lifecycle states for weight magazine adapters."""
    REGISTERED = "REGISTERED"      # Manifest exists in registry, not yet cryptographically verified
    VERIFIED = "VERIFIED"          # Cryptographic SHA-256 and compatibility verified, eligible for load
    LOADED = "LOADED"              # Resident in memory pool, inactive
    ACTIVE = "ACTIVE"              # Currently assigned to inference engine for active transaction
    EVICTED = "EVICTED"            # Unloaded from memory pool due to LRU or resource policy
    QUARANTINED = "QUARANTINED"    # Verification or execution failure; prohibited from execution


@dataclass(frozen=True)
class TrainingLineage:
    """Provenance and lineage of how the adapter weights were produced."""
    base_model_name: str
    base_model_revision: str
    training_dataset_id: str
    training_dataset_sha256: str
    epochs: int
    learning_rate: float
    rank: int
    alpha: int
    target_modules: list[str]
    timestamp_utc: str
    compiler_version: str = "uow.compiler.v1"


@dataclass(frozen=True)
class CapabilityManifest:
    """Immutable manifest for an adapter entry in the uow.magazine.v1 specification."""
    manifest_version: str = "uow.magazine.v1"
    adapter_id: str = ""
    domain: str = ""
    grammar: str = ""
    version: str = "1.0.0"
    foundation_model: str = ""
    foundation_revision: str = ""
    adapter_sha256: str = ""
    weight_size_bytes: int = 0
    target_schema: str = ""
    target_modules: list[str] = field(default_factory=list)
    rank: int = 8
    alpha: int = 16
    lineage: Optional[TrainingLineage] = None
    tested_capabilities: list[str] = field(default_factory=list)
    known_failures: list[str] = field(default_factory=list)
    authority_limitations: list[str] = field(default_factory=list)
    extra_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CapabilityManifest:
        lineage_data = data.get("lineage")
        lineage = TrainingLineage(**lineage_data) if lineage_data and isinstance(lineage_data, dict) else lineage_data
        copied = dict(data)
        copied["lineage"] = lineage
        return cls(**copied)

    @classmethod
    def from_json(cls, json_str: str) -> CapabilityManifest:
        return cls.from_dict(json.loads(json_str))
