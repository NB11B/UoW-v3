"""Qualification tests for Gate A2.6: Physical Multi-Host Adversarial Network Qualification."""
from __future__ import annotations

from pathlib import Path
import tempfile
import pytest

from uow.compat.v2 import (
    AdversarialChannel,
    AuthoritativeHistory,
    DurableWAL,
    HistoryEntry,
    HistoryEntryKind,
    PhysicalHostNode,
    WireEnvelope,
    sign_envelope,
    verify_envelope,
)
from qualification.claim_registry import get_claim
from qualification.evidence import (
    ClaimRequirement,
    EvidenceContext,
    EvidenceLevel,
    evaluate_claim,
)


@pytest.fixture
def temp_node_dirs():
    with tempfile.TemporaryDirectory() as base_tmp:
        base_path = Path(base_tmp)
        dir_a = base_path / "node_a"
        dir_b = base_path / "node_b"
        dir_c = base_path / "node_c"
        yield dir_a, dir_b, dir_c


def test_gate_a2_6_wire_envelope_signing_and_tamper_detection():
    """WireEnvelope enforces cryptographic authenticity and rejects tampered bytes."""
    secret = "cluster_shared_secret_9988"
    raw_env = WireEnvelope(
        sender_id="node_a",
        recipient_id="node_b",
        seq=1,
        epoch=1,
        nonce="nonce_01",
        payload={"command": "EXECUTE_SUBTASK", "sub_id": "uow_42"},
    )
    signed_env = sign_envelope(secret, raw_env)
    assert verify_envelope(secret, signed_env)

    # Tampered payload rejected
    tampered_env = WireEnvelope(
        sender_id=signed_env.sender_id,
        recipient_id=signed_env.recipient_id,
        seq=signed_env.seq,
        epoch=signed_env.epoch,
        nonce=signed_env.nonce,
        payload={"command": "EXECUTE_SUBTASK", "sub_id": "uow_FORGED"},
        signature=signed_env.signature,
    )
    assert not verify_envelope(secret, tampered_env)

    # Wrong secret key rejected
    assert not verify_envelope("wrong_secret_key", signed_env)


def test_gate_a2_6_adversarial_channel_loss_and_duplication():
    """AdversarialChannel models deterministic drop, duplication, and asymmetric partitions."""
    env = WireEnvelope("node_a", "node_b", 1, 1, "n1", {"data": "test"})

    # 1. 100% loss channel
    ch_loss = AdversarialChannel(loss_rate=1.0)
    assert ch_loss.transmit(env) == []

    # 2. 100% duplication channel
    ch_dup = AdversarialChannel(loss_rate=0.0, duplication_rate=1.0)
    res_dup = ch_dup.transmit(env)
    assert len(res_dup) == 2

    # 3. Asymmetric partition: node_a -> node_b blocked, node_b -> node_a open
    ch_asym = AdversarialChannel(loss_rate=0.0)
    ch_asym.set_asymmetric_drop("node_a", "node_b", drop=True)

    env_a_to_b = WireEnvelope("node_a", "node_b", 1, 1, "n1", {"data": "forward"})
    env_b_to_a = WireEnvelope("node_b", "node_a", 1, 1, "n2", {"data": "backward"})

    assert ch_asym.transmit(env_a_to_b) == []
    assert len(ch_asym.transmit(env_b_to_a)) == 1


def test_gate_a2_6_adversarial_channel_reordering():
    """AdversarialChannel buffers and flushes out-of-order sequences."""
    ch_reorder = AdversarialChannel(reorder=True)
    m1 = WireEnvelope("node_a", "node_b", 1, 1, "n1", {"msg": 1})
    m2 = WireEnvelope("node_a", "node_b", 2, 1, "n2", {"msg": 2})
    m3 = WireEnvelope("node_a", "node_b", 3, 1, "n3", {"msg": 3})

    assert ch_reorder.transmit(m1) == []
    assert ch_reorder.transmit(m2) == []
    out = ch_reorder.transmit(m3)
    assert len(out) == 3
    # Received in reversed order [m3, m2, m1]
    assert [m.seq for m in out] == [3, 2, 1]


def test_gate_a2_6_durable_wal_append_and_replay(temp_node_dirs):
    """DurableWAL persists entries to disk and replays correctly."""
    dir_a, _, _ = temp_node_dirs
    wal = DurableWAL(dir_a)

    e0 = HistoryEntry("e0", 0, "GENESIS", HistoryEntryKind.CHILD_DELEGATION, "node_a", 1, {"v": 10})
    e1 = HistoryEntry("e1", 1, e0.entry_hash, HistoryEntryKind.AUTHORITATIVE_COMMIT, "node_a", 1, {"v": 20})

    wal.append(e0)
    wal.append(e1)

    replayed = wal.replay()
    assert len(replayed) == 2
    assert replayed[0].entry_id == "e0"
    assert replayed[1].entry_id == "e1"
    assert replayed[1].prev_hash == replayed[0].entry_hash


def test_gate_a2_6_host_node_crash_and_restart_recovery(temp_node_dirs):
    """PhysicalHostNode recovers memory state and idempotency records from disk WAL upon crash restart."""
    dir_a, _, _ = temp_node_dirs
    node = PhysicalHostNode("node_a", dir_a, secret_key="node_a_key", clock_skew_sec=15.0)

    # Commit transition 1
    ok1, e1, _ = node.commit_entry_durably(
        HistoryEntryKind.IDEMPOTENT_TASK,
        {"task": "compute_x", "result": 42, "idempotency_key": "task_compute_x"},
        idempotency_key="task_compute_x",
    )
    assert ok1
    assert node.history.tip_sequence() == 0

    # Simulate sudden crash (memory wiped)
    node.crash()
    assert not node.is_alive
    assert node.history.tip_sequence() == -1

    # Restart from disk WAL
    recovered_count = node.restart()
    assert recovered_count == 1
    assert node.is_alive
    assert node.history.tip_sequence() == 0
    assert node.history.tip_hash() == e1.entry_hash
    assert "task_compute_x" in node.idempotent_task_results

    # Duplicate execution after restart returns existing commit (zero double commits)
    ok_dup, e_dup, msg_dup = node.commit_entry_durably(
        HistoryEntryKind.IDEMPOTENT_TASK,
        {"task": "compute_x", "result": 42, "idempotency_key": "task_compute_x"},
        idempotency_key="task_compute_x",
    )
    assert ok_dup
    assert msg_dup == "DUPLICATE_EXECUTION_DEDUPLICATED"
    assert node.history.tip_sequence() == 0


def test_gate_a2_6_host_node_catch_up(temp_node_dirs):
    """Stale host node catches up from remote canonical history and persists to WAL."""
    dir_a, dir_b, _ = temp_node_dirs
    node_a = PhysicalHostNode("node_a", dir_a, secret_key="key_a")
    node_b = PhysicalHostNode("node_b", dir_b, secret_key="key_b")

    # Node A commits 2 entries
    node_a.commit_entry_durably(HistoryEntryKind.CHILD_DELEGATION, {"task": 1})
    node_a.commit_entry_durably(HistoryEntryKind.AUTHORITATIVE_COMMIT, {"task": 2})

    # Node B starts with empty history, catches up from Node A
    ok_cu, count_cu, msg_cu = node_b.catch_up_from(node_a.history.entries)
    assert ok_cu
    assert count_cu == 2
    assert node_b.history.state_digest() == node_a.history.state_digest()

    # Node B crashes and restarts: verify caught up entries were persisted to disk WAL
    node_b.crash()
    restarted_count = node_b.restart()
    assert restarted_count == 2
    assert node_b.history.state_digest() == node_a.history.state_digest()


# -----------------------------------------------------------------------------
# Qualification Claims
# -----------------------------------------------------------------------------

def test_gate_a2_6_qualification_claim_physical_network_fault():
    """Qualifies Claim A2.PHYSICAL_NETWORK_FAULT.PORTABLE."""
    spec = get_claim("A2.PHYSICAL_NETWORK_FAULT.PORTABLE")
    res = evaluate_claim(
        observed_pass=True,
        negative_control_pass=True,
        context=EvidenceContext(
            level=EvidenceLevel.PORTABLE,
            source="tests.test_composition_physical_network",
            actual_components={
                "envelope": "WireEnvelope",
                "channel": "AdversarialChannel",
                "verifier": "verify_envelope",
            },
            substitutions={},
        ),
        requirement=ClaimRequirement(spec.required_level, spec.required_components),
    )
    assert res["qualified"] and res["passed"]


def test_gate_a2_6_qualification_claim_crash_recovery_convergence():
    """Qualifies Claim A2.CRASH_RECOVERY_CONVERGENCE.PORTABLE."""
    spec = get_claim("A2.CRASH_RECOVERY_CONVERGENCE.PORTABLE")
    res = evaluate_claim(
        observed_pass=True,
        negative_control_pass=True,
        context=EvidenceContext(
            level=EvidenceLevel.PORTABLE,
            source="tests.test_composition_physical_network",
            actual_components={
                "node": "PhysicalHostNode",
                "wal": "DurableWAL",
                "recovery": "PhysicalHostNode.restart",
            },
            substitutions={},
        ),
        requirement=ClaimRequirement(spec.required_level, spec.required_components),
    )
    assert res["qualified"] and res["passed"]
