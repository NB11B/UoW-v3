"""UoW canonical protocol definitions and schemas."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def load_canonical_schemas() -> Dict[str, Any]:
    """Load canonical object schema definition."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent / "schemas" / "canonical" / "canonical_objects.json",
        Path(__file__).resolve().parent.parent.parent / "schemas" / "canonical" / "canonical_objects.json",
    ]
    for p in candidates:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    return {}


__all__ = ["load_canonical_schemas"]
