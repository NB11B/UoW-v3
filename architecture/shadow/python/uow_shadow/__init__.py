"""R3 research-only UoW shadow semantic package."""

from .types import (
    AttestationKind,
    AttestationRef,
    AuthoritativeStateRef,
    BindingRef,
    CausalCoordinate,
    ConformanceDecision,
    ConformanceResult,
    EvidenceEntryRef,
    ExternalEffectRef,
    ProposalEnvelope,
    RealizationRef,
    SemanticContractRef,
)
from .requirements import (
    Capability,
    MatchContext,
    MatcherKind,
    Requirement,
    match_requirement,
)

__all__ = [
    "AttestationKind",
    "AttestationRef",
    "AuthoritativeStateRef",
    "BindingRef",
    "Capability",
    "CausalCoordinate",
    "ConformanceDecision",
    "ConformanceResult",
    "EvidenceEntryRef",
    "ExternalEffectRef",
    "MatchContext",
    "MatcherKind",
    "ProposalEnvelope",
    "RealizationRef",
    "Requirement",
    "SemanticContractRef",
    "match_requirement",
]
