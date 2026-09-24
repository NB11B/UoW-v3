"""Certified deterministic fallback scheduler for Gate U14.7."""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence, Tuple

from .resource_policies import BaseSchedulingPolicy, PriorityDeadlineSchedulingPolicy
from ...resources.requirement import ResourceBoundTask, ResourceRequirement
from ...resources.state import ResourceState, get_authoritative_resource_state
from ...state import WorldState


class DeterministicFallbackScheduler:
    """Certified deterministic fallback scheduler (Gate U14.7).

    The deterministic fallback provides a certified deterministic schedule whenever
    a legal ready task exists; correctness does not depend on proposer availability.
    Engages whenever a model proposer crashes, times out, or emits an empty or
    fully rejected candidate schedule.
    """

    def __init__(self, policy: Optional[BaseSchedulingPolicy] = None) -> None:
        self.policy = policy or PriorityDeadlineSchedulingPolicy()

    def fallback_schedule(
        self,
        ready_candidates: Sequence[str],
        graph: Mapping[str, Any],
        state: WorldState,
    ) -> Tuple[str, ...]:
        """Calculates a strictly legal, deterministic candidate schedule from ready tasks."""
        def get_req(cid: str) -> ResourceRequirement:
            item = graph[cid]
            if isinstance(item, ResourceBoundTask):
                return item.requirement
            req = getattr(item, "resources", None)
            if isinstance(req, ResourceRequirement):
                return req
            return ResourceRequirement()

        res_state: ResourceState = get_authoritative_resource_state(state)
        chosen = self.policy.select_schedule(ready_candidates, get_req, res_state)
        return tuple(chosen)
