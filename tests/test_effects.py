"""Comprehensive qualification and falsification suite for Pass 4.1: Hardened External Effects & Sagas."""
from dataclasses import replace
import hashlib
import hmac
from pathlib import Path
import tempfile
import time
import pytest

from uow import (
    DeterministicSequencer,
    EffectDescriptor,
    EffectReceipt,
    EffectRunner,
    EffectStatus,
    HMACReceiptAuthenticator,
    LEGAL_EFFECT_TRANSITIONS,
    MockExternalClient,
    ORCH_COMPENSATION_FAILED_KEY,
    ORCH_EFFECTS_KEY,
    ORCH_SAGAS_KEY,
    PrefixReceiptAuthenticator,
    SagaCompensationError,
    SagaCoordinator,
    SagaRecord,
    SagaStatus,
    SagaStep,
    WALSequencer,
    WorldState,
    compute_idempotency_key,
    create_effect_descriptor,
    get_effects_map,
    get_sagas_map,
    verify_effect_intent_binding,
    verify_effect_receipt_binding,
)
from uow.state import canonical_json


# ===========================================================================
# Test 1: Control-state preservation across effect and saga lifecycle
# ===========================================================================

def test_control_state_preserved_across_effect_and_saga_lifecycle():
    """Bookkeeping transitions preserve enclosing WorldState.status and WorldState.cursor."""
    s0 = WorldState(
        status="RUNNING",
        cursor="task_active_alpha",
        attributes={"balance": 1000},
    )
    seq = DeterministicSequencer(s0)
    client = MockExternalClient()
    runner = EffectRunner(seq, client)
    coordinator = SagaCoordinator(runner)

    eff = create_effect_descriptor(
        uow_id="ctrl_preserve_1",
        pre_state_hash=s0.state_hash,
        intent="authorize_payment",
        request={"amount": 100},
        compensation_intent="void_payment",
        compensation_request={"amount": 100},
    )

    # 1. Intent commit preserves status and cursor
    committed_intent = runner.commit_intent(eff)
    s_intent = seq.current_state
    assert s_intent.status == "RUNNING"
    assert s_intent.cursor == "task_active_alpha"

    # 2. Suspend to PENDING_EXTERNAL preserves status and cursor
    eff_pending = runner.suspend_pending_external(committed_intent)
    s_pending = seq.current_state
    assert s_pending.status == "RUNNING"
    assert s_pending.cursor == "task_active_alpha"

    # 3. Receipt commit preserves status and cursor
    receipt = client.invoke({"effect_id": eff.effect_id}, eff.idempotency_key)
    eff_result = runner.commit_receipt(eff_pending, receipt)
    s_result = seq.current_state
    assert s_result.status == "RUNNING"
    assert s_result.cursor == "task_active_alpha"

    # 4. Multi-step saga execution preserves status and cursor
    def build_step(state: WorldState):
        return create_effect_descriptor(
            uow_id="saga_step_alpha",
            pre_state_hash=state.state_hash,
            intent="notify_user",
            request={"msg": "hello"},
        )

    step = SagaStep("notify", build_step)
    coordinator.execute_saga([step], saga_id="ctrl_saga")
    s_saga = seq.current_state
    assert s_saga.status == "RUNNING"
    assert s_saga.cursor == "task_active_alpha"


# ===========================================================================
# Test 2: Receipt without committed intent is rejected
# ===========================================================================

def test_receipt_without_committed_intent_rejected():
    """Attempting to commit a receipt without prior authoritative intent is rejected."""
    s0 = WorldState(attributes={})
    seq = DeterministicSequencer(s0)
    client = MockExternalClient()
    runner = EffectRunner(seq, client)

    eff = create_effect_descriptor("uncommitted_1", s0.state_hash, "api_call", {"x": 1})
    receipt = client.invoke({"effect_id": eff.effect_id}, eff.idempotency_key)

    with pytest.raises(ValueError, match="no previously committed authoritative intent"):
        runner.commit_receipt(eff, receipt)


# ===========================================================================
# Test 3: Suspend uncommitted effect is rejected
# ===========================================================================

def test_suspend_uncommitted_effect_rejected():
    """Attempting to suspend an effect not found in authoritative state is rejected."""
    s0 = WorldState(attributes={})
    seq = DeterministicSequencer(s0)
    runner = EffectRunner(seq, MockExternalClient())

    eff = create_effect_descriptor("uncommitted_2", s0.state_hash, "async_task", {"y": 2})

    with pytest.raises(ValueError, match="Cannot suspend uncommitted effect"):
        runner.suspend_pending_external(eff)


# ===========================================================================
# Test 4: Reuse effect_id with different request/idempotency key is rejected
# ===========================================================================

def test_reuse_effect_id_with_different_request_or_idempotency_key_rejected():
    """Reusing the same effect_id with different request payloads or idempotency keys is rejected."""
    s0 = WorldState(attributes={})
    seq = DeterministicSequencer(s0)
    runner = EffectRunner(seq, MockExternalClient())

    eff1 = create_effect_descriptor(
        uow_id="fixed_eff",
        pre_state_hash=s0.state_hash,
        intent="create_invoice",
        request={"amount": 100},
        effect_id="eff::reused_id",
    )
    runner.commit_intent(eff1)

    # Attempt to commit different request under the same effect_id
    eff2 = create_effect_descriptor(
        uow_id="fixed_eff",
        pre_state_hash=s0.state_hash,
        intent="create_invoice",
        request={"amount": 999},  # Altered amount
        effect_id="eff::reused_id",
    )

    with pytest.raises(ValueError, match="Cannot reuse effect_id"):
        runner.commit_intent(eff2)


# ===========================================================================
# Test 5: Illegal effect-status transitions rejected
# ===========================================================================

def test_illegal_effect_status_transition_rejected():
    """Strict lifecycle transition graph enforces valid state progression."""
    s0 = WorldState(attributes={})
    seq = DeterministicSequencer(s0)
    client = MockExternalClient()
    runner = EffectRunner(seq, client)

    eff = create_effect_descriptor("lifecycle_test", s0.state_hash, "op", {"k": 1})
    runner.execute_effect(eff)
    assert get_effects_map(seq.current_state)[eff.effect_id].status == EffectStatus.COMMITTED_RESULT

    # Illegal transition 1: Cannot suspend an already completed effect
    with pytest.raises(ValueError, match="Cannot suspend effect from status 'COMMITTED_RESULT'"):
        runner.suspend_pending_external(eff)


# ===========================================================================
# Test 6: Compensation receipt with wrong idempotency key rejected
# ===========================================================================

def test_compensation_receipt_with_wrong_idempotency_key_rejected():
    """Compensation receipts presented with mismatched idempotency keys are rejected."""
    s0 = WorldState(attributes={})
    seq = DeterministicSequencer(s0)
    client = MockExternalClient()
    runner = EffectRunner(seq, client)

    eff = create_effect_descriptor(
        uow_id="order_op",
        pre_state_hash=s0.state_hash,
        intent="place_order",
        request={"item": "widget"},
        compensation_intent="cancel_order",
        compensation_request={"item": "widget"},
    )
    comp_spec = eff.compensation
    assert comp_spec is not None

    comp_eff = EffectDescriptor(
        effect_id=f"comp::{eff.effect_id}",
        uow_id=f"{eff.uow_id}::comp",
        intent=comp_spec.intent,
        idempotency_key=comp_spec.idempotency_key,
        request=dict(comp_spec.request),
        status=EffectStatus.INTENDED,
        pre_state_hash=eff.pre_state_hash,
    )

    # Generate a receipt with a mismatched/forged idempotency key
    forged_receipt = client.invoke(
        {"effect_id": comp_eff.effect_id, "is_compensation": True},
        "forged_idempotency_key_xyz",
    )

    with pytest.raises(ValueError, match="Receipt idempotency key mismatch"):
        verify_effect_receipt_binding(comp_eff, forged_receipt)


# ===========================================================================
# Test 7: Compensation receipt payload tampering and HMAC verification
# ===========================================================================

def test_compensation_receipt_payload_tampering_and_hmac_rejected():
    """Tampering receipt response payload and invalid HMAC signatures are rejected."""
    s0 = WorldState(attributes={})
    secret = b"super_secure_key_1234567890123456"
    auth = HMACReceiptAuthenticator(secret)

    eff = create_effect_descriptor("auth_op", s0.state_hash, "transfer", {"v": 50})

    # Create valid HMAC signed receipt
    payload = {"status": "SUCCESS", "tx": "0xabc"}
    payload_hash = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    ts = str(int(time.time()))

    unsigned_rcpt = EffectReceipt(
        receipt_id="rcpt::1",
        effect_id=eff.effect_id,
        idempotency_key=eff.idempotency_key,
        response_payload=payload,
        response_hash=payload_hash,
        timestamp=ts,
    )
    sig = auth.sign(unsigned_rcpt)
    valid_rcpt = replace(unsigned_rcpt, signature=sig, receipt_hash="")

    # 1. Valid HMAC receipt passes
    verify_effect_receipt_binding(eff, valid_rcpt, authenticator=auth)

    # 2. Tampered response payload rejected
    tampered_payload = replace(
        valid_rcpt,
        response_payload={"status": "TAMPERED"},
        receipt_hash="",
    )
    with pytest.raises(ValueError, match="Receipt response_hash mismatch"):
        verify_effect_receipt_binding(eff, tampered_payload, authenticator=auth)

    # 3. Forged HMAC signature rejected
    bad_sig_rcpt = replace(
        valid_rcpt,
        signature="bad_hmac_signature_value",
        receipt_hash="",
    )
    with pytest.raises(ValueError, match="HMAC signature mismatch"):
        verify_effect_receipt_binding(eff, bad_sig_rcpt, authenticator=auth)


# ===========================================================================
# Test 8: Exact compensation invocation order is [F_2^{-1}, F_1^{-1}]
# ===========================================================================

def test_exact_compensation_invocation_order_is_reverse():
    """When a 3-step saga fails at step 3, compensation is invoked in strict reverse order [F2, F1]."""
    s0 = WorldState(attributes={})
    seq = DeterministicSequencer(s0)
    client = MockExternalClient()
    runner = EffectRunner(seq, client)
    coordinator = SagaCoordinator(runner)

    def make_step(name: str):
        def build(state: WorldState):
            return create_effect_descriptor(
                uow_id=name,
                pre_state_hash=state.state_hash,
                intent=f"exec_{name}",
                request={"step": name},
                compensation_intent=f"undo_{name}",
                compensation_request={"step": name, "undo": True},
            )
        return SagaStep(name, build)

    step1 = make_step("step1")
    step2 = make_step("step2")

    def failing_step(state: WorldState):
        raise RuntimeError("Step 3 simulated failure")

    step3 = SagaStep("step3", failing_step)

    with pytest.raises(RuntimeError, match="Step 3 simulated failure"):
        coordinator.execute_saga([step1, step2, step3], saga_id="order_saga")

    # Filter client call_log for compensation invocations
    comp_calls = [c for c in client.call_log if c["is_compensation"]]
    assert len(comp_calls) == 2

    # Verify exact reverse order: F2 compensated first, then F1
    assert "step2" in comp_calls[0]["effect_id"]
    assert "step1" in comp_calls[1]["effect_id"]

    # Verify final states of step 1 and step 2 are COMPENSATED
    final_effects = get_effects_map(seq.current_state)
    eff1 = [v for v in final_effects.values() if v.uow_id == "step1"][0]
    eff2 = [v for v in final_effects.values() if v.uow_id == "step2"][0]
    assert eff1.status == EffectStatus.COMPENSATED
    assert eff2.status == EffectStatus.COMPENSATED
    assert eff1.compensation_effect_id == f"comp::{eff1.effect_id}"
    assert eff2.compensation_effect_id == f"comp::{eff2.effect_id}"


# ===========================================================================
# Test 9: Crash between steps recovers saga progress from WorldState
# ===========================================================================

def test_crash_between_steps_recovers_saga_progress_from_world_state():
    """Crash after step 1 and step 2 durably recovers completed effects and step index from WorldState."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = Path(tmpdir) / "saga_recovery.wal"
        s0 = WorldState(attributes={})
        seq = WALSequencer(wal_path, s0)
        client = MockExternalClient()
        runner = EffectRunner(seq, client)
        coordinator = SagaCoordinator(runner)

        def make_step(name: str):
            def build(state: WorldState):
                return create_effect_descriptor(
                    uow_id=name,
                    pre_state_hash=state.state_hash,
                    intent=f"exec_{name}",
                    request={"name": name},
                )
            return SagaStep(name, build)

        step1 = make_step("step1")
        step2 = make_step("step2")

        # Execute only step 1 and step 2
        coordinator.execute_saga([step1, step2], saga_id="durable_saga")

        # Simulate process crash: recover authoritative state from durable WAL
        rec_state, rec_ledger = WALSequencer.recover(wal_path)
        rec_sagas = get_sagas_map(rec_state)
        assert "durable_saga" in rec_sagas

        record = rec_sagas["durable_saga"]
        assert record.status == SagaStatus.COMPLETED
        assert record.current_step_index == 2
        assert len(record.completed_effects) == 2


# ===========================================================================
# Test 10: Crash after durable COMPENSATING resumes correctly
# ===========================================================================

def test_crash_after_durable_compensating_resumes_correctly():
    """Crash after effect is marked COMPENSATING in WorldState resumes compensation to completion."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = Path(tmpdir) / "comp_resume.wal"
        s0 = WorldState(attributes={})
        seq = WALSequencer(wal_path, s0)
        client = MockExternalClient()
        runner = EffectRunner(seq, client)
        coordinator = SagaCoordinator(runner)

        eff = runner.execute_effect(
            create_effect_descriptor(
                uow_id="c_step1",
                pre_state_hash=s0.state_hash,
                intent="reserve_hotel",
                request={"room": 101},
                compensation_intent="cancel_hotel",
                compensation_request={"room": 101},
            )
        )
        assert eff.status == EffectStatus.COMMITTED_RESULT

        # Durably mark effect as COMPENSATING in WAL before crash
        coordinator._set_effect_status(eff, EffectStatus.COMPENSATING)

        # Simulate crash and recovery from WAL
        rec_state, rec_ledger = WALSequencer.recover(wal_path)
        assert rec_state.attributes[ORCH_EFFECTS_KEY][eff.effect_id]["status"] == "COMPENSATING"

        # Resume compensation on recovered sequencer
        resumed_seq = WALSequencer(wal_path, rec_state, rec_ledger)
        resumed_runner = EffectRunner(resumed_seq, client)
        resumed_coordinator = SagaCoordinator(resumed_runner)

        compensated = resumed_coordinator.compensate([eff], saga_id="c_saga")
        assert len(compensated) == 1
        assert compensated[0].status == EffectStatus.COMPENSATED

        final_state = resumed_seq.current_state
        assert final_state.attributes[ORCH_EFFECTS_KEY][eff.effect_id]["status"] == "COMPENSATED"
        assert get_sagas_map(final_state)["c_saga"].status == SagaStatus.COMPENSATED


# ===========================================================================
# Test 11: Crash after compensation succeeds externally reconciles without duplicate
# ===========================================================================

def test_crash_after_compensation_succeeds_externally_reconciles_without_duplicate():
    """Crash after external compensation invocation reconciles via idempotency key without duplicate invocation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = Path(tmpdir) / "comp_reconcile.wal"
        s0 = WorldState(attributes={})
        seq = WALSequencer(wal_path, s0)
        client = MockExternalClient()
        runner = EffectRunner(seq, client)
        coordinator = SagaCoordinator(runner)

        eff = runner.execute_effect(
            create_effect_descriptor(
                uow_id="recon_step",
                pre_state_hash=s0.state_hash,
                intent="debit_account",
                request={"acc": "A", "val": 200},
                compensation_intent="credit_account",
                compensation_request={"acc": "A", "val": 200},
            )
        )

        # External undo call executes successfully in client
        comp_spec = eff.compensation
        assert comp_spec is not None
        comp_req = dict(comp_spec.request)
        comp_req["effect_id"] = f"comp::{eff.effect_id}"
        comp_req["is_compensation"] = True
        client.invoke(comp_req, comp_spec.idempotency_key)
        invocations_after_undo = client.invocation_count

        # Simulate crash before result is committed to WAL: recover state
        rec_state, rec_ledger = WALSequencer.recover(wal_path)
        resumed_seq = WALSequencer(wal_path, rec_state, rec_ledger)
        resumed_runner = EffectRunner(resumed_seq, client)
        resumed_coordinator = SagaCoordinator(resumed_runner)

        # Resume compensation: must reconcile without duplicate external call
        resumed_coordinator.compensate([eff], saga_id="recon_saga")

        assert client.invocation_count == invocations_after_undo  # ZERO duplicate invocations!
        assert client.reconcile_count >= 1
        assert resumed_seq.current_state.attributes[ORCH_EFFECTS_KEY][eff.effect_id]["status"] == "COMPENSATED"


# ===========================================================================
# Test 12: Replay completed saga makes zero external calls
# ===========================================================================

def test_replay_completed_saga_makes_zero_external_calls():
    """Replaying an already completed saga returns completed effects with zero additional network calls."""
    s0 = WorldState(attributes={})
    seq = DeterministicSequencer(s0)
    client = MockExternalClient()
    runner = EffectRunner(seq, client)
    coordinator = SagaCoordinator(runner)

    def make_step(name: str):
        def build(state: WorldState):
            return create_effect_descriptor(
                uow_id=name,
                pre_state_hash=state.state_hash,
                intent=f"exec_{name}",
                request={"k": name},
            )
        return SagaStep(name, build)

    steps = [make_step("s1"), make_step("s2")]
    res1 = coordinator.execute_saga(steps, saga_id="replay_saga")
    assert len(res1) == 2
    initial_invocations = client.invocation_count
    assert initial_invocations == 2

    # Replay saga execution
    res2 = coordinator.execute_saga(steps, saga_id="replay_saga")
    assert len(res2) == 2
    assert client.invocation_count == initial_invocations  # ZERO additional network invocations!


# ===========================================================================
# Fundamental tests preserved from baseline
# ===========================================================================

def test_stale_intent_state_binding_rejected():
    """An effect intent created against stale pre-state is rejected during commit."""
    s0 = WorldState(attributes={"v": 10})
    s1 = s0.with_attribute("v", 20).advance_sequence()
    eff_stale = create_effect_descriptor("u1", s0.state_hash, "call", {})

    seq = DeterministicSequencer(s1)
    runner = EffectRunner(seq, MockExternalClient())

    with pytest.raises(ValueError, match="Effect intent is not bound to current authoritative pre-state"):
        runner.commit_intent(eff_stale)


def test_compensation_failure_retains_unresolved_compensating_state():
    """If a compensation action itself fails, status transitions to COMPENSATION_FAILED and state is preserved."""
    s0 = WorldState(attributes={})
    seq = DeterministicSequencer(s0)
    client = MockExternalClient()
    runner = EffectRunner(seq, client)
    coordinator = SagaCoordinator(runner)

    eff1 = runner.execute_effect(
        create_effect_descriptor(
            uow_id="fail_step1",
            pre_state_hash=s0.state_hash,
            intent="book_flight",
            request={"flight": "AA100"},
            compensation_intent="cancel_flight",
            compensation_request={"flight": "AA100"},
        )
    )
    assert eff1.status == EffectStatus.COMMITTED_RESULT

    # Configure client to fail when compensation is invoked
    client.crash_on_invoke = True

    with pytest.raises(SagaCompensationError) as exc_info:
        coordinator.compensate([eff1], saga_id="fail_saga")

    assert len(exc_info.value.unresolved_effects) == 1
    unres = exc_info.value.unresolved_effects[0]
    assert unres.status == EffectStatus.COMPENSATION_FAILED

    curr_state = seq.current_state
    retained_failed = curr_state.attributes[ORCH_COMPENSATION_FAILED_KEY]
    assert len(retained_failed) == 1
    assert retained_failed[0]["effect_id"] == eff1.effect_id
    assert get_sagas_map(curr_state)["fail_saga"].status == SagaStatus.COMPENSATION_FAILED

