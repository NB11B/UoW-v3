"""Deterministic Canonical Serialization (RFC 8785 inspired) and Cryptographic Hashing.

Guarantees unambiguous byte representation for signing, hashing, and state auditing.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Union


def _normalize_for_canonical_json(obj: Any) -> Any:
    """Recursively normalize objects for deterministic serialization."""
    if obj is None:
        return None
    if isinstance(obj, (bool, str, int)):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            raise ValueError(f"Cannot canonically serialize NaN or Infinity: {obj}")
        # Format floats consistently to avoid platform-dependent precision discrepancies
        if obj.is_integer():
            return int(obj)
        # 8 decimal places normalized
        return round(obj, 8)
    if isinstance(obj, (list, tuple)):
        return [_normalize_for_canonical_json(item) for item in obj]
    if isinstance(obj, dict):
        # Sort keys lexicographically
        return {
            str(k): _normalize_for_canonical_json(v)
            for k, v in sorted(obj.items(), key=lambda item: str(item[0]))
        }
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return _normalize_for_canonical_json(obj.to_dict())
    if hasattr(obj, "__dataclass_fields__"):
        import dataclasses
        return _normalize_for_canonical_json(dataclasses.asdict(obj))
    # Fallback to string representation for enums or unknown objects
    return str(obj)


def canonical_json(data: Any) -> str:
    """Serialize data into a deterministic, compact JSON string without extra whitespace.
    
    Keys are sorted lexicographically at every level.
    """
    normalized = _normalize_for_canonical_json(data)
    return json.dumps(
        normalized,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def compute_digest(data: Any) -> str:
    """Compute standard SHA-256 hexadecimal digest from canonical JSON representation."""
    encoded = canonical_json(data).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
