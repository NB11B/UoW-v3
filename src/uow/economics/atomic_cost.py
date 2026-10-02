"""Atomic cost representation and observation records for UoW economics.

Governing Separations:
    Cost Observation != Pricing Decision
    Production Cost != Market Price != Consumer Value
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional


@dataclass(frozen=True)
class AtomicCost:
    """Orthogonal 6-dimension atomic cost representation:

        C(u) = C_H + C_M + C_E + C_R + C_K + C_D

    Dimensions:
        c_h: Human work cost (review, manual approval, supervision)
        c_m: Machine/compute cost (CPU/GPU instruction cycles)
        c_e: Energy cost (joules / kWh consumption)
        c_r: Resource/capital cost (RAM/storage lease & device depreciation)
        c_k: Failure/recovery expectation (p_fail * recovery cost)
        c_d: Delay/opportunity cost (latency penalty / queue wait)
        currency: Denomination unit (default "USD")
    """

    c_h: float = 0.0
    c_m: float = 0.0
    c_e: float = 0.0
    c_r: float = 0.0
    c_k: float = 0.0
    c_d: float = 0.0
    currency: str = "USD"

    def total(self) -> float:
        """Calculate total production cost as the sum of all 6 orthogonal dimensions."""
        return round(
            self.c_h + self.c_m + self.c_e + self.c_r + self.c_k + self.c_d,
            6,
        )

    def __add__(self, other: object) -> "AtomicCost":
        if not isinstance(other, AtomicCost):
            return NotImplemented
        if self.currency != other.currency:
            raise ValueError(
                f"Cannot add costs with differing currency denominations: {self.currency} vs {other.currency}"
            )
        return AtomicCost(
            c_h=round(self.c_h + other.c_h, 6),
            c_m=round(self.c_m + other.c_m, 6),
            c_e=round(self.c_e + other.c_e, 6),
            c_r=round(self.c_r + other.c_r, 6),
            c_k=round(self.c_k + other.c_k, 6),
            c_d=round(self.c_d + other.c_d, 6),
            currency=self.currency,
        )

    def __sub__(self, other: object) -> "AtomicCost":
        if not isinstance(other, AtomicCost):
            return NotImplemented
        if self.currency != other.currency:
            raise ValueError(
                f"Cannot subtract costs with differing currency denominations: {self.currency} vs {other.currency}"
            )
        return AtomicCost(
            c_h=round(self.c_h - other.c_h, 6),
            c_m=round(self.c_m - other.c_m, 6),
            c_e=round(self.c_e - other.c_e, 6),
            c_r=round(self.c_r - other.c_r, 6),
            c_k=round(self.c_k - other.c_k, 6),
            c_d=round(self.c_d - other.c_d, 6),
            currency=self.currency,
        )

    def friction_against(self, ideal: "AtomicCost") -> "AtomicCost":
        """Compute friction cost C_F = C_observed - C* against an ideal baseline."""
        return self - ideal

    def is_non_negative(self) -> bool:
        """Check if all component costs are non-negative."""
        return (
            self.c_h >= 0.0
            and self.c_m >= 0.0
            and self.c_e >= 0.0
            and self.c_r >= 0.0
            and self.c_k >= 0.0
            and self.c_d >= 0.0
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "c_h": self.c_h,
            "c_m": self.c_m,
            "c_e": self.c_e,
            "c_r": self.c_r,
            "c_k": self.c_k,
            "c_d": self.c_d,
            "total": self.total(),
            "currency": self.currency,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AtomicCost":
        return cls(
            c_h=float(data.get("c_h", 0.0)),
            c_m=float(data.get("c_m", 0.0)),
            c_e=float(data.get("c_e", 0.0)),
            c_r=float(data.get("c_r", 0.0)),
            c_k=float(data.get("c_k", 0.0)),
            c_d=float(data.get("c_d", 0.0)),
            currency=str(data.get("currency", "USD")),
        )


def compute_cost_evidence_hash(
    uow_id: str,
    cost: AtomicCost,
    realization_id: str,
    timestamp_epoch_ms: int,
    state_hash_pre: str,
    state_hash_post: str,
) -> str:
    """Compute deterministic cryptographic digest binding cost to transition evidence."""
    payload = {
        "uow_id": uow_id,
        "cost": cost.to_dict(),
        "realization_id": realization_id,
        "timestamp_epoch_ms": timestamp_epoch_ms,
        "state_hash_pre": state_hash_pre,
        "state_hash_post": state_hash_post,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CostObservationRecord:
    """Immutable evidence-bound cost observation recorded as protocol telemetry."""

    observation_id: str
    uow_id: str
    cost: AtomicCost
    realization_id: str
    timestamp_epoch_ms: int
    state_hash_pre: str
    state_hash_post: str
    evidence_hash: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def verify_hash(self) -> bool:
        """Verify that the cryptographic evidence hash matches the observed data."""
        expected = compute_cost_evidence_hash(
            uow_id=self.uow_id,
            cost=self.cost,
            realization_id=self.realization_id,
            timestamp_epoch_ms=self.timestamp_epoch_ms,
            state_hash_pre=self.state_hash_pre,
            state_hash_post=self.state_hash_post,
        )
        return self.evidence_hash == expected

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "uow_id": self.uow_id,
            "cost": self.cost.to_dict(),
            "realization_id": self.realization_id,
            "timestamp_epoch_ms": self.timestamp_epoch_ms,
            "state_hash_pre": self.state_hash_pre,
            "state_hash_post": self.state_hash_post,
            "evidence_hash": self.evidence_hash,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CostObservationRecord":
        return cls(
            observation_id=str(data["observation_id"]),
            uow_id=str(data["uow_id"]),
            cost=AtomicCost.from_dict(data["cost"]),
            realization_id=str(data["realization_id"]),
            timestamp_epoch_ms=int(data["timestamp_epoch_ms"]),
            state_hash_pre=str(data["state_hash_pre"]),
            state_hash_post=str(data["state_hash_post"]),
            evidence_hash=str(data["evidence_hash"]),
            metadata=dict(data.get("metadata", {})),
        )
