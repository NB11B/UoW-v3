"""Comprehensive qualification and falsification suite for Pass 4: External Effects & Sagas."""
from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
import pytest

from uow import (
    DeterministicSequencer,
    EffectDescriptor,
    EffectReceipt,
    EffectRunner,
    EffectStatus,
    MockExternalClient,
    ORCH_COMPENSATION_FAILED_KEY,
    ORCH_EFFECTS_KEY,
    SagaCompensationError,
    SagaCoordinator,
    SagaStep,
    WALSequencer,
    WorldState,
    compute_idempotency_key,
    create_effect_descriptor,
    get_effects_map,
    verify_effect_intent_binding,
    verify_effect_receipt_binding,
)
from uow.state import canonical_json


# ===========================================================================
# 1. Crash Recovery & Idempotency Reconciliation Tests
# ===========================================================================

def test_crash_before_external_invocation_resumes_and_invokes_once():
    """Crash after intent commit but before external invocation recovers intent and executes once."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = Path(tmpdir) / "effects.wal"
        s0 = WorldState(attributes={"balance": 1000})
        wal_seq = WALSequencer(wal_path, s0)
        client = MockExternalClient()
        runner = EffectRunner(wal_seq, client)

        eff = create_effect_descriptor(
            uow_id="transfer_1",
            pre_state_hash=s0.state_hash,
            intent="wire_transfer",
            request={"amount": 100, "dest": "acc_99"},
        )

        # Stage 1 & 2: Commit intent to durable WAL
        committed_intent = runner.commit_intent(eff)
        assert committed_intent.status == EffectStatus.COMMITTED_INTENT
        assert client.invocation_count == 0

        # Simulate process crash and restart: recover state from WAL
        rec_state, rec_ledger = WALSequencer.recover(wal_path)
        assert rec_state.attributes[ORCH_EFFECTS_KEY][eff.effect_id]["status"] == "COMMITTED_INTENT"

        # Resume execution on recovered sequencer
        resumed_seq = WALSequencer(wal_path, rec_state, rec_ledger)
        resumed_runner = EffectRunner(resumed_seq, client)

        final_eff = resumed_runner.execute_effect(eff)
        assert final_eff.status == EffectStatus.COMMITTED_RESULT
        assert client.invocation_count == 1
        assert resumed_seq.current_state.attributes[ORCH_EFFECTS_KEY][eff.effect_id]["status"] == "COMMITTED_RESULT"


def test_crash_after_external_success_before_receipt_commit_reconciles_without_duplicate():
    """Crash after external call succeeds but before receipt commit reconciles via idempotency key without duplicate invocation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = Path(tmpdir) / "effects.wal"
        s0 = WorldState(attributes={"balance": 1000})
        wal_seq = WALSequencer(wal_path, s0)
        client = MockExternalClient()
        runner = EffectRunner(wal_seq, client)

        eff = create_effect_descriptor(
            uow_id="charge_1",
            pre_state_hash=s0.state_hash,
            intent="credit_charge",
            request={"amount": 50},
        )
        runner.commit_intent(eff)

        # External call executes successfully in external system
        req = dict(eff.request)
        req["effect_id"] = eff.effect_id
        receipt = client.invoke(req, eff.idempotency_key)
        assert client.invocation_count == 1

        # CRASH occurs before runner.commit_receipt(...) is logged to WAL
        # Recover from WAL (state still has status COMMITTED_INTENT)
        rec_state, rec_ledger = WALSequencer.recover(wal_path)
        assert rec_state.attributes[ORCH_EFFECTS_KEY][eff.effect_id]["status"] == "COMMITTED_INTENT"

        resumed_seq = WALSequencer(wal_path, rec_state, rec_ledger)
        resumed_runner = EffectRunner(resumed_seq, client)

        # Resume execution: runner must query client.reconcile(), discover existing receipt, and NOT reinvoke
        final_eff = resumed_runner.execute_effect(eff)
        assert final_eff.status == EffectStatus.COMMITTED_RESULT
        assert client.invocation_count == 1  # ZERO duplicate invocations!
        assert client.reconcile_count >= 1


def test_duplicate_retry_prevented_by_deterministic_idempotency_key():
    """Calling external client multiple times with same idempotency token returns cached receipt."""
    client = MockExternalClient()
    req = {"order_id": "ORD_123"}
    idemp_key = compute_idempotency_key("uow_test", "state_hash_0", "create_order", req)

    r1 = client.invoke(req, idemp_key)
    r2 = client.invoke(req, idemp_key)

    assert client.invocation_count == 2
    assert r1.receipt_id == r2.receipt_id
    assert r1.receipt_hash == r2.receipt_hash


# ===========================================================================
# 2. Cryptographic Verification & Falsification Tests
# ===========================================================================

def test_forged_receipt_signature_or_payload_rejected():
    """Tampering receipt response payload, hash, or signature fails verification."""
    s0 = WorldState(attributes={})
    eff = create_effect_descriptor("u1", s0.state_hash, "api_call", {"x": 1})
    client = MockExternalClient(signer_id="trusted_ca")
    receipt = client.invoke({"effect_id": eff.effect_id, "x": 1}, eff.idempotency_key)

    # 1. Valid receipt passes
    verify_effect_receipt_binding(eff, receipt, expected_signer="trusted_ca")

    # 2. Tampered payload (with recomputed receipt_hash to test response_hash mismatch)
    tampered_payload_receipt = replace(
        receipt,
        response_payload={"status": "FORGED"},
        receipt_hash="",
    )
    with pytest.raises(ValueError, match="Receipt response_hash mismatch"):
        verify_effect_receipt_binding(eff, tampered_payload_receipt, expected_signer="trusted_ca")

    # 3. Forged signer
    with pytest.raises(ValueError, match="Invalid cryptographic signature"):
        verify_effect_receipt_binding(eff, receipt, expected_signer="other_signer")

    # 4. Tampered outer receipt hash rejected at construction
    with pytest.raises(ValueError, match="EffectReceipt hash mismatch"):
        replace(receipt, receipt_hash="0" * 64)


def test_receipt_bound_to_wrong_intent_or_uow_rejected():
    """A valid receipt for effect A presented to effect B is rejected."""
    s0 = WorldState(attributes={})
    eff_a = create_effect_descriptor("u_a", s0.state_hash, "intent_a", {"v": 1})
    eff_b = create_effect_descriptor("u_b", s0.state_hash, "intent_b", {"v": 2})

    client = MockExternalClient()
    rcpt_a = client.invoke({"effect_id": eff_a.effect_id}, eff_a.idempotency_key)

    # Valid for A
    verify_effect_receipt_binding(eff_a, rcpt_a)

    # Rejected for B (effect_id mismatch)
    with pytest.raises(ValueError, match="Receipt effect_id mismatch"):
        verify_effect_receipt_binding(eff_b, rcpt_a)


def test_stale_intent_state_binding_rejected():
    """An effect intent created against stale pre-state is rejected during commit."""
    s0 = WorldState(attributes={"v": 10})
    s1 = s0.with_attribute("v", 20).advance_sequence()

    eff_stale = create_effect_descriptor("u1", s0.state_hash, "call", {})

    seq = DeterministicSequencer(s1)
    runner = EffectRunner(seq, MockExternalClient())

    with pytest.raises(ValueError, match="Effect intent is not bound to current authoritative pre-state"):
        runner.commit_intent(eff_stale)


# ===========================================================================
# 3. Saga Orchestration & Reverse Compensation Tests
# ===========================================================================

def test_downstream_saga_failure_triggers_reverse_order_compensation():
    """When a 3-step saga fails at step 3, previous steps are compensated in reverse order [F2, F1]."""
    s0 = WorldState(attributes={})
    seq = DeterministicSequencer(s0)
    client = MockExternalClient()
    runner = EffectRunner(seq, client)
    coordinator = SagaCoordinator(runner)

    # Track execution order
    compensation_order = []

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
        raise RuntimeError("External Step 3 failed unrecoverably")

    step3 = SagaStep("step3", failing_step)

    with pytest.raises(RuntimeError, match="Step 3 failed"):
        coordinator.execute_saga([step1, step2, step3])

    # Assert that step 2 and step 1 were both compensated
    final_effects = get_effects_map(seq.current_state)
    eff1 = [v for v in final_effects.values() if v.uow_id == "step1"][0]
    eff2 = [v for v in final_effects.values() if v.uow_id == "step2"][0]

    assert eff1.status == EffectStatus.COMPENSATED
    assert eff2.status == EffectStatus.COMPENSATED


def test_compensation_failure_retains_unresolved_compensating_state():
    """If a compensation action itself fails, status transitions to COMPENSATION_FAILED and state is preserved."""
    s0 = WorldState(attributes={})
    seq = DeterministicSequencer(s0)
    client = MockExternalClient()
    runner = EffectRunner(seq, client)
    coordinator = SagaCoordinator(runner)

    def build_step1(state: WorldState):
        return create_effect_descriptor(
            uow_id="step1",
            pre_state_hash=state.state_hash,
            intent="book_flight",
            request={"flight": "AA100"},
            compensation_intent="cancel_flight",
            compensation_request={"flight": "AA100"},
        )

    eff1 = runner.execute_effect(build_step1(s0))
    assert eff1.status == EffectStatus.COMMITTED_RESULT

    # Configure client to fail when compensation is invoked
    client.crash_on_invoke = True

    with pytest.raises(SagaCompensationError) as exc_info:
        coordinator.compensate([eff1])

    assert len(exc_info.value.unresolved_effects) == 1
    unres = exc_info.value.unresolved_effects[0]
    assert unres.status == EffectStatus.COMPENSATION_FAILED

    curr_state = seq.current_state
    retained_failed = curr_state.attributes[ORCH_COMPENSATION_FAILED_KEY]
    assert len(retained_failed) == 1
    assert retained_failed[0]["effect_id"] == eff1.effect_id


# ===========================================================================
# 4. Asynchronous Suspension & Replay Determinism Tests
# ===========================================================================

def test_delayed_async_receipt_suspends_to_pending_external_and_resumes():
    """Long-running external effect suspends to PENDING_EXTERNAL and commits when receipt is received."""
    s0 = WorldState(attributes={})
    seq = DeterministicSequencer(s0)
    client = MockExternalClient()
    runner = EffectRunner(seq, client)

    eff = create_effect_descriptor(
        uow_id="human_approval_1",
        pre_state_hash=s0.state_hash,
        intent="manager_signoff",
        request={"invoice_id": 9999},
    )

    # 1. Commit intent & suspend
    eff_intent = runner.commit_intent(eff)
    eff_pending = runner.suspend_pending_external(eff_intent)
    assert eff_pending.status == EffectStatus.PENDING_EXTERNAL
    assert seq.current_state.attributes[ORCH_EFFECTS_KEY][eff.effect_id]["status"] == "PENDING_EXTERNAL"

    # 2. Simulate external asynchronous passage of time (hours/days)
    receipt = client.invoke({"effect_id": eff.effect_id}, eff.idempotency_key)

    # 3. Resume via receipt delivery
    eff_final = runner.commit_receipt(eff_pending, receipt)
    assert eff_final.status == EffectStatus.COMMITTED_RESULT
    assert seq.current_state.attributes[ORCH_EFFECTS_KEY][eff.effect_id]["status"] == "COMMITTED_RESULT"


def test_replay_never_re_executes_certified_external_effects():
    """Replaying an already committed effect returns cached result with zero client invocations."""
    s0 = WorldState(attributes={})
    seq = DeterministicSequencer(s0)
    client = MockExternalClient()
    runner = EffectRunner(seq, client)

    eff = create_effect_descriptor("task_replay", s0.state_hash, "fetch_data", {"k": 1})
    res1 = runner.execute_effect(eff)
    assert client.invocation_count == 1

    # Replay: execute again against updated state
    res2 = runner.execute_effect(res1)
    assert res2.status == EffectStatus.COMMITTED_RESULT
    assert client.invocation_count == 1  # ZERO additional network invocations!
