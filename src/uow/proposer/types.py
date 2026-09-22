"""Cryptographic data types and telemetry records for the Proposer Seam (Gate U14)."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ..state import canonical_json


@dataclass(frozen=True)
class ModelProposal:
    """Pure proposal emitted by an external, learned, stochastic, or hardware model P_theta.

    Contains proposed candidate schedule, predicted metrics, and cryptographic proposal hash.
    The proposer has ZERO commit authority over world state.
    """

    model_id: str
    model_version: str
    input_state_hash: str
    input_sequence: int
    input_epoch: int
    candidate_schedule: Tuple[str, ...]
    predicted_metrics: Mapping[str, float] = field(default_factory=dict)
    # Non-authoritative observational telemetry (e.g. accelerator device tags, debug logs).
    # Invariant: anything affecting authority or certification must be hash-bound;
    # metadata does not affect certification and is excluded from proposal_hash.
    metadata: Mapping[str, Any] = field(default_factory=dict)
    proposal_hash: str = field(default="")

    def __post_init__(self) -> None:
        expected = self.calculate_hash(
            model_id=self.model_id,
            model_version=self.model_version,
            input_state_hash=self.input_state_hash,
            input_sequence=self.input_sequence,
            input_epoch=self.input_epoch,
            candidate_schedule=self.candidate_schedule,
            predicted_metrics=dict(self.predicted_metrics),
        )
        if not self.proposal_hash:
            object.__setattr__(self, "proposal_hash", expected)
        elif self.proposal_hash != expected:
            raise ValueError(f"ModelProposal hash mismatch: {self.proposal_hash} != {expected}")

    @staticmethod
    def calculate_hash(
        model_id: str,
        model_version: str,
        input_state_hash: str,
        input_sequence: int,
        input_epoch: int,
        candidate_schedule: Tuple[str, ...],
        predicted_metrics: Mapping[str, float],
    ) -> str:
        payload = {
            "model_id": model_id,
            "model_version": model_version,
            "input_state_hash": input_state_hash,
            "input_sequence": input_sequence,
            "input_epoch": input_epoch,
            "candidate_schedule": list(candidate_schedule),
            "predicted_metrics": dict(sorted(predicted_metrics.items())),
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "input_state_hash": self.input_state_hash,
            "input_sequence": self.input_sequence,
            "input_epoch": self.input_epoch,
            "candidate_schedule": list(self.candidate_schedule),
            "predicted_metrics": dict(self.predicted_metrics),
            "metadata": dict(self.metadata),
            "proposal_hash": self.proposal_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModelProposal:
        return cls(
            model_id=str(data["model_id"]),
            model_version=str(data.get("model_version", "1.0.0")),
            input_state_hash=str(data["input_state_hash"]),
            input_sequence=int(data.get("input_sequence", 0)),
            input_epoch=int(data.get("input_epoch", 0)),
            candidate_schedule=tuple(str(x) for x in data.get("candidate_schedule", ())),
            predicted_metrics={str(k): float(v) for k, v in data.get("predicted_metrics", {}).items()},
            metadata=dict(data.get("metadata", {})),
            proposal_hash=str(data.get("proposal_hash", "")),
        )


@dataclass(frozen=True)
class ProposalCertificate:
    """Deterministic audit certificate produced by the Judge certifying a model proposal.

    Binds proposal hash to acceptance decisions, rejection diagnostics, and fallback activation.
    """

    proposal_hash: str
    is_valid: bool
    accepted_tasks: Tuple[str, ...]
    rejected_tasks: Mapping[str, str] = field(default_factory=dict)
    fallback_triggered: bool = False
    certificate_hash: str = field(default="")

    def __post_init__(self) -> None:
        expected = self.calculate_hash(
            proposal_hash=self.proposal_hash,
            is_valid=self.is_valid,
            accepted_tasks=self.accepted_tasks,
            rejected_tasks=dict(self.rejected_tasks),
            fallback_triggered=self.fallback_triggered,
        )
        if not self.certificate_hash:
            object.__setattr__(self, "certificate_hash", expected)
        elif self.certificate_hash != expected:
            raise ValueError(
                f"ProposalCertificate hash mismatch: {self.certificate_hash} != {expected}"
            )

    @staticmethod
    def calculate_hash(
        proposal_hash: str,
        is_valid: bool,
        accepted_tasks: Tuple[str, ...],
        rejected_tasks: Mapping[str, str],
        fallback_triggered: bool,
    ) -> str:
        payload = {
            "proposal_hash": proposal_hash,
            "is_valid": is_valid,
            "accepted_tasks": list(accepted_tasks),
            "rejected_tasks": dict(sorted(rejected_tasks.items())),
            "fallback_triggered": fallback_triggered,
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_hash": self.proposal_hash,
            "is_valid": self.is_valid,
            "accepted_tasks": list(self.accepted_tasks),
            "rejected_tasks": dict(self.rejected_tasks),
            "fallback_triggered": self.fallback_triggered,
            "certificate_hash": self.certificate_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ProposalCertificate:
        return cls(
            proposal_hash=str(data["proposal_hash"]),
            is_valid=bool(data["is_valid"]),
            accepted_tasks=tuple(str(x) for x in data.get("accepted_tasks", ())),
            rejected_tasks={str(k): str(v) for k, v in data.get("rejected_tasks", {}).items()},
            fallback_triggered=bool(data.get("fallback_triggered", False)),
            certificate_hash=str(data.get("certificate_hash", "")),
        )


@dataclass(frozen=True)
class TelemetryRecord:
    """Immutable audit pairing of model proposal and deterministic judge certificate."""

    step: int
    proposal: Optional[ModelProposal]
    certificate: ProposalCertificate

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "proposal": self.proposal.to_dict() if self.proposal is not None else None,
            "certificate": self.certificate.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TelemetryRecord:
        prop_data = data.get("proposal")
        return cls(
            step=int(data["step"]),
            proposal=ModelProposal.from_dict(prop_data) if prop_data is not None else None,
            certificate=ProposalCertificate.from_dict(data["certificate"]),
        )
