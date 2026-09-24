r"""Gate P2: Live Policy Promotion Qualification.

Verifies the complete exceptional path end-to-end:
    NO POLICY -> DISCOVER -> OBSERVE -> QUALIFY -> PROMOTE -> FAST PATH

Proves the 7 Core P2 Invariants:
1. Unknown-state handling: No matching policy produces a controlled discovery request, not a crash.
2. Candidate isolation: Discovered graph G_c \notin \Pi_k until qualification completes.
3. Evidence accumulation: Observations accumulate tied to candidate and region R_c \subseteq U \times S.
4. Prospective qualification: Prospective observations evaluate: Correct?, Better?, Repeatable?, Worth promoting?
5. Atomic promotion: Promotion transitions \Pi_k -> \Pi_{k+1} without mutating \Pi_k snapshot.
6. Immediate deterministic reuse: Subsequent equivalent UoWs resolve directly to \Pi_{k+1} with N_discovery = 0.
7. Rollback: Drift invalidates \Pi_{k+1} policy while preserving evidence and allowing fallback.
8. PolicyDecisionRecord -> ExecutionCertificate causal chain-of-custody.
"""
from __future__ import annotations

import pytest

from uow.contracts import (
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    Route,
    Successor,
    UoW,
    make_uow,
)
from uow.ontology import MatrixCell, WorkCategory
from uow.policy import (
    CandidateObservation,
    DecisionSource,
    DiscoveryCandidate,
    DiscoveryEngine,
    DriftMonitor,
    ExecutionCertificate,
    GraphExecutionError,
    Policy,
    PolicyDecisionRecord,
    PolicyEvidence,
    PolicyRegion,
    PolicyResolution,
    PolicyResolver,
    PolicyRegistry,
    QualificationEngine,
    QualifiedPolicyCandidate,
    RealizationGraph,
    RealizationStage,
    RealizationGraphExecutor,
    ResourceCapability,
    WorkRequirement,
    WorldConditions,
)


@pytest.fixture
def uow_u1() -> UoW:
    """Create authoritative parent UoW U1."""
    route = Route(
        guard=Guard(GuardOp.ALWAYS),
        mutations=(Mutation(MutationOp.SET, "counter", 100),),
        successor=Successor.halt(),
    )
    return make_uow(
        identity="uow_dense_tensor_u1",
        routes=[route],
        matrix_cell=MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA),
        layer="tensor",
        parent_context="production_runtime",
    )


@pytest.fixture
def uow_u2() -> UoW:
    """Create subsequent identical UoW U2 (equivalent requirement)."""
    route = Route(
        guard=Guard(GuardOp.ALWAYS),
        mutations=(Mutation(MutationOp.SET, "counter", 100),),
        successor=Successor.halt(),
    )
    return make_uow(
        identity="uow_dense_tensor_u2",
        routes=[route],
        matrix_cell=MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA),
        layer="tensor",
        parent_context="production_runtime",
    )


@pytest.fixture
def world_s() -> WorldConditions:
    return WorldConditions.create(
        available_capabilities=[
            ResourceCapability.LOW_POWER_ACCELERATOR,
            ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR,
            ResourceCapability.GENERAL_COMPUTE,
            ResourceCapability.DETERMINISTIC_AUTHORITY,
        ],
        power_budget_w=120.0,
        max_concurrency=4,
    )


def test_p2_1_unknown_state_handling(uow_u1: UoW, world_s: WorldConditions):
    """P2.1: No matching policy produces controlled discovery request rather than execution error."""
    registry = PolicyRegistry()
    discovery = DiscoveryEngine()
    resolver = PolicyResolver(registry, discovery)

    req = WorkRequirement.from_uow(uow_u1, scale=500)
    assert registry.total_policies == 0

    # Must NOT raise exception; returns mode == BOUNDED_DISCOVERY
    res = resolver.resolve(req, world_s)
    assert res.mode == "BOUNDED_DISCOVERY"
    assert res.policy is None
    assert res.candidate is not None
    assert res.decision_record.decision_source == DecisionSource.DISCOVERY_CANDIDATE
    assert res.decision_record.resolution_status == "NO_QUALIFIED_POLICY"


def test_p2_2_candidate_isolation(uow_u1: UoW, world_s: WorldConditions):
    r"""P2.2: Discovered graph G_c remains strictly outside registry \Pi_k during exploration."""
    registry = PolicyRegistry()
    discovery = DiscoveryEngine()
    resolver = PolicyResolver(registry, discovery)
    executor = RealizationGraphExecutor()

    req = WorkRequirement.from_uow(uow_u1, scale=500)
    res = resolver.resolve(req, world_s)
    candidate = res.candidate
    assert candidate is not None

    # Registry snapshot Pi_1 remains completely empty
    v1, policies_v1 = registry.snapshot()
    assert v1 == 1
    assert len(policies_v1) == 0

    # Candidate executes non-authoritatively
    cert = executor.execute_graph(
        graph=candidate.graph,
        requirement=req,
        world=world_s,
        decision=res.decision_record,
    )
    assert cert.is_certified is True

    # Candidate is STILL not in the registry!
    assert registry.total_policies == 0
    assert registry.version == 1


def test_p2_3_and_4_prospective_qualification_gates(uow_u1: UoW, world_s: WorldConditions):
    """P2.3 & P2.4: Evidence accumulates prospectively and answers the 4 qualification questions."""
    registry = PolicyRegistry()
    discovery = DiscoveryEngine()
    qualifier = QualificationEngine(registry, min_observations=3)
    resolver = PolicyResolver(registry, discovery)
    executor = RealizationGraphExecutor()

    req = WorkRequirement.from_uow(uow_u1, scale=500)
    res = resolver.resolve(req, world_s)
    candidate = res.candidate

    # Observations not yet sufficient (N=1 < 3)
    cert1 = executor.execute_graph(candidate.graph, req, world_s, decision=res.decision_record)
    qualifier.record_observation(candidate.candidate_id, req, world_s, cert1.measured_energy_wh, cert1.measured_latency_ms)
    assert qualifier.qualify_candidate(candidate, req, world_s) is None

    # Accumulate observation 2 & 3
    for _ in range(2):
        cert = executor.execute_graph(candidate.graph, req, world_s, decision=res.decision_record)
        qualifier.record_observation(candidate.candidate_id, req, world_s, cert.measured_energy_wh, cert.measured_latency_ms)

    assert qualifier.get_observation_count(candidate.candidate_id) == 3

    # Prospective Qualification check
    baseline_energy = cert1.measured_energy_wh * 2.0  # Monolithic baseline is higher
    qualified = qualifier.qualify_candidate(
        candidate=candidate,
        requirement=req,
        conditions=world_s,
        baseline_energy_wh=baseline_energy,
    )

    assert qualified is not None
    assert isinstance(qualified, QualifiedPolicyCandidate)
    # Answers the 4 questions:
    assert qualified.evidence.correctness_breaches == 0  # 1. Correct?
    assert qualified.savings_pct > 30.0                  # 2. Better?
    assert qualified.evidence.energy_ci95_upper < baseline_energy  # 3. Repeatable?
    assert qualified.roi > 1.0                           # 4. Worth promoting?


def test_p2_5_and_6_atomic_promotion_and_immediate_reuse(
    uow_u1: UoW,
    uow_u2: UoW,
    world_s: WorldConditions,
):
    """P2.5 & P2.6: Atomic promotion Pi_k -> Pi_{k+1} and immediate zero-discovery reuse for U2."""
    registry = PolicyRegistry()
    discovery = DiscoveryEngine()
    qualifier = QualificationEngine(registry, min_observations=3)
    resolver = PolicyResolver(registry, discovery)
    executor = RealizationGraphExecutor()

    req_u1 = WorkRequirement.from_uow(uow_u1, scale=500)
    res_u1 = resolver.resolve(req_u1, world_s)
    candidate = res_u1.candidate

    # Accumulate 3 prospective observations
    for _ in range(3):
        cert = executor.execute_graph(candidate.graph, req_u1, world_s, decision=res_u1.decision_record)
        qualifier.record_observation(candidate.candidate_id, req_u1, world_s, cert.measured_energy_wh, cert.measured_latency_ms)

    qualified = qualifier.qualify_candidate(candidate, req_u1, world_s)
    assert qualified is not None

    v_before = registry.version
    assert v_before == 1

    # Atomic Promotion!
    promoted_policy = qualifier.promote(qualified)
    assert promoted_policy is not None
    assert registry.version == 2  # Pi_1 -> Pi_2 atomically
    assert promoted_policy.is_active is True

    # Immediate Deterministic Reuse for subsequent equivalent UoW U2
    req_u2 = WorkRequirement.from_uow(uow_u2, scale=500)
    # U2 is an equivalent workload in the same operating region
    res_u2 = resolver.resolve(req_u2, world_s)

    # Invariants confirmed:
    assert res_u2.mode == "POLICY_REUSE"
    assert res_u2.policy is not None
    assert res_u2.policy.policy_id == promoted_policy.policy_id
    assert res_u2.policy_registry_version == 2
    assert res_u2.candidate is None  # Zero discovery!
    assert res_u2.decision_record.decision_source == DecisionSource.QUALIFIED_POLICY


def test_p2_7_rollback_and_drift_invalidation(
    uow_u1: UoW,
    uow_u2: UoW,
    world_s: WorldConditions,
):
    """P2.7: Drift invalidates policy (Pi_2 -> Pi_3), preserves evidence, and safely falls back."""
    registry = PolicyRegistry()
    discovery = DiscoveryEngine()
    qualifier = QualificationEngine(registry, min_observations=3)
    resolver = PolicyResolver(registry, discovery)
    executor = RealizationGraphExecutor()
    drift_monitor = DriftMonitor(registry, energy_drift_threshold=0.20, consecutive_violations_to_invalidate=2)

    # Qualify and promote policy
    req_u1 = WorkRequirement.from_uow(uow_u1, scale=500)
    res_u1 = resolver.resolve(req_u1, world_s)
    promoted = qualifier.evaluate_and_promote(
        candidate=res_u1.candidate,
        requirement=req_u1,
        conditions=world_s,
        observed_energies_wh=[0.00032] * 3,
        observed_latencies_ms=[10.0] * 3,
        correctness_breaches=0,
    )
    assert registry.version == 2

    # Simulate 2 consecutive degraded executions
    for i in range(2):
        degraded_cert = ExecutionCertificate(
            certificate_id=f"deg_{i}",
            uow_id=req_u1.uow_id,
            graph_id=promoted.realization_graph.graph_id,
            state_hash="hash_deg",
            is_certified=True,
            measured_energy_wh=0.00055,  # +71% drift
            measured_latency_ms=10.0,
            authority_compliant=True,
            policy_id=promoted.policy_id,
        )
        is_invalidated = drift_monitor.record_and_evaluate(degraded_cert, promoted)

    assert is_invalidated is True
    # Rollback version incremented atomically
    assert registry.version == 3
    # Historical policy preserved in inactive state
    retrieved = registry.get_policy(promoted.policy_id)
    assert retrieved is not None
    assert retrieved.is_active is False
    assert retrieved.evidence.observations_count == 3  # Evidence preserved!

    # Next execution for U2 safely triggers bounded discovery
    req_u2 = WorkRequirement.from_uow(uow_u2, scale=500)
    res_u2 = resolver.resolve(req_u2, world_s)
    assert res_u2.mode == "BOUNDED_DISCOVERY"
    assert res_u2.candidate is not None


def test_p2_decision_record_to_certificate_chain(
    uow_u1: UoW,
    world_s: WorldConditions,
):
    """P2.8: DecisionRecord -> ExecutionCertificate cryptographic chain-of-custody."""
    registry = PolicyRegistry()
    discovery = DiscoveryEngine()
    qualifier = QualificationEngine(registry, min_observations=3)
    resolver = PolicyResolver(registry, discovery)
    executor = RealizationGraphExecutor()

    req = WorkRequirement.from_uow(uow_u1, scale=500)
    res = resolver.resolve(req, world_s)

    promoted = qualifier.evaluate_and_promote(
        candidate=res.candidate,
        requirement=req,
        conditions=world_s,
        observed_energies_wh=[0.00032] * 3,
        observed_latencies_ms=[10.0] * 3,
        correctness_breaches=0,
    )

    # Execute under promoted policy
    res_promoted = resolver.resolve(req, world_s)
    cert = executor.execute_graph(
        graph=res_promoted.graph,
        requirement=req,
        world=world_s,
        decision=res_promoted.decision_record,
    )

    # Chain of custody verified
    assert cert.decision_id == res_promoted.decision_record.decision_id
    assert cert.decision_digest == res_promoted.decision_record.decision_digest
    assert cert.policy_id == promoted.policy_id
    assert cert.policy_registry_version == registry.version
    assert cert.composite_hash != ""
