"""Pluggable resource-aware scheduling heuristics.

Enforces Legality Dominance:
Policy choices propose candidate schedules, but only candidates that satisfy
available resource capacities (leased and consumable) may be selected.

These policies are greedy heuristics:
- FIFOSchedulingPolicy: preserves arrival order
- GreedyCapacitySchedulingPolicy: greedy heuristic favoring smaller footprints
- PriorityDeadlineSchedulingPolicy: heuristic prioritizing urgent deadlines and priorities with anti-starvation aging
- CostEnergySchedulingPolicy: heuristic prioritizing lower cost and energy consumption
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, List, Mapping, Optional, Sequence, Tuple

from ...resources.requirement import ResourceRequirement
from ...resources.state import ResourceState


class BaseSchedulingPolicy(ABC):
    """Abstract interface for pluggable scheduler proposal policies."""

    @abstractmethod
    def name(self) -> str:
        """Human-readable policy name."""
        ...

    @abstractmethod
    def select_schedule(
        self,
        ready_candidates: Sequence[str],
        get_requirement: Callable[[str], ResourceRequirement],
        resources: ResourceState,
    ) -> List[str]:
        """Proposes a subset of ready_candidates to dispatch under resource state R_t.

        INVARIANT (Legality Dominance):
        Selected subset S must satisfy sum_{u in S} rho(u) <= R_t^avail.
        """
        ...


def filter_feasible_candidates(
    candidates: Sequence[str],
    get_requirement: Callable[[str], ResourceRequirement],
    available_res: ResourceState,
) -> List[str]:
    """Greedily selects candidates from the ordered list that fit simultaneously in available resources."""
    selected: List[str] = []
    sim_res = available_res

    for cid in candidates:
        req = get_requirement(cid)
        if sim_res.can_accommodate(req):
            sim_res, _ = sim_res.acquire_lease(cid, req, sequence=0)
            selected.append(cid)

    return selected


class FIFOSchedulingPolicy(BaseSchedulingPolicy):
    """First-In, First-Out proposal heuristic respecting available resource capacities."""

    def name(self) -> str:
        return "FIFO"

    def select_schedule(
        self,
        ready_candidates: Sequence[str],
        get_requirement: Callable[[str], ResourceRequirement],
        resources: ResourceState,
    ) -> List[str]:
        return filter_feasible_candidates(ready_candidates, get_requirement, resources)


class GreedyCapacitySchedulingPolicy(BaseSchedulingPolicy):
    """Greedy packing heuristic prioritizing tasks with smaller resource footprints."""

    def name(self) -> str:
        return "GreedyCapacityPacking"

    def select_schedule(
        self,
        ready_candidates: Sequence[str],
        get_requirement: Callable[[str], ResourceRequirement],
        resources: ResourceState,
    ) -> List[str]:
        def footprint(cid: str) -> int:
            req = get_requirement(cid)
            return req.cpu_cores + req.ram_units + (req.gpu_slots * 4) + (req.npu_slots * 2)

        sorted_candidates = sorted(ready_candidates, key=footprint)
        return filter_feasible_candidates(sorted_candidates, get_requirement, resources)


class PriorityDeadlineSchedulingPolicy(BaseSchedulingPolicy):
    """Priority and deadline ordering heuristic with dynamic anti-starvation aging."""

    def __init__(self, starvation_threshold: int = 3) -> None:
        self.starvation_threshold = starvation_threshold

    def name(self) -> str:
        return f"PriorityDeadlineAging(starvation_threshold={self.starvation_threshold})"

    def select_schedule(
        self,
        ready_candidates: Sequence[str],
        get_requirement: Callable[[str], ResourceRequirement],
        resources: ResourceState,
    ) -> List[str]:
        starving_set = set(resources.get_starving_tasks(self.starvation_threshold))

        def sort_key(cid: str) -> Tuple[int, int, int]:
            req = get_requirement(cid)
            # 1. Starving tasks are boosted to urgency rank 0
            starvation_boost = 0 if cid in starving_set else 1
            # 2. Priority (lower number = higher priority)
            pri = req.priority
            # 3. Deadline (earlier deadline first; None treated as infinity)
            dl = req.deadline if req.deadline is not None else 10**9
            return (starvation_boost, pri, dl)

        sorted_candidates = sorted(ready_candidates, key=sort_key)
        return filter_feasible_candidates(sorted_candidates, get_requirement, resources)


class CostEnergySchedulingPolicy(BaseSchedulingPolicy):
    """Heuristic preference prioritizing lower financial cost and consumable energy consumption."""

    def name(self) -> str:
        return "CostEnergyPreference"

    def select_schedule(
        self,
        ready_candidates: Sequence[str],
        get_requirement: Callable[[str], ResourceRequirement],
        resources: ResourceState,
    ) -> List[str]:
        def cost_energy_score(cid: str) -> Tuple[float, int]:
            req = get_requirement(cid)
            return (req.cost, req.energy_budget)

        sorted_candidates = sorted(ready_candidates, key=cost_energy_score)
        return filter_feasible_candidates(sorted_candidates, get_requirement, resources)
