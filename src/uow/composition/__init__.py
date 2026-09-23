"""A2: Adaptive Composition Runtime package.

Provides formal tools to separate parent semantic intent from execution topology:
  U = ParentContract(O, D, A, E, T, R, F)
  G = RealizationGraph(V, E)
  Phi(G, U) = SemanticProjection
"""
from .contract import (
    AuthorityObligation,
    CausalConstraint,
    EvidenceObligation,
    FailureSemantics,
    ParentContract,
    ResourceConstraint,
    TemporalConstraint,
)
from .graph import RealizationGraph, RealizationNode
from .projection import (
    SemanticProjection,
    are_equivalent,
    check_conformance,
    project_semantics,
)

from .actor import (
    ActorDescriptor,
    ActorRegistry,
    AuthorityClass,
)
from .binding import (
    ActorBinding,
    validate_binding,
)
from .policy import (
    AdaptiveGraphProposer,
    CompositionRuntimeState,
    GraphAdaptationObservation,
)
from .substitution import (
    CompositionCertifier,
    GraphReplacementCertificate,
    GraphReplacementProposal,
    SubstitutionDecision,
    SubstitutionStrategy,
)
from .runtime import (
    AdaptiveCompositionRuntime,
    ExecutionRecord,
    NodeExecutionResult,
)
from .fabric import (
    ActorLease,
    AgentMessage,
    AgentMessageKind,
    DistributedActorFabric,
    NetworkAgent,
)

__all__ = [
    "ActorBinding",
    "ActorDescriptor",
    "ActorLease",
    "ActorRegistry",
    "AdaptiveCompositionRuntime",
    "AdaptiveGraphProposer",
    "AgentMessage",
    "AgentMessageKind",
    "AuthorityClass",
    "AuthorityObligation",
    "CausalConstraint",
    "CompositionCertifier",
    "CompositionRuntimeState",
    "DistributedActorFabric",
    "EvidenceObligation",
    "ExecutionRecord",
    "FailureSemantics",
    "GraphAdaptationObservation",
    "GraphReplacementCertificate",
    "GraphReplacementProposal",
    "NetworkAgent",
    "NodeExecutionResult",
    "ParentContract",
    "RealizationGraph",
    "RealizationNode",
    "ResourceConstraint",
    "SemanticProjection",
    "SubstitutionDecision",
    "SubstitutionStrategy",
    "TemporalConstraint",
    "are_equivalent",
    "check_conformance",
    "project_semantics",
    "validate_binding",
]
