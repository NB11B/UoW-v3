"""Authoritative resource state, capacity tracking, and atomic certified leases."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..state import WorldState
from .requirement import ResourceRequirement

ORCH_RESOURCES_KEY = "__resources__"

DEFAULT_HOST_CAPACITIES: Mapping[str, int] = {
    "cpu_cores": 1000,
    "ram_units": 1000,
    "gpu_slots": 100,
    "npu_slots": 100,
    "energy_budget": 100000,
}


@dataclass(frozen=True)
class ResourceLease:
    """Certified deterministic resource lease: L = (lease_id, uow_id, allocations, epoch, sequence)."""

    lease_id: str
    uow_id: str
    allocations: Mapping[str, int]
    epoch: int
    granted_sequence: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "uow_id": self.uow_id,
            "allocations": dict(self.allocations),
            "epoch": self.epoch,
            "granted_sequence": self.granted_sequence,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ResourceLease:
        return cls(
            lease_id=str(d["lease_id"]),
            uow_id=str(d["uow_id"]),
            allocations={k: int(v) for k, v in d.get("allocations", {}).items()},
            epoch=int(d.get("epoch", 0)),
            granted_sequence=int(d.get("granted_sequence", 0)),
        )


@dataclass(frozen=True)
class ResourceState:
    """Authoritative resource state R_t maintaining capacities, allocations, and active leases.

    Distinguishes:
    - Leased capacities: temporarily held, returned on task completion.
    - Consumable budgets: debited permanently upon dispatch.
    """

    capacities: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_HOST_CAPACITIES))
    allocated: Mapping[str, int] = field(default_factory=lambda: {k: 0 for k in DEFAULT_HOST_CAPACITIES})
    leases: Tuple[ResourceLease, ...] = ()
    starvation_counters: Mapping[str, int] = field(default_factory=dict)

    def available(self, res: str) -> int:
        return self.capacities.get(res, 0) - self.allocated.get(res, 0)

    def can_accommodate(self, req: ResourceRequirement) -> bool:
        # Check leased capacities
        for res, amount in req.leased_allocations_dict().items():
            if self.available(res) < amount:
                return False
        # Check consumable budgets
        for budget_key, amount in req.consumable_budgets_dict().items():
            if self.available(budget_key) < int(amount):
                return False
        return True

    def acquire_lease(
        self,
        uow_id: str,
        req: ResourceRequirement,
        sequence: int,
        epoch: int = 0,
    ) -> Tuple["ResourceState", ResourceLease]:
        """Atomically acquires a certified lease for leased resources and debits consumable budgets."""
        leased_allocs = req.leased_allocations_dict()
        for res, amount in leased_allocs.items():
            avail = self.available(res)
            if avail < amount:
                raise ValueError(
                    f"Resource over-allocation rejected on '{res}': requested {amount}, available {avail}"
                )

        consumables = req.consumable_budgets_dict()
        for budget_key, amount in consumables.items():
            avail = self.available(budget_key)
            if avail < int(amount):
                raise ValueError(
                    f"Consumable budget exhausted on '{budget_key}': requested {amount}, available {avail}"
                )

        # Allocate leased capacities
        new_allocated = dict(self.allocated)
        for res, amount in leased_allocs.items():
            new_allocated[res] = new_allocated.get(res, 0) + amount

        # Debit consumable budgets permanently from capacity
        new_capacities = dict(self.capacities)
        for budget_key, amount in consumables.items():
            new_capacities[budget_key] = max(0, new_capacities.get(budget_key, 0) - int(amount))

        lease_id = f"LEASE_{uow_id}_{sequence}"
        lease = ResourceLease(
            lease_id=lease_id,
            uow_id=uow_id,
            allocations=leased_allocs,
            epoch=epoch,
            granted_sequence=sequence,
        )
        new_leases = tuple(list(self.leases) + [lease])

        # Reset starvation counter for this task
        new_starv = dict(self.starvation_counters)
        new_starv.pop(uow_id, None)

        return (
            replace(
                self,
                capacities=new_capacities,
                allocated=new_allocated,
                leases=new_leases,
                starvation_counters=new_starv,
            ),
            lease,
        )

    def release_lease(self, uow_id_or_lease_id: str) -> "ResourceState":
        matching = [
            l for l in self.leases if l.uow_id == uow_id_or_lease_id or l.lease_id == uow_id_or_lease_id
        ]
        if not matching:
            return self

        lease_to_release = matching[0]
        new_allocated = dict(self.allocated)
        for res, amount in lease_to_release.allocations.items():
            new_allocated[res] = max(0, new_allocated.get(res, 0) - amount)

        new_leases = tuple(l for l in self.leases if l.lease_id != lease_to_release.lease_id)
        return replace(self, allocated=new_allocated, leases=new_leases)

    def record_starvation(self, blocked_ready_uows: Sequence[str]) -> "ResourceState":
        new_starv = dict(self.starvation_counters)
        for u in blocked_ready_uows:
            new_starv[u] = new_starv.get(u, 0) + 1
        return replace(self, starvation_counters=new_starv)

    def get_starving_tasks(self, threshold: int = 3) -> List[str]:
        return [u for u, count in self.starvation_counters.items() if count >= threshold]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capacities": dict(self.capacities),
            "allocated": dict(self.allocated),
            "leases": [l.to_dict() for l in self.leases],
            "starvation_counters": dict(self.starvation_counters),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ResourceState:
        leases = tuple(ResourceLease.from_dict(l) for l in d.get("leases", []))
        return cls(
            capacities={k: int(v) for k, v in d.get("capacities", {}).items()},
            allocated={k: int(v) for k, v in d.get("allocated", {}).items()},
            leases=leases,
            starvation_counters={k: int(v) for k, v in d.get("starvation_counters", {}).items()},
        )


def get_authoritative_resource_state(state: WorldState) -> ResourceState:
    """Extracts the authoritative ResourceState from state.__resources__."""
    raw = state.get(ORCH_RESOURCES_KEY)
    if raw is None or not isinstance(raw, Mapping):
        raise KeyError("Authoritative resource state '__resources__' not present in WorldState.")
    return ResourceState.from_dict(raw)


def set_authoritative_resource_state(state: WorldState, res: ResourceState) -> WorldState:
    """Binds ResourceState into WorldState attributes, automatically binding into state_hash."""
    return state.with_attribute(ORCH_RESOURCES_KEY, res.to_dict())
