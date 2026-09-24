from __future__ import annotations

import pytest

from uow import (
    EffectStatus,
    MockExternalClient,
    SagaCompensationError,
    SagaStep,
    WorldState,
    create_effect_descriptor,
    get_effects_map,
    get_sagas_map,
)

from uow_shadow.effects_reconstruction import ShadowEffectRuntime, ShadowSagaCoordinator


def test_r4_q1_effect_intent_and_result_use_shadow_authority_but_external_call_stays_external():
    initial = WorldState(
        attributes={"balance": 100},
        cursor="task-active",
        status="RUNNING",
    )
    client = MockExternalClient()
    runtime = ShadowEffectRuntime(initial, client)

    effect = create_effect_descriptor(
        "payment",
        initial.state_hash,
        "charge",
        {"amount": 10},
    )

    committed_intent = runtime.commit_intent(effect)
    assert committed_intent.status == EffectStatus.COMMITTED_INTENT
    assert runtime.state.cursor == "task-active"
    assert runtime.state.status == "RUNNING"
    assert client.invocation_count == 0

    request = dict(effect.request)
    request["effect_id"] = effect.effect_id
    receipt = client.invoke(request, effect.idempotency_key)

    # External reality has changed, but authoritative internal state still records
    # only committed intent until receipt certification/result commit.
    assert client.invocation_count == 1
    assert get_effects_map(runtime.state)[effect.effect_id].status == EffectStatus.COMMITTED_INTENT

    result = runtime.commit_receipt(committed_intent, receipt)
    assert result.status == EffectStatus.COMMITTED_RESULT
    assert get_effects_map(runtime.state)[effect.effect_id].status == EffectStatus.COMMITTED_RESULT
    assert runtime.state.cursor == "task-active"
    assert runtime.state.status == "RUNNING"
    assert len(runtime.evidence) == 2


def test_r4_q1_crash_window_reconciles_without_duplicate_external_invocation():
    initial = WorldState(attributes={}, cursor="controller", status="RUNNING")
    client = MockExternalClient()
    runtime = ShadowEffectRuntime(initial, client)
    effect = create_effect_descriptor(
        "order",
        initial.state_hash,
        "place_order",
        {"sku": "A"},
    )

    committed_intent = runtime.commit_intent(effect)
    request = dict(effect.request)
    request["effect_id"] = effect.effect_id
    client.invoke(request, effect.idempotency_key)
    assert client.invocation_count == 1

    # Simulated process restart after external success but before internal result commit.
    resumed = ShadowEffectRuntime(runtime.state, client)
    result = resumed.execute_effect(effect)

    assert result.status == EffectStatus.COMMITTED_RESULT
    assert client.invocation_count == 1
    assert client.reconcile_count >= 1


def test_r4_q1_receipt_without_committed_intent_is_rejected():
    initial = WorldState(attributes={})
    client = MockExternalClient()
    runtime = ShadowEffectRuntime(initial, client)
    effect = create_effect_descriptor(
        "uncommitted",
        initial.state_hash,
        "call",
        {"x": 1},
    )
    receipt = client.invoke({"effect_id": effect.effect_id}, effect.idempotency_key)

    with pytest.raises(ValueError, match="previously committed authoritative intent"):
        runtime.commit_receipt(effect, receipt)


def _compensable_step(name: str):
    def build(state: WorldState):
        return create_effect_descriptor(
            name,
            state.state_hash,
            f"do_{name}",
            {"step": name},
            compensation_intent=f"undo_{name}",
            compensation_request={"step": name, "undo": True},
        )

    return SagaStep(name, build)


def test_r4_q1_saga_compensation_runs_in_reverse_order():
    runtime = ShadowEffectRuntime(WorldState(attributes={}), MockExternalClient())
    saga = ShadowSagaCoordinator(runtime)

    def fail(_state: WorldState):
        raise RuntimeError("injected step failure")

    with pytest.raises(RuntimeError, match="injected step failure"):
        saga.execute_saga(
            [
                _compensable_step("step1"),
                _compensable_step("step2"),
                SagaStep("step3", fail),
            ],
            saga_id="reverse-order",
        )

    comp_calls = [c for c in runtime.client.call_log if c["is_compensation"]]
    assert len(comp_calls) == 2
    assert "step2" in comp_calls[0]["effect_id"]
    assert "step1" in comp_calls[1]["effect_id"]

    effects = get_effects_map(runtime.state)
    forward = [e for e in effects.values() if e.uow_id in ("step1", "step2")]
    assert len(forward) == 2
    assert all(e.status == EffectStatus.COMPENSATED for e in forward)
    assert get_sagas_map(runtime.state)["reverse-order"].status.value == "COMPENSATED"


class _FailCompensationClient(MockExternalClient):
    def invoke(self, request, idempotency_key):
        if request.get("is_compensation"):
            raise ConnectionError("compensation unavailable")
        return super().invoke(request, idempotency_key)


def test_r4_q1_compensation_failure_is_preserved_not_erased():
    runtime = ShadowEffectRuntime(WorldState(attributes={}), _FailCompensationClient())
    saga = ShadowSagaCoordinator(runtime)

    def fail(_state: WorldState):
        raise RuntimeError("forward failure")

    with pytest.raises(SagaCompensationError):
        saga.execute_saga(
            [
                _compensable_step("step1"),
                SagaStep("step2", fail),
            ],
            saga_id="failed-compensation",
        )

    effects = get_effects_map(runtime.state)
    forward = [e for e in effects.values() if e.uow_id == "step1"]
    assert len(forward) == 1
    assert forward[0].status == EffectStatus.COMPENSATION_FAILED

    saga_record = get_sagas_map(runtime.state)["failed-compensation"]
    assert saga_record.status.value == "COMPENSATION_FAILED"
    assert saga_record.unresolved_effects


def test_r4_q1_duplicate_completed_effect_replay_does_not_reinvoke_external_system():
    initial = WorldState(attributes={})
    client = MockExternalClient()
    runtime = ShadowEffectRuntime(initial, client)
    effect = create_effect_descriptor(
        "notify",
        initial.state_hash,
        "notify",
        {"msg": "hello"},
    )

    first = runtime.execute_effect(effect)
    count = client.invocation_count
    second = runtime.execute_effect(effect)

    assert first.receipt.receipt_hash == second.receipt.receipt_hash
    assert client.invocation_count == count
