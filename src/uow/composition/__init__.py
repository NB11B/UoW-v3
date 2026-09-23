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
from .delegation import (
    AuthorityPermission,
    AuthorityScope,
    ChildUoWSpec,
    DelegationCertificate,
    DelegationResult,
    DistributedDelegationNode,
    validate_delegation,
)
from .convergence import (
    AuthoritativeHistory,
    HistoryEntry,
    HistoryEntryKind,
    MultiOrchestratorCluster,
)
from .wire import (
    AdversarialChannel,
    WireEnvelope,
    sign_envelope,
    verify_envelope,
)
from .host_node import (
    DurableWAL,
    PhysicalHostNode,
)
from .mutation import (
    AuthorityMutationVote,
    QuorumMutationCoordinator,
    RuntimeMutationProposal,
    RuntimeMutationQC,
    assemble_mutation_qc,
    sign_mutation_vote,
    verify_mutation_qc,
    verify_mutation_vote,
)

__all__ = [
    "ActorBinding",
    "ActorDescriptor",
    "ActorLease",
    "ActorRegistry",
    "AdaptiveCompositionRuntime",
    "AdaptiveGraphProposer",
    "AdversarialChannel",
    "AgentMessage",
    "AgentMessageKind",
    "AuthoritativeHistory",
    "AuthorityClass",
    "AuthorityMutationVote",
    "AuthorityObligation",
    "AuthorityPermission",
    "AuthorityScope",
    "CausalConstraint",
    "ChildUoWSpec",
    "CompositionCertifier",
    "CompositionRuntimeState",
    "DelegationCertificate",
    "DelegationResult",
    "DistributedActorFabric",
    "DistributedDelegationNode",
    "DurableWAL",
    "EvidenceObligation",
    "ExecutionRecord",
    "FailureSemantics",
    "GraphAdaptationObservation",
    "GraphReplacementCertificate",
    "GraphReplacementProposal",
    "HistoryEntry",
    "HistoryEntryKind",
    "MultiOrchestratorCluster",
    "NetworkAgent",
    "NodeExecutionResult",
    "ParentContract",
    "PhysicalHostNode",
    "QuorumMutationCoordinator",
    "RealizationGraph",
    "RealizationNode",
    "ResourceConstraint",
    "RuntimeMutationProposal",
    "RuntimeMutationQC",
    "SemanticProjection",
    "SubstitutionDecision",
    "SubstitutionStrategy",
    "TemporalConstraint",
    "WireEnvelope",
    "are_equivalent",
    "assemble_mutation_qc",
    "check_conformance",
    "project_semantics",
    "sign_envelope",
    "sign_mutation_vote",
    "validate_binding",
    "validate_delegation",
    "verify_envelope",
    "verify_mutation_qc",
    "verify_mutation_vote",
]
