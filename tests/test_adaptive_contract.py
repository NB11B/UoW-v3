"""Canonical qualification tests for Gates U15.1 and U15.2 (Adaptive Proposer Contract & Feedback Integrity).

Enforces the core invariants:
    1. PROPOSAL HAS ZERO AUTHORITY: Swapping or updating model parameters CANNOT alter certification semantics.
    2. FEEDBACK INTEGRITY: Learning observations are machine-readable, unforgeable, tamper-evident supervision.
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
    HeuristicSchedulingProposer,
    ModelIdentity,
    ModelProposal,
    Mutation,
    MutationOp,
    OrchestrationState,
    ProposalCertificate,
    ProposerOrchestrationEngine,
    RandomProposer,
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


def create_u15_test_dag() -> Tuple[Mapping[str, ResourceBoundTask], WorldState]:
    """Constructs a test DAG with resource bounds and dependencies."""
    host_caps = {
        "cpu_cores": 4,
        "ram_units": 8,
        "gpu_slots": 1,
        "npu_slots": 1,
    }
    res_state = ResourceState(capacities=host_caps)

    registry: Mapping[str, ResourceBoundTask] = {
        "task_cpu_1": make_resource_domain_task(
            "task_cpu_1",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "cpu_res", 1),))],
            ResourceRequirement(cpu_cores=2, ram_units=2, priority=1),
        ),
        "task_cpu_2": make_resource_domain_task(
            "task_cpu_2",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "cpu_res", 2),))],
            ResourceRequirement(cpu_cores=2, ram_units=2, priority=2),
        ),
        "task_gpu": make_resource_domain_task(
            "task_gpu",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "gpu_res", 10),))],
            ResourceRequirement(cpu_cores=1, ram_units=4, gpu_slots=1, priority=5),
        ),
        "task_npu": make_resource_domain_task(
            "task_npu",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "npu_res", 20),))],
            ResourceRequirement(cpu_cores=1, ram_units=2, npu_slots=1, priority=3),
        ),
    }

    queue = ["task_cpu_1", "task_cpu_2", "task_gpu", "task_npu"]
    init_base = create_initial_orchestration_state(
        queue=queue,
        dependencies={},
        attributes={"cpu_res": 0, "gpu_res": 0, "npu_res": 0},
    )
    init_state = set_authoritative_resource_state(init_base, res_state)
    return registry, init_state


class SimpleAdaptivePolicyProposer:
    """Mock adaptive proposer implementing the AdaptiveProposer contract."""

    def __init__(self, model_id: str = "TestAdaptiveModel", bias_preference: str = "cpu") -> None:
        self._model_id = model_id
        self._bias_preference = bias_preference
        self._generation = 0
        self._artifact_hash = hashlib.sha256(f"weights_gen_{self._generation}_{bias_preference}".encode()).hexdigest()
        self._identity = ModelIdentity(
            model_id=self._model_id,
            model_version="1.0.0",
            model_artifact_hash=self._artifact_hash,
            training_generation=self._generation,
        )
        self.observations_received: List[AdaptationObservation] = []

    def model_id(self) -> str:
        return self._identity.model_id

    def model_version(self) -> str:
        return self._identity.model_version

    def model_identity(self) -> ModelIdentity:
        return self._identity

    def propose(
        self,
        ready_candidates: Sequence[str],
        graph: Mapping[str, Any],
        state: WorldState,
    ) -> ModelProposal:
        # Bias candidate selection according to current learned policy (avoiding intra-batch write collision)
        chosen: List[str] = []
        if self._bias_preference == "cpu":
            if "task_cpu_1" in ready_candidates:
                chosen.append("task_cpu_1")
            if "task_gpu" in ready_candidates:
                chosen.append("task_gpu")
        elif self._bias_preference == "gpu":
            if "task_gpu" in ready_candidates:
                chosen.append("task_gpu")
            if "task_npu" in ready_candidates:
                chosen.append("task_npu")

        if not chosen and ready_candidates:
            chosen = [ready_candidates[0]]

        return ModelProposal(
            model_id=self._identity.model_id,
            model_version=self._identity.model_version,
            input_state_hash=state.state_hash,
            input_sequence=state.sequence,
            input_epoch=state.sequence,
            candidate_schedule=tuple(chosen),
            model_artifact_hash=self._identity.model_artifact_hash,
            training_generation=self._identity.training_generation,
            parent_model_hash=self._identity.parent_model_hash,
        )

    def observe_feedback(self, observation: AdaptationObservation) -> None:
        self.observations_received.append(observation)

    def update(self) -> ModelIdentity:
        self._generation += 1
        new_artifact = hashlib.sha256(f"weights_gen_{self._generation}_{self._bias_preference}".encode()).hexdigest()
        self._identity = self._identity.child_identity(new_artifact)
        return self._identity


# ===========================================================================
# Gate U15.1: Adaptive Proposer Contract & Isolation
# ===========================================================================

def test_gate_u15_1_proposer_protocol_conformance_and_isolation():
    """Verify that AdaptiveProposer adheres to protocol and has zero commit authority."""
    proposer = SimpleAdaptivePolicyProposer()

    # Verify structural protocol requirements
    assert isinstance(proposer, BaseProposer)
    assert hasattr(proposer, "model_id")
    assert hasattr(proposer, "model_version")
    assert hasattr(proposer, "model_identity")
    assert hasattr(proposer, "propose")
    assert hasattr(proposer, "observe_feedback")
    assert hasattr(proposer, "update")

    # Invariant: commit() and mutate_world() DO NOT EXIST on the proposer
    assert not hasattr(proposer, "commit"), "Proposer must not expose commit method"
    assert not hasattr(proposer, "mutate_world"), "Proposer must not expose mutate_world method"
    assert not hasattr(proposer, "execute"), "Proposer must not expose execute method"


def test_gate_u15_1_cryptographic_lineage_chain():
    """Verify cryptographic model identity chaining theta_0 -> theta_1 -> theta_2."""
    proposer = SimpleAdaptivePolicyProposer()
    id0 = proposer.model_identity()
    assert id0.training_generation == 0
    assert id0.parent_model_hash is None
    assert id0.identity_hash != ""

    # Generation 1 update
    id1 = proposer.update()
    assert id1.training_generation == 1
    assert id1.parent_model_hash == id0.identity_hash
    assert id1.identity_hash != id0.identity_hash

    # Generation 2 update
    id2 = proposer.update()
    assert id2.training_generation == 2
    assert id2.parent_model_hash == id1.identity_hash

    # Verify tampering with identity fields triggers cryptographic validation failure
    with pytest.raises(ValueError, match="ModelIdentity hash mismatch"):
        ModelIdentity(
            model_id=id2.model_id,
            model_version=id2.model_version,
            model_artifact_hash="tampered_artifact_hash",
            training_generation=id2.training_generation,
            parent_model_hash=id2.parent_model_hash,
            identity_hash=id2.identity_hash,  # forged / mismatched
        )


def test_gate_u15_1_swapping_model_cannot_alter_certification_semantics():
    """Swapping or updating model parameters (even to adversarial ones) cannot bypass certification."""
    registry, init_state = create_u15_test_dag()
    ready = OrchestrationState(init_state).ready_frontier()

    # Normal proposer
    proposer_cpu = SimpleAdaptivePolicyProposer(bias_preference="cpu")
    prop_cpu = proposer_cpu.propose(ready, registry, init_state)
    cert_cpu = certify_proposal(prop_cpu, ready, registry, init_state)
    assert cert_cpu.is_valid

    # Mutated/adversarial model proposing an illegal batch (e.g. overcapacity or non-existent tasks)
    class AdversarialAdaptiveProposer(SimpleAdaptivePolicyProposer):
        def propose(self, ready_candidates: Sequence[str], graph: Mapping[str, Any], state: WorldState) -> ModelProposal:
            return ModelProposal(
                model_id=self._identity.model_id,
                model_version=self._identity.model_version,
                input_state_hash=state.state_hash,
                input_sequence=state.sequence,
                input_epoch=state.sequence,
                candidate_schedule=("non_existent_task", "task_cpu_1", "task_cpu_2", "task_gpu", "task_npu"),
                model_artifact_hash=self._identity.model_artifact_hash,
                training_generation=self._identity.training_generation,
            )

    adv_proposer = AdversarialAdaptiveProposer()
    adv_prop = adv_proposer.propose(ready, registry, init_state)
    cert_adv = certify_proposal(adv_prop, ready, registry, init_state)

    # Certification rules are fixed: illegal tasks are rejected regardless of model claims
    assert not cert_adv.is_valid
    assert "non_existent_task" in cert_adv.rejected_tasks
    assert "UNKNOWN_TASK" in cert_adv.rejected_tasks["non_existent_task"]
    assert "task_cpu_2" in cert_adv.rejected_tasks
    assert "OCC_WRITE_WRITE_CONFLICT" in cert_adv.rejected_tasks["task_cpu_2"]

    # Also verify resource capacity bounds are strictly enforced regardless of model claims
    over_task = make_resource_domain_task(
        "over_cpu",
        [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "cpu_res", 1),))],
        ResourceRequirement(cpu_cores=16),
    )
    over_registry = {**registry, "over_cpu": over_task}
    prop_over = ModelProposal(
        model_id=adv_proposer.model_id(),
        model_version=adv_proposer.model_version(),
        input_state_hash=init_state.state_hash,
        input_sequence=init_state.sequence,
        input_epoch=init_state.sequence,
        candidate_schedule=("over_cpu",),
        model_artifact_hash=adv_proposer.model_identity().model_artifact_hash,
        training_generation=adv_proposer.model_identity().training_generation,
    )
    cert_over = certify_proposal(prop_over, ("over_cpu",), over_registry, init_state)
    assert not cert_over.is_valid
    assert "over_cpu" in cert_over.rejected_tasks
    assert "RESOURCE_CAPACITY_EXCEEDED" in cert_over.rejected_tasks["over_cpu"]


# ===========================================================================
# Gate U15.2: Certified Feedback Object & Integrity
# ===========================================================================

def test_gate_u15_2_feedback_object_creation_and_tamper_detection():
    """AdaptationObservation binds pre-state, proposal, certificate, and post-state with hash integrity."""
    registry, init_state = create_u15_test_dag()
    proposer = SimpleAdaptivePolicyProposer()
    engine = ProposerOrchestrationEngine(proposer=proposer)

    terminal_state, seq, telem = engine.run_dag(registry, init_state)
    assert terminal_state.status == "HALTED"
    assert len(engine.observations) > 0

    first_obs = engine.observations[0]
    assert isinstance(first_obs, AdaptationObservation)
    assert first_obs.pre_state_hash == init_state.state_hash
    assert first_obs.committed is True
    assert first_obs.observation_hash != ""

    # Verify tamper resistance: modifying any field in observation fails hash check
    with pytest.raises(ValueError, match="AdaptationObservation hash mismatch"):
        AdaptationObservation(
            observation_id=first_obs.observation_id,
            pre_state_hash=first_obs.pre_state_hash,
            pre_sequence=first_obs.pre_sequence,
            pre_epoch=first_obs.pre_epoch,
            proposal_hash=first_obs.proposal_hash,
            model_id=first_obs.model_id,
            model_version=first_obs.model_version,
            model_artifact_hash=first_obs.model_artifact_hash,
            training_generation=first_obs.training_generation,
            parent_model_hash=first_obs.parent_model_hash,
            accepted_tasks=("forged_task",),  # FORGED!
            rejected_tasks=first_obs.rejected_tasks,
            fallback_triggered=first_obs.fallback_triggered,
            committed=first_obs.committed,
            post_state_hash=first_obs.post_state_hash,
            post_sequence=first_obs.post_sequence,
            certificate_hash=first_obs.certificate_hash,
            observation_hash=first_obs.observation_hash,  # Reused hash must fail!
        )


def test_gate_u15_2_zero_state_mutation_on_rejection():
    """A rejected proposal produces an observation where post_state == pre_state."""
    registry, init_state = create_u15_test_dag()
    stale_prop = ModelProposal(
        model_id="TestStale",
        model_version="1.0.0",
        input_state_hash="0000000000000000000000000000000000000000000000000000000000000000",
        input_sequence=init_state.sequence,
        input_epoch=init_state.sequence,
        candidate_schedule=("task_cpu_1",),
    )
    cert = certify_proposal(stale_prop, ("task_cpu_1",), registry, init_state)
    assert not cert.is_valid
    assert cert.fallback_triggered

    # Construct observation for rejected proposal without commit
    obs = create_adaptation_observation(
        pre_state=init_state,
        proposal=stale_prop,
        certificate=cert,
        post_state=init_state,
        committed=False,
    )

    assert obs.committed is False
    assert obs.post_state_hash == init_state.state_hash
    assert obs.post_sequence == init_state.sequence
    assert len(obs.accepted_tasks) == 0
    assert "task_cpu_1" in obs.rejected_tasks
    assert "STALE_STATE_HASH_OR_EPOCH" in obs.rejected_tasks["task_cpu_1"]


def test_gate_u15_2_stale_feedback_detection():
    """Learner or observer detects when an observation's pre-state hash does not match current state."""
    registry, init_state = create_u15_test_dag()
    proposer = SimpleAdaptivePolicyProposer()
    engine = ProposerOrchestrationEngine(proposer=proposer)
    out_state, seq, _ = engine.run_dag(registry, init_state)

    obs = engine.observations[0]
    # Obs was generated from init_state; verifying it against terminal out_state must flag mismatch
    is_valid_against_current = (obs.pre_state_hash == out_state.state_hash)
    assert not is_valid_against_current, "Stale feedback against out_state must be detected as stale"


def test_gate_u15_2_replay_reconstructs_identical_training_dataset():
    """Replaying an identical execution produces bitwise identical sequence of AdaptationObservations."""
    registry, init_state = create_u15_test_dag()

    # Run 1
    p1 = SimpleAdaptivePolicyProposer()
    e1 = ProposerOrchestrationEngine(proposer=p1)
    s1, _, _ = e1.run_dag(registry, init_state)

    # Run 2
    p2 = SimpleAdaptivePolicyProposer()
    e2 = ProposerOrchestrationEngine(proposer=p2)
    s2, _, _ = e2.run_dag(registry, init_state)

    assert s1.state_hash == s2.state_hash
    assert len(e1.observations) == len(e2.observations)

    for o1, o2 in zip(e1.observations, e2.observations):
        assert o1.observation_hash == o2.observation_hash
        assert o1.proposal_hash == o2.proposal_hash
        assert o1.certificate_hash == o2.certificate_hash
        assert o1.pre_state_hash == o2.pre_state_hash
        assert o1.post_state_hash == o2.post_state_hash
        assert o1.accepted_tasks == o2.accepted_tasks
        assert dict(o1.rejected_tasks) == dict(o2.rejected_tasks)
