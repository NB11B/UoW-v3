from __future__ import annotations

import copy
from typing import Mapping, Tuple

import pytest

from uow import (
    AdaptationObservation,
    Guard,
    GuardOp,
    ModelIdentity,
    Mutation,
    MutationOp,
    OrchestrationState,
    PortableAdaptiveProposer,
    ResourceBoundTask,
    ResourceRequirement,
    ResourceState,
    Route,
    create_initial_orchestration_state,
    make_resource_domain_task,
    set_authoritative_resource_state,
    validate_observation_integrity,
)

from uow_shadow.adaptive_reconstruction import run_adaptive_orchestration_reconstructed


def _environment(kind: str) -> Tuple[Mapping[str, ResourceBoundTask], object]:
    if kind == "gpu_scarce":
        caps = {"cpu_cores": 8, "ram_units": 16, "gpu_slots": 1, "npu_slots": 2}
    elif kind == "cpu_scarce":
        caps = {"cpu_cores": 2, "ram_units": 16, "gpu_slots": 4, "npu_slots": 2}
    else:
        raise ValueError(kind)

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

    base = create_initial_orchestration_state(
        list(registry),
        {},
        attributes={
            "cpu_out_1": 0,
            "cpu_out_2": 0,
            "gpu_out_1": 0,
            "gpu_out_2": 0,
            "npu_out_1": 0,
            "npu_out_2": 0,
        },
    )
    return registry, set_authoritative_resource_state(base, ResourceState(capacities=caps))


def _rejection_rate(result) -> float:
    props = [t for t in result.telemetry if t.proposal is not None]
    rejects = sum(len(t.certificate.rejected_tasks) for t in result.telemetry)
    return float(rejects) / float(len(props)) if props else 0.0


def test_r4_u15_model_lineage_and_zero_authority_survive_reconstruction():
    proposer = PortableAdaptiveProposer()
    id0 = proposer.model_identity()

    assert not hasattr(proposer, "commit")
    assert not hasattr(proposer, "mutate_world")

    id1 = proposer.update()
    id2 = proposer.update()

    assert id1.training_generation == 1
    assert id1.parent_model_hash == id0.identity_hash
    assert id2.training_generation == 2
    assert id2.parent_model_hash == id1.identity_hash

    with pytest.raises(ValueError, match="ModelIdentity hash mismatch"):
        ModelIdentity(
            model_id=id2.model_id,
            model_version=id2.model_version,
            model_artifact_hash="tampered",
            training_generation=id2.training_generation,
            parent_model_hash=id2.parent_model_hash,
            identity_hash=id2.identity_hash,
        )


def test_r4_u15_certified_feedback_is_bound_to_shadow_authoritative_outcome():
    registry, initial = _environment("gpu_scarce")
    proposer = PortableAdaptiveProposer()

    result = run_adaptive_orchestration_reconstructed(registry, initial, proposer)

    assert result.final_state.status == "HALTED"
    assert len(OrchestrationState(result.final_state).completed) == 6
    assert result.observations
    assert len(proposer.observation_buffer) == len(result.observations)

    first = result.observations[0]
    first_telem = result.telemetry[0]
    assert first.pre_state_hash == initial.state_hash
    assert first.committed
    assert first.certificate_hash == first_telem.certificate.certificate_hash
    assert first.observation_hash
    # The observation's post-state is the actual shadow-authorized scheduler transition.
    assert first.post_sequence == first.pre_sequence + 1


def test_r4_u15_portable_adaptation_reduces_rejection_rate():
    registry0, initial0 = _environment("gpu_scarce")
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

    before = run_adaptive_orchestration_reconstructed(registry0, initial0, proposer)
    rate_before = _rejection_rate(before)
    assert rate_before > 0.0
    assert before.final_state.status == "HALTED"

    initial_generation = proposer.model_identity().training_generation
    identity = proposer.update()
    assert identity.training_generation == initial_generation + 1
    assert proposer.weights["gpu_affinity"] < 10.0
    assert proposer.weights["batch_capacity_target"] < 4.0

    registry1, initial1 = _environment("gpu_scarce")
    after = run_adaptive_orchestration_reconstructed(registry1, initial1, proposer)
    rate_after = _rejection_rate(after)

    assert rate_after < rate_before
    assert after.final_state.status == "HALTED"
    assert len(OrchestrationState(after.final_state).completed) == 6


def test_r4_u15_workload_drift_preserves_authority_after_update():
    registry_a, initial_a = _environment("gpu_scarce")
    proposer = PortableAdaptiveProposer(learning_rate=2.0)

    first = run_adaptive_orchestration_reconstructed(registry_a, initial_a, proposer)
    assert first.final_state.status == "HALTED"
    proposer.update()

    registry_b, initial_b = _environment("cpu_scarce")
    drift = run_adaptive_orchestration_reconstructed(registry_b, initial_b, proposer)
    assert drift.final_state.status == "HALTED"
    assert len(OrchestrationState(drift.final_state).completed) == 6
    proposer.update()

    registry_b2, initial_b2 = _environment("cpu_scarce")
    after = run_adaptive_orchestration_reconstructed(registry_b2, initial_b2, proposer)
    assert after.final_state.status == "HALTED"
    assert len(OrchestrationState(after.final_state).completed) == 6


def test_r4_u15_catastrophic_model_poisoning_degrades_proposal_not_authority():
    registry, initial = _environment("gpu_scarce")
    proposer = PortableAdaptiveProposer()
    proposer.inject_corrupt_weights_on_update = True
    proposer.update()

    assert all(w < -1e8 for w in proposer.weights.values())

    result = run_adaptive_orchestration_reconstructed(registry, initial, proposer)

    assert result.final_state.status == "HALTED"
    assert len(OrchestrationState(result.final_state).completed) == 6
    assert sum(1 for t in result.telemetry if t.certificate.fallback_triggered) > 0


def test_r4_u15_corrupt_duplicate_and_stale_feedback_remain_contained():
    registry, initial = _environment("gpu_scarce")
    proposer = PortableAdaptiveProposer()
    result = run_adaptive_orchestration_reconstructed(registry, initial, proposer)
    obs = result.observations[0]

    buffered = len(proposer.observation_buffer)
    proposer.observe_feedback(obs)
    assert proposer.dropped_duplicate_count >= 1
    assert len(proposer.observation_buffer) == buffered

    tampered = copy.copy(obs)
    object.__setattr__(tampered, "certificate_hash", "forged-certificate")
    proposer.observe_feedback(tampered)
    assert proposer.dropped_corrupt_count >= 1
    assert len(proposer.observation_buffer) == buffered

    stale = copy.copy(obs)
    object.__setattr__(stale, "observation_id", "stale-distinct")
    object.__setattr__(
        stale,
        "observation_hash",
        AdaptationObservation.calculate_hash(
            observation_id="stale-distinct",
            pre_state_hash=stale.pre_state_hash,
            pre_sequence=stale.pre_sequence,
            pre_epoch=stale.pre_epoch,
            proposal_hash=stale.proposal_hash,
            model_id=stale.model_id,
            model_version=stale.model_version,
            model_artifact_hash=stale.model_artifact_hash,
            training_generation=stale.training_generation,
            parent_model_hash=stale.parent_model_hash,
            accepted_tasks=stale.accepted_tasks,
            rejected_tasks=dict(stale.rejected_tasks),
            fallback_triggered=stale.fallback_triggered,
            committed=stale.committed,
            post_state_hash=stale.post_state_hash,
            post_sequence=stale.post_sequence,
            certificate_hash=stale.certificate_hash,
        ),
    )
    proposer.last_observed_sequence = 10**9
    proposer.observe_feedback(stale)
    assert proposer.dropped_stale_count >= 1


def test_r4_u15_update_crash_rolls_back_model_state():
    proposer = PortableAdaptiveProposer()
    identity = proposer.model_identity()
    weights = copy.deepcopy(proposer.weights)
    proposer.inject_crash_on_update = True

    with pytest.raises(RuntimeError, match="Simulated crash during model parameter update"):
        proposer.update()

    assert proposer.model_identity() == identity
    assert proposer.weights == weights
