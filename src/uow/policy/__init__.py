"""Public API for Policy-Aware UoW Orchestration.

Architectural Principles:
- Architecture understands capabilities;
- Policy understands realizations;
- Drivers understand devices.

Core Abstractions:
- WorkRequirement, WorldConditions, RealizationStage, RealizationGraph
- Policy, PolicyRegion, PolicyEvidence, ExecutionCertificate
- DecisionSource, PolicyDecisionRecord
- PolicyRegistry, PolicyResolver, PolicyResolution
- RealizationGraphExecutor, GraphExecutionError
- DiscoveryEngine, DiscoveryCandidate
- QualificationEngine, CandidateObservation, QualifiedPolicyCandidate
- DriftMonitor
"""
from __future__ import annotations

from .authority import (
    AuthorityError,
    AuthorityRule,
    AuthorityVote,
    ConflictingProposalError,
    DistributedAuthorityNode,
    DistributedPolicyGovernor,
    InvalidVoteError,
    QuorumNotSatisfiedError,
    StaleProposalError,
)
from .discovery import DiscoveryCandidate, DiscoveryEngine
from .drift import DriftEvaluationResult, DriftMonitor, MultidimensionalDriftMonitor
from .executor import GraphExecutionError, RealizationGraphExecutor
from .models import (
    AuthorityVote,
    DecisionSource,
    DistributedPolicyCertificate,
    ExecutionCertificate,
    InFlightTransaction,
    Policy,
    PolicyDecisionRecord,
    PolicyEvidence,
    PolicyLifecycleEvent,
    PolicyLifecycleRecord,
    PolicyRegion,
    PolicyState,
    PolicyTransitionProposal,
    PolicyTransitionType,
    RealizationGraph,
    RealizationStage,
    RecoveryRecord,
    RecoveryResultStatus,
    ResourceCapability,
    TransactionExecutionStatus,
    WorkRequirement,
    WorldConditions,
)
from .persistence import (
    CorruptedStorageError,
    DurablePolicyStore,
    IncompleteCommitError,
    PersistenceError,
)
from .qualification import (
    CandidateObservation,
    QualificationEngine,
    QualifiedPolicyCandidate,
)
from .recovery import (
    NodeRecoveryCoordinator,
    SplitBrainRecoveryError,
)
from .registry import PolicyRegistry
from .resolver import PolicyResolution, PolicyResolver

__all__ = [
    "AuthorityError",
    "AuthorityRule",
    "AuthorityVote",
    "CandidateObservation",
    "ConflictingProposalError",
    "CorruptedStorageError",
    "DecisionSource",
    "DiscoveryCandidate",
    "DiscoveryEngine",
    "DistributedAuthorityNode",
    "DistributedPolicyCertificate",
    "DistributedPolicyGovernor",
    "DriftEvaluationResult",
    "DriftMonitor",
    "DurablePolicyStore",
    "ExecutionCertificate",
    "GraphExecutionError",
    "IncompleteCommitError",
    "InFlightTransaction",
    "InvalidVoteError",
    "MultidimensionalDriftMonitor",
    "NodeRecoveryCoordinator",
    "PersistenceError",
    "Policy",
    "PolicyDecisionRecord",
    "PolicyEvidence",
    "PolicyLifecycleEvent",
    "PolicyLifecycleRecord",
    "PolicyRegion",
    "PolicyResolution",
    "PolicyResolver",
    "PolicyRegistry",
    "PolicyState",
    "PolicyTransitionProposal",
    "PolicyTransitionType",
    "QualificationEngine",
    "QualifiedPolicyCandidate",
    "QuorumNotSatisfiedError",
    "RealizationGraph",
    "RealizationGraphExecutor",
    "RealizationStage",
    "RecoveryRecord",
    "RecoveryResultStatus",
    "ResourceCapability",
    "SplitBrainRecoveryError",
    "StaleProposalError",
    "TransactionExecutionStatus",
    "WorkRequirement",
    "WorldConditions",
]
