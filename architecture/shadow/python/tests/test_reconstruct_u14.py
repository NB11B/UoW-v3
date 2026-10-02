from __future__ import annotations

from typing import Any, Mapping, Sequence

from uow.compat.v2 import (
    BaseProposer,
    Guard,
    GuardOp,
    HeuristicSchedulingProposer,
    ModelProposal,
    Mutation,
    MutationOp,
    OrchestrationState,
    RandomProposer,
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

from uow_shadow.proposer_reconstruction import run_proposer_orchestration_reconstructed


def _dag():
    caps = {
        "cpu_cores": 4,
        "ram_units": 16,
        "gpu_slots": 1,
        "npu_slots": 1,
        "energy_budget": 1000,
        "cost": 100,
    }
    resources = ResourceState(capacities=caps)

    registry: Mapping[str, ResourceBoundTask] = {
        "t1": make_resource_domain_task(
            "t1",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "x", 10),))],
            ResourceRequirement(cpu_cores=2, ram_units=2, priority=3),
        ),
        "t2": make_resource_domain_task(
            "t2",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "x", 20),))],
            ResourceRequirement(cpu_cores=2, ram_units=2, priority=3),
        ),
        "t3": make_resource_domain_task(
            "t3",
            [Route(Guard(GuardOp.NE, "x", -1), (Mutation(MutationOp.ADD, "y", 30),))],
            ResourceRequirement(cpu_cores=2, ram_units=2, priority=4),
        ),
        "t4": make_resource_domain_task(
            "t4",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "npu", 40),))],
            ResourceRequirement(cpu_cores=3, ram_units=2, npu_slots=1, priority=1, deadline=10),
        ),
        "t5": make_resource_domain_task(
            "t5",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "downstream", 50),))],
            ResourceRequirement(cpu_cores=1, ram_units=2, priority=2),
        ),
        "t6": make_resource_domain_task(
            "t6",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "bg", 60),))],
            ResourceRequirement(cpu_cores=3, ram_units=2, priority=10),
        ),
    }
    deps = {"t5": ("t4",)}
    base = create_initial_orchestration_state(
        list(registry),
        deps,
        attributes={"x": 0, "y": 0, "npu": 0, "downstream": 0, "bg": 0},
    )
    return registry, set_authoritative_resource_state(base, resources)


def test_r4_u14_proposer_call_has_zero_authority():
    registry, state = _dag()
    proposer = RandomProposer(seed=7)
    ready = OrchestrationState(state).ready_frontier()

    before_hash = state.state_hash
    before_sequence = state.sequence
    proposal = proposer.propose(ready, registry, state)

    assert isinstance(proposal, ModelProposal)
    assert state.state_hash == before_hash
    assert state.sequence == before_sequence
    assert OrchestrationState(state).active == ()


def test_r4_u14_judge_rejects_illegal_dependency_and_unknown_task():
    registry, state = _dag()
    ready = OrchestrationState(state).ready_frontier()
    proposal = ModelProposal(
        model_id="bad",
        model_version="1",
        input_state_hash=state.state_hash,
        input_sequence=state.sequence,
        input_epoch=state.sequence,
        candidate_schedule=("t5", "phantom"),
    )
    cert = certify_proposal(proposal, ready, registry, state)

    assert "DEPENDENCY_UNSATISFIED" in cert.rejected_tasks["t5"]
    assert "UNKNOWN_TASK" in cert.rejected_tasks["phantom"]


def test_r4_u14_judge_rejects_occ_conflict():
    registry, state = _dag()
    ready = OrchestrationState(state).ready_frontier()
    proposal = ModelProposal(
        model_id="bad",
        model_version="1",
        input_state_hash=state.state_hash,
        input_sequence=state.sequence,
        input_epoch=state.sequence,
        candidate_schedule=("t1", "t2"),
    )
    cert = certify_proposal(proposal, ready, registry, state)

    assert "t1" in cert.accepted_tasks
    assert "OCC_WRITE_WRITE_CONFLICT" in cert.rejected_tasks["t2"]


def test_r4_u14_judge_rejects_resource_overallocation():
    registry, state = _dag()
    ready = OrchestrationState(state).ready_frontier()
    proposal = ModelProposal(
        model_id="bad",
        model_version="1",
        input_state_hash=state.state_hash,
        input_sequence=state.sequence,
        input_epoch=state.sequence,
        candidate_schedule=("t4", "t6"),
    )
    cert = certify_proposal(proposal, ready, registry, state)

    assert len(cert.accepted_tasks) == 1
    assert any("RESOURCE_CAPACITY_EXCEEDED" in r for r in cert.rejected_tasks.values())


def test_r4_u14_stale_proposal_is_rejected_and_fallback_requested():
    registry, state = _dag()
    ready = OrchestrationState(state).ready_frontier()
    proposal = ModelProposal(
        model_id="stale",
        model_version="1",
        input_state_hash="old-state",
        input_sequence=state.sequence,
        input_epoch=state.sequence,
        candidate_schedule=("t1",),
    )
    cert = certify_proposal(proposal, ready, registry, state)

    assert not cert.is_valid
    assert cert.fallback_triggered
    assert "STALE_STATE_HASH_OR_EPOCH" in cert.rejected_tasks["t1"]


def test_r4_u14_crashing_proposer_falls_back_and_completes():
    registry, state = _dag()
    result = run_proposer_orchestration_reconstructed(
        registry,
        state,
        RandomProposer(inject_crash=True),
    )

    assert result.final_state.status == "HALTED"
    assert len(OrchestrationState(result.final_state).completed) == len(registry)
    assert result.telemetry
    assert all(t.certificate.fallback_triggered for t in result.telemetry)


def test_r4_u14_seeded_stochastic_replay_is_deterministic():
    registry, state = _dag()
    a = run_proposer_orchestration_reconstructed(
        registry,
        state,
        RandomProposer(seed=777),
    )
    b = run_proposer_orchestration_reconstructed(
        registry,
        state,
        RandomProposer(seed=777),
    )

    assert a.final_state.state_hash == b.final_state.state_hash
    assert a.evidence_root() == b.evidence_root()
    assert [t.proposal.proposal_hash if t.proposal else None for t in a.telemetry] == [
        t.proposal.proposal_hash if t.proposal else None for t in b.telemetry
    ]
    assert [t.certificate.certificate_hash for t in a.telemetry] == [
        t.certificate.certificate_hash for t in b.telemetry
    ]


def test_r4_u14_heuristic_and_stochastic_both_complete_with_authority_invariant():
    registry, state = _dag()
    random_result = run_proposer_orchestration_reconstructed(
        registry,
        state,
        RandomProposer(seed=42),
    )
    heuristic_result = run_proposer_orchestration_reconstructed(
        registry,
        state,
        HeuristicSchedulingProposer(),
    )

    assert random_result.final_state.status == "HALTED"
    assert heuristic_result.final_state.status == "HALTED"
    assert len(OrchestrationState(random_result.final_state).completed) == len(registry)
    assert len(OrchestrationState(heuristic_result.final_state).completed) == len(registry)

    random_rejections = sum(len(t.certificate.rejected_tasks) for t in random_result.telemetry)
    heuristic_rejections = sum(len(t.certificate.rejected_tasks) for t in heuristic_result.telemetry)
    assert heuristic_rejections <= random_rejections


class SimulatedEdgePolicyProposer(BaseProposer):
    def model_id(self) -> str:
        return "portable-edge-policy"

    def model_version(self) -> str:
        return "1"

    def propose(
        self,
        ready_candidates: Sequence[str],
        graph: Mapping[str, Any],
        state: WorldState,
    ) -> ModelProposal:
        chosen = (ready_candidates[0],) if ready_candidates else ()
        return ModelProposal(
            model_id=self.model_id(),
            model_version=self.model_version(),
            input_state_hash=state.state_hash,
            input_sequence=state.sequence,
            input_epoch=state.sequence,
            candidate_schedule=chosen,
            predicted_metrics={"confidence": 0.9},
            metadata={"substrate": "simulated-edge"},
        )


def test_r4_u14_external_proposer_seam_is_swappable_without_authority_change():
    registry, state = _dag()
    result = run_proposer_orchestration_reconstructed(
        registry,
        state,
        SimulatedEdgePolicyProposer(),
    )

    assert result.final_state.status == "HALTED"
    assert len(OrchestrationState(result.final_state).completed) == len(registry)
    assert any(
        t.proposal is not None and t.proposal.model_id == "portable-edge-policy"
        for t in result.telemetry
    )
