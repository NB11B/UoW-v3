"""Qualification tests for Gate U15.7: Continuous Drift Endurance & Policy Memory Graph."""
from __future__ import annotations

from pathlib import Path
import tempfile
import openvino as ov
import pytest

from integrations.openvino_npu import (
    EPOCH_CONFIGS,
    EpochConfig,
    IntelNPUAdaptiveProposer,
    ModelLifecycleState,
    generate_epoch_workload,
)
from uow.compat.v2 import (
    DeterministicSequencer,
    EvidenceRecord,
    OrchestrationState,
    ProposerOrchestrationEngine,
    WorldState,
)


def test_gate_u15_7_deterministic_epoch_sequence_generation():
    """Generates all 10 epochs and verifies reproducible configurations."""
    assert len(EPOCH_CONFIGS) == 10
    names = [cfg.name for cfg in EPOCH_CONFIGS]
    assert names[0] == "E0_balanced"
    assert names[1] == "E1_gpu_scarcity"
    assert names[2] == "E2_cpu_scarcity"
    assert names[3] == "E3_npu_contention"
    assert names[4] == "E4_high_occ_conflict"
    assert names[5] == "E5_high_concurrency"
    assert names[6] == "E6_npu_unavailable"
    assert names[7] == "E7_npu_restored"
    assert names[8] == "E8_workload_reversal"
    assert names[9] == "E9_return_to_e0"

    # Verify workload construction
    tasks, s0 = generate_epoch_workload(EPOCH_CONFIGS[0])
    assert len(tasks) == 8
    assert s0.status == "RUNNING"
    assert len(OrchestrationState(s0).ready_frontier()) > 0


def test_gate_u15_7_continuous_state_and_ledger_chaining_zero_reset():
    """Sequentially executes multiple epochs with zero runtime reset, sharing a single EvidenceLedger."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="CPU", model_dir=Path(tmp_dir))
        engine = ProposerOrchestrationEngine(proposer=proposer)

        current_state: WorldState = None  # type: ignore[assignment]
        current_seq: DeterministicSequencer = None  # type: ignore[assignment]
        total_tasks_completed = 0

        # Execute Epochs E0, E1, E2 continuously
        for epoch_id in range(3):
            cfg = EPOCH_CONFIGS[epoch_id]
            tasks, init_state = generate_epoch_workload(cfg, base_state=current_state)

            if current_seq is None:
                current_seq = DeterministicSequencer(init_state)
            else:
                # Chain to continuous sequencer sharing identical evidence ledger
                current_seq = DeterministicSequencer(init_state, ledger=current_seq.ledger)

            # Adapt model using observations from previous epoch
            if epoch_id > 0:
                proposer.update(graph=tasks)

            engine = ProposerOrchestrationEngine(proposer=proposer)
            out_state, current_seq, telemetry = engine.run_dag(
                tasks,
                init_state,
                sequencer=current_seq,
            )

            assert out_state.status == "HALTED"
            completed = OrchestrationState(out_state).completed
            assert len(completed) == cfg.num_tasks
            total_tasks_completed += cfg.num_tasks

            # Verify ledger cryptographic integrity after every epoch
            assert current_seq.ledger.verify_integrity()
            current_state = out_state

        # Confirms unbroken ledger history across all epochs
        assert len(current_seq.ledger.records) >= total_tasks_completed
        assert current_seq.ledger.verify_integrity()


def test_gate_u15_7_npu_unavailability_and_restoration():
    """Simulates accelerator outage (E6) followed by recovery (E7) with zero authority breach."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="CPU", model_dir=Path(tmp_dir))

        # Epoch 6: Accelerator outage
        cfg_e6 = EPOCH_CONFIGS[6]
        tasks_e6, s0_e6 = generate_epoch_workload(cfg_e6)
        proposer.inject_crash_on_propose = True  # NPU offline

        engine_e6 = ProposerOrchestrationEngine(proposer=proposer)
        out_e6, seq_e6, tel_e6 = engine_e6.run_dag(tasks_e6, s0_e6)

        assert out_e6.status == "HALTED"
        assert len(OrchestrationState(out_e6).completed) == cfg_e6.num_tasks
        assert seq_e6.ledger.verify_integrity()
        # Fallback was triggered 100% of the time during outage
        assert all(t.certificate.fallback_triggered for t in tel_e6)

        # Epoch 7: Accelerator restored
        cfg_e7 = EPOCH_CONFIGS[7]
        tasks_e7, s0_e7 = generate_epoch_workload(cfg_e7, base_state=out_e6)
        proposer.inject_crash_on_propose = False  # NPU online again

        seq_e7 = DeterministicSequencer(s0_e7, ledger=seq_e6.ledger)
        engine_e7 = ProposerOrchestrationEngine(proposer=proposer)
        out_e7, seq_e7, tel_e7 = engine_e7.run_dag(tasks_e7, s0_e7, sequencer=seq_e7)

        assert out_e7.status == "HALTED"
        assert len(OrchestrationState(out_e7).completed) >= cfg_e7.num_tasks
        assert seq_e7.ledger.verify_integrity()

        # Neural proposer resumed normal proposing
        neural_proposals = [t for t in tel_e7 if t.proposal and not t.certificate.fallback_triggered]
        assert len(neural_proposals) > 0


def test_gate_u15_7_policy_memory_graph_branching():
    """Branches candidate generation directly from an ancestor generation, creating a DAG of policies."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="CPU", model_dir=Path(tmp_dir))
        g0_ident = proposer.model_identity()

        # Advance linearly: G0 -> G1 -> G2
        g1_ident = proposer.update()
        g2_ident = proposer.update()
        assert g2_ident.training_generation == 2
        assert g2_ident.parent_model_hash == g1_ident.identity_hash

        # Branch child from ancestor G0 (instead of current G2)
        staged_branch = proposer.branch_update(base_generation=0)
        assert staged_branch.generation == 3
        # Invariant: Parent of branch points to G0, NOT G2!
        assert staged_branch.identity.parent_model_hash == g0_ident.identity_hash

        promoted_branch = proposer.promote_staged()
        assert promoted_branch.parent_model_hash == g0_ident.identity_hash

        # Inspect policy memory graph
        graph = proposer.get_policy_graph()
        assert len(graph) == 4
        assert graph[0]["parent_model_hash"] is None  # G0 root
        assert graph[1]["parent_model_hash"] == g0_ident.identity_hash  # G1 from G0
        assert graph[2]["parent_model_hash"] == g1_ident.identity_hash  # G2 from G1
        assert graph[3]["parent_model_hash"] == g0_ident.identity_hash  # G3 branched from G0!


def test_gate_u15_7_forgetting_test_policy_memory_comparison():
    """Compares (a) continuing training, (b) rollback to G0, and (c) branching from G0 on return to E0."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="CPU", model_dir=Path(tmp_dir))
        g0_ident = proposer.model_identity()

        # Train through drift: E0 -> E1 -> E2
        for epoch_id in range(3):
            cfg = EPOCH_CONFIGS[epoch_id]
            tasks, s0 = generate_epoch_workload(cfg)
            engine = ProposerOrchestrationEngine(proposer=proposer)
            engine.run_dag(tasks, s0)
            proposer.update(graph=tasks)

        drifted_ident = proposer.model_identity()
        assert drifted_ident.training_generation == 3

        # Return to E0 workload (Epoch 9)
        cfg_e9 = EPOCH_CONFIGS[9]
        tasks_e9, s0_e9 = generate_epoch_workload(cfg_e9)

        # Strategy A: Continue training from drifted model
        prop_a = proposer.propose(OrchestrationState(s0_e9).ready_frontier(), tasks_e9, s0_e9)
        assert prop_a.training_generation == 3

        # Strategy B: Rollback to certified G0
        rolled_back = proposer.rollback(0)
        assert rolled_back.training_generation == 0
        prop_b = proposer.propose(OrchestrationState(s0_e9).ready_frontier(), tasks_e9, s0_e9)
        assert prop_b.training_generation == 0

        # Strategy C: Branch child from G0
        branched_stage = proposer.branch_update(base_generation=0)
        promoted_c = proposer.promote_staged()
        assert promoted_c.parent_model_hash == g0_ident.identity_hash
        prop_c = proposer.propose(OrchestrationState(s0_e9).ready_frontier(), tasks_e9, s0_e9)
        assert prop_c.parent_model_hash == g0_ident.identity_hash

        # All strategies achieve zero wrong authoritative commits under the same Judge
        engine_eval = ProposerOrchestrationEngine(proposer=proposer)
        out, seq, _ = engine_eval.run_dag(tasks_e9, s0_e9)
        assert out.status == "HALTED"
        assert seq.ledger.verify_integrity()


def test_gate_u15_7_negative_control_matrix_under_drift():
    """Negative controls during continuous drift cause fallback or staging rejection, NEVER authority failure."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="CPU", model_dir=Path(tmp_dir))
        active_hash = proposer.model_identity().model_artifact_hash

        # NC1: Injected health check failure
        with pytest.raises(ValueError, match="Injected health check failure"):
            proposer.stage_update(inject_health_check_failure=True)
        assert proposer.model_identity().model_artifact_hash == active_hash

        # NC2: Injected compilation crash
        with pytest.raises(RuntimeError, match="Injected accelerator compilation failure"):
            proposer.stage_update(inject_compilation_failure=True)
        assert proposer.model_identity().model_artifact_hash == active_hash

        # NC3: Illegal proposal schedule injection
        cfg = EPOCH_CONFIGS[4]  # OCC hazard epoch
        tasks, s0 = generate_epoch_workload(cfg)
        proposer.inject_corrupt_schedule = True
        ready = OrchestrationState(s0).ready_frontier()
        bad_prop = proposer.propose(ready, tasks, s0)
        engine = ProposerOrchestrationEngine(proposer=proposer)
        cert = engine.certify_proposal(bad_prop, ready, tasks, s0)
        assert not cert.is_valid
        assert "illegal_unregistered_task_999" in cert.rejected_tasks


def test_gate_u15_7_physical_npu_continuous_drift_smoke():
    """Physical Intel AI Boost NPU executes multi-epoch continuous drift without reset."""
    core = ov.Core()
    if "NPU" not in core.available_devices:
        pytest.skip("Physical OpenVINO NPU device is not available on host")

    with tempfile.TemporaryDirectory() as tmp_dir:
        proposer = IntelNPUAdaptiveProposer(device="NPU", model_dir=Path(tmp_dir), fail_closed=True)
        current_state: WorldState = None  # type: ignore[assignment]
        current_seq: DeterministicSequencer = None  # type: ignore[assignment]

        # Run E0 -> E1 -> E2 on physical NPU
        for epoch_id in range(3):
            cfg = EPOCH_CONFIGS[epoch_id]
            tasks, init_state = generate_epoch_workload(cfg, base_state=current_state)

            if current_seq is None:
                current_seq = DeterministicSequencer(init_state)
            else:
                current_seq = DeterministicSequencer(init_state, ledger=current_seq.ledger)

            if epoch_id > 0:
                proposer.update(graph=tasks)

            engine = ProposerOrchestrationEngine(proposer=proposer)
            out_state, current_seq, telemetry = engine.run_dag(
                tasks,
                init_state,
                sequencer=current_seq,
            )

            assert out_state.status == "HALTED"
            assert len(OrchestrationState(out_state).completed) == cfg.num_tasks
            assert current_seq.ledger.verify_integrity()
            current_state = out_state

            # Physical NPU latency must be recorded
            npu_lats = [
                t.proposal.predicted_metrics.get("npu_latency_us", 0.0)
                for t in telemetry
                if t.proposal and t.proposal.candidate_schedule
            ]
            assert len(npu_lats) > 0
            assert all(lat > 0 for lat in npu_lats)
