"""Certified learning-feedback object for autonomous adaptive proposers (Gate U15.2)."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from ..state import WorldState, canonical_json
from .identity import ModelIdentity
from .types import ModelProposal, ProposalCertificate


@dataclass(frozen=True)
class AdaptationObservation:
    """Deterministic, certified supervisory feedback signal for model adaptation (Gate U15.2).

    Contains strictly authoritative outcomes emitted by the deterministic Judge and sequencer:
        - Input state fingerprint and sequence epoch
        - Pure proposal hash and model identity lineage
        - Accepted and rejected candidate schedules with diagnostic reasons
        - Fallback activation status
        - Committed world state outcome (or unmutated state on rejection)
        - Non-authoritative observational metrics (resource utilization, latency)

    Invariant:
        Authority output -> Learning observation.
        Learner -> Authority mutation is strictly FORBIDDEN.
        An adaptive model has ZERO commit authority.
    """

    observation_id: str
    pre_state_hash: str
    pre_sequence: int
    pre_epoch: int
    proposal_hash: str
    model_id: str
    model_version: str
    model_artifact_hash: str
    training_generation: int
    parent_model_hash: Optional[str]
    accepted_tasks: Tuple[str, ...]
    rejected_tasks: Mapping[str, str]
    fallback_triggered: bool
    committed: bool
    post_state_hash: str
    post_sequence: int
    resource_utilization: Mapping[str, float] = field(default_factory=dict)
    observed_latency_us: float = 0.0
    certificate_hash: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    observation_hash: str = field(default="")

    def __post_init__(self) -> None:
        expected = self.calculate_hash(
            observation_id=self.observation_id,
            pre_state_hash=self.pre_state_hash,
            pre_sequence=self.pre_sequence,
            pre_epoch=self.pre_epoch,
            proposal_hash=self.proposal_hash,
            model_id=self.model_id,
            model_version=self.model_version,
            model_artifact_hash=self.model_artifact_hash,
            training_generation=self.training_generation,
            parent_model_hash=self.parent_model_hash,
            accepted_tasks=self.accepted_tasks,
            rejected_tasks=dict(self.rejected_tasks),
            fallback_triggered=self.fallback_triggered,
            committed=self.committed,
            post_state_hash=self.post_state_hash,
            post_sequence=self.post_sequence,
            certificate_hash=self.certificate_hash,
        )
        if not self.observation_hash:
            object.__setattr__(self, "observation_hash", expected)
        elif self.observation_hash != expected:
            raise ValueError(
                f"AdaptationObservation hash mismatch: {self.observation_hash} != {expected}"
            )

    @staticmethod
    def calculate_hash(
        observation_id: str,
        pre_state_hash: str,
        pre_sequence: int,
        pre_epoch: int,
        proposal_hash: str,
        model_id: str,
        model_version: str,
        model_artifact_hash: str,
        training_generation: int,
        parent_model_hash: Optional[str],
        accepted_tasks: Tuple[str, ...],
        rejected_tasks: Mapping[str, str],
        fallback_triggered: bool,
        committed: bool,
        post_state_hash: str,
        post_sequence: int,
        certificate_hash: str,
    ) -> str:
        payload = {
            "observation_id": observation_id,
            "pre_state_hash": pre_state_hash,
            "pre_sequence": pre_sequence,
            "pre_epoch": pre_epoch,
            "proposal_hash": proposal_hash,
            "model_id": model_id,
            "model_version": model_version,
            "model_artifact_hash": model_artifact_hash,
            "training_generation": training_generation,
            "parent_model_hash": parent_model_hash,
            "accepted_tasks": list(accepted_tasks),
            "rejected_tasks": dict(sorted(rejected_tasks.items())),
            "fallback_triggered": fallback_triggered,
            "committed": committed,
            "post_state_hash": post_state_hash,
            "post_sequence": post_sequence,
            "certificate_hash": certificate_hash,
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "pre_state_hash": self.pre_state_hash,
            "pre_sequence": self.pre_sequence,
            "pre_epoch": self.pre_epoch,
            "proposal_hash": self.proposal_hash,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "model_artifact_hash": self.model_artifact_hash,
            "training_generation": self.training_generation,
            "parent_model_hash": self.parent_model_hash,
            "accepted_tasks": list(self.accepted_tasks),
            "rejected_tasks": dict(self.rejected_tasks),
            "fallback_triggered": self.fallback_triggered,
            "committed": self.committed,
            "post_state_hash": self.post_state_hash,
            "post_sequence": self.post_sequence,
            "resource_utilization": dict(self.resource_utilization),
            "observed_latency_us": self.observed_latency_us,
            "certificate_hash": self.certificate_hash,
            "metadata": dict(self.metadata),
            "observation_hash": self.observation_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AdaptationObservation:
        return cls(
            observation_id=str(data["observation_id"]),
            pre_state_hash=str(data["pre_state_hash"]),
            pre_sequence=int(data["pre_sequence"]),
            pre_epoch=int(data.get("pre_epoch", 0)),
            proposal_hash=str(data["proposal_hash"]),
            model_id=str(data["model_id"]),
            model_version=str(data.get("model_version", "1.0.0")),
            model_artifact_hash=str(data.get("model_artifact_hash", "")),
            training_generation=int(data.get("training_generation", 0)),
            parent_model_hash=(
                str(data["parent_model_hash"]) if data.get("parent_model_hash") else None
            ),
            accepted_tasks=tuple(str(x) for x in data.get("accepted_tasks", ())),
            rejected_tasks={str(k): str(v) for k, v in data.get("rejected_tasks", {}).items()},
            fallback_triggered=bool(data.get("fallback_triggered", False)),
            committed=bool(data.get("committed", False)),
            post_state_hash=str(data["post_state_hash"]),
            post_sequence=int(data["post_sequence"]),
            resource_utilization={
                str(k): float(v) for k, v in data.get("resource_utilization", {}).items()
            },
            observed_latency_us=float(data.get("observed_latency_us", 0.0)),
            certificate_hash=str(data.get("certificate_hash", "")),
            metadata=dict(data.get("metadata", {})),
            observation_hash=str(data.get("observation_hash", "")),
        )


def create_adaptation_observation(
    pre_state: WorldState,
    proposal: Optional[ModelProposal],
    certificate: ProposalCertificate,
    post_state: Optional[WorldState] = None,
    *,
    model_identity: Optional[ModelIdentity] = None,
    committed: bool = False,
    resource_utilization: Optional[Mapping[str, float]] = None,
    observed_latency_us: float = 0.0,
    observation_id: Optional[str] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> AdaptationObservation:
    """Constructs a certified AdaptationObservation binding Judge certification and commit outcome.

    Invariants:
        1. If no post_state is provided or committed is False, post_state defaults to pre_state.
        2. If proposal was rejected, post_state must equal pre_state (no mutation on rejection).
        3. Model lineage fields are derived from model_identity or proposal metadata.
    """
    actual_post = post_state if (committed and post_state is not None) else pre_state
    obs_id = (
        observation_id
        if observation_id is not None
        else f"obs-{pre_state.sequence}-{certificate.certificate_hash[:12]}"
    )

    # Resolve model identity attributes
    if model_identity is not None:
        m_id = model_identity.model_id
        m_ver = model_identity.model_version
        m_art = model_identity.model_artifact_hash
        m_gen = model_identity.training_generation
        m_parent = model_identity.parent_model_hash
    elif proposal is not None:
        m_id = proposal.model_id
        m_ver = proposal.model_version
        m_art = getattr(proposal, "model_artifact_hash", "")
        m_gen = getattr(proposal, "training_generation", 0)
        m_parent = getattr(proposal, "parent_model_hash", None)
    else:
        m_id = "UNKNOWN"
        m_ver = "0.0.0"
        m_art = ""
        m_gen = 0
        m_parent = None

    prop_hash = proposal.proposal_hash if proposal is not None else ""

    return AdaptationObservation(
        observation_id=obs_id,
        pre_state_hash=pre_state.state_hash,
        pre_sequence=pre_state.sequence,
        pre_epoch=pre_state.sequence,
        proposal_hash=prop_hash,
        model_id=m_id,
        model_version=m_ver,
        model_artifact_hash=m_art,
        training_generation=m_gen,
        parent_model_hash=m_parent,
        accepted_tasks=certificate.accepted_tasks,
        rejected_tasks=certificate.rejected_tasks,
        fallback_triggered=certificate.fallback_triggered,
        committed=committed,
        post_state_hash=actual_post.state_hash,
        post_sequence=actual_post.sequence,
        resource_utilization=dict(resource_utilization) if resource_utilization else {},
        observed_latency_us=observed_latency_us,
        certificate_hash=certificate.certificate_hash,
        metadata=dict(metadata) if metadata else {},
    )


def validate_observation_integrity(
    obs: AdaptationObservation,
    pre_state: WorldState,
    certificate: ProposalCertificate,
    post_state: Optional[WorldState] = None,
) -> bool:
    """Verifies that an AdaptationObservation faithfully reflects authoritative state and certificate."""
    if obs.pre_state_hash != pre_state.state_hash:
        return False
    if obs.pre_sequence != pre_state.sequence:
        return False
    if obs.certificate_hash != certificate.certificate_hash:
        return False
    if obs.accepted_tasks != certificate.accepted_tasks:
        return False
    if dict(obs.rejected_tasks) != dict(certificate.rejected_tasks):
        return False
    if obs.fallback_triggered != certificate.fallback_triggered:
        return False

    actual_post = post_state if (obs.committed and post_state is not None) else pre_state
    if obs.post_state_hash != actual_post.state_hash:
        return False
    if obs.post_sequence != actual_post.sequence:
        return False

    # Verify cryptographic self-hash
    expected_hash = AdaptationObservation.calculate_hash(
        observation_id=obs.observation_id,
        pre_state_hash=obs.pre_state_hash,
        pre_sequence=obs.pre_sequence,
        pre_epoch=obs.pre_epoch,
        proposal_hash=obs.proposal_hash,
        model_id=obs.model_id,
        model_version=obs.model_version,
        model_artifact_hash=obs.model_artifact_hash,
        training_generation=obs.training_generation,
        parent_model_hash=obs.parent_model_hash,
        accepted_tasks=obs.accepted_tasks,
        rejected_tasks=dict(obs.rejected_tasks),
        fallback_triggered=obs.fallback_triggered,
        committed=obs.committed,
        post_state_hash=obs.post_state_hash,
        post_sequence=obs.post_sequence,
        certificate_hash=obs.certificate_hash,
    )
    return obs.observation_hash == expected_hash
