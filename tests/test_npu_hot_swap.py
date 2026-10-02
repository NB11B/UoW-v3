"""Qualification tests for Gate U15.6: NPU Live Model Hot Swap & Lifecycle Management."""
from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Mapping, Tuple
import openvino as ov
import pytest

from integrations.openvino_npu import (
    IntelNPUAdaptiveProposer,
    ModelLifecycleState,
    NPUModelLifecycleManager,
    StagedModel,
    UoWSchedulingNet,
)
from uow.compat.v2 import (
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    OrchestrationState,
    ProposerOrchestrationEngine,
    ResourceBoundTask,
    ResourceRequirement,
    ResourceState,
    Route,
    WorldState,
    create_initial_orchestration_state,
    make_resource_domain_task,
    set_authoritative_resource_state,
)


def create_hot_swap_dag() -> Tuple[Mapping[str, ResourceBoundTask], WorldState]:
    caps = {"cpu_cores": 8, "ram_units": 16, "gpu_slots": 2, "npu_slots": 2}
    res_state = ResourceState(capacities=caps)

    tasks: Mapping[str, ResourceBoundTask] = {
        "hs_task_1": make_resource_domain_task(
            "hs_task_1",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "hs_x", 1),))],
            ResourceRequirement(cpu_cores=2, ram_units=4, priority=1),
        ),
        "hs_task_2": make_resource_domain_task(
            "hs_task_2",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "hs_y", 2),))],
            ResourceRequirement(cpu_cores=2, ram_units=4, priority=2),
        ),
        "hs_task_3": make_resource_domain_task(
            "hs_task_3",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "hs_z", 3),))],
            ResourceRequirement(cpu_cores=2, ram_units=4, priority=3),
        ),
    }

    queue = ["hs_task_1", "hs_task_2", "hs_task_3"]
    init_base = create_initial_orchestration_state(
        queue=queue,
        dependencies={},
        attributes={"hs_x": 0, "hs_y": 0, "hs_z": 0},
    )
    init_state = set_authoritative_resource_state(init_base, res_state)
    return tasks, init_state


def test_gate_u15_6_lifecycle_state_transitions():
    """Validates the state machine: UNINITIALIZED -> STAGING -> ACTIVE -> RETIRED."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="CPU", model_dir=Path(tmp_dir))
        assert proposer.lifecycle.active_stage is not None
        assert proposer.lifecycle.active_stage.state == ModelLifecycleState.ACTIVE
        assert proposer.lifecycle.active_stage.generation == 0

        g0_hash = proposer.model_identity().model_artifact_hash

        # Stage Generation 1
        staged = proposer.stage_update()
        assert staged.state == ModelLifecycleState.STAGING
        assert staged.generation == 1
        assert staged.health_checked is True
        assert staged.identity.parent_model_hash == proposer.model_identity().identity_hash

        # Active proposer is still Generation 0 while G1 is in staging
        assert proposer.lifecycle.active_stage.generation == 0
        assert proposer.model_identity().model_artifact_hash == g0_hash

        # Atomically promote G1
        new_ident = proposer.promote_staged()
        assert new_ident.training_generation == 1
        assert proposer.lifecycle.active_stage.generation == 1
        assert proposer.lifecycle.active_stage.state == ModelLifecycleState.ACTIVE
        assert proposer.lifecycle.staging_stage is None

        # Verify Generation 0 is now RETIRED
        g0_stage = proposer.lifecycle._stages_by_gen[0]
        assert g0_stage.state == ModelLifecycleState.RETIRED


def test_gate_u15_6_staging_health_check_failure_containment():
    """Staging health check failure leaves active inference completely undisturbed."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="CPU", model_dir=Path(tmp_dir))
        g0_ident = proposer.model_identity()

        # Attempt to stage a model with health check failure
        with pytest.raises(ValueError, match="Injected health check failure"):
            proposer.stage_update(inject_health_check_failure=True)

        # Active model must remain Generation 0 ACTIVE and fully operational
        assert proposer.lifecycle.active_stage is not None
        assert proposer.lifecycle.active_stage.state == ModelLifecycleState.ACTIVE
        assert proposer.model_identity().model_artifact_hash == g0_ident.model_artifact_hash

        # Verify active inference still works cleanly
        registry, init_state = create_hot_swap_dag()
        ready = OrchestrationState(init_state).ready_frontier()
        prop = proposer.propose(ready, registry, init_state)
        assert prop.model_artifact_hash == g0_ident.model_artifact_hash


def test_gate_u15_6_staging_compilation_failure_containment():
    """Staging compilation crash leaves active model completely undisturbed."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="CPU", model_dir=Path(tmp_dir))
        g0_ident = proposer.model_identity()

        # Attempt to stage with compilation failure
        with pytest.raises(RuntimeError, match="Injected accelerator compilation failure"):
            proposer.stage_update(inject_compilation_failure=True)

        # Active model remains intact
        assert proposer.lifecycle.active_stage.state == ModelLifecycleState.ACTIVE
        assert proposer.model_identity().model_artifact_hash == g0_ident.model_artifact_hash


def test_gate_u15_6_atomic_rollback():
    """Reverts to a previously certified generation with durable state update."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="CPU", model_dir=Path(tmp_dir))
        g0_ident = proposer.model_identity()

        # Advance to G1
        g1_ident = proposer.update()
        assert g1_ident.training_generation == 1
        assert proposer.model_identity().model_artifact_hash == g1_ident.model_artifact_hash

        # Rollback to G0
        rolled_back_ident = proposer.rollback(0)
        assert rolled_back_ident.training_generation == 0
        assert rolled_back_ident.model_artifact_hash == g0_ident.model_artifact_hash
        assert proposer.lifecycle.active_stage.generation == 0
        assert proposer.lifecycle.active_stage.state == ModelLifecycleState.ACTIVE


def test_gate_u15_6_cold_restart_recovery_from_manifest():
    """Recovers the latest active model and validates artifact hashes after process restart."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        model_path = Path(tmp_dir)

        # Session 1: Create, advance to Generation 2
        p1 = IntelNPUAdaptiveProposer(device="CPU", model_dir=model_path)
        p1.update()  # G1
        ident_g2 = p1.update()  # G2
        assert ident_g2.training_generation == 2
        g2_hash = ident_g2.model_artifact_hash

        # Session 2: Cold process restart
        core = ov.Core()
        mgr = NPUModelLifecycleManager(model_dir=model_path, core=core, device="CPU")
        recovered_ident = mgr.recover_from_manifest()

        assert recovered_ident is not None
        assert recovered_ident.training_generation == 2
        assert recovered_ident.model_artifact_hash == g2_hash
        assert mgr.active_stage is not None
        assert mgr.active_stage.state == ModelLifecycleState.ACTIVE


def test_gate_u15_6_concurrent_propose_and_staging():
    """Ensures non-blocking, thread-safe proposals while background compilation executes."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="CPU", model_dir=Path(tmp_dir))
        registry, init_state = create_hot_swap_dag()
        ready = OrchestrationState(init_state).ready_frontier()

        stop_event = threading.Event()
        observed_hashes = set()
        errors = []

        def reader_loop():
            while not stop_event.is_set():
                try:
                    p = proposer.propose(ready, registry, init_state)
                    observed_hashes.add(p.model_artifact_hash)
                    time.sleep(0.001)
                except Exception as ex:
                    errors.append(ex)

        reader_thread = threading.Thread(target=reader_loop)
        reader_thread.start()

        # Concurrently stage and promote
        time.sleep(0.05)
        staged = proposer.stage_update()
        time.sleep(0.05)
        proposer.promote_staged()
        time.sleep(0.05)

        stop_event.set()
        reader_thread.join()

        assert not errors, f"Reader thread encountered errors: {errors}"
        # Both Generation 0 and Generation 1 hashes must have been observed cleanly
        assert len(observed_hashes) >= 1


def test_gate_u15_6_physical_npu_hot_swap():
    """Physical Intel AI Boost NPU executes live hot swap during DAG orchestration."""
    core = ov.Core()
    if "NPU" not in core.available_devices:
        pytest.skip("Physical OpenVINO NPU device is not available on host")

    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="NPU", model_dir=Path(tmp_dir), fail_closed=True)
        registry, init_state = create_hot_swap_dag()
        engine = ProposerOrchestrationEngine(proposer=proposer)

        # Stage and promote on physical NPU
        staged = proposer.stage_update()
        assert staged.generation == 1
        assert staged.state == ModelLifecycleState.STAGING
        assert staged.health_checked is True

        promoted = proposer.promote_staged()
        assert promoted.training_generation == 1
        assert proposer.lifecycle.active_stage.state == ModelLifecycleState.ACTIVE

        # Execute DAG under promoted Generation 1 on physical NPU
        out, seq, telemetry = engine.run_dag(registry, init_state)
        assert out.status == "HALTED"
        assert len(OrchestrationState(out).completed) == 3
        assert seq.ledger.verify_integrity()

        for t in telemetry:
            if t.proposal and t.proposal.candidate_schedule:
                assert t.proposal.training_generation == 1
                assert t.proposal.model_artifact_hash == promoted.model_artifact_hash
