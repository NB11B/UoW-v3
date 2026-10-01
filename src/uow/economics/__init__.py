"""UoW economics data plane observations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class CostObservation:
    """Carries economic observations as protocol data without enforcing pricing policy."""

    observation_id: str
    resource_type: str  # COMPUTE, HUMAN, ENERGY, RESOURCE, LATENCY, RECOVERY, MARKET
    metric_unit: str
    observed_cost: float
    spot_market_price: Optional[float] = None
    realization_overhead: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ResourceObservation:
    """Instantaneous capacity and scarcity telemetry from executing hosts."""

    host_id: str
    timestamp_epoch_ms: int
    available_cpu_cores: int
    available_ram_units: int
    available_gpu_slots: int = 0
    available_npu_slots: int = 0
    power_draw_watts: Optional[float] = None
    capacity_scarcity_ratio: Optional[float] = None


__all__ = ["CostObservation", "ResourceObservation"]
