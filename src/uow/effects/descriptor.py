"""External Effect models and descriptors for Pass 4: External Effects and Sagas."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
from typing import Any, Mapping, Optional, Set

from ..state import canonical_json


class EffectStatus(str, Enum):
    """Lifecycle states for an external effect."""

    INTENDED = "INTENDED"
    COMMITTED_INTENT = "COMMITTED_INTENT"
    PENDING_EXTERNAL = "PENDING_EXTERNAL"
    OBSERVED = "OBSERVED"
    COMMITTED_RESULT = "COMMITTED_RESULT"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
    COMPENSATION_FAILED = "COMPENSATION_FAILED"


LEGAL_EFFECT_TRANSITIONS: Mapping[EffectStatus, Set[EffectStatus]] = {
    EffectStatus.INTENDED: {EffectStatus.COMMITTED_INTENT},
    EffectStatus.COMMITTED_INTENT: {
        EffectStatus.PENDING_EXTERNAL,
        EffectStatus.COMMITTED_RESULT,
        EffectStatus.COMPENSATING,
    },
    EffectStatus.PENDING_EXTERNAL: {
        EffectStatus.COMMITTED_RESULT,
        EffectStatus.COMPENSATING,
    },
    EffectStatus.COMMITTED_RESULT: {EffectStatus.COMPENSATING},
    EffectStatus.COMPENSATING: {
        EffectStatus.COMPENSATED,
        EffectStatus.COMPENSATION_FAILED,
    },
    EffectStatus.COMPENSATED: set(),
    EffectStatus.COMPENSATION_FAILED: set(),
}


@dataclass(frozen=True)
class CompensationSpec:
    """Specification for compensating (undoing) an external effect if downstream fails."""

    intent: str
    request: Mapping[str, Any]
    idempotency_key: str

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "request": dict(self.request),
            "idempotency_key": self.idempotency_key,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CompensationSpec:
        return cls(
            intent=str(data["intent"]),
            request=dict(data.get("request", {})),
            idempotency_key=str(data["idempotency_key"]),
        )


@dataclass(frozen=True)
class EffectReceipt:
    """Cryptographically verifiable proof of external execution or observation."""

    receipt_id: str
    effect_id: str
    idempotency_key: str
    response_payload: Mapping[str, Any]
    response_hash: str
    timestamp: str
    signature: Optional[str] = None
    receipt_hash: str = field(default="")

    def __post_init__(self) -> None:
        expected = self.compute_receipt_hash()
        if not self.receipt_hash:
            object.__setattr__(self, "receipt_hash", expected)
        elif self.receipt_hash != expected:
            raise ValueError(f"EffectReceipt hash mismatch: {self.receipt_hash} != {expected}")

    def compute_receipt_hash(self) -> str:
        payload = {
            "receipt_id": self.receipt_id,
            "effect_id": self.effect_id,
            "idempotency_key": self.idempotency_key,
            "response_payload": dict(self.response_payload),
            "response_hash": self.response_hash,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {
            "receipt_id": self.receipt_id,
            "effect_id": self.effect_id,
            "idempotency_key": self.idempotency_key,
            "response_payload": dict(self.response_payload),
            "response_hash": self.response_hash,
            "timestamp": self.timestamp,
            "signature": self.signature,
            "receipt_hash": self.receipt_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EffectReceipt:
        return cls(
            receipt_id=str(data["receipt_id"]),
            effect_id=str(data["effect_id"]),
            idempotency_key=str(data["idempotency_key"]),
            response_payload=dict(data.get("response_payload", {})),
            response_hash=str(data["response_hash"]),
            timestamp=str(data["timestamp"]),
            signature=str(data["signature"]) if data.get("signature") is not None else None,
            receipt_hash=str(data.get("receipt_hash", "")),
        )


def compute_idempotency_key(
    uow_id: str,
    pre_state_hash: str,
    intent: str,
    request: Mapping[str, Any],
) -> str:
    """Generates a deterministic cryptographic idempotency key: H(uow_id, state_hash, intent, request)."""
    payload = {
        "uow_id": uow_id,
        "pre_state_hash": pre_state_hash,
        "intent": intent,
        "request": dict(request),
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EffectDescriptor:
    """Formal External Effect envelope: F_i = (effect_id, intent, idempotency_key, request, observation, receipt, status, compensation)."""

    effect_id: str
    uow_id: str
    intent: str
    idempotency_key: str
    request: Mapping[str, Any]
    status: EffectStatus = EffectStatus.INTENDED
    observation: Optional[Mapping[str, Any]] = None
    receipt: Optional[EffectReceipt] = None
    compensation: Optional[CompensationSpec] = None
    compensation_effect_id: Optional[str] = None
    pre_state_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "effect_id": self.effect_id,
            "uow_id": self.uow_id,
            "intent": self.intent,
            "idempotency_key": self.idempotency_key,
            "request": dict(self.request),
            "status": self.status.value,
            "observation": dict(self.observation) if self.observation is not None else None,
            "receipt": self.receipt.to_dict() if self.receipt is not None else None,
            "compensation": self.compensation.to_dict() if self.compensation is not None else None,
            "compensation_effect_id": self.compensation_effect_id,
            "pre_state_hash": self.pre_state_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EffectDescriptor:
        comp_data = data.get("compensation")
        receipt_data = data.get("receipt")
        return cls(
            effect_id=str(data["effect_id"]),
            uow_id=str(data["uow_id"]),
            intent=str(data["intent"]),
            idempotency_key=str(data["idempotency_key"]),
            request=dict(data.get("request", {})),
            status=EffectStatus(data.get("status", EffectStatus.INTENDED.value)),
            observation=dict(data["observation"]) if data.get("observation") is not None else None,
            receipt=EffectReceipt.from_dict(receipt_data) if receipt_data is not None else None,
            compensation=CompensationSpec.from_dict(comp_data) if comp_data is not None else None,
            compensation_effect_id=str(data["compensation_effect_id"]) if data.get("compensation_effect_id") is not None else None,
            pre_state_hash=str(data.get("pre_state_hash", "")),
        )


def create_effect_descriptor(
    uow_id: str,
    pre_state_hash: str,
    intent: str,
    request: Mapping[str, Any],
    *,
    effect_id: Optional[str] = None,
    compensation_intent: Optional[str] = None,
    compensation_request: Optional[Mapping[str, Any]] = None,
) -> EffectDescriptor:
    """Factory function constructing a valid EffectDescriptor with cryptographic idempotency key."""
    idemp_key = compute_idempotency_key(uow_id, pre_state_hash, intent, request)
    eff_id = effect_id or f"eff::{uow_id}::{idemp_key[:16]}"

    comp_spec: Optional[CompensationSpec] = None
    if compensation_intent:
        comp_req = compensation_request or {}
        comp_idemp = compute_idempotency_key(
            f"{uow_id}::comp",
            pre_state_hash,
            compensation_intent,
            comp_req,
        )
        comp_spec = CompensationSpec(
            intent=compensation_intent,
            request=comp_req,
            idempotency_key=comp_idemp,
        )

    return EffectDescriptor(
        effect_id=eff_id,
        uow_id=uow_id,
        intent=intent,
        idempotency_key=idemp_key,
        request=request,
        status=EffectStatus.INTENDED,
        compensation=comp_spec,
        pre_state_hash=pre_state_hash,
    )
