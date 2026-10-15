"""Q6 Cryptographic Module: Ed25519 Authenticated Voting for Authority Replicas."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Mapping

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature
from uow.state import canonical_json

@dataclass(frozen=True)
class AuthorityKeypair:
    node_id: str
    _private_key: ed25519.Ed25519PrivateKey
    public_key_bytes: bytes

    @classmethod
    def generate(cls, node_id: str) -> AuthorityKeypair:
        priv = ed25519.Ed25519PrivateKey.generate()
        pub = priv.public_key().public_bytes_raw()
        return cls(node_id=node_id, _private_key=priv, public_key_bytes=pub)

    @classmethod
    def from_seed(cls, node_id: str, seed: bytes) -> AuthorityKeypair:
        # Deterministic key generation from 32-byte seed
        if len(seed) != 32:
            seed = hashlib.sha256(seed).digest()
        priv = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
        pub = priv.public_key().public_bytes_raw()
        return cls(node_id=node_id, _private_key=priv, public_key_bytes=pub)

    @property
    def public_key_hex(self) -> str:
        return self.public_key_bytes.hex()

    def sign(self, message: bytes) -> str:
        sig = self._private_key.sign(message)
        return sig.hex()

class KeyRegistry:
    """Registry of trusted authority replica public keys."""

    def __init__(self, public_keys: Mapping[str, bytes]) -> None:
        self._keys: Dict[str, ed25519.Ed25519PublicKey] = {}
        self._hex_keys: Dict[str, str] = {}
        for nid, pbytes in public_keys.items():
            self._keys[nid] = ed25519.Ed25519PublicKey.from_public_bytes(pbytes)
            self._hex_keys[nid] = pbytes.hex()

    def has_node(self, node_id: str) -> bool:
        return node_id in self._keys

    def get_public_key_hex(self, node_id: str) -> str:
        return self._hex_keys[node_id]

    def verify(self, node_id: str, message: bytes, signature_hex: str) -> bool:
        pub = self._keys.get(node_id)
        if pub is None:
            return False
        try:
            sig = bytes.fromhex(signature_hex)
            pub.verify(sig, message)
            return True
        except (InvalidSignature, ValueError):
            return False

def hash_payload(data: object) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()
