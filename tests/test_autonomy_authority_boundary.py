"""Mandatory authority-boundary verification for production autonomy execution.

Enforces:
    Autonomy -> Proposal
    ApplicationSpine -> Authority

The production autonomy controller must not own or mutate authoritative state directly.
Every state transition must lower through a WorkItemCompiler to a native UoW and commit
authoritatively via ApplicationSpine.
"""
from __future__ import annotations

import pytest

from uow import (
    Guard,
    GuardOp,
    MatrixCell,
    Mutation,
    MutationOp,
    Route,
    Successor,
    WorkCategory,
    WorldState,
    make_uow,
)
from uow.application import ApplicationSpine, CursorPolicy
from uow.autonomy import (
    AutonomousRuntime,
    AutonomyBudget,
    AutonomyRequest,
    CapabilitySpec,
    GoalSpec,
    TerminalDisposition,
)
from uow.autonomy.controller import AutonomousClosureController, ClosureState
from uow.autonomy.model import (
    AuthorityScope,
    CapabilityDescriptor,
    CapabilityRegistry,
    Criterion,
    GoalEnvelope,
    PredicateOp,
    StatePredicate,
    WorkItem,
)
from uow.autonomy.ports import ApplicationExecutionPort, WorkItemCompiler
from uow.transactions.sequencer import DeterministicSequencer


class MockDomainCompiler:
    """Compiles WorkItem into native authoritative UoWs."""

    def compile(self, item: WorkItem, state: WorldState):
        attr = item.parameters.get("attr", "metric")
        val = item.parameters.get("val", 100)
        return make_uow(
            item.work_id,
            [
                Route(
                    guard=Guard(GuardOp.ALWAYS),
                    mutations=(Mutation(MutationOp.SET, attr, val),),
                    successor=Successor.halt(),
                )
            ],
            MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA),
        )


def test_production_execution_routes_strictly_through_application_spine():
    """Verify that all state transitions pass through ApplicationSpine into EvidenceLedger."""
    initial_state = WorldState(attributes={"balance": 50})
    sequencer = DeterministicSequencer(initial_state)

    port = ApplicationExecutionPort(
        sequencer=sequencer,
        compiler=MockDomainCompiler(),
        cursor_policy=CursorPolicy.DETACHED,
    )

    # Initial state verification
    assert port.state.attributes["balance"] == 50
    assert len(sequencer.ledger.records) == 0

    item = WorkItem(
        work_id="tx_credit_50",
        work_kind="credit",
        parameters={"attr": "balance", "val": 100},
        required_capabilities=("finance.write",),
    )
    authority = AuthorityScope(authorized_scopes=("finance.write",))

    outcome = port.execute(item, authority)
    assert outcome.success is True
    # Authoritative sequencer state updated
    assert sequencer.current_state.attributes["balance"] == 100
    # Port state reflects sequencer current state
    assert port.state.attributes["balance"] == 100
    # Exactly one authoritative commit recorded in evidence ledger
    assert len(sequencer.ledger.records) == 1
    assert sequencer.ledger.records[0].uow_id == "tx_credit_50"


def test_authority_violation_prevents_spine_execution():
    """When authority is withheld, ApplicationSpine is not reached and state is unchanged."""
    initial_state = WorldState(attributes={"balance": 50})
    sequencer = DeterministicSequencer(initial_state)

    port = ApplicationExecutionPort(
        sequencer=sequencer,
        compiler=MockDomainCompiler(),
        cursor_policy=CursorPolicy.DETACHED,
    )

    item = WorkItem(
        work_id="tx_unauthorized",
        work_kind="admin_override",
        parameters={"attr": "balance", "val": 9999},
        required_capabilities=("admin.root",),
    )
    # Restricted authority scope
    restricted_authority = AuthorityScope(authorized_scopes=("finance.read_only",))

    outcome = port.execute(item, restricted_authority)
    assert outcome.success is False
    assert "UNAUTHORIZED_WORK_AUTHORITY" in (outcome.error_code or "")
    # Authoritative state is completely unchanged
    assert sequencer.current_state.attributes["balance"] == 50
    # No records written to evidence ledger
    assert len(sequencer.ledger.records) == 0


def test_controller_cannot_self_grant_authority():
    """Autonomous controller respects goal's authority scope and halts if unauthorized."""
    initial_state = WorldState(attributes={"secure_vault": "locked"})
    sequencer = DeterministicSequencer(initial_state)

    port = ApplicationExecutionPort(
        sequencer=sequencer,
        compiler=MockDomainCompiler(),
        cursor_policy=CursorPolicy.DETACHED,
    )

    # Capability requiring root authority
    cap = CapabilityDescriptor(
        capability_id="unlock_vault",
        name="Unlock Vault",
        effects=(StatePredicate("secure_vault", PredicateOp.EQ, "unlocked"),),
        required_authority=("vault.superadmin",),
    )
    reg = CapabilityRegistry([cap])

    # Goal provided with standard user authority only
    crit = Criterion("c_vault", StatePredicate("secure_vault", PredicateOp.EQ, "unlocked"))
    goal = GoalEnvelope(
        goal_id="break_vault",
        initial_state_ref=initial_state.state_hash,
        desired_state=(crit.predicate,),
        success_criteria=(crit,),
        allowed_authority=AuthorityScope(authorized_scopes=("vault.user",)),
    )

    controller = AutonomousClosureController(reg)
    result = controller.run(goal, port)

    assert result.success is False
    assert result.terminal_state in (ClosureState.FAILED, ClosureState.ESCALATE)
    assert any("UNAUTHORIZED" in r for r in result.rejection_reasons)
    # Vault state was NOT mutated
    assert sequencer.current_state.attributes["secure_vault"] == "locked"
    assert len(sequencer.ledger.records) == 0


def test_spine_certification_failure_preserves_authoritative_state():
    """If a UoW fails certification in ApplicationSpine, state is preserved without partial mutation."""
    initial_state = WorldState(attributes={"count": 10})
    sequencer = DeterministicSequencer(initial_state)

    class FailingCompiler:
        def compile(self, item: WorkItem, state: WorldState):
            # Propose an impossible guard that fails certification
            return make_uow(
                item.work_id,
                [
                    Route(
                        guard=Guard(GuardOp.EQ, "nonexistent_key", 42),
                        mutations=(Mutation(MutationOp.SET, "count", 999),),
                        successor=Successor.halt(),
                    )
                ],
                MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA),
            )

    port = ApplicationExecutionPort(
        sequencer=sequencer,
        compiler=FailingCompiler(),
        cursor_policy=CursorPolicy.DETACHED,
    )

    item = WorkItem(
        work_id="tx_invalid_route",
        work_kind="invalid_action",
        parameters={},
        required_capabilities=("authority.default",),
    )
    outcome = port.execute(item, AuthorityScope(authorized_scopes=("authority.default",)))

    assert outcome.success is False
    assert "EXECUTION_REJECTED" in (outcome.error_code or "")
    assert sequencer.current_state.attributes["count"] == 10
    assert len(sequencer.ledger.records) == 0
