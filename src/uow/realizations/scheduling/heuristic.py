"""Reference heuristic scheduling proposer implementations (Gate U14.9, U14.10)."""
from __future__ import annotations

from typing import Any, List, Mapping, Optional, Sequence, Tuple

from ...resources.requirement import ResourceBoundTask, ResourceRequirement
from ...resources.state import ResourceState, get_authoritative_resource_state
from ...state import WorldState
from ...transactions.descriptor import infer_footprint
from ...proposer.base import BaseProposer
from ...proposer.types import ModelProposal


class HeuristicSchedulingProposer(BaseProposer):
    """Reference heuristic scheduling proposer.

    Optimizes candidate selection using greedy priority ranking, deadline sensitivity,
    multidimensional bin-packing, and intra-batch OCC hazard avoidance. Emits candidate
    schedules with predicted duration and energy metrics.

    Note: This is a reference scheduling heuristic for proposal generation. It possesses
    zero state authority; all proposals must be certified by the deterministic Judge.
    External learned or hardware-accelerated runtimes (e.g. TFWR / NPU) plug in via
    BaseProposer (see integrations/tfwr/adapter.py).
    """

    def __init__(
        self,
        model_id: str = "ReferenceHeuristicScheduler",
        model_version: str = "1.0.0-heuristic",
    ) -> None:
        self._model_id = model_id
        self._version = model_version

    def model_id(self) -> str:
        return self._model_id

    def model_version(self) -> str:
        return self._version

    def propose(
        self,
        ready_candidates: Sequence[str],
        graph: Mapping[str, Any],
        state: WorldState,
    ) -> ModelProposal:
        # Heuristic ranking: priority (lower = higher priority), deadline, and resource footprint
        def heuristic_rank(task_id: str) -> Tuple[int, int, int]:
            item = graph[task_id]
            req: Optional[ResourceRequirement] = (
                item.requirement if isinstance(item, ResourceBoundTask)
                else getattr(item, "resources", None)
            )
            if req is None:
                return (10, 10**6, 1)
            dl = req.deadline if req.deadline is not None else 10**6
            footprint = req.cpu_cores + req.ram_units + (req.gpu_slots * 4) + (req.npu_slots * 2)
            return (req.priority, dl, footprint)

        sorted_candidates = sorted(ready_candidates, key=heuristic_rank)

        # Packing candidates against available capacity and transaction footprints
        sim_res: ResourceState = get_authoritative_resource_state(state)
        chosen: List[str] = []
        batch_writes: set[str] = set()
        batch_reads: set[str] = set()
        est_duration = 0.0
        est_energy = 0.0

        for cid in sorted_candidates:
            item = graph[cid]
            uow = item.uow if isinstance(item, ResourceBoundTask) else item
            try:
                _idx, route = uow.Gamma.select_route(state)
                r_set, w_set = infer_footprint(route)
            except Exception:
                r_set, w_set = (), ()

            # Skip candidates that would trigger OCC read/write or write/write hazards in this batch
            if any(w in batch_writes or w in batch_reads for w in w_set):
                continue
            if any(r in batch_writes for r in r_set):
                continue

            req = item.requirement if isinstance(item, ResourceBoundTask) else getattr(item, "resources", None)
            if req is not None:
                if sim_res.can_accommodate(req):
                    sim_res, _ = sim_res.acquire_lease(cid, req, sequence=state.sequence)
                    chosen.append(cid)
                    batch_writes.update(w_set)
                    batch_reads.update(r_set)
                    est_duration = max(est_duration, float(req.duration_est))
                    est_energy += float(req.energy_budget)
            else:
                chosen.append(cid)
                batch_writes.update(w_set)
                batch_reads.update(r_set)

        return ModelProposal(
            model_id=self.model_id(),
            model_version=self.model_version(),
            input_state_hash=state.state_hash,
            input_sequence=state.sequence,
            input_epoch=state.sequence,
            candidate_schedule=tuple(chosen),
            predicted_metrics={
                "predicted_duration": est_duration,
                "predicted_energy": est_energy,
                "confidence": 0.99,
            },
            metadata={"heuristic": "greedy_capacity_occ", "reference": True},
        )


ReferenceSchedulingProposer = HeuristicSchedulingProposer
