"""Recursive composition cost accounting for Unit-of-Work trees.

Core Invariant:
    C(U) = sum_i C(U_i) + C_composition
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence

from .atomic_cost import AtomicCost, CostObservationRecord


@dataclass(frozen=True)
class CompositionCostProfile:
    """Evaluates cost conservation across recursively composed UoW hierarchies.

    Formula:
        C(U_composite) = sum_i(C(U_i)) + C_composition
    """

    parent_uow_id: str
    child_costs: Sequence[AtomicCost]
    composition_overhead: AtomicCost = field(default_factory=AtomicCost)

    def total_child_cost(self) -> AtomicCost:
        """Sum of all constituent child UoW costs."""
        currency = self.composition_overhead.currency
        if self.child_costs:
            currency = self.child_costs[0].currency

        total = AtomicCost(currency=currency)
        for child in self.child_costs:
            total = total + child
        return total

    def compute_total_composite_cost(self) -> AtomicCost:
        """Compute the preserved total composite cost including composition overhead."""
        return self.total_child_cost() + self.composition_overhead

    def verify_conservation(
        self,
        observed_composite: AtomicCost,
        tolerance: float = 1e-6,
    ) -> bool:
        """Verify that observed composite cost strictly matches sum(children) + overhead."""
        expected = self.compute_total_composite_cost()
        if expected.currency != observed_composite.currency:
            return False

        dims = ["c_h", "c_m", "c_e", "c_r", "c_k", "c_d"]
        for dim in dims:
            diff = abs(getattr(expected, dim) - getattr(observed_composite, dim))
            if diff > tolerance:
                return False

        return abs(expected.total() - observed_composite.total()) <= tolerance

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parent_uow_id": self.parent_uow_id,
            "child_costs": [c.to_dict() for c in self.child_costs],
            "composition_overhead": self.composition_overhead.to_dict(),
            "total_child_cost": self.total_child_cost().to_dict(),
            "composite_total": self.compute_total_composite_cost().to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CompositionCostProfile":
        return cls(
            parent_uow_id=str(data["parent_uow_id"]),
            child_costs=[AtomicCost.from_dict(c) for c in data["child_costs"]],
            composition_overhead=AtomicCost.from_dict(
                data.get("composition_overhead", {})
            ),
        )
