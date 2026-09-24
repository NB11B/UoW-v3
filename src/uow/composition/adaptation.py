"""Semantic state and evidence types for adaptive composition."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Mapping, Tuple


def canonical_json(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class CompositionRuntimeState:
    """Runtime state vector S_t representing current environmental conditions."""

    actor_availability: Mapping[str, bool]
    actor_loads: Mapping[str, float]
    actor_latencies: Mapping[str, float]
    actor_failure_counts: Mapping[str, int]
    active_graph_id: str
    queue_depth: int = 0
    network_latency_ms: float = 0.0
    state_hash: str = ""

    def __post_init__(self) -> None:
        if not self.state_hash:
            payload = {
                "availability": {k: self.actor_availability[k] for k in sorted(self.actor_availability.keys())},
                "loads": {k: f"{self.actor_loads[k]:.3f}" for k in sorted(self.actor_loads.keys())},
                "latencies": {k: f"{self.actor_latencies[k]:.1f}" for k in sorted(self.actor_latencies.keys())},
                "failures": {k: self.actor_failure_counts[k] for k in sorted(self.actor_failure_counts.keys())},
                "active_graph_id": self.active_graph_id,
                "queue_depth": self.queue_depth,
                "network_latency_ms": f"{self.network_latency_ms:.1f}",
            }
            digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
            object.__setattr__(self, "state_hash", digest)


@dataclass(frozen=True)
class GraphAdaptationObservation:
    """Certified observation from authority certifier and runtime execution."""

    observation_id: str
    parent_contract_id: str
    state_snapshot_hash: str
    proposed_graph_id: str
    proposed_strategy: str
    certification_outcome: str
    execution_status: str
    observed_latency_ms: float = 0.0
    violations: Tuple[str, ...] = ()
    timestamp_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


__all__ = [
    "CompositionRuntimeState",
    "GraphAdaptationObservation",
    "canonical_json",
]
