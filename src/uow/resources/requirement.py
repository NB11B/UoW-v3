"""Typed resource envelope declared by a Unit of Work."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional


@dataclass(frozen=True)
class ResourceRequirement:
    """Typed resource envelope rho(U_i) declaring requirements, limits, and priorities."""

    cpu_cores: int = 1
    ram_units: int = 1
    gpu_slots: int = 0
    npu_slots: int = 0
    energy_budget: int = 0
    duration_est: int = 1
    deadline: Optional[int] = None
    priority: int = 10  # Lower number = higher priority (1 is urgent, 10 is default)
    cost: float = 0.0

    def allocations_dict(self) -> Dict[str, int]:
        allocs: Dict[str, int] = {}
        if self.cpu_cores > 0:
            allocs["cpu_cores"] = self.cpu_cores
        if self.ram_units > 0:
            allocs["ram_units"] = self.ram_units
        if self.gpu_slots > 0:
            allocs["gpu_slots"] = self.gpu_slots
        if self.npu_slots > 0:
            allocs["npu_slots"] = self.npu_slots
        if self.energy_budget > 0:
            allocs["energy_budget"] = self.energy_budget
        return allocs

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_cores": self.cpu_cores,
            "ram_units": self.ram_units,
            "gpu_slots": self.gpu_slots,
            "npu_slots": self.npu_slots,
            "energy_budget": self.energy_budget,
            "duration_est": self.duration_est,
            "deadline": self.deadline,
            "priority": self.priority,
            "cost": self.cost,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ResourceRequirement:
        return cls(
            cpu_cores=int(d.get("cpu_cores", 1)),
            ram_units=int(d.get("ram_units", 1)),
            gpu_slots=int(d.get("gpu_slots", 0)),
            npu_slots=int(d.get("npu_slots", 0)),
            energy_budget=int(d.get("energy_budget", 0)),
            duration_est=int(d.get("duration_est", 1)),
            deadline=int(d["deadline"]) if d.get("deadline") is not None else None,
            priority=int(d.get("priority", 10)),
            cost=float(d.get("cost", 0.0)),
        )
