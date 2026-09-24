from __future__ import annotations

import tempfile
from pathlib import Path

from uow.composition.convergence import HistoryEntry, HistoryEntryKind
from uow.composition.host_node import PhysicalHostNode
from uow.composition.wire import AdversarialChannel, WireEnvelope, sign_envelope


def test_r4_a2_6_retains_authenticated_wire_and_tamper_rejection():
    secret = "cluster-secret"
    env = sign_envelope(
        secret,
        WireEnvelope("host_b", "host_a", 1, 1, "n1", {"task": "x"}),
    )

    with tempfile.TemporaryDirectory() as tmp:
        node = PhysicalHostNode("host_a", Path(tmp), secret)
        node.startup()
        ok, reason = node.receive_wire_envelope(env)
        assert ok, reason

        forged = WireEnvelope(
            env.sender_id,
            env.recipient_id,
            env.seq,
            env.epoch,
            env.nonce,
            {"task": "tampered"},
            signature=env.signature,
        )
        ok2, reason2 = node.receive_wire_envelope(forged)
        assert not ok2
        assert reason2 == "UNAUTHENTICATED_WIRE_SIGNATURE"


def test_r4_a2_6_duplicate_delivery_remains_idempotent():
    secret = "cluster-secret"
    channel = AdversarialChannel(duplication_rate=1.0, seed=42)
    env = sign_envelope(
        secret,
        WireEnvelope(
            "host_b",
            "host_a",
            17,
            1,
            "n17",
            {"task": "U17", "idempotency_key": "u17-key"},
        ),
    )
    delivered = channel.transmit(env)
    assert len(delivered) == 2

    with tempfile.TemporaryDirectory() as tmp:
        node = PhysicalHostNode("host_a", Path(tmp), secret)
        node.startup()
        for item in delivered:
            ok, reason = node.receive_wire_envelope(item)
            assert ok, reason
            committed, _, _ = node.commit_entry_durably(
                HistoryEntryKind.IDEMPOTENT_TASK,
                item.payload,
                idempotency_key=item.payload["idempotency_key"],
            )
            assert committed

        assert len(node.history.entries) == 1


def test_r4_a2_6_reordering_and_asymmetric_partition_controls_survive():
    secret = "cluster-secret"

    channel = AdversarialChannel(reorder=True, seed=42)
    m1 = sign_envelope(secret, WireEnvelope("b", "a", 1, 1, "1", {"seq": 1}))
    m2 = sign_envelope(secret, WireEnvelope("b", "a", 2, 1, "2", {"seq": 2}))
    m3 = sign_envelope(secret, WireEnvelope("b", "a", 3, 1, "3", {"seq": 3}))
    assert channel.transmit(m1) == []
    assert channel.transmit(m2) == []
    reversed_batch = channel.transmit(m3)
    assert [x.seq for x in reversed_batch] == [3, 2, 1]

    asymmetric = AdversarialChannel()
    asymmetric.set_asymmetric_drop("b", "a", True)
    assert asymmetric.transmit(
        sign_envelope(secret, WireEnvelope("a", "b", 1, 1, "ab", {"ping": 1}))
    )
    assert asymmetric.transmit(
        sign_envelope(secret, WireEnvelope("b", "a", 1, 1, "ba", {"pong": 1}))
    ) == []


def test_r4_a2_6_wal_crash_recovery_and_idempotency_are_retained():
    with tempfile.TemporaryDirectory() as tmp:
        node = PhysicalHostNode("host_a", Path(tmp), "secret")
        node.startup()

        ok, entry, reason = node.commit_entry_durably(
            HistoryEntryKind.AUTHORITATIVE_COMMIT,
            {"value": 1},
            quorum_sigs=("A", "B"),
        )
        assert ok, reason
        assert entry is not None
        tip = node.history.tip_hash()

        ok2, _, reason2 = node.commit_entry_durably(
            HistoryEntryKind.IDEMPOTENT_TASK,
            {"task": "delegated", "idempotency_key": "d1"},
            idempotency_key="d1",
        )
        assert ok2, reason2

        before_count = len(node.history.entries)
        node.crash()
        assert not node.is_alive
        replayed = node.restart()

        assert replayed == before_count
        assert node.history.verify_integrity()
        assert node.history.entries[0].entry_hash == tip
        assert "d1" in node.idempotent_task_results

        ok3, _, reason3 = node.commit_entry_durably(
            HistoryEntryKind.IDEMPOTENT_TASK,
            {"task": "delegated", "idempotency_key": "d1"},
            idempotency_key="d1",
        )
        assert ok3
        assert reason3 == "DUPLICATE_EXECUTION_DEDUPLICATED"
        assert len(node.history.entries) == before_count


def test_r4_a2_6_clock_skew_does_not_change_generation_authority():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        a = PhysicalHostNode("a", base / "a", "secret", clock_skew_sec=0.0, generation=7)
        b = PhysicalHostNode("b", base / "b", "secret", clock_skew_sec=30.0, generation=7)
        c = PhysicalHostNode("c", base / "c", "secret", clock_skew_sec=-45.0, generation=7)

        ta, tb, tc = a.local_time(), b.local_time(), c.local_time()
        assert tb - ta >= 29.0
        assert ta - tc >= 44.0
        assert a.generation == b.generation == c.generation == 7
