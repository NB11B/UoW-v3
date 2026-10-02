from __future__ import annotations

import inspect

import uow
from uow.compat.v2 import (
    DeterministicSequencer,
    EffectRunner,
    EffectStatus,
    MockExternalClient,
    WorldState,
    create_effect_descriptor,
)
from uow.implementations.effects.runner import (
    EffectRunner as ImplEffectRunner,
    MockExternalClient as ImplMockClient,
)


def _initial():
    return WorldState(
        attributes={"business_state": "open"},
        cursor="workflow-main",
        status="RUNNING",
    )


def test_s4_effect_import_paths_remain_identity_compatible():
    assert EffectRunner is ImplEffectRunner
    assert MockExternalClient is ImplMockClient
    assert uow.EffectRunner is ImplEffectRunner
    assert uow.MockExternalClient is ImplMockClient


def test_s4_historical_effect_runner_is_only_shim():
    import uow.effects.runner as shim

    source = inspect.getsource(shim)
    assert "class EffectRunner" not in source
    assert "class MockExternalClient" not in source
    assert "implementations.effects.runner" in source


def test_s4_effect_implementation_preserves_external_nonclosure_boundary():
    import uow.implementations.effects.runner as implementation

    source = inspect.getsource(implementation)
    assert source.count("DEFAULT_APPLICATION_SPINE.execute") == 3
    assert "CursorPolicy.DETACHED" in source
    assert "self.client.invoke(" in source
    assert "self.client.reconcile(" in source
    assert "self.sequencer.commit(" not in source


def test_s4_effect_lifecycle_preserves_cursor_and_idempotent_external_call():
    initial = _initial()
    seq = DeterministicSequencer(initial)
    client = MockExternalClient()
    runner = EffectRunner(seq, client)

    effect = create_effect_descriptor(
        "workflow-main",
        initial.state_hash,
        "send",
        {"amount": 1},
    )
    result = runner.execute_effect(effect)

    assert result.status is EffectStatus.COMMITTED_RESULT
    assert seq.current_state.cursor == "workflow-main"
    assert seq.current_state.status == "RUNNING"
    assert client.invocation_count == 1
    assert seq.ledger.verify_integrity()

    again = runner.execute_effect(effect)
    assert again.status is EffectStatus.COMMITTED_RESULT
    assert client.invocation_count == 1


def test_s4_effect_crash_window_reconciles_without_duplicate_invoke():
    initial = _initial()
    seq = DeterministicSequencer(initial)
    client = MockExternalClient()
    runner = EffectRunner(seq, client)

    effect = create_effect_descriptor(
        "workflow-main",
        initial.state_hash,
        "send",
        {"amount": 2},
    )
    committed = runner.commit_intent(effect)

    request = dict(committed.request)
    request["effect_id"] = committed.effect_id
    receipt = client.invoke(request, committed.idempotency_key)
    assert client.invocation_count == 1

    # Simulate restart after external success but before internal result commit.
    restarted = EffectRunner(seq, client)
    result = restarted.execute_effect(effect)

    assert result.status is EffectStatus.COMMITTED_RESULT
    assert result.receipt is not None
    assert result.receipt.receipt_hash == receipt.receipt_hash
    assert client.invocation_count == 1
    assert client.reconcile_count >= 1
    assert seq.current_state.cursor == "workflow-main"
    assert seq.ledger.verify_integrity()
