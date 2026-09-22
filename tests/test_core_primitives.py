from dataclasses import replace

import pytest

from uow import (
    ALL_MATRIX_CELLS,
    Guard,
    GuardOp,
    MatrixCell,
    Mutation,
    MutationOp,
    Route,
    Successor,
    WorkCategory,
    WorldState,
    commit,
    certify,
    make_uow,
    propose,
)


def test_semantic_matrix_has_exactly_64_pairings():
    assert len(ALL_MATRIX_CELLS) == 64
    assert len(set(ALL_MATRIX_CELLS)) == 64


def test_world_state_supports_typed_json_values_and_hash_binding():
    state = WorldState(
        attributes={
            "count": 3,
            "approved": True,
            "label": "alpha",
            "receipt": {"id": "r-1", "items": [1, 2, 3]},
        },
        cursor="u0",
    )
    changed = state.with_attribute("receipt", {"id": "r-2", "items": [1, 2, 3]})

    assert state.state_hash != changed.state_hash
    assert state.require("receipt")["id"] == "r-1"

    with pytest.raises(TypeError):
        state.attributes["count"] = 4


def test_propose_certify_commit_round_trip():
    uow = make_uow(
        "u0",
        [
            Route(
                guard=Guard(GuardOp.ALWAYS),
                mutations=(Mutation(MutationOp.ADD, "count", 2),),
                successor=Successor.halt(),
            )
        ],
        MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA),
    )
    before = WorldState(attributes={"count": 5}, cursor="u0")

    proposal = propose(uow, before)
    certificate = certify(uow, before, proposal)
    committed, evidence = commit(
        uow,
        before,
        proposal,
        certificate,
        prev_evidence_hash="0" * 64,
        step_number=1,
    )

    assert certificate.is_valid
    assert committed.require("count") == 7
    assert committed.status == "HALTED"
    assert committed.sequence == 1
    assert evidence.pre_state_hash == before.state_hash
    assert evidence.post_state_hash == committed.state_hash


def test_corrupted_proposal_is_rejected():
    uow = make_uow(
        "u0",
        [
            Route(
                guard=Guard(GuardOp.ALWAYS),
                mutations=(Mutation(MutationOp.SET, "value", 10),),
                successor=Successor.halt(),
            )
        ],
    )
    before = WorldState(attributes={"value": 0}, cursor="u0")
    proposal = propose(uow, before)
    corrupted = replace(
        proposal,
        proposed_state=proposal.proposed_state.with_attribute("value", 11),
    )

    certificate = certify(uow, before, corrupted)

    assert not certificate.is_valid
    assert certificate.rejection_reason == "STATE_DIVERGENCE"


def test_dynamic_successor_is_first_class_not_magic_string():
    dispatch = make_uow(
        "dispatch",
        [
            Route(
                guard=Guard(GuardOp.ALWAYS),
                successor=Successor.from_attribute("next_task"),
            )
        ],
        MatrixCell(WorkCategory.RULES, WorkCategory.PROCESSES),
    )
    before = WorldState(
        attributes={"next_task": "task-a"},
        cursor="dispatch",
    )

    proposal = propose(dispatch, before)

    assert proposal.selected_successor == "task-a"
    assert proposal.proposed_state.cursor == "task-a"
