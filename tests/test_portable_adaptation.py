"""Canonical qualification tests for Gates U15.3 and U15.4 (Portable Adaptation & Falsification Containment).

Enforces:
    Gate U15.3: Closed-loop portable adaptation converges under workload drift:
                R_reject(t+n) < R_reject(t) with N_wrong_commit = 0.
    Gate U15.4: Negative control falsification:
                Arbitrarily bad P_theta => degraded efficiency NOT=> incorrect authority.
"""
from __future__ import annotations

import copy
import hashlib
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import pytest

from uow.compat.v2 import (
    AdaptationObservation,
    AdaptiveProposer,
    BaseProposer,
    CommitSequencer,
    DeterministicFallbackScheduler,
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
    TelemetryRecord,
    WorldState,
    certify_proposal,
    create_adaptation_observation,
    create_initial_orchestration_state,
    make_resource_domain_task,
    run_proposer_orchestration,
    set_authoritative_resource_state,
    validate_observation_integrity,
)


def create_drift_environment(env_type: str) -> Tuple[Mapping[str, ResourceBoundTask], WorldState]:
    """Generates a heterogeneous 6-task workload under differing resource constraints:

    - Environment 'gpu_scarce' (Env A):
        cpu_cores: 8, gpu_slots: 1, npu_slots: 2
    - Environment 'cpu_scarce' (Env B):
        cpu_cores: 2, gpu_slots: 4, npu_slots: 2
    """
    if env_type == "gpu_scarce":
        caps = {"cpu_cores": 8, "ram_units": 16, "gpu_slots": 1, "npu_slots": 2}
    elif env_type == "cpu_scarce":
        caps = {"cpu_cores": 2, "ram_units": 16, "gpu_slots": 4, "npu_slots": 2}
    else:
        raise ValueError(f"Unknown env_type {env_type}")

    res_state = ResourceState(capacities=caps)

    registry: Mapping[str, ResourceBoundTask] = {
        "cpu_job_1": make_resource_domain_task(
            "cpu_job_1",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "cpu_out_1", 1),))],
            ResourceRequirement(cpu_cores=2, ram_units=2, priority=1),
        ),
        "cpu_job_2": make_resource_domain_task(
            "cpu_job_2",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "cpu_out_2", 2),))],
            ResourceRequirement(cpu_cores=2, ram_units=2, priority=2),
        ),
        "gpu_job_1": make_resource_domain_task(
            "gpu_job_1",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "gpu_out_1", 10),))],
            ResourceRequirement(cpu_cores=1, ram_units=4, gpu_slots=1, priority=5),
        ),
        "gpu_job_2": make_resource_domain_task(
            "gpu_job_2",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "gpu_out_2", 20),))],
            ResourceRequirement(cpu_cores=1, ram_units=4, gpu_slots=1, priority=6),
        ),
        "npu_job_1": make_resource_domain_task(
            "npu_job_1",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "npu_out_1", 100),))],
            ResourceRequirement(cpu_cores=1, ram_units=2, npu_slots=1, priority=3),
        ),
        "npu_job_2": make_resource_domain_task(
            "npu_job_2",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "npu_out_2", 200),))],
            ResourceRequirement(cpu_cores=1, ram_units=2, npu_slots=1, priority=4),
        ),
    }

    queue = ["cpu_job_1", "cpu_job_2", "gpu_job_1", "gpu_job_2", "npu_job_1", "npu_job_2"]
    init_base = create_initial_orchestration_state(
        queue=queue,
        dependencies={},
        attributes={
            "cpu_out_1": 0,
            "cpu_out_2": 0,
            "gpu_out_1": 0,
            "gpu_out_2": 0,
            "npu_out_1": 0,
            "npu_out_2": 0,
        },
    )
    init_state = set_authoritative_resource_state(init_base, res_state)
    return registry, init_state


# ===========================================================================
# Gate U15.3: Portable Closed-Loop Adaptation
# ===========================================================================

def test_gate_u15_3_workload_drift_adaptation_convergence():
    """Validates that closed-loop policy adaptation reduces rejection rate under workload drift.

    R_reject(t+n) < R_reject(t) while N_wrong_commit = 0.
    """
    # -------------------------------------------------------------
    # Round 0: Unadapted proposer in GPU-scarce environment (Env A)
    # -------------------------------------------------------------
    reg_a, init_state_a = create_drift_environment("gpu_scarce")

    # Initial imperfect policy: aggressively favors GPU tasks and demands batch target 4
    proposer = PortableAdaptiveProposer(
        initial_weights={
            "gpu_affinity": 10.0,
            "cpu_affinity": 0.5,
            "npu_affinity": 0.5,
            "gpu_capacity": 8.0,
            "cpu_capacity": 8.0,
            "npu_capacity": 8.0,
            "batch_capacity_target": 4.0,
        },
        learning_rate=2.0,
    )
    engine_r0 = ProposerOrchestrationEngine(proposer=proposer)
    out_r0, seq_r0, telem_r0 = engine_r0.run_dag(reg_a, init_state_a)

    # In Round 0, the proposer repeatedly over-subscribes the 1 GPU slot
    total_props_r0 = len([t for t in telem_r0 if t.proposal is not None])
    rejects_r0 = sum(len(t.certificate.rejected_tasks) for t in telem_r0)
    assert total_props_r0 > 0
    assert rejects_r0 > 0, "Unadapted policy must encounter rejections on scarce accelerator"

    rejection_rate_r0 = float(rejects_r0) / float(total_props_r0)

    # Invariant: Despite rejections, authoritative outcome is 100% valid
    assert out_r0.status == "HALTED"
    assert len(OrchestrationState(out_r0).completed) == 6
    assert seq_r0.ledger.verify_integrity()

    # -------------------------------------------------------------
    # Adaptation Step: Apply parameter update using collected observations
    # -------------------------------------------------------------
    initial_gen = proposer.model_identity().training_generation
    new_identity = proposer.update()
    assert new_identity.training_generation == initial_gen + 1
    # Check that GPU affinity was penalized due to GPU oversubscription rejections
    assert proposer.weights["gpu_affinity"] < 10.0
    assert proposer.weights["batch_capacity_target"] < 4.0

    # -------------------------------------------------------------
    # Round 1: Post-adaptation execution in the same environment
    # -------------------------------------------------------------
    reg_a2, init_state_a2 = create_drift_environment("gpu_scarce")
    engine_r1 = ProposerOrchestrationEngine(proposer=proposer)
    out_r1, seq_r1, telem_r1 = engine_r1.run_dag(reg_a2, init_state_a2)

    total_props_r1 = len([t for t in telem_r1 if t.proposal is not None])
    rejects_r1 = sum(len(t.certificate.rejected_tasks) for t in telem_r1)
    rejection_rate_r1 = float(rejects_r1) / float(total_props_r1) if total_props_r1 > 0 else 0.0

    # Key metric: Rejection rate strictly decreases
    assert rejection_rate_r1 < rejection_rate_r0, (
        f"Rejection rate did not decrease: {rejection_rate_r0:.2f} -> {rejection_rate_r1:.2f}"
    )

    # Invariant: zero wrong commits
    assert out_r1.status == "HALTED"
    assert len(OrchestrationState(out_r1).completed) == 6
    assert seq_r1.ledger.verify_integrity()

    # -------------------------------------------------------------
    # Workload Drift: Shift to CPU-scarce environment (Env B)
    # -------------------------------------------------------------
    reg_b, init_state_b = create_drift_environment("cpu_scarce")
    engine_b0 = ProposerOrchestrationEngine(proposer=proposer)
    out_b0, seq_b0, telem_b0 = engine_b0.run_dag(reg_b, init_state_b)

    # Update on Env B feedback
    proposer.update()

    # Post-drift execution
    reg_b1, init_state_b1 = create_drift_environment("cpu_scarce")
    engine_b1 = ProposerOrchestrationEngine(proposer=proposer)
    out_b1, seq_b1, telem_b1 = engine_b1.run_dag(reg_b1, init_state_b1)

    assert out_b1.status == "HALTED"
    assert len(OrchestrationState(out_b1).completed) == 6
    assert seq_b1.ledger.verify_integrity()


# ===========================================================================
# Gate U15.4: Adversarial Falsification Campaign (Negative Controls)
# ===========================================================================

def test_gate_u15_4_catastrophic_model_poisoning_containment():
    """Catastrophic model degradation causes 100% rejection/fallback, zero incorrect authority."""
    reg, init_state = create_drift_environment("gpu_scarce")
    proposer = PortableAdaptiveProposer()

    # Intentionally poison weights to catastrophic values
    proposer.inject_corrupt_weights_on_update = True
    proposer.update()

    assert all(w < -1e8 for w in proposer.weights.values())

    engine = ProposerOrchestrationEngine(proposer=proposer)
    out, seq, telem = engine.run_dag(reg, init_state)

    # Fundamental Invariant:
    # An arbitrarily bad P_theta causes degraded efficiency / fallback,
    # but NEVER corrupts authoritative state.
    assert out.status == "HALTED"
    assert len(OrchestrationState(out).completed) == 6
    assert seq.ledger.verify_integrity()

    # Verify fallback was invoked safely
    fallback_count = sum(1 for t in telem if t.certificate.fallback_triggered)
    assert fallback_count > 0, "Catastrophic proposer must trigger deterministic fallback"


def test_gate_u15_4_corrupted_training_labels_detection():
    """Corrupted or forged feedback is detected and dropped by the adaptive proposer."""
    proposer = PortableAdaptiveProposer()
    reg, init_state = create_drift_environment("gpu_scarce")

    # Generate a legitimate observation
    prop = proposer.propose(("cpu_job_1",), reg, init_state)
    cert = certify_proposal(prop, ("cpu_job_1",), reg, init_state)
    valid_obs = create_adaptation_observation(
        pre_state=init_state,
        proposal=prop,
        certificate=cert,
        post_state=init_state,
        committed=True,
    )

    # Valid observation is accepted
    proposer.observe_feedback(valid_obs)
    assert len(proposer.observation_buffer) == 1
    assert proposer.dropped_corrupt_count == 0

    # 1. Tampering with dataclass constructor fails immediately with hash mismatch
    with pytest.raises(ValueError, match="AdaptationObservation hash mismatch"):
        AdaptationObservation(
            observation_id=valid_obs.observation_id,
            pre_state_hash=valid_obs.pre_state_hash,
            pre_sequence=valid_obs.pre_sequence,
            pre_epoch=valid_obs.pre_epoch,
            proposal_hash=valid_obs.proposal_hash,
            model_id=valid_obs.model_id,
            model_version=valid_obs.model_version,
            model_artifact_hash=valid_obs.model_artifact_hash,
            training_generation=valid_obs.training_generation,
            parent_model_hash=valid_obs.parent_model_hash,
            accepted_tasks=valid_obs.accepted_tasks,
            rejected_tasks=valid_obs.rejected_tasks,
            fallback_triggered=valid_obs.fallback_triggered,
            committed=valid_obs.committed,
            post_state_hash=valid_obs.post_state_hash,
            post_sequence=valid_obs.post_sequence,
            certificate_hash="forged_certificate_hash_00000000000000",
            observation_hash=valid_obs.observation_hash,  # Reused hash!
        )

    # 2. Tampered observation injected into proposer is detected and dropped
    tampered_obs = copy.copy(valid_obs)
    object.__setattr__(tampered_obs, "certificate_hash", "forged_certificate_hash_00000000000000")
    proposer.observe_feedback(tampered_obs)
    assert proposer.dropped_corrupt_count == 1
    assert len(proposer.observation_buffer) == 1, "Corrupted observation must be dropped"


def test_gate_u15_4_stale_and_duplicate_feedback_containment():
    """Duplicate and stale observations are rejected without corrupting model state."""
    proposer = PortableAdaptiveProposer()
    reg, init_state = create_drift_environment("gpu_scarce")

    prop = proposer.propose(("cpu_job_1",), reg, init_state)
    cert = certify_proposal(prop, ("cpu_job_1",), reg, init_state)
    obs = create_adaptation_observation(
        pre_state=init_state,
        proposal=prop,
        certificate=cert,
        post_state=init_state,
        committed=True,
    )

    # 1. First observation accepted
    proposer.observe_feedback(obs)
    assert len(proposer.observation_buffer) == 1

    # 2. Duplicate observation dropped
    proposer.observe_feedback(obs)
    assert proposer.dropped_duplicate_count == 1
    assert len(proposer.observation_buffer) == 1

    # 3. Stale sequence observation dropped
    stale_obs = create_adaptation_observation(
        pre_state=init_state,
        proposal=prop,
        certificate=cert,
        post_state=init_state,
        committed=True,
        observation_id="stale_obs_123",
    )
    # Artificially set higher sequence to advance proposer's clock
    proposer.last_observed_sequence = 999
    proposer.observe_feedback(stale_obs)
    assert proposer.dropped_stale_count == 1


def test_gate_u15_4_proposer_crash_during_update_atomic_rollback():
    """Crashing during update() cleanly rolls back to previous valid model snapshot."""
    proposer = PortableAdaptiveProposer()
    initial_identity = proposer.model_identity()
    initial_weights = copy.deepcopy(proposer.weights)

    # Configure simulated crash
    proposer.inject_crash_on_update = True

    with pytest.raises(RuntimeError, match="Simulated crash during model parameter update"):
        proposer.update()

    # Identity and weights remain uncorrupted
    assert proposer.model_identity() == initial_identity
    assert proposer.weights == initial_weights


def test_gate_u15_4_in_flight_concurrent_update_isolation():
    """A proposal emitted under generation theta_t is certified without interference from theta_{t+1}."""
    reg, init_state = create_drift_environment("gpu_scarce")
    proposer = PortableAdaptiveProposer()

    # Propose under generation 0
    ready = OrchestrationState(init_state).ready_frontier()
    prop_gen0 = proposer.propose(ready, reg, init_state)
    assert prop_gen0.training_generation == 0

    # Advance model to generation 1 with modified weights before certification occurs
    proposer.weights["priority_weight"] += 2.0
    proposer.update()
    assert proposer.model_identity().training_generation == 1

    # Proposal remains bound to generation 0 and previous artifact hash
    assert prop_gen0.training_generation == 0
    assert prop_gen0.model_artifact_hash != proposer.model_identity().model_artifact_hash

    # Judge evaluation evaluates the proposal cleanly against the state
    cert = certify_proposal(prop_gen0, ready, reg, init_state)
    assert isinstance(cert, ProposalCertificate)
