"""Canonicalization utilities for model proposal outputs and ground-truth comparisons."""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional


def canonicalize_value(val: Any) -> Any:
    """Recursively canonicalizes strings, floats, ints, lists, and dicts."""
    if isinstance(val, str):
        return val.strip()
    elif isinstance(val, (int, float)):
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return str(val)
        # Round floats to 4 decimal places for precision comparison
        if isinstance(val, float):
            return round(val, 4)
        return val
    elif isinstance(val, list):
        return [canonicalize_value(x) for x in val]
    elif isinstance(val, dict):
        return {str(k).strip(): canonicalize_value(v) for k, v in val.items()}
    return val


def canonicalize_proposal(payload: dict[str, Any]) -> dict[str, Any]:
    """Standardizes keys, sorts unknowns/guard_conditions, strips whitespaces."""
    canon: dict[str, Any] = {}
    for k, v in payload.items():
        k_str = str(k).strip()
        canon[k_str] = canonicalize_value(v)

    # Sort list fields where ordering does not convey semantic sequence
    for list_key in ["unknowns", "guard_conditions", "dependencies"]:
        if list_key in canon and isinstance(canon[list_key], list):
            canon[list_key] = sorted([str(x) for x in canon[list_key]])

    return canon
