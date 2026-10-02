"""UoW economics data plane observations and measurement semantics.

Governing Principles:
    1. Cost Observation != Pricing Decision
    2. Production Cost != Market Price != Consumer Value
    3. Economic Optimizer Proposes -> UoW Authority Certifies -> State Changes
    4. C(u) = C_H + C_M + C_E + C_R + C_K + C_D
    5. C(U) = sum_i C(U_i) + C_composition
    6. C_F = C_observed - C*
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

# Core Atomic Economics
from .atomic_cost import (
    AtomicCost,
    CostObservationRecord,
    compute_cost_evidence_hash,
)
from .composition import (
    CompositionCostProfile,
)
from .friction import (
    FrictionAnalysis,
)
from .boundary import (
    EconomicProposal,
    EconomicAdmissionResult,
    evaluate_economic_proposal,
)


# Legacy / Telemetry Data Plane shims for backward compatibility
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


__all__ = [
    # Atomic Cost Models
    "AtomicCost",
    "CostObservationRecord",
    "compute_cost_evidence_hash",
    "CompositionCostProfile",
    "FrictionAnalysis",
    "EconomicProposal",
    "EconomicAdmissionResult",
    "evaluate_economic_proposal",
    # Legacy Telemetry
    "CostObservation",
    "ResourceObservation",
]
