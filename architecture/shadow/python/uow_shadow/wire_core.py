"""UOW-CORE-WIRE/1 L3 interoperability codec.

This is a transport profile only. It is not an authority canonicalization profile.
"""
from __future__ import annotations

from typing import Dict, Mapping, Tuple


PREFIX = "UOW1"

SCHEMAS: Mapping[str, Tuple[Tuple[str, str], ...]] = {
    "STATE": (
        ("r0", "uint"),
        ("r1", "uint"),
        ("pc", "uint"),
        ("sequence", "uint"),
        ("halted", "bool"),
    ),
    "PROPOSAL": (
        ("pre_state_hash", "hex64"),
        ("proposal_hash", "hex64"),
        ("r0", "uint"),
        ("r1", "uint"),
        ("pc", "uint"),
        ("sequence", "uint"),
        ("halted", "bool"),
        ("selected_pc", "uint"),
        ("proposal_halted", "bool"),
        ("proposer_clock", "uint"),
    ),
    "CERTIFICATE": (
        ("valid", "bool"),
        ("reason", "token"),
        ("certificate_hash", "hex64"),
    ),
    "EVIDENCE": (
        ("step", "uint"),
        ("pre_state_hash", "hex64"),
        ("post_state_hash", "hex64"),
        ("proposal_hash", "hex64"),
        ("certificate_hash", "hex64"),
        ("prev_record_hash", "hex64"),
        ("record_hash", "hex64"),
    ),
}


def _validate_token(value: str) -> str:
    if "|" in value or "=" in value or "\n" in value or "\r" in value:
        raise ValueError("Wire token contains a reserved delimiter.")
    return value


def _normalize(kind: str, key: str, value: object, type_name: str) -> str:
    if type_name == "uint":
        ivalue = int(value)
        if ivalue < 0:
            raise ValueError(f"{kind}.{key} must be unsigned.")
        return str(ivalue)
    if type_name == "bool":
        if value in (True, 1, "1"):
            return "1"
        if value in (False, 0, "0"):
            return "0"
        raise ValueError(f"{kind}.{key} must be boolean/0/1.")
    text = _validate_token(str(value))
    if type_name == "hex64":
        if len(text) != 64 or any(c not in "0123456789abcdefABCDEF" for c in text):
            raise ValueError(f"{kind}.{key} must be a 64-character hex digest.")
        return text.lower()
    if not text:
        raise ValueError(f"{kind}.{key} must not be empty.")
    return text


def encode_wire(kind: str, fields: Mapping[str, object]) -> str:
    kind = str(kind).upper()
    if kind not in SCHEMAS:
        raise ValueError(f"Unknown wire kind {kind!r}.")
    schema = SCHEMAS[kind]
    expected = {key for key, _ in schema}
    if set(fields) != expected:
        missing = sorted(expected - set(fields))
        extra = sorted(set(fields) - expected)
        raise ValueError(f"Wire field mismatch missing={missing} extra={extra}.")
    parts = [PREFIX, kind]
    for key, type_name in schema:
        parts.append(f"{key}={_normalize(kind, key, fields[key], type_name)}")
    return "|".join(parts)


def decode_wire(line: str) -> tuple[str, Dict[str, object]]:
    parts = line.strip().split("|")
    if len(parts) < 3 or parts[0] != PREFIX:
        raise ValueError("Invalid UOW-CORE-WIRE prefix.")
    kind = parts[1].upper()
    if kind not in SCHEMAS:
        raise ValueError(f"Unknown wire kind {kind!r}.")

    raw: Dict[str, str] = {}
    for item in parts[2:]:
        if "=" not in item:
            raise ValueError("Malformed wire field.")
        key, value = item.split("=", 1)
        if key in raw:
            raise ValueError(f"Duplicate wire field {key!r}.")
        raw[key] = value

    schema = SCHEMAS[kind]
    expected = {key for key, _ in schema}
    if set(raw) != expected:
        missing = sorted(expected - set(raw))
        extra = sorted(set(raw) - expected)
        raise ValueError(f"Wire field mismatch missing={missing} extra={extra}.")

    decoded: Dict[str, object] = {}
    for key, type_name in schema:
        normalized = _normalize(kind, key, raw[key], type_name)
        if type_name == "uint":
            decoded[key] = int(normalized)
        elif type_name == "bool":
            decoded[key] = normalized == "1"
        else:
            decoded[key] = normalized
    return kind, decoded
