"""Deterministic non-authority identity helper for conformance envelopes."""
from __future__ import annotations

import hashlib
from typing import Any

from ..state import canonical_json


PROFILE_ID = "UOW-CONFORMANCE-v1"


def conformance_identity(kind: str, payload: Any) -> str:
    body = {
        "profile": PROFILE_ID,
        "kind": kind,
        "payload": payload,
    }
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
