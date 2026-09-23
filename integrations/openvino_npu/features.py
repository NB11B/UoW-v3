"""Deterministic feature encoding for ready UoW candidate tasks (Gate U15.5)."""
from __future__ import annotations

from typing import Any, Mapping, Sequence, Tuple
import numpy as np

from uow.contracts import UoW
from uow.orchestration.state import OrchestrationState
from uow.resources.requirement import ResourceBoundTask, ResourceRequirement
from uow.resources.state import ResourceState, get_authoritative_resource_state
from uow.state import WorldState
from uow.transactions.descriptor import infer_footprint

FEATURE_DIM: int = 14


class CandidateFeatureEncoder:
    """Encodes a candidate UoW and the current world state into a fixed-dimension vector.

    Feature vector schema (dim = 14, dtype = float32):
        [0]: normalized priority
        [1]: CPU demand / 8.0
        [2]: RAM demand / 16.0
        [3]: GPU demand / 2.0
        [4]: NPU demand / 2.0
        [5]: estimated duration / 100.0
        [6]: read footprint count / 10.0
        [7]: write footprint count / 10.0
        [8]: host available CPU / 8.0
        [9]: host available RAM / 16.0
        [10]: host available GPU / 2.0
        [11]: host available NPU / 2.0
        [12]: currently active task count / 8.0
        [13]: ready frontier candidate count / 8.0

    Deterministic, platform-invariant, non-authoritative.
    """

    def __init__(self, feature_dim: int = FEATURE_DIM) -> None:
        self.feature_dim = feature_dim

    def encode(
        self,
        task_id: str,
        graph: Mapping[str, Any],
        state: WorldState,
        ready_frontier: Sequence[str] = (),
    ) -> np.ndarray:
        """Produces a 1D float32 numpy vector of length feature_dim."""
        item = graph.get(task_id)
        req: Optional[ResourceRequirement] = None
        uow: Optional[UoW] = None

        if isinstance(item, ResourceBoundTask):
            req = item.requirement
            uow = item.uow
        elif hasattr(item, "requirement"):
            req = getattr(item, "requirement")
            uow = getattr(item, "uow", None)
        elif hasattr(item, "resources"):
            req = getattr(item, "resources")
            uow = getattr(item, "uow", None)
        elif isinstance(item, UoW):
            uow = item

        # 1. Task demand features
        priority = float(req.priority) if req else 1.0
        cpu_demand = float(req.cpu_cores) if req else 0.0
        ram_demand = float(req.ram_units) if req else 0.0
        gpu_demand = float(req.gpu_slots) if req else 0.0
        npu_demand = float(req.npu_slots) if req else 0.0
        duration_est = float(req.duration_est) if req else 1.0

        # 2. Footprint features
        read_count = 0.0
        write_count = 0.0
        if uow is not None and hasattr(uow, "Gamma"):
            try:
                _, route = uow.Gamma.select_route(state)
                r_set, w_set = infer_footprint(route)
                read_count = float(len(r_set))
                write_count = float(len(w_set))
            except Exception:
                pass

        # 3. Host availability features
        avail_cpu = 8.0
        avail_ram = 16.0
        avail_gpu = 1.0
        avail_npu = 2.0
        try:
            res_state: ResourceState = get_authoritative_resource_state(state)
            avail_map = res_state.available_capacities()
            avail_cpu = float(avail_map.get("cpu_cores", 8.0))
            avail_ram = float(avail_map.get("ram_units", 16.0))
            avail_gpu = float(avail_map.get("gpu_slots", 1.0))
            avail_npu = float(avail_map.get("npu_slots", 2.0))
        except Exception:
            pass

        # 4. Context features
        active_count = 0.0
        frontier_count = float(len(ready_frontier)) if ready_frontier else 1.0
        if state is not None:
            try:
                orch = OrchestrationState(state)
                active_count = float(len(orch.active))
            except Exception:
                pass

        vec = np.array(
            [
                min(1.0, max(0.0, (priority - 1.0) / 10.0)),
                min(2.0, max(0.0, cpu_demand / 8.0)),
                min(2.0, max(0.0, ram_demand / 16.0)),
                min(2.0, max(0.0, gpu_demand / 2.0)),
                min(2.0, max(0.0, npu_demand / 2.0)),
                min(1.0, max(0.0, duration_est / 100.0)),
                min(1.0, max(0.0, read_count / 10.0)),
                min(1.0, max(0.0, write_count / 10.0)),
                min(2.0, max(0.0, avail_cpu / 8.0)),
                min(2.0, max(0.0, avail_ram / 16.0)),
                min(2.0, max(0.0, avail_gpu / 2.0)),
                min(2.0, max(0.0, avail_npu / 2.0)),
                min(1.0, max(0.0, active_count / 8.0)),
                min(1.0, max(0.0, frontier_count / 8.0)),
            ],
            dtype=np.float32,
        )
        return vec
