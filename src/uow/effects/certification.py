"""Certification rules and authenticators for External Effects & Sagas."""
from __future__ import annotations

import hashlib
import hmac
from typing import Optional, Protocol

from ..state import WorldState, canonical_json
from .descriptor import EffectDescriptor, EffectReceipt, compute_idempotency_key


class ReceiptAuthenticator(Protocol):
    """Protocol for external receipt authentication."""

    def authenticate(self, effect: EffectDescriptor, receipt: EffectReceipt) -> bool:
        """Returns True if receipt passes authentication, or raises ValueError."""
        ...


class PrefixReceiptAuthenticator:
    """Test-only reference authenticator checking signature prefixes."""

    def __init__(self, signer_id: str) -> None:
        self.signer_id = signer_id

    def authenticate(self, effect: EffectDescriptor, receipt: EffectReceipt) -> bool:
        if not receipt.signature:
            raise ValueError(f"Missing cryptographic signature for signer: {self.signer_id}")
        expected_prefix = f"sig::{self.signer_id}::"
        if not receipt.signature.startswith(expected_prefix):
            raise ValueError(f"Invalid cryptographic signature: {receipt.signature!r}")
        return True


class HMACReceiptAuthenticator:
    """Cryptographic HMAC-SHA256 receipt authenticator."""

    def __init__(self, secret_key: bytes) -> None:
        self.secret_key = secret_key

    def _payload(self, receipt: EffectReceipt) -> str:
        return f"{receipt.receipt_id}::{receipt.effect_id}::{receipt.idempotency_key}::{receipt.response_hash}::{receipt.timestamp}"

    def sign(self, receipt: EffectReceipt) -> str:
        """Computes HMAC-SHA256 signature for an EffectReceipt."""
        return hmac.new(
            self.secret_key,
            self._payload(receipt).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def authenticate(self, effect: EffectDescriptor, receipt: EffectReceipt) -> bool:
        if not receipt.signature:
            raise ValueError("Missing HMAC signature on receipt.")
        expected = self.sign(receipt)
        if not hmac.compare_digest(receipt.signature, expected):
            raise ValueError(f"HMAC signature mismatch: {receipt.signature!r} != {expected!r}")
        return True


def verify_effect_intent_binding(state: WorldState, effect: EffectDescriptor) -> None:
    """Rigidly cross-validates effect intent against current authoritative state and UoW contract."""
    expected_idemp = compute_idempotency_key(
        effect.uow_id,
        effect.pre_state_hash,
        effect.intent,
        effect.request,
    )
    if effect.idempotency_key != expected_idemp:
        raise ValueError(
            f"Effect idempotency key mismatch: {effect.idempotency_key!r} != {expected_idemp!r}"
        )

    # For child compensation effects, verify parent effect exists in authoritative state
    if effect.effect_id.startswith("comp::"):
        parent_id = effect.effect_id[len("comp::"):]
        raw_effects = state.attributes.get("__effects__", {})
        if parent_id not in raw_effects:
            raise ValueError(f"Compensation effect {effect.effect_id!r} has no parent effect in state.")
        return

    if effect.pre_state_hash != state.state_hash:
        raise ValueError("Effect intent is not bound to current authoritative pre-state.")


def verify_effect_receipt_binding(
    effect: EffectDescriptor,
    receipt: EffectReceipt,
    *,
    authenticator: Optional[ReceiptAuthenticator] = None,
    expected_signer: Optional[str] = None,
) -> None:
    """Cryptographically validates that an external receipt is bound to the declared effect intent."""
    if receipt.effect_id != effect.effect_id:
        raise ValueError(
            f"Receipt effect_id mismatch: {receipt.effect_id!r} != {effect.effect_id!r}"
        )

    if receipt.idempotency_key != effect.idempotency_key:
        raise ValueError(
            f"Receipt idempotency key mismatch: {receipt.idempotency_key!r} != {effect.idempotency_key!r}"
        )

    # 1. Verify receipt internal hash
    expected_hash = receipt.compute_receipt_hash()
    if receipt.receipt_hash != expected_hash:
        raise ValueError(
            f"Receipt hash mismatch (tampered receipt): {receipt.receipt_hash!r} != {expected_hash!r}"
        )

    # 2. Verify response payload hash
    expected_payload_hash = hashlib.sha256(
        canonical_json(dict(receipt.response_payload)).encode("utf-8")
    ).hexdigest()
    if receipt.response_hash != expected_payload_hash:
        raise ValueError(
            f"Receipt response_hash mismatch: {receipt.response_hash!r} != {expected_payload_hash!r}"
        )

    # 3. Authenticator check
    if authenticator is not None:
        authenticator.authenticate(effect, receipt)
    elif expected_signer is not None:
        PrefixReceiptAuthenticator(expected_signer).authenticate(effect, receipt)
