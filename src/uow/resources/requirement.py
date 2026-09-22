"""Typed resource envelope and work-bound task abstractions."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..contracts import (
    Contract,
    Header,
    Route,
    Successor,
    SuccessorKind,
    UoW,
)
from ..ontology import MatrixCell, WorkCategory
from ..orchestration import COMPLETION_PREFIX, TASK_CELL
from ..state import canonical_json


@dataclass(frozen=True)
class ResourceRequirement:
    """Typed resource envelope rho(U_i) declaring leased capacities and consumable budgets.

    Leased capacities:
    - cpu_cores, ram_units, gpu_slots, npu_slots (returned upon completion)

    Consumable budgets:
    - energy_budget, cost (debited permanently upon dispatch)
    """

    cpu_cores: int = 1
    ram_units: int = 1
    gpu_slots: int = 0
    npu_slots: int = 0
    energy_budget: int = 0
    duration_est: int = 1
    deadline: Optional[int] = None
    priority: int = 10  # Lower number = higher priority (1 is urgent, 10 is default)
    cost: float = 0.0

    def leased_allocations_dict(self) -> Dict[str, int]:
        """Returns allocations for leased resources that return upon task completion."""
        allocs: Dict[str, int] = {}
        if self.cpu_cores > 0:
            allocs["cpu_cores"] = self.cpu_cores
        if self.ram_units > 0:
            allocs["ram_units"] = self.ram_units
        if self.gpu_slots > 0:
            allocs["gpu_slots"] = self.gpu_slots
        if self.npu_slots > 0:
            allocs["npu_slots"] = self.npu_slots
        return allocs

    def consumable_budgets_dict(self) -> Dict[str, float]:
        """Returns allocations for consumable budgets that are debited permanently."""
        consumable: Dict[str, float] = {}
        if self.energy_budget > 0:
            consumable["energy_budget"] = float(self.energy_budget)
        if self.cost > 0.0:
            consumable["cost"] = float(self.cost)
        return consumable

    def allocations_dict(self) -> Dict[str, int]:
        """Backward-compatible map of all integer allocations."""
        allocs = self.leased_allocations_dict()
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


@dataclass(frozen=True)
class ResourceBoundTask:
    """A domain task whose ResourceRequirement is cryptographically bound into its contract."""

    uow: UoW
    requirement: ResourceRequirement

    @property
    def requirement_hash(self) -> str:
        return hashlib.sha256(canonical_json(self.requirement.to_dict()).encode("utf-8")).hexdigest()

    def verify_binding(self) -> bool:
        """Verifies that the UoW header cryptographically binds this requirement."""
        return self.uow.H.parent_context == f"req:{self.requirement_hash}"


def verify_requirement_binding(task: ResourceBoundTask) -> bool:
    """Explicit invariant check preventing forged registry requirements."""
    return task.verify_binding()


def make_resource_domain_task(
    identity: str,
    routes: Sequence[Route],
    requirement: ResourceRequirement,
    *,
    matrix_cell: MatrixCell = TASK_CELL,
) -> ResourceBoundTask:
    """Constructs a domain task with cryptographically bound resource requirements."""
    wrapped_routes: List[Route] = []
    for route in routes:
        successor = (
            Successor.static(f"{COMPLETION_PREFIX}{identity}")
            if route.successor.kind is SuccessorKind.HALT
            else route.successor
        )
        wrapped_routes.append(
            Route(
                guard=route.guard,
                mutations=route.mutations,
                successor=successor,
            )
        )

    req_hash = hashlib.sha256(canonical_json(requirement.to_dict()).encode("utf-8")).hexdigest()
    uow = UoW(
        H=Header(
            identity=identity,
            source_category=matrix_cell.source,
            target_category=matrix_cell.target,
            layer="domain",
            parent_context=f"req:{req_hash}",
        ),
        Gamma=Contract(tuple(wrapped_routes)),
    )
    uow.validate()
    return ResourceBoundTask(uow=uow, requirement=requirement)
