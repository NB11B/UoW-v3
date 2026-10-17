"""Typed Python SDK Models for UoW Capability Platform (WP09)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ClientWorkRequest:
    capability_id: str
    payload: Dict[str, Any]
    work_id: Optional[str] = None
    state_reference: str = "current"
    deadline_policy: str = "best_effort"


@dataclass
class ClientWorkResponse:
    work_id: str
    success: bool
    disposition: str
    action: Optional[str]
    bindings: Dict[str, Any] = field(default_factory=dict)
    certificate_id: Optional[str] = None
    audit_explanation: Optional[str] = None
    rejection_reason: Optional[str] = None
    total_latency_ms: float = 0.0


@dataclass
class NodeStatus:
    node_id: str
    node_type: str
    is_online: bool
    registered_capabilities_count: int
    ledger_height: int
    ledger_root_hash: str
