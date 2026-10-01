"""Unit-of-Work (UoW) Protocol and Runtime Architecture.

Minimal Root API:
    from uow import UoW, WorldState, execute

Namespaced Subsystems:
    uow.authority  - PROPOSE -> CERTIFY -> COMMIT, distributed quorum, evidence ledgers
    uow.runtime    - DAG orchestration, OCC transactions, resource leases, effects, proposers
    uow.autonomy   - Goal profiles, gap/deficit analysis, autonomous repair, closure
    uow.semantic   - Semantic mediation, ontology matrix, governed egress filters
    uow.economics  - Economic observations (compute/energy/market costs) as protocol data
    uow.protocol   - Canonical schemas and wire envelope definitions
    uow.adapters   - Hardware and neural model adapters (e.g. OpenVINO NPU)
"""
from __future__ import annotations

import sys
from typing import Any

# Canonical Minimal Root API
from .contracts import UoW
from .state import WorldState
from .engine import execute

# Namespaces
from . import authority as authority
from . import runtime as runtime
from . import autonomy as autonomy
from . import semantic as semantic
from . import economics as economics
from . import protocol as protocol
from . import adapters as adapters

__all__ = [
    "UoW",
    "WorldState",
    "execute",
    "authority",
    "runtime",
    "autonomy",
    "semantic",
    "economics",
    "protocol",
    "adapters",
]

# ---------------------------------------------------------------------------
# Backward-compatibility layer for legacy imports and existing test suites
# ---------------------------------------------------------------------------
from .contracts import (
    Boundary,
    Contract,
    EvidenceSpec,
    Guard,
    GuardOp,
    Header,
    Lifecycle,
    LifecyclePhase,
    Mutation,
    MutationOp,
    Realization,
    Route,
    Successor,
    SuccessorKind,
    Timing,
    make_uow,
)
from .engine import (
    CertificateResult,
    EvidenceLedger,
    EvidenceRecord,
    Proposal,
    commit,
    certify,
    execute_one,
    propose,
    run,
    validate_graph,
)
from .ontology import ALL_MATRIX_CELLS, MatrixCell, WorkCategory
from . import policy as policy
from .orchestration import (
    COMPLETION_PREFIX,
    ORCH_ACTIVE_KEY,
    ORCH_COMPLETED_KEY,
    ORCH_DEPS_KEY,
    ORCH_QUEUE_KEY,
    ORCH_TERMINATION_KEY,
    CompletionMaterializer,
    MaterializedUoW,
    OrchestrationState,
    SCHEDULER_CELL,
    SCHEDULER_ID,
    SchedulerMaterializer,
    TASK_CELL,
    bind_materialization,
    canonical_uow_payload,
    certify_materialization,
    create_initial_orchestration_state,
    evaluate_scheduler_step,
    execute_domain_task,
    execute_materialized,
    make_domain_task,
    run_orchestration,
    uow_fingerprint,
)
from .transactions import (
    CommitSequencer,
    DeterministicSequencer,
    HazardType,
    TransactionConflictError,
    TransactionDescriptor,
    WALSequencer,
    apply_transaction,
    create_transaction_descriptor,
    infer_footprint,
    validate_occ,
    verify_commit_bindings,
)
from .resources import (
    BaseSchedulingPolicy,
    CostEnergySchedulingPolicy,
    DEFAULT_HOST_CAPACITIES,
    FIFOSchedulingPolicy,
    GreedyCapacitySchedulingPolicy,
    ORCH_RESOURCES_KEY,
    PriorityDeadlineSchedulingPolicy,
    ResourceAwareCompletionMaterializer,
    ResourceAwareSchedulerMaterializer,
    ResourceBoundTask,
    ResourceLease,
    ResourceRequirement,
    ResourceState,
    filter_feasible_candidates,
    get_authoritative_resource_state,
    make_resource_domain_task,
    run_resource_orchestration,
    set_authoritative_resource_state,
    verify_requirement_binding,
)
from .effects import (
    CompensationSpec,
    EFFECT_CELL,
    EffectDescriptor,
    EffectReceipt,
    EffectRunner,
    EffectStatus,
    ExternalClientProtocol,
    HMACReceiptAuthenticator,
    LEGAL_EFFECT_TRANSITIONS,
    MockExternalClient,
    ORCH_COMPENSATION_FAILED_KEY,
    ORCH_EFFECTS_KEY,
    ORCH_SAGAS_KEY,
    PrefixReceiptAuthenticator,
    ReceiptAuthenticator,
    SagaCompensationError,
    SagaCoordinator,
    SagaRecord,
    SagaStatus,
    SagaStep,
    compute_idempotency_key,
    create_effect_descriptor,
    get_effects_map,
    get_sagas_map,
    verify_effect_intent_binding,
    verify_effect_receipt_binding,
)
from .proposer import (
    AdaptationObservation,
    AdaptiveProposer,
    BaseProposer,
    DeterministicFallbackScheduler,
    HeuristicSchedulingProposer,
    ModelIdentity,
    ModelProposal,
    PortableAdaptiveProposer,
    ProposalCertificate,
    ProposerOrchestrationEngine,
    QuorumCommitError,
    QuorumCommitSequencer,
    RandomProposer,
    ReferenceSchedulingProposer,
    TFWRProposer,
    TelemetryRecord,
    certify_proposal,
    create_adaptation_observation,
    run_proposer_orchestration,
    validate_observation_integrity,
)
from .composition import (
    ActorBinding,
    ActorDescriptor,
    ActorLease,
    ActorRegistry,
    AdaptiveCompositionRuntime,
    AdaptiveGraphProposer,
    AdversarialChannel,
    AgentMessage,
    AgentMessageKind,
    AntiThrashingHysteresis,
    AuthoritativeHistory,
    AuthorityClass,
    AuthorityMutationVote,
    AuthorityObligation,
    AuthorityPermission,
    AuthorityScope,
    CausalConstraint,
    ChildUoWSpec,
    CompositionCertifier,
    CompositionRuntimeState,
    ContinuousPerturbationTrace,
    DelegationCertificate,
    DelegationResult,
    DistributedActorFabric,
    DistributedDelegationNode,
    DurableWAL,
    EnduranceAdaptiveRuntime,
    EnvironmentalState,
    EvidenceObligation,
    ExecutionRecord,
    FailureSemantics,
    FixedBaselineRuntime,
    GraphAdaptationObservation,
    GraphReplacementCertificate,
    GraphReplacementProposal,
    HistoryEntry,
    HistoryEntryKind,
    LineageEdge,
    MultiOrchestratorCluster,
    NetworkAgent,
    NodeExecutionResult,
    ObservationPoisoningEngine,
    ParentContract,
    PhysicalHostNode,
    QuorumMutationCoordinator,
    RealizationGraph,
    RealizationNode,
    ResourceConstraint,
    RuleBasedRuntime,
    RuntimeMutationProposal,
    RuntimeMutationQC,
    RuntimeObjectiveFunction,
    SemanticProjection,
    SubstitutionDecision,
    SubstitutionStrategy,
    TemporalConstraint,
    TopologyLineage,
    WireEnvelope,
    are_equivalent,
    assemble_mutation_qc,
    check_conformance,
    project_semantics,
    sign_envelope,
    sign_mutation_vote,
    validate_binding,
    validate_delegation,
    verify_envelope,
    verify_mutation_qc,
    verify_mutation_vote,
)
