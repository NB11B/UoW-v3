"""Data models and interfaces for the Universal Capability Registry."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.uow.protocol.v1 import (
    CapabilityDescriptor,
    CapabilityKind,
    QualificationStatus,
    compute_digest,
)


class CapabilityLifecycleState(str, Enum):
    REGISTERED = "registered"
    ACTIVE = "active"
    QUARANTINED = "quarantined"
    DEPRECATED = "deprecated"


@dataclass
class CapabilityRecord:
    """Live registry record for an installed capability."""
    descriptor: CapabilityDescriptor
    state: CapabilityLifecycleState = CapabilityLifecycleState.REGISTERED
    package_id: str = ""
    installed_at: float = 0.0
    quarantine_reason: Optional[str] = None
    # Concrete runtime references
    deterministic_handler: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
    artifact_path: Optional[Path] = None
    knowledge_payload: Optional[Dict[str, Any]] = None

    @property
    def capability_id(self) -> str:
        return self.descriptor.capability_id

    @property
    def version(self) -> str:
        return self.descriptor.version

    @property
    def kind(self) -> CapabilityKind:
        return self.descriptor.kind

    @property
    def is_invokable(self) -> bool:
        return (
            self.state == CapabilityLifecycleState.ACTIVE
            and self.descriptor.qualification_status != QualificationStatus.DISQUALIFIED
        )
