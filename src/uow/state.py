"""Immutable, hash-bound world state for canonical UoW transitions."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping, Optional


def _freeze(value: Any) -> Any:
    """Deep-freeze JSON-compatible values and reject unstable values."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("WorldState does not permit NaN or infinite floats.")
        return value
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    raise TypeError(
        "WorldState values must be JSON-compatible: null, bool, number, string, "
        "mapping, list, or tuple."
    )


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_thaw(v) for v in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _thaw(_freeze(value)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


@dataclass(frozen=True)
class WorldState:
    """Minimal authoritative state.

    Runtime layers may store richer orchestration structures in attributes or
    compose their own typed state objects over this primitive. The kernel itself
    knows nothing about queues, transactions, resources, models, or hardware.
    """

    attributes: Mapping[str, Any] = field(default_factory=dict)
    cursor: Optional[str] = None
    status: str = "RUNNING"
    sequence: int = 0
    state_hash: str = ""

    def __post_init__(self) -> None:
        frozen = _freeze(dict(self.attributes))
        object.__setattr__(self, "attributes", frozen)
        expected = self.calculate_hash(
            attributes=frozen,
            cursor=self.cursor,
            status=self.status,
            sequence=self.sequence,
        )
        if self.state_hash and self.state_hash != expected:
            raise ValueError("Provided state_hash does not match WorldState contents.")
        object.__setattr__(self, "state_hash", expected)

    @staticmethod
    def calculate_hash(
        *,
        attributes: Mapping[str, Any],
        cursor: Optional[str],
        status: str,
        sequence: int,
    ) -> str:
        payload = {
            "attributes": _thaw(attributes),
            "cursor": cursor,
            "status": status,
            "sequence": sequence,
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    @property
    def values(self) -> Mapping[str, Any]:
        """Canonical protocol alias for attributes."""
        return self.attributes

    @property
    def sequence_number(self) -> int:
        """Canonical protocol alias for sequence."""
        return self.sequence

    def get(self, key: str, default: Any = None) -> Any:
        return self.attributes.get(key, default)

    def require(self, key: str) -> Any:
        if key not in self.attributes:
            raise KeyError(f"State attribute {key!r} is not defined.")
        return self.attributes[key]

    def with_attribute(self, key: str, value: Any) -> "WorldState":
        attributes = _thaw(self.attributes)
        attributes[key] = value
        return replace(self, attributes=attributes, state_hash="")

    def without_attribute(self, key: str) -> "WorldState":
        attributes = _thaw(self.attributes)
        attributes.pop(key, None)
        return replace(self, attributes=attributes, state_hash="")

    def with_cursor(self, cursor: Optional[str]) -> "WorldState":
        return replace(self, cursor=cursor, state_hash="")

    def with_status(self, status: str) -> "WorldState":
        return replace(self, status=status, state_hash="")

    def advance_sequence(self) -> "WorldState":
        return replace(self, sequence=self.sequence + 1, state_hash="")

    def to_dict(self) -> dict[str, Any]:
        return {
            "attributes": _thaw(self.attributes),
            "cursor": self.cursor,
            "status": self.status,
            "sequence": self.sequence,
            "state_hash": self.state_hash,
        }
