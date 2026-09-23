"""Qualification tests for Gate U15.5: Canonical OpenVINO NPU Adaptive Proposer."""
from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence, Tuple
import pytest

from integrations.openvino_npu import (
    CandidateFeatureEncoder,
    FEATURE_DIM,
    IntelNPUAdaptiveProposer,
    UoWSchedulingNet,
    export_and_hash_onnx,
)
from uow import (
    AdaptiveProposer,
    BaseProposer,
    DeterministicSequencer,
    Guard,
    GuardOp,
    ModelIdentity,
    ModelProposal,
    Mutation,
    MutationOp,
    OrchestrationState,
    PortableAdaptiveProposer,
    ProposalCertificate,
    ProposerOrchestrationEngine,
    ResourceBoundTask,
    ResourceRequirement,
    ResourceState,
    Route,
    WorldState,
    certify_proposal,
    create_initial_orchestration_state,
    make_resource_domain_task,
    set_authoritative_resource_state,
)


def create_npu_test_dag() -> Tuple[Mapping[str, ResourceBoundTask], WorldState]:
    """Heterogeneous DAG exercising CPU, GPU, and NPU resource bounds."""
    caps = {"cpu_cores": 8, "ram_units": 16, "gpu_slots": 2, "npu_slots": 2}
    res_state = ResourceState(capacities=caps)

    registry: Mapping[str, ResourceBoundTask] = {
        "cpu_task_1": make_resource_domain_task(
            "cpu_task_1",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "cpu_res", 1),))],
            ResourceRequirement(cpu_cores=2, ram_units=4, priority=1),
        ),
        "cpu_task_2": make_resource_domain_task(
            "cpu_task_2",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "cpu_res", 2),))],
            ResourceRequirement(cpu_cores=2, ram_units=4, priority=2),
        ),
        "gpu_task": make_resource_domain_task(
            "gpu_task",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "gpu_res", 10),))],
            ResourceRequirement(cpu_cores=1, ram_units=4, gpu_slots=1, priority=5),
        ),
        "npu_task": make_resource_domain_task(
            "npu_task",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "npu_res", 20),))],
            ResourceRequirement(cpu_cores=1, ram_units=4, npu_slots=1, priority=3),
        ),
        "io_task": make_resource_domain_task(
            "io_task",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "io_res", 30),))],
            ResourceRequirement(cpu_cores=1, ram_units=2, priority=4),
        ),
    }

    queue = ["cpu_task_1", "cpu_task_2", "gpu_task", "npu_task", "io_task"]
    init_base = create_initial_orchestration_state(
        queue=queue,
        dependencies={},
        attributes={"cpu_res": 0, "gpu_res": 0, "npu_res": 0, "io_res": 0},
    )
    init_state = set_authoritative_resource_state(init_base, res_state)
    return registry, init_state


# ===========================================================================
# Gate U15.5: Canonical OpenVINO Proposer Contract & Engine Execution
# ===========================================================================

def test_gate_u15_5_feature_encoder_determinism():
    """CandidateFeatureEncoder produces fixed-dimension deterministic float32 vectors."""
    registry, init_state = create_npu_test_dag()
    encoder = CandidateFeatureEncoder()

    v1 = encoder.encode("cpu_task_1", registry, init_state)
    v2 = encoder.encode("cpu_task_1", registry, init_state)

    assert v1.shape == (FEATURE_DIM,)
    assert v1.dtype.name == "float32"
    assert (v1 == v2).all(), "Feature encoding must be bitwise deterministic"


def test_gate_u15_5_proposer_protocol_and_lineage_binding():
    """IntelNPUAdaptiveProposer implements AdaptiveProposer with cryptographic lineage."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="CPU", model_dir=Path(tmp_dir))

        # Protocol conformance
        assert isinstance(proposer, AdaptiveProposer)
        assert isinstance(proposer, BaseProposer)
        assert not hasattr(proposer, "commit")
        assert not hasattr(proposer, "mutate_world")

        # Cryptographic lineage
        identity = proposer.model_identity()
        assert isinstance(identity, ModelIdentity)
        assert identity.training_generation == 0
        assert identity.parent_model_hash is None
        assert len(identity.model_artifact_hash) == 64
        assert identity.identity_hash != ""


def test_gate_u15_5_canonical_engine_execution_portable():
    """IntelNPUAdaptiveProposer executes within canonical ProposerOrchestrationEngine."""
    registry, init_state = create_npu_test_dag()

    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="CPU", model_dir=Path(tmp_dir))
        engine = ProposerOrchestrationEngine(proposer=proposer)

        terminal_state, seq, telemetry = engine.run_dag(registry, init_state)

        assert terminal_state.status == "HALTED"
        assert len(OrchestrationState(terminal_state).completed) == 5
        assert seq.ledger.verify_integrity()
        assert len(telemetry) > 0

        # Verify proposal bound to artifact hash and carries observational telemetry
        for t in telemetry:
            if t.proposal:
                assert t.proposal.model_artifact_hash == proposer.model_identity().model_artifact_hash
                assert "npu_latency_us" in t.proposal.predicted_metrics


def test_gate_u15_5_negative_control_crash_fallback():
    """Accelerator crash during propose() falls back cleanly to deterministic scheduler."""
    registry, init_state = create_npu_test_dag()

    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="CPU", model_dir=Path(tmp_dir))
        proposer.inject_crash_on_propose = True

        engine = ProposerOrchestrationEngine(proposer=proposer)
        out, seq, telemetry = engine.run_dag(registry, init_state)

        # Invariant: DAG completes 100% via fallback without data corruption
        assert out.status == "HALTED"
        assert len(OrchestrationState(out).completed) == 5
        assert seq.ledger.verify_integrity()
        assert all(t.certificate.fallback_triggered for t in telemetry)


def test_gate_u15_5_negative_control_illegal_candidate_rejection():
    """Corrupted proposal proposing illegal tasks is rejected by the fixed Judge."""
    registry, init_state = create_npu_test_dag()

    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="CPU", model_dir=Path(tmp_dir))
        proposer.inject_corrupt_schedule = True

        ready = OrchestrationState(init_state).ready_frontier()
        prop = proposer.propose(ready, registry, init_state)
        cert = certify_proposal(prop, ready, registry, init_state)

        assert not cert.is_valid
        assert "illegal_unregistered_task_999" in cert.rejected_tasks
        assert "UNKNOWN_TASK" in cert.rejected_tasks["illegal_unregistered_task_999"]


def test_gate_u15_5_proposer_swappability_authority_invariance():
    """Swapping between PortableAdaptiveProposer and IntelNPUAdaptiveProposer preserves authority."""
    registry, init_state = create_npu_test_dag()

    # Run 1: PortableAdaptiveProposer
    p1 = PortableAdaptiveProposer()
    e1 = ProposerOrchestrationEngine(proposer=p1)
    out1, seq1, _ = e1.run_dag(registry, init_state)

    # Run 2: IntelNPUAdaptiveProposer (CPU portable)
    with tempfile.TemporaryDirectory() as tmp_dir:
        p2 = IntelNPUAdaptiveProposer(device="CPU", model_dir=Path(tmp_dir))
        e2 = ProposerOrchestrationEngine(proposer=p2)
        out2, seq2, _ = e2.run_dag(registry, init_state)

        # Both achieve 100% valid completion under the same deterministic Judge
        assert out1.status == "HALTED" and len(OrchestrationState(out1).completed) == 5
        assert out2.status == "HALTED" and len(OrchestrationState(out2).completed) == 5
        assert seq1.ledger.verify_integrity()
        assert seq2.ledger.verify_integrity()


def test_gate_u15_5_physical_npu_execution():
    """Physical Intel AI Boost NPU executes canonical UoW proposal pipeline."""
    import openvino as ov
    core = ov.Core()
    if "NPU" not in core.available_devices:
        pytest.skip("Physical OpenVINO NPU device is not available on host")

    registry, init_state = create_npu_test_dag()

    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="NPU", model_dir=Path(tmp_dir), fail_closed=True)
        assert "Intel" in proposer.device_full_name or "AI Boost" in proposer.device_full_name or "NPU" in proposer.device_full_name

        engine = ProposerOrchestrationEngine(proposer=proposer)
        out, seq, telemetry = engine.run_dag(registry, init_state)

        assert out.status == "HALTED"
        assert len(OrchestrationState(out).completed) == 5
        assert seq.ledger.verify_integrity()

        # Confirm NPU latency was physically measured
        npu_latencies = [
            t.proposal.predicted_metrics.get("npu_latency_us", 0.0)
            for t in telemetry
            if t.proposal and t.proposal.candidate_schedule
        ]
        assert len(npu_latencies) > 0
        assert all(lat > 0.0 for lat in npu_latencies)

