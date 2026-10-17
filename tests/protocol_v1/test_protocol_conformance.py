"""Conformance suite for UoW Canonical Protocol v1."""
import pytest
from uow.protocol.v1 import (
    canonical_json,
    compute_digest,
    CapabilityDescriptor,
    CapabilityKind,
    CapabilityPackageManifest,
    CapabilityProposal,
    CommitDisposition,
    CommitRecord,
    CorruptMagicError,
    CRCError,
    decode_frame,
    encode_frame,
    QualificationStatus,
    RecoveryCommand,
    TruncatedFrameError,
    WorkCertificate,
    WorkEvent,
    WorkRequest,
    CausalClock,
    CausalOrderDetector,
)


def test_canonical_json_determinism():
    """Verify that key ordering and formatting are strictly normalized."""
    obj1 = {"z": 1, "a": 2, "m": {"b": 3, "a": 4}}
    obj2 = {"a": 2, "m": {"a": 4, "b": 3}, "z": 1}
    assert canonical_json(obj1) == '{"a":2,"m":{"a":4,"b":3},"z":1}'
    assert canonical_json(obj1) == canonical_json(obj2)
    assert compute_digest(obj1) == compute_digest(obj2)


def test_float_canonical_normalization():
    """Verify consistent float formatting without floating-point drift."""
    obj = {"val": 1.5000000001, "int_val": 2.0}
    c_str = canonical_json(obj)
    assert c_str == '{"int_val":2,"val":1.5}'


def test_work_request_roundtrip():
    """Verify WorkRequest envelope serialization."""
    req = WorkRequest(
        work_id="work-001",
        origin_node="node-alpha",
        state_reference="state-abc123",
        requested_capability="industrial.telemetry.v1",
        payload={"sensor": "pressure", "value": 142.5},
        deadline_policy="hard:500ms",
        causal_parents=["work-000"],
        local_sequence=1,
        created_at_utc=1700000000.0,
    )
    d = req.digest()
    assert len(d) == 64
    assert req.to_canonical_json().startswith('{"causal_parents":["work-000"]')


def test_proposal_authority_boundary_invariant():
    """Verify invariant: Neural proposals cannot grant authority directly."""
    clean_proposal = CapabilityProposal(
        proposal_id="prop-001",
        work_id="work-001",
        producer_identity="cerebras_111m:operational",
        capability_id="industrial.telemetry.v1",
        proposed_action="vent_pressure",
        bindings={"valve_id": "V-101"},
    )
    assert clean_proposal.validate_boundary() is True

    # Malicious/corrupt proposal attempting to assert authority
    rogue_proposal = CapabilityProposal(
        proposal_id="prop-002",
        work_id="work-001",
        producer_identity="cerebras_111m:operational",
        capability_id="industrial.telemetry.v1",
        proposed_action="vent_pressure",
        bindings={"valve_id": "V-101", "authorized": True},
    )
    assert rogue_proposal.validate_boundary() is False


def test_binary_framing_roundtrip():
    """Verify binary framing encode/decode with CRC32."""
    event = WorkEvent(
        event_id="evt-101",
        node_id="nano-01",
        local_sequence=42,
        local_time_ms=158200,
        causal_parents=["evt-100"],
        event_type="sensor_sample",
        payload={"temp": 28.4},
    )
    raw_frame = encode_frame(event, sequence=42)
    assert len(raw_frame) > 20
    assert raw_frame.startswith(b"UOW1")

    decoded_msg, seq, flags = decode_frame(raw_frame)
    assert isinstance(decoded_msg, WorkEvent)
    assert decoded_msg.event_id == "evt-101"
    assert seq == 42


def test_framing_negative_corrupted_crc():
    """Verify that bit flips trigger CRCError."""
    event = WorkEvent(
        event_id="evt-102",
        node_id="uno-01",
        local_sequence=1,
        local_time_ms=100,
        causal_parents=[],
        event_type="heartbeat",
        payload={},
    )
    raw_frame = bytearray(encode_frame(event, sequence=1))
    # Corrupt a byte in the payload
    raw_frame[20] ^= 0xFF

    with pytest.raises(CRCError):
        decode_frame(bytes(raw_frame))


def test_framing_negative_corrupted_magic():
    """Verify that wrong magic bytes trigger CorruptMagicError."""
    event = WorkEvent(
        event_id="evt-103",
        node_id="uno-01",
        local_sequence=1,
        local_time_ms=100,
        causal_parents=[],
        event_type="heartbeat",
        payload={},
    )
    raw_frame = bytearray(encode_frame(event, sequence=1))
    raw_frame[0:4] = b"BAD!"

    with pytest.raises(CorruptMagicError):
        decode_frame(bytes(raw_frame))


def test_framing_negative_truncated_frame():
    """Verify truncated bytes trigger TruncatedFrameError."""
    event = WorkEvent(
        event_id="evt-104",
        node_id="uno-01",
        local_sequence=1,
        local_time_ms=100,
        causal_parents=[],
        event_type="heartbeat",
        payload={},
    )
    raw_frame = encode_frame(event, sequence=1)
    # Truncate by removing the last 10 bytes
    truncated = raw_frame[:-10]

    with pytest.raises(TruncatedFrameError):
        decode_frame(truncated)


def test_causal_replay_detection():
    """Verify duplicate and replayed event detection without shared clocks."""
    detector = CausalOrderDetector()
    assert detector.is_replay_or_duplicate("evt-1", "node-A", 1) is False
    detector.record_processed("evt-1", "node-A", 1)

    # Duplicate event ID
    assert detector.is_replay_or_duplicate("evt-1", "node-A", 1) is True

    # Stale/replayed sequence counter from same node
    assert detector.is_replay_or_duplicate("evt-2", "node-A", 1) is True

    # Valid successor sequence
    assert detector.is_replay_or_duplicate("evt-3", "node-A", 2) is False
