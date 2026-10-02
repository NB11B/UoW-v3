from __future__ import annotations

from uow.compat.v2 import FIFOSchedulingPolicy, OrchestrationState

from uow_shadow.goal_synthesis import (
    CandidateGraphProposal,
    CandidateUoWSpec,
    DeterministicGraphCertifier,
    GoalDecompositionProposer,
)
from uow_shadow.reconstruction import run_resource_orchestration_reconstructed


def test_r4_u14b_valid_goal_synthesis_certifies_and_executes():
    proposer = GoalDecompositionProposer()
    proposal = proposer.propose_graph("Reconcile two datasets and publish a report")

    ok, registry, initial, error = DeterministicGraphCertifier.certify_and_build(proposal)
    assert ok, error
    assert registry is not None
    assert initial is not None
    assert len(registry) == 5

    result = run_resource_orchestration_reconstructed(
        registry,
        initial,
        FIFOSchedulingPolicy(),
    )

    assert result.final_state.status == "HALTED"
    assert result.final_state.get("loaded") == 1
    assert result.final_state.get("validated") == 1
    assert result.final_state.get("reconciled") == 1
    assert result.final_state.get("audited") == 1
    assert result.final_state.get("published") == 1
    assert len(OrchestrationState(result.final_state).completed) == 5


def test_r4_u14b_cycle_is_rejected_before_execution_authority():
    proposal = GoalDecompositionProposer().propose_graph(
        "reconcile datasets",
        inject_cycle=True,
    )
    ok, registry, initial, error = DeterministicGraphCertifier.certify_and_build(proposal)

    assert not ok
    assert registry is None
    assert initial is None
    assert error == "CYCLIC_DEPENDENCY"


def test_r4_u14b_invalid_ontology_category_is_rejected():
    proposal = GoalDecompositionProposer().propose_graph(
        "reconcile datasets",
        inject_invalid_cell=True,
    )
    ok, registry, initial, error = DeterministicGraphCertifier.certify_and_build(proposal)

    assert not ok
    assert registry is None
    assert initial is None
    assert error == "INVALID_CATEGORY"


def test_r4_u14b_dangling_dependency_is_rejected():
    spec = CandidateUoWSpec(
        identity="task",
        source_category="Processes",
        target_category="Data",
        mutations=({"target": "x", "op": "SET", "operand": 1},),
        dependencies=("missing",),
    )
    proposal = CandidateGraphProposal(
        goal="manual",
        model_id="test",
        specs=(spec,),
    )
    ok, registry, initial, error = DeterministicGraphCertifier.certify_and_build(proposal)

    assert not ok
    assert registry is None
    assert initial is None
    assert error.startswith("DANGLING_DEPENDENCY")


def test_r4_u14b_replay_is_deterministic():
    proposer = GoalDecompositionProposer()
    p1 = proposer.propose_graph("reconcile datasets")
    p2 = proposer.propose_graph("reconcile datasets")

    assert p1.proposal_hash == p2.proposal_hash

    ok1, registry1, initial1, error1 = DeterministicGraphCertifier.certify_and_build(p1)
    ok2, registry2, initial2, error2 = DeterministicGraphCertifier.certify_and_build(p2)
    assert ok1 and ok2, (error1, error2)

    a = run_resource_orchestration_reconstructed(
        registry1,
        initial1,
        FIFOSchedulingPolicy(),
    )
    b = run_resource_orchestration_reconstructed(
        registry2,
        initial2,
        FIFOSchedulingPolicy(),
    )

    assert a.final_state.state_hash == b.final_state.state_hash
    assert a.evidence_root() == b.evidence_root()
