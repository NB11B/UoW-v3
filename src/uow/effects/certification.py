"""Certification rules for External Effects & Sagas."""
from __future__ import annotations

import hashlib
from typing import Optional

from ..state import WorldState, canonical_json
from .descriptor import EffectDescriptor, EffectReceipt, compute_idempotency_key


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

    if effect.pre_state_hash != state.state_hash:
        raise ValueError("Effect intent is not bound to current authoritative pre-state.")


def verify_effect_receipt_binding(
    effect: EffectDescriptor,
    receipt: EffectReceipt,
    *,
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

    # 3. Cryptographic signature check if signature is required
    if expected_signer is not None:
        if not receipt.signature:
            raise ValueError(f"Missing cryptographic signature for signer: {expected_signer}")
        # Standard signature verification scheme: sig::<signer>::<hash>
        expected_sig_prefix = f"sig::{expected_signer}::"
        if not receipt.signature.startswith(expected_sig_prefix):
            raise ValueError(f"Invalid cryptographic signature: {receipt.signature!r}")
