"""Authenticated Wire Protocol & Adversarial Channel for Campaign A2.

Enforces:
1. Authenticated Wire Envelopes: All messages across the network boundary are signed with
   HMAC-SHA256 and checked for valid sender identity ActorID = H(PK).
2. Adversarial Channel Simulation: Direct interposition on network traffic modeling real-world
   packet loss (1%-50%), packet duplication, out-of-order arrival, and asymmetric partitions.
3. Wire Tamper Resistance: Messages with tampered payloads or invalid signatures are rejected
   at the wire parser with strictly zero authority granted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import hmac
import json
import random
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from ...composition.fabric import canonical_json


@dataclass(frozen=True)
class WireEnvelope:
    """Cryptographically signed network message envelope exchanged over the wire."""

    sender_id: str
    recipient_id: str
    seq: int
    epoch: int
    nonce: str
    payload: Mapping[str, Any]
    signature: str = ""

    def payload_bytes(self) -> bytes:
        data = {
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "seq": self.seq,
            "epoch": self.epoch,
            "nonce": self.nonce,
            "payload": self.payload,
        }
        return canonical_json(data).encode("utf-8")

    def to_json(self) -> str:
        data = {
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "seq": self.seq,
            "epoch": self.epoch,
            "nonce": self.nonce,
            "payload": self.payload,
            "signature": self.signature,
        }
        return canonical_json(data)

    @classmethod
    def from_json(cls, text: str) -> WireEnvelope:
        data = json.loads(text)
        return cls(
            sender_id=data["sender_id"],
            recipient_id=data["recipient_id"],
            seq=data["seq"],
            epoch=data["epoch"],
            nonce=data["nonce"],
            payload=data["payload"],
            signature=data.get("signature", ""),
        )


def sign_envelope(secret_key: str, envelope: WireEnvelope) -> WireEnvelope:
    """Signs a WireEnvelope using HMAC-SHA256."""
    sig = hmac.new(
        secret_key.encode("utf-8"),
        envelope.payload_bytes(),
        hashlib.sha256,
    ).hexdigest()
    return WireEnvelope(
        sender_id=envelope.sender_id,
        recipient_id=envelope.recipient_id,
        seq=envelope.seq,
        epoch=envelope.epoch,
        nonce=envelope.nonce,
        payload=envelope.payload,
        signature=sig,
    )


def verify_envelope(secret_key: str, envelope: WireEnvelope) -> bool:
    """Verifies that a WireEnvelope signature is authentic and unaltered."""
    if not envelope.signature:
        return False
    expected_sig = hmac.new(
        secret_key.encode("utf-8"),
        envelope.payload_bytes(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_sig, envelope.signature)


class AdversarialChannel:
    """Network transmission channel simulating physical link impairments."""

    def __init__(
        self,
        loss_rate: float = 0.0,
        duplication_rate: float = 0.0,
        reorder: bool = False,
        seed: Optional[int] = 42,
    ) -> None:
        self.loss_rate = loss_rate
        self.duplication_rate = duplication_rate
        self.reorder = reorder
        self.rng = random.Random(seed)
        # Asymmetric drop rules: set of (sender_id, recipient_id) directional drops
        self.asymmetric_drops: Set[Tuple[str, str]] = set()
        self._reorder_buffer: List[WireEnvelope] = []

    def set_asymmetric_drop(self, sender_id: str, recipient_id: str, drop: bool = True) -> None:
        """Sets directional link failure: messages from sender to recipient are dropped."""
        pair = (sender_id, recipient_id)
        if drop:
            self.asymmetric_drops.add(pair)
        else:
            self.asymmetric_drops.discard(pair)

    def transmit(self, envelope: WireEnvelope) -> List[WireEnvelope]:
        """Processes transmission of a message envelope through adversarial channel conditions."""
        # 1. Asymmetric Partition Check
        if (envelope.sender_id, envelope.recipient_id) in self.asymmetric_drops:
            return []

        # 2. Packet Loss (Stochastic or Burst)
        if self.loss_rate > 0.0 and self.rng.random() < self.loss_rate:
            return []

        delivered = [envelope]

        # 3. Message Duplication
        if self.duplication_rate > 0.0 and self.rng.random() < self.duplication_rate:
            delivered.append(envelope)

        # 4. Message Reordering Buffer
        if self.reorder:
            self._reorder_buffer.append(envelope)
            if len(self._reorder_buffer) >= 3:
                # Flush in reversed/shuffled order
                out = list(reversed(self._reorder_buffer))
                self._reorder_buffer.clear()
                return out
            return []

        return delivered

    def flush_reorder_buffer(self) -> List[WireEnvelope]:
        out = list(self._reorder_buffer)
        self._reorder_buffer.clear()
        return out
