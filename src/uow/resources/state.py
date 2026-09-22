"""Authoritative resource state, capacity tracking, and atomic certified leases."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .requirement import ResourceRequirement

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
    """Authoritative resource state R_t maintaining capacities, allocations, and active leases."""

    capacities: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_HOST_CAPACITIES))
    allocated: Mapping[str, int] = field(default_factory=lambda: {k: 0 for k in DEFAULT_HOST_CAPACITIES})
    leases: Tuple[ResourceLease, ...] = ()
    starvation_counters: Mapping[str, int] = field(default_factory=dict)

    def available(self, res: str) -> int:
        return self.capacities.get(res, 0) - self.allocated.get(res, 0)

    def can_accommodate(self, req: ResourceRequirement) -> bool:
        allocs = req.allocations_dict()
        for res, amount in allocs.items():
            if self.available(res) < amount:
                return False
        return True

    def acquire_lease(
        self,
        uow_id: str,
        req: ResourceRequirement,
        sequence: int,
        epoch: int = 0,
    ) -> Tuple["ResourceState", ResourceLease]:
        allocs = req.allocations_dict()
        for res, amount in allocs.items():
            avail = self.available(res)
            if avail < amount:
                raise ValueError(
                    f"Resource over-allocation rejected on '{res}': requested {amount}, available {avail}"
                )

        new_allocated = dict(self.allocated)
        for res, amount in allocs.items():
            new_allocated[res] = new_allocated.get(res, 0) + amount

        lease_id = f"LEASE_{uow_id}_{sequence}"
        lease = ResourceLease(
            lease_id=lease_id,
            uow_id=uow_id,
            allocations=allocs,
            epoch=epoch,
            granted_sequence=sequence,
        )
        new_leases = tuple(list(self.leases) + [lease])

        # Reset starvation counter for this task
        new_starv = dict(self.starvation_counters)
        new_starv.pop(uow_id, None)

        return (
            replace(self, allocated=new_allocated, leases=new_leases, starvation_counters=new_starv),
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
