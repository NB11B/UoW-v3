"""
Continuous Drift Workload & Environment Generators (Gate U15.7).

Defines a 10-epoch deterministic sequence of oscillating environments:
E0: balanced CPU/GPU/NPU
E1: GPU scarcity
E2: CPU scarcity
E3: NPU contention
E4: high OCC conflict
E5: high concurrency
E6: NPU temporarily unavailable (fallback scheduler takeover)
E7: NPU restored (hardware inference resumed)
E8: workload mix reverses
E9: return to original distribution (forgetting test)

Supports continuous state and ledger chaining across all epochs with ZERO runtime reset.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import numpy as np

from uow import (
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    OrchestrationState,
    ResourceBoundTask,
    ResourceRequirement,
    ResourceState,
    Route,
    WorldState,
    create_initial_orchestration_state,
    make_resource_domain_task,
    set_authoritative_resource_state,
)


@dataclass(frozen=True)
class EpochConfig:
    epoch_id: int
    name: str
    description: str
    capacities: Mapping[str, int]
    num_tasks: int
    npu_unavailable: bool = False
    high_occ: bool = False
    inverted_mix: bool = False


EPOCH_CONFIGS: Tuple[EpochConfig, ...] = (
    EpochConfig(
        epoch_id=0,
        name="E0_balanced",
        description="Balanced CPU/GPU/NPU demands and standard capacities",
        capacities={"cpu_cores": 8, "ram_units": 16, "gpu_slots": 2, "npu_slots": 2},
        num_tasks=8,
    ),
    EpochConfig(
        epoch_id=1,
        name="E1_gpu_scarcity",
        description="Severe GPU constraint with high GPU demand competition",
        capacities={"cpu_cores": 8, "ram_units": 16, "gpu_slots": 1, "npu_slots": 2},
        num_tasks=8,
    ),
    EpochConfig(
        epoch_id=2,
        name="E2_cpu_scarcity",
        description="Severe CPU constraint with heavy CPU workloads",
        capacities={"cpu_cores": 2, "ram_units": 16, "gpu_slots": 2, "npu_slots": 2},
        num_tasks=8,
    ),
    EpochConfig(
        epoch_id=3,
        name="E3_npu_contention",
        description="Single NPU slot with competing accelerator tasks",
        capacities={"cpu_cores": 8, "ram_units": 16, "gpu_slots": 2, "npu_slots": 1},
        num_tasks=8,
    ),
    EpochConfig(
        epoch_id=4,
        name="E4_high_occ_conflict",
        description="Multiple concurrent tasks writing to shared hazard keys",
        capacities={"cpu_cores": 8, "ram_units": 16, "gpu_slots": 2, "npu_slots": 2},
        num_tasks=8,
        high_occ=True,
    ),
    EpochConfig(
        epoch_id=5,
        name="E5_high_concurrency",
        description="Wide frontier with expanded system capacities",
        capacities={"cpu_cores": 16, "ram_units": 32, "gpu_slots": 4, "npu_slots": 4},
        num_tasks=12,
    ),
    EpochConfig(
        epoch_id=6,
        name="E6_npu_unavailable",
        description="NPU accelerator offline; fallback scheduler preserves progress",
        capacities={"cpu_cores": 8, "ram_units": 16, "gpu_slots": 2, "npu_slots": 2},
        num_tasks=6,
        npu_unavailable=True,
    ),
    EpochConfig(
        epoch_id=7,
        name="E7_npu_restored",
        description="NPU accelerator restored online; hardware inference resumed",
        capacities={"cpu_cores": 8, "ram_units": 16, "gpu_slots": 2, "npu_slots": 2},
        num_tasks=8,
    ),
    EpochConfig(
        epoch_id=8,
        name="E8_workload_reversal",
        description="Workload profile inverted: high priority light tasks, deprioritized heavy compute",
        capacities={"cpu_cores": 8, "ram_units": 16, "gpu_slots": 2, "npu_slots": 2},
        num_tasks=8,
        inverted_mix=True,
    ),
    EpochConfig(
        epoch_id=9,
        name="E9_return_to_e0",
        description="Return to original balanced distribution (evaluates policy memory and forgetting)",
        capacities={"cpu_cores": 8, "ram_units": 16, "gpu_slots": 2, "npu_slots": 2},
        num_tasks=8,
    ),
)


def generate_epoch_workload(
    config: EpochConfig,
    base_state: Optional[WorldState] = None,
    seed: int = 42,
) -> Tuple[Mapping[str, ResourceBoundTask], WorldState]:
    """Generates tasks for an epoch and queues them into the continuous world state.

    If base_state is provided, the previous state attributes and sequence are preserved,
    preventing any runtime reset between epochs.
    """
    rng = np.random.default_rng(seed + config.epoch_id * 100)
    tasks: Dict[str, ResourceBoundTask] = {}
    task_ids = [f"ep{config.epoch_id}_t{i:02d}" for i in range(config.num_tasks)]
    dependencies: Dict[str, Sequence[str]] = {}

    prev_attrs = dict(base_state.attributes) if base_state is not None else {}
    attributes: Dict[str, Any] = dict(prev_attrs)

    for i, tid in enumerate(task_ids):
        # Dependencies: later tasks occasionally depend on earlier tasks in the epoch
        if i >= 3 and (i % 2 == 1):
            dependencies[tid] = (task_ids[i - 2],)

        # Resource demand shaping per epoch config
        if config.epoch_id == 1:  # GPU scarcity
            cpu_need = int(rng.integers(1, 3))
            ram_need = int(rng.integers(2, 6))
            gpu_need = 1  # Single GPU slot; tasks serialize on GPU
            npu_need = 0
            prio = int(rng.integers(1, 10))
        elif config.epoch_id == 2:  # CPU scarcity
            cpu_need = int(rng.choice([1, 2]))  # Max 2 CPU cores; tasks compete heavily on CPU
            ram_need = int(rng.integers(2, 6))
            gpu_need = 0
            npu_need = 0
            prio = int(rng.integers(1, 10))
        elif config.epoch_id == 3:  # NPU contention
            cpu_need = int(rng.integers(1, 3))
            ram_need = int(rng.integers(2, 6))
            gpu_need = 0
            npu_need = 1  # Single NPU slot; accelerator tasks serialize
            prio = int(rng.integers(1, 10))
        elif config.inverted_mix:  # Inverted priority/demand
            cpu_need = int(rng.integers(1, 3)) if (i % 2 == 0) else 4
            ram_need = int(rng.integers(2, 4))
            gpu_need = 1 if (i % 2 == 1) else 0
            npu_need = 1 if (i % 3 == 0) else 0
            prio = 1 if (cpu_need <= 2) else 10  # light tasks get top priority
        else:  # Balanced E0, E4, E5, E6, E7, E9
            cpu_need = int(rng.integers(1, 4))
            ram_need = int(rng.integers(2, 6))
            gpu_need = int(rng.integers(0, 2)) if (i % 2 == 0) else 0
            npu_need = int(rng.integers(0, 2)) if (i % 3 == 0) else 0
            prio = int(rng.integers(1, 10))

        # Clamp all demands to epoch capacities to prevent impossible resource requests
        cpu_need = max(1, min(cpu_need, config.capacities.get("cpu_cores", 8)))
        ram_need = max(1, min(ram_need, config.capacities.get("ram_units", 16)))
        gpu_need = min(gpu_need, config.capacities.get("gpu_slots", 0))
        npu_need = min(npu_need, config.capacities.get("npu_slots", 0))

        # OCC mutation targets
        if config.high_occ:
            # Shared write hazard keys inducing intra-batch OCC conflicts
            target_key = "shared_occ_alpha" if (i % 2 == 0) else "shared_occ_beta"
            mutations = (
                Mutation(MutationOp.ADD, target_key, 1),
                Mutation(MutationOp.SET, f"done_{tid}", 1),
            )
            attributes.setdefault(target_key, 0)
        else:
            mutations = (
                Mutation(MutationOp.ADD, f"counter_{tid}", 1),
                Mutation(MutationOp.SET, f"done_{tid}", 1),
            )
            attributes[f"counter_{tid}"] = 0

        attributes[f"done_{tid}"] = 0

        tasks[tid] = make_resource_domain_task(
            tid,
            [Route(Guard(GuardOp.ALWAYS), mutations)],
            ResourceRequirement(
                cpu_cores=cpu_need,
                ram_units=ram_need,
                gpu_slots=gpu_need,
                npu_slots=npu_need,
                priority=prio,
            ),
        )

    # Queue tasks into continuous WorldState
    init_state = create_initial_orchestration_state(
        queue=task_ids,
        dependencies=dependencies,
        attributes=attributes,
    )

    # Bind resource capacities for this epoch
    res_state = ResourceState(capacities=dict(config.capacities))
    init_state = set_authoritative_resource_state(init_state, res_state)

    if base_state is not None:
        # Preserve monotonic state sequence from previous epoch
        init_state = WorldState(
            attributes=dict(init_state.attributes),
            cursor=init_state.cursor,
            status=init_state.status,
            sequence=base_state.sequence,
        )

    return tasks, init_state
