"""Research-only shadow semantic types for R3.

These types are not part of the canonical runtime and carry no authority.
They provide a stable semantic shape for matched conformance experiments.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Optional, Tuple


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, tuple):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, set):
        return frozenset(_freeze(v) for v in value)
    return value


@dataclass(frozen=True)
class CausalCoordinate:
    kind: str
    value: Any

    def __post_init__(self) -> None:
        if not self.kind:
            raise ValueError("CausalCoordinate.kind must be non-empty.")
        object.__setattr__(self, "value", _freeze(self.value))


@dataclass(frozen=True)
class AuthoritativeStateRef:
    state_id: str
    schema_id: str
    schema_version: str
    semantic_payload: Mapping[str, Any]
    causal_coordinate: CausalCoordinate
    status: str
    cursor: Optional[str] = None
    source_type: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "semantic_payload", _freeze(dict(self.semantic_payload)))


@dataclass(frozen=True)
class SemanticContractRef:
    contract_id: str
    contract_kind: str
    semantic_classification: Mapping[str, Any] = field(default_factory=dict)
    requirements: Tuple[Any, ...] = ()
    source_type: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "semantic_classification", _freeze(dict(self.semantic_classification)))
        object.__setattr__(self, "requirements", tuple(_freeze(x) for x in self.requirements))


@dataclass(frozen=True)
class RealizationRef:
    realization_id: str
    contract_id: str
    offered_capabilities: Tuple[Any, ...] = ()
    failure_behavior: Optional[str] = None
    evidence_profile: Optional[str] = None
    source_type: str = ""


@dataclass(frozen=True)
class BindingRef:
    binding_id: str
    realization_id: str
    role_to_actor: Mapping[str, str]
    causal_coordinate: CausalCoordinate
    binding_identity: str = ""
    source_type: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "role_to_actor", MappingProxyType(dict(self.role_to_actor)))


@dataclass(frozen=True)
class ProposalEnvelope:
    proposal_id: str
    proposal_kind: str
    proposer_id: str
    subject_contract_id: str
    precondition_context_id: str
    causal_coordinate: CausalCoordinate
    candidate_payload: Mapping[str, Any]
    proposal_identity: str
    predicted_metrics: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    source_type: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_payload", _freeze(dict(self.candidate_payload)))
        object.__setattr__(self, "predicted_metrics", _freeze(dict(self.predicted_metrics)))
        object.__setattr__(self, "metadata", _freeze(dict(self.metadata)))


class ConformanceDecision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


@dataclass(frozen=True)
class ConformanceResult:
    conformance_id: str
    subject_id: str
    contract_id: str
    context_id: str
    decision: ConformanceDecision
    violations: Tuple[str, ...] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)
    source_validator: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "violations", tuple(str(v) for v in self.violations))
        object.__setattr__(self, "evidence", _freeze(dict(self.evidence)))

    @property
    def accepted(self) -> bool:
        return self.decision is ConformanceDecision.ACCEPT


class AttestationKind(str, Enum):
    CONFORMANCE_CERTIFICATE = "CONFORMANCE_CERTIFICATE"
    AUTHORITY_VOTE = "AUTHORITY_VOTE"
    QUORUM_AUTHORIZATION = "QUORUM_AUTHORIZATION"
    DELEGATION_GRANT = "DELEGATION_GRANT"
    EXTERNAL_RECEIPT = "EXTERNAL_RECEIPT"


@dataclass(frozen=True)
class AttestationRef:
    attestation_id: str
    attestation_kind: AttestationKind
    issuer_id: str
    subject_id: str
    policy_or_contract_id: str
    causal_coordinate: CausalCoordinate
    claim_or_decision: str
    evidence_profile: str
    proof_reference: Optional[str] = None
    source_type: str = ""


@dataclass(frozen=True)
class EvidenceEntryRef:
    entry_id: str
    event_kind: str
    subject_id: str
    causal_references: Tuple[str, ...]
    pre_context_identity: Optional[str]
    post_context_identity_or_outcome: str
    evidence_profile: str
    entry_identity: str
    proposal_reference: Optional[str] = None
    conformance_reference: Optional[str] = None
    authorization_reference: Optional[str] = None
    issuer_or_source: Optional[str] = None
    source_type: str = ""


@dataclass(frozen=True)
class ExternalEffectRef:
    effect_id: str
    governing_work_id: str
    intent: str
    request: Mapping[str, Any]
    idempotency_id: str
    precondition_context_id: str
    status: str
    observation: Optional[Mapping[str, Any]] = None
    receipt_reference: Optional[str] = None
    source_type: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "request", _freeze(dict(self.request)))
        if self.observation is not None:
            object.__setattr__(self, "observation", _freeze(dict(self.observation)))
