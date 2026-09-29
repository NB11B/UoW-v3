"""Tests for uow.autonomy public API surface and clean namespace isolation."""
from __future__ import annotations

import sys
import pytest

from uow.state import WorldState


def test_public_api_imports_cleanly():
    """Verify that all public autonomy symbols import directly from uow.autonomy."""
    from uow.autonomy import (
        AutonomousRuntime,
        AutonomyBudget,
        AutonomyRequest,
        AutonomyResult,
        CapabilitySpec,
        ExecutionPort,
        GoalSpec,
        TerminalDisposition,
    )

    assert AutonomousRuntime is not None
    assert AutonomyBudget is not None
    assert AutonomyRequest is not None
    assert AutonomyResult is not None
    assert CapabilitySpec is not None
    assert ExecutionPort is not None
    assert GoalSpec is not None
    assert TerminalDisposition is not None


def test_import_isolation_guarantee():
    """Verify that importing uow.autonomy in a clean process does not load research packages."""
    import subprocess

    code = (
        "import sys, uow.autonomy\n"
        "forbidden = ('qualification', 'architecture.shadow', 'uow_shadow', 'external_challenge_e1', 'prospective_', 'endurance_100k')\n"
        "loaded = set(sys.modules.keys())\n"
        "for mod in loaded:\n"
        "    for p in forbidden:\n"
        "        if mod.startswith(p):\n"
        "            raise AssertionError(f'Forbidden research module loaded: {mod}')\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert res.returncode == 0, f"Import isolation failed: {res.stderr}"


def test_top_level_uow_does_not_leak_autonomy_symbols():
    """Verify uow root namespace does not dump internal autonomy symbols."""
    import uow

    # Top-level should retain production core without leaking entire autonomy surface
    assert not hasattr(uow, "AutonomousClosureController")
    assert not hasattr(uow, "GoalDecompositionEngine")
    assert not hasattr(uow, "RepairJudge")
    assert not hasattr(uow, "UnifiedAdaptationJudge")


def test_public_api_smoke_simulation():
    """Smoke test of AutonomousRuntime end-to-end execution on SimulatedExecutionPort."""
    from uow.autonomy import (
        AutonomousRuntime,
        AutonomyBudget,
        AutonomyRequest,
        AutonomyResult,
        CapabilitySpec,
        GoalSpec,
        TerminalDisposition,
    )
    from uow.autonomy.model import PredicateOp, StatePredicate
    from uow.autonomy.ports import SimulatedExecutionPort

    init_state = WorldState(attributes={"stepA": "pending", "stepB": "pending"})

    req = AutonomyRequest(
        goal=GoalSpec(
            goal_id="smoke_goal",
            desired_state=(
                StatePredicate("stepA", PredicateOp.EQ, "done"),
                StatePredicate("stepB", PredicateOp.EQ, "done"),
            ),
        ),
        capabilities=(
            CapabilitySpec(
                capability_id="do_a",
                effects=(StatePredicate("stepA", PredicateOp.EQ, "done"),),
            ),
            CapabilitySpec(
                capability_id="do_b",
                preconditions=(StatePredicate("stepA", PredicateOp.EQ, "done"),),
                effects=(StatePredicate("stepB", PredicateOp.EQ, "done"),),
            ),
        ),
        initial_state=init_state,
        budget=AutonomyBudget(max_steps=20),
    )

    port = SimulatedExecutionPort(
        initial_state=init_state,
        capability_registry=None,  # runtime will populate or we can provide
    )
    # Give port the capabilities from the request
    from uow.autonomy.model import capability_spec_to_descriptor, CapabilityRegistry
    port.environment.registry = CapabilityRegistry(
        [capability_spec_to_descriptor(c) for c in req.capabilities]
    )

    runtime = AutonomousRuntime(execution_port=port)
    result = runtime.run(req)

    assert result.success is True
    assert result.disposition == TerminalDisposition.COMPLETE
    assert result.final_state.attributes["stepA"] == "done"
    assert result.final_state.attributes["stepB"] == "done"
    assert len(result.transitions) > 0
