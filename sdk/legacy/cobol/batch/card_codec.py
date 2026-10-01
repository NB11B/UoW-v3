"""Bidirectional COBOL Fixed-Width Batch Card Codec.

Encodes and decodes canonical UoWEnvelope records to/from the 1024-byte
fixed-width card layout specified in legacy/cobol/copybooks/UOWENVLP.cpy
and legacy/cobol/batch/CARDMAP.md.
"""
from __future__ import annotations

import json
from typing import Any, Dict


CARD_LENGTH = 1024


def encode_card(envelope: Dict[str, Any]) -> bytes:
    """Encodes a canonical UoWEnvelope into a 1024-byte fixed-width record."""
    buf = bytearray(b" " * CARD_LENGTH)

    def write_str(start: int, length: int, val: str) -> None:
        trimmed = val[:length].encode("utf-8")
        buf[start : start + len(trimmed)] = trimmed

    # Cols 0001 - 0008: UOW-PROTOCOL-VERSION
    write_str(0, 8, envelope.get("protocol_version", "1.0.0"))
    # Cols 0009 - 0072: UOW-OPERATION-ID
    write_str(8, 64, envelope.get("operation", ""))
    # Cols 0073 - 0080: UOW-OPERATION-VERSION
    write_str(72, 8, envelope.get("operation_version", "1.0.0"))
    # Cols 0081 - 0116: UOW-REQUEST-ID
    write_str(80, 36, envelope.get("request_id", ""))
    # Cols 0117 - 0152: UOW-CORRELATION-ID
    write_str(116, 36, envelope.get("correlation_id", ""))

    actor = envelope.get("actor", {})
    # Cols 0153 - 0184: UOW-ACTOR-ID
    write_str(152, 32, actor.get("id", ""))
    # Cols 0185 - 0200: UOW-ACTOR-ROLE
    write_str(184, 16, actor.get("role", ""))
    # Cols 0201 - 0220: UOW-ACTOR-CLAIM-TYPE
    write_str(200, 20, actor.get("claim_type", "UNVERIFIED_CLAIM"))

    # Cols 0221 - 0284: UOW-AUTH-TOKEN
    tokens = envelope.get("authority_context", {}).get("tokens", [])
    if tokens:
        write_str(220, 64, tokens[0])

    # Cols 0285 - 0348: UOW-IDEMPOTENCY-KEY
    idem_key = envelope.get("constraints", {}).get("idempotency_key", "")
    write_str(284, 64, idem_key)

    # Cols 0349 - 0412: UOW-PARENT-EVID-HASH
    parent_evid = envelope.get("evidence_context", {}).get("parent_evidence_hash", "")
    write_str(348, 64, parent_evid)

    # Cols 0413 - 0476: UOW-REPLY-TO
    write_str(412, 64, envelope.get("reply_to", ""))

    # Payload serialized to JSON
    payload_str = json.dumps(envelope.get("payload", {}), separators=(",", ":"))
    payload_bytes = payload_str.encode("utf-8")
    payload_len = len(payload_bytes)

    # Cols 0477 - 0480: UOW-PAYLOAD-LENGTH (big endian 2-byte integer)
    buf[476:478] = payload_len.to_bytes(2, byteorder="big")

    # Cols 0481 - 0992: UOW-PAYLOAD-DATA
    max_payload = 512
    write_len = min(payload_len, max_payload)
    buf[480 : 480 + write_len] = payload_bytes[:write_len]

    return bytes(buf)


def decode_card(card: bytes) -> Dict[str, Any]:
    """Decodes a 1024-byte fixed-width card record into a canonical UoWEnvelope dictionary."""
    if len(card) < CARD_LENGTH:
        raise ValueError(f"Invalid card record length: {len(card)} < {CARD_LENGTH}")

    def read_str(start: int, length: int) -> str:
        return card[start : start + length].decode("utf-8", errors="replace").strip()

    protocol_version = read_str(0, 8)
    operation = read_str(8, 64)
    operation_version = read_str(72, 8)
    request_id = read_str(80, 36)
    correlation_id = read_str(116, 36)
    actor_id = read_str(152, 32)
    actor_role = read_str(184, 16)
    claim_type = read_str(200, 20)
    auth_token = read_str(220, 64)
    idem_key = read_str(284, 64)
    parent_evid = read_str(348, 64)
    reply_to = read_str(412, 64)

    payload_len = int.from_bytes(card[476:478], byteorder="big")
    max_payload = 512
    actual_len = min(payload_len, max_payload)
    payload_raw = card[480 : 480 + actual_len].decode("utf-8", errors="replace")
    try:
        payload = json.loads(payload_raw) if payload_raw else {}
    except Exception:
        payload = {"raw_payload": payload_raw}

    envelope: Dict[str, Any] = {
        "protocol_version": protocol_version,
        "operation": operation,
        "operation_version": operation_version,
        "request_id": request_id,
        "correlation_id": correlation_id,
        "actor": {
            "id": actor_id,
            "claim_type": claim_type or "UNVERIFIED_CLAIM",
        },
        "payload": payload,
    }
    if actor_role:
        envelope["actor"]["role"] = actor_role
    if auth_token:
        envelope["authority_context"] = {"tokens": [auth_token]}
    if idem_key:
        envelope["constraints"] = {"idempotency_key": idem_key}
    if parent_evid:
        envelope["evidence_context"] = {"parent_evidence_hash": parent_evid}
    if reply_to:
        envelope["reply_to"] = reply_to

    return envelope
