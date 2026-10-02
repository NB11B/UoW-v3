"""Separation of operational friction from necessary thermodynamic/computational work.

Core Formula:
    C_F = C_observed - C*
where:
    C_observed = Total observed production cost
    C*         = Minimal necessary work bound to effect the state transition
    C_F        = Operational and coordination friction (retries, lock waits, idle time)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping

from .atomic_cost import AtomicCost


@dataclass(frozen=True)
class FrictionAnalysis:
    """Isolates operational friction from fundamental work costs."""

    observed_cost: AtomicCost
    necessary_cost: AtomicCost

    @property
    def friction_cost(self) -> AtomicCost:
        """Calculate friction C_F = C_observed - C*."""
        return self.observed_cost.friction_against(self.necessary_cost)

    def is_friction_non_negative(self, tolerance: float = 1e-6) -> bool:
        """Verify that observed cost is at least the necessary minimal bound."""
        fc = self.friction_cost
        return (
            fc.c_h >= -tolerance
            and fc.c_m >= -tolerance
            and fc.c_e >= -tolerance
            and fc.c_r >= -tolerance
            and fc.c_k >= -tolerance
            and fc.c_d >= -tolerance
        )

    def friction_ratio(self) -> float:
        """Proportion of observed expenditure attributable to friction: C_F / C_observed."""
        obs_total = self.observed_cost.total()
        if obs_total <= 0.0:
            return 0.0
        return round(max(0.0, self.friction_cost.total()) / obs_total, 6)

    def work_efficiency(self) -> float:
        """Work efficiency ratio: C* / C_observed (1.0 = frictionless execution)."""
        obs_total = self.observed_cost.total()
        if obs_total <= 0.0:
            return 1.0
        return round(min(1.0, max(0.0, self.necessary_cost.total() / obs_total)), 6)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observed_cost": self.observed_cost.to_dict(),
            "necessary_cost": self.necessary_cost.to_dict(),
            "friction_cost": self.friction_cost.to_dict(),
            "friction_ratio": self.friction_ratio(),
            "work_efficiency": self.work_efficiency(),
            "is_non_negative": self.is_friction_non_negative(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FrictionAnalysis":
        return cls(
            observed_cost=AtomicCost.from_dict(data["observed_cost"]),
            necessary_cost=AtomicCost.from_dict(data["necessary_cost"]),
        )
