"""Non-authoritative shadow identity helpers.

SHADOW-JSON-v0.1 identities are for research comparison only. They are not
accepted by the canonical UoW authority boundary.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping


SHADOW_PROFILE_ID = "SHADOW-JSON-v0.1"


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Shadow identities do not allow NaN or infinite floats.")
        return value
    if isinstance(value, Mapping):
        return {str(k): _normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if isinstance(value, (set, frozenset)):
        normalized = [_normalize(v) for v in value]
        return sorted(normalized, key=lambda x: json.dumps(x, sort_keys=True, separators=(",", ":")))
    if hasattr(value, "value"):
        return _normalize(value.value)
    return str(value)


def shadow_canonical_json(value: Any) -> str:
    return json.dumps(
        _normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def shadow_identity(kind: str, payload: Any) -> str:
    body = {
        "profile": SHADOW_PROFILE_ID,
        "kind": kind,
        "payload": _normalize(payload),
    }
    return hashlib.sha256(shadow_canonical_json(body).encode("utf-8")).hexdigest()
