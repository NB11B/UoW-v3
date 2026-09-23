"""Cryptographic model identity and lineage for adaptive proposers (Gate U15.1)."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Dict, Mapping, Optional

from ..state import canonical_json


@dataclass(frozen=True)
class ModelIdentity:
    """Cryptographic lineage identity for adaptive proposer models (Gate U15.1).

    Enforces lineage tracking across model parameter updates:
        theta_0 -> theta_1 -> theta_2 -> ...

    An adaptive model gets exactly the same authority as a static model: ZERO.
    """

    model_id: str
    model_version: str
    model_artifact_hash: str
    training_generation: int = 0
    parent_model_hash: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    identity_hash: str = field(default="")

    def __post_init__(self) -> None:
        expected = self.calculate_hash(
            model_id=self.model_id,
            model_version=self.model_version,
            model_artifact_hash=self.model_artifact_hash,
            training_generation=self.training_generation,
            parent_model_hash=self.parent_model_hash,
        )
        if not self.identity_hash:
            object.__setattr__(self, "identity_hash", expected)
        elif self.identity_hash != expected:
            raise ValueError(
                f"ModelIdentity hash mismatch: {self.identity_hash} != {expected}"
            )

    @staticmethod
    def calculate_hash(
        model_id: str,
        model_version: str,
        model_artifact_hash: str,
        training_generation: int,
        parent_model_hash: Optional[str],
    ) -> str:
        payload = {
            "model_id": model_id,
            "model_version": model_version,
            "model_artifact_hash": model_artifact_hash,
            "training_generation": training_generation,
            "parent_model_hash": parent_model_hash,
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def child_identity(
        self,
        new_artifact_hash: str,
        new_version: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> ModelIdentity:
        """Derives the next generation identity with cryptographic parent linkage."""
        return ModelIdentity(
            model_id=self.model_id,
            model_version=new_version if new_version is not None else self.model_version,
            model_artifact_hash=new_artifact_hash,
            training_generation=self.training_generation + 1,
            parent_model_hash=self.identity_hash,
            metadata=dict(metadata) if metadata is not None else dict(self.metadata),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "model_artifact_hash": self.model_artifact_hash,
            "training_generation": self.training_generation,
            "parent_model_hash": self.parent_model_hash,
            "metadata": dict(self.metadata),
            "identity_hash": self.identity_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModelIdentity:
        return cls(
            model_id=str(data["model_id"]),
            model_version=str(data.get("model_version", "1.0.0")),
            model_artifact_hash=str(data["model_artifact_hash"]),
            training_generation=int(data.get("training_generation", 0)),
            parent_model_hash=(
                str(data["parent_model_hash"]) if data.get("parent_model_hash") else None
            ),
            metadata=dict(data.get("metadata", {})),
            identity_hash=str(data.get("identity_hash", "")),
        )
