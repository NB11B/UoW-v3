r"""Gate P3: Live Drift, Invalidation, and Requalification Qualification.

Verifies the complete stale-knowledge departure and replacement lifecycle:
    QUALIFIED POLICY -> LIVE EXECUTION -> DRIFT -> INVALIDATE -> BOUNDED DISCOVERY -> REQUALIFY -> PROMOTE NEW VERSION

Proves the 9 Core P3 Behaviors:
1. Normal operation with live telemetry accumulation.
2. Multidimensional drift: Delta E (energy), Delta L (latency), Delta P (power), Delta C (congestion), Delta Q (quality).
3. Hysteresis state machine: Single noisy deviation triggers DRIFT_SUSPECTED without premature invalidation; recovery clears suspicion back to ACTIVE.
4. Sustained drift triggers atomic invalidation (\Pi_k -> \Pi_{k+1}).
5. In-flight execution preservation (The Hard Case): In-flight UoWs retain their original decision context (\Pi_k, policy_id, world_snapshot) while new UoWs see \Pi_{k+1} and fall back to bounded discovery.
6. Replacement discovery & prospective qualification within new operating region.
7. Monotonic policy versioning (\pi^{(1)} -> \pi^{(2)}) preserving operational history without overwriting.
8. Restoration of prior regime & policy requalification / reactivation.
9. Complete 3-tier audit chain: PolicyLifecycleRecord -> PolicyDecisionRecord -> ExecutionCertificate.
"""
from __future__ import annotations

import concurrent.futures
import time
from typing import List

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
    DecisionSource,
    DiscoveryEngine,
    ExecutionCertificate,
    MultidimensionalDriftMonitor,
    Policy,
    PolicyDecisionRecord,
    PolicyEvidence,
    PolicyLifecycleEvent,
    PolicyLifecycleRecord,
    PolicyRegion,
    PolicyRegistry,
    PolicyResolution,
    PolicyResolver,
    PolicyState,
    QualificationEngine,
    RealizationGraph,
    RealizationGraphExecutor,
    ResourceCapability,
    WorkRequirement,
    WorldConditions,
)


@pytest.fixture
def base_uow_route() -> List[Route]:
    return [
        Route(
            guard=Guard(GuardOp.ALWAYS),
            mutations=(
                Mutation(MutationOp.SET, "state_status", "validated"),
                Mutation(MutationOp.SET, "hash_accumulator", 999),
            ),
            successor=Successor.halt(),
        )
    ]


@pytest.fixture
def uow_stream_1(base_uow_route: List[Route]) -> UoW:
    return make_uow(
        identity="uow_stream_p3_001",
        routes=base_uow_route,
        matrix_cell=MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA),
        layer="streaming",
    )


@pytest.fixture
def uow_stream_2(base_uow_route: List[Route]) -> UoW:
    return make_uow(
        identity="uow_stream_p3_002",
        routes=base_uow_route,
        matrix_cell=MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA),
        layer="streaming",
    )


@pytest.fixture
def uow_stream_3(base_uow_route: List[Route]) -> UoW:
    return make_uow(
        identity="uow_stream_p3_003",
        routes=base_uow_route,
        matrix_cell=MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA),
        layer="streaming",
    )


@pytest.fixture
def world_s1() -> WorldConditions:
    """Nominal high-power envelope (120W budget)."""
    return WorldConditions.create(
        available_capabilities=[
            ResourceCapability.LOW_POWER_ACCELERATOR,
            ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR,
            ResourceCapability.GENERAL_COMPUTE,
            ResourceCapability.DETERMINISTIC_AUTHORITY,
        ],
        power_budget_w=120.0,
        max_concurrency=4,
        congestion_factors={ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR: 1.0},
        timestamp=1000.0,
        snapshot_id="snap_world_s1_nominal",
    )


@pytest.fixture
def world_s2_constrained() -> WorldConditions:
    """Constrained low-power envelope (35W budget) inducing drift."""
    return WorldConditions.create(
        available_capabilities=[
            ResourceCapability.LOW_POWER_ACCELERATOR,
            ResourceCapability.GENERAL_COMPUTE,
            ResourceCapability.DETERMINISTIC_AUTHORITY,
        ],
        power_budget_w=35.0,
        max_concurrency=2,
        congestion_factors={ResourceCapability.GENERAL_COMPUTE: 1.5},
        timestamp=2000.0,
        snapshot_id="snap_world_s2_constrained",
    )


def test_p3_1_and_2_multidimensional_drift_detection(
    uow_stream_1: UoW,
    world_s1: WorldConditions,
):
    """P3.1 & P3.2: Normal telemetry accumulation and multidimensional drift evaluation (E, L, P, C, Q)."""
    registry = PolicyRegistry()
    discovery = DiscoveryEngine()
    qualifier = QualificationEngine(registry, min_observations=3)
    resolver = PolicyResolver(registry, discovery)
    executor = RealizationGraphExecutor()

    # Step 1: Discover, qualify, and promote policy Pi_1 -> Pi_2
    req = WorkRequirement.from_uow(uow_stream_1, scale=500)
    res = resolver.resolve(req, world_s1)
    for _ in range(3):
        cert = executor.execute_graph(res.candidate.graph, req, world_s1, decision=res.decision_record)
        qualifier.record_observation(res.candidate.candidate_id, req, world_s1, cert.measured_energy_wh, cert.measured_latency_ms)

    qualified = qualifier.qualify_candidate(res.candidate, req, world_s1)
    assert qualified is not None
    promoted_policy = qualifier.promote(qualified)
    assert promoted_policy.state == PolicyState.ACTIVE
    assert registry.version == 2

    # Step 2: Initialize MultidimensionalDriftMonitor
    monitor = MultidimensionalDriftMonitor(
        registry,
        energy_drift_threshold=0.20,
        latency_drift_threshold=0.30,
        power_drift_threshold=0.25,
        congestion_drift_threshold=0.40,
        quality_drift_threshold=0.15,
        consecutive_violations_to_invalidate=3,
        consecutive_compliant_to_clear=2,
    )

    # Compliant observation passes clean
    nominal_cert = executor.execute_graph(promoted_policy.realization_graph, req, world_s1)
    eval_nominal = monitor.evaluate(nominal_cert, promoted_policy, world_s1)
    assert eval_nominal.drift_detected is False
    assert eval_nominal.is_invalidated is False
    assert eval_nominal.policy_state == PolicyState.ACTIVE

    # Test multidimensional drift dimensions:
    # Dimension ΔE (Energy surge)
    high_e_cert = ExecutionCertificate(
        certificate_id="cert_high_e",
        uow_id=req.uow_id,
        graph_id=promoted_policy.realization_graph.graph_id,
        state_hash="h1",
        is_certified=True,
        measured_energy_wh=promoted_policy.evidence.expected_energy_wh * 1.5,  # +50% > 20%
        measured_latency_ms=promoted_policy.evidence.expected_latency_ms,
        authority_compliant=True,
    )
    eval_e = monitor.evaluate(high_e_cert, promoted_policy, world_s1)
    assert "DELTA_E" in eval_e.drift_dimensions
    assert eval_e.is_suspected is True

    # Dimension ΔL (Latency surge)
    high_l_cert = ExecutionCertificate(
        certificate_id="cert_high_l",
        uow_id=req.uow_id,
        graph_id=promoted_policy.realization_graph.graph_id,
        state_hash="h2",
        is_certified=True,
        measured_energy_wh=promoted_policy.evidence.expected_energy_wh,
        measured_latency_ms=promoted_policy.evidence.expected_latency_ms * 1.8,  # +80% > 30%
        authority_compliant=True,
    )
    eval_l = monitor.evaluate(high_l_cert, promoted_policy, world_s1)
    assert "DELTA_L" in eval_l.drift_dimensions

    # Dimension ΔP (Power surge exceeding budget)
    eval_p = monitor.evaluate(nominal_cert, promoted_policy, world_s1, measured_power_w=160.0)  # 160W > 120W (+33%)
    assert "DELTA_P" in eval_p.drift_dimensions

    # Dimension ΔC (Congestion surge)
    eval_c = monitor.evaluate(nominal_cert, promoted_policy, world_s1, congestion_factor=0.65)  # 65% > 40%
    assert "DELTA_C" in eval_c.drift_dimensions

    # Dimension ΔQ (Quality / degradation surge)
    eval_q = monitor.evaluate(nominal_cert, promoted_policy, world_s1, quality_metric=0.25)  # 25% > 15%
    assert "DELTA_Q" in eval_q.drift_dimensions


def test_p3_3_hysteresis_state_machine(
    uow_stream_1: UoW,
    world_s1: WorldConditions,
):
    """P3.3: Hysteresis state machine: Single deviation triggers DRIFT_SUSPECTED; recovery clears suspicion."""
    registry = PolicyRegistry()
    discovery = DiscoveryEngine()
    qualifier = QualificationEngine(registry, min_observations=3)
    resolver = PolicyResolver(registry, discovery)
    executor = RealizationGraphExecutor()

    req = WorkRequirement.from_uow(uow_stream_1, scale=500)
    res = resolver.resolve(req, world_s1)
    for _ in range(3):
        cert = executor.execute_graph(res.candidate.graph, req, world_s1, decision=res.decision_record)
        qualifier.record_observation(res.candidate.candidate_id, req, world_s1, cert.measured_energy_wh, cert.measured_latency_ms)

    policy = qualifier.promote(qualifier.qualify_candidate(res.candidate, req, world_s1))
    assert policy.state == PolicyState.ACTIVE

    monitor = MultidimensionalDriftMonitor(
        registry,
        consecutive_violations_to_invalidate=3,
        consecutive_compliant_to_clear=2,
    )

    # 1. Single noisy observation triggers DRIFT_SUSPECTED (NOT invalidation!)
    noisy_cert = ExecutionCertificate(
        certificate_id="cert_noise_1",
        uow_id=req.uow_id,
        graph_id=policy.realization_graph.graph_id,
        state_hash="h_noise",
        is_certified=True,
        measured_energy_wh=policy.evidence.expected_energy_wh * 1.4,  # +40%
        measured_latency_ms=policy.evidence.expected_latency_ms,
        authority_compliant=True,
    )
    eval1 = monitor.evaluate(noisy_cert, policy, world_s1)
    assert eval1.is_suspected is True
    assert eval1.is_invalidated is False
    assert registry.get_policy(policy.policy_id).state == PolicyState.DRIFT_SUSPECTED
    assert registry.get_policy(policy.policy_id).is_active is True  # Policy remains active during suspicion!
    assert registry.version == 2  # Registry version does NOT increment on suspicion

    # 2. Compliant observation 1 (recovery count = 1)
    nominal_cert = executor.execute_graph(policy.realization_graph, req, world_s1)
    eval2 = monitor.evaluate(nominal_cert, registry.get_policy(policy.policy_id), world_s1)
    assert eval2.consecutive_compliant == 1
    assert registry.get_policy(policy.policy_id).state == PolicyState.DRIFT_SUSPECTED

    # 3. Compliant observation 2 (recovery count = 2 -> Clears suspicion!)
    eval3 = monitor.evaluate(nominal_cert, registry.get_policy(policy.policy_id), world_s1)
    assert eval3.policy_state == PolicyState.ACTIVE
    assert registry.get_policy(policy.policy_id).state == PolicyState.ACTIVE

    # Verify lifecycle records captured the transition: ACTIVE -> DRIFT_SUSPECTED -> DRIFT_CLEARED
    records = registry.get_lifecycle_records(policy.policy_id)
    events = [r.event_type for r in records]
    assert PolicyLifecycleEvent.DRIFT_SUSPECTED in events
    assert PolicyLifecycleEvent.DRIFT_CLEARED in events


def test_p3_4_sustained_drift_and_hard_gate_invalidation(
    uow_stream_1: UoW,
    world_s1: WorldConditions,
):
    """P3.4: 3 consecutive deviations trigger atomic invalidation; correctness breach invalidates immediately."""
    registry = PolicyRegistry()
    discovery = DiscoveryEngine()
    qualifier = QualificationEngine(registry, min_observations=3)
    resolver = PolicyResolver(registry, discovery)
    executor = RealizationGraphExecutor()

    req = WorkRequirement.from_uow(uow_stream_1, scale=500)
    res = resolver.resolve(req, world_s1)
    for _ in range(3):
        cert = executor.execute_graph(res.candidate.graph, req, world_s1, decision=res.decision_record)
        qualifier.record_observation(res.candidate.candidate_id, req, world_s1, cert.measured_energy_wh, cert.measured_latency_ms)

    policy = qualifier.promote(qualifier.qualify_candidate(res.candidate, req, world_s1))
    assert registry.version == 2

    monitor = MultidimensionalDriftMonitor(registry, consecutive_violations_to_invalidate=3)

    noisy_cert = ExecutionCertificate(
        certificate_id="cert_noise",
        uow_id=req.uow_id,
        graph_id=policy.realization_graph.graph_id,
        state_hash="h_noise",
        is_certified=True,
        measured_energy_wh=policy.evidence.expected_energy_wh * 1.5,
        measured_latency_ms=policy.evidence.expected_latency_ms,
        authority_compliant=True,
    )

    # Violation 1 -> DRIFT_SUSPECTED
    monitor.evaluate(noisy_cert, registry.get_policy(policy.policy_id), world_s1)
    assert registry.get_policy(policy.policy_id).state == PolicyState.DRIFT_SUSPECTED

    # Violation 2 -> DRIFT_SUSPECTED (count = 2)
    monitor.evaluate(noisy_cert, registry.get_policy(policy.policy_id), world_s1)
    assert registry.get_policy(policy.policy_id).state == PolicyState.DRIFT_SUSPECTED

    # Violation 3 -> SUSTAINED DRIFT! Atomic Invalidation: Pi_2 -> Pi_3
    eval3 = monitor.evaluate(noisy_cert, registry.get_policy(policy.policy_id), world_s1)
    assert eval3.is_invalidated is True
    assert registry.version == 3  # Monotonic version increment!
    assert registry.get_policy(policy.policy_id).state == PolicyState.INVALIDATED
    assert registry.get_policy(policy.policy_id).is_active is False
    assert registry.active_policies_count == 0

    # Hard gate test: Correctness breach invalidates immediately (zero tolerance)
    # Reactivate to test hard gate
    registry.reactivate_policy(policy.policy_id, policy.policy_version)
    assert registry.version == 4
    bad_cert = ExecutionCertificate(
        certificate_id="cert_bad",
        uow_id=req.uow_id,
        graph_id=policy.realization_graph.graph_id,
        state_hash="h_bad",
        is_certified=True,
        measured_energy_wh=policy.evidence.expected_energy_wh,
        measured_latency_ms=policy.evidence.expected_latency_ms,
        authority_compliant=True,
        correctness_breaches=1,  # Hard gate violation!
    )
    eval_bad = monitor.evaluate(bad_cert, registry.get_policy(policy.policy_id), world_s1)
    assert eval_bad.is_invalidated is True
    assert registry.version == 5
    assert registry.get_policy(policy.policy_id).state == PolicyState.INVALIDATED


def test_p3_5_inflight_execution_preservation_under_live_drift(
    uow_stream_1: UoW,
    uow_stream_2: UoW,
    uow_stream_3: UoW,
    world_s1: WorldConditions,
):
    r"""P3.5: THE HARD CASE — In-flight executions retain their original decision context (\Pi_k) during live invalidation.
    
    Proves:
    - Running transactions hold immutable snapshot reference (Pi_2, policy_id, world_snapshot_id).
    - Policy invalidation increments registry Pi_2 -> Pi_3.
    - New work arriving after invalidation falls back to BOUNDED_DISCOVERY.
    - In-flight executions finish, certify against Pi_2, and remain 100% deterministically replayable.
    """
    registry = PolicyRegistry()
    discovery = DiscoveryEngine()
    qualifier = QualificationEngine(registry, min_observations=3)
    resolver = PolicyResolver(registry, discovery)
    executor = RealizationGraphExecutor()
    monitor = MultidimensionalDriftMonitor(registry, consecutive_violations_to_invalidate=1)

    # 1. Bootstrap: Promote policy Pi_1 -> Pi_2
    req_u1 = WorkRequirement.from_uow(uow_stream_1, scale=500)
    res_boot = resolver.resolve(req_u1, world_s1)
    for _ in range(3):
        c = executor.execute_graph(res_boot.candidate.graph, req_u1, world_s1, decision=res_boot.decision_record)
        qualifier.record_observation(res_boot.candidate.candidate_id, req_u1, world_s1, c.measured_energy_wh, c.measured_latency_ms)

    policy = qualifier.promote(qualifier.qualify_candidate(res_boot.candidate, req_u1, world_s1))
    assert registry.version == 2
    assert registry.active_policies_count == 1

    # 2. U1 and U2 resolve UNDER REGISTRY VERSION 2 (Fast Path)
    res_u1 = resolver.resolve(req_u1, world_s1)
    req_u2 = WorkRequirement.from_uow(uow_stream_2, scale=500)
    res_u2 = resolver.resolve(req_u2, world_s1)

    assert res_u1.mode == "POLICY_REUSE"
    assert res_u1.policy_registry_version == 2
    assert res_u1.decision_record.registry_version == 2
    assert res_u1.decision_record.selected_policy_id == policy.policy_id

    assert res_u2.mode == "POLICY_REUSE"
    assert res_u2.policy_registry_version == 2
    assert res_u2.decision_record.registry_version == 2

    # 3. Simulate In-Flight Execution: U1 and U2 are executing asynchronously!
    # IN THE MIDDLE OF EXECUTION: Drift occurs and INVALIDATES policy!
    drift_cert = ExecutionCertificate(
        certificate_id="cert_drift_trigger",
        uow_id="external_noisy_uow",
        graph_id=policy.realization_graph.graph_id,
        state_hash="h_drift",
        is_certified=True,
        measured_energy_wh=policy.evidence.expected_energy_wh * 2.0,  # Extreme surge
        measured_latency_ms=policy.evidence.expected_latency_ms,
        authority_compliant=True,
    )
    invalidated = monitor.record_and_evaluate(drift_cert, policy, world_s1)
    assert invalidated is True
    assert registry.version == 3  # Registry advanced Pi_2 -> Pi_3!
    assert registry.get_policy(policy.policy_id).is_active is False

    # 4. A NEW UoW (U3) arrives AFTER invalidation!
    req_u3 = WorkRequirement.from_uow(uow_stream_3, scale=500)
    res_u3 = resolver.resolve(req_u3, world_s1)

    # Invariant: New work sees Pi_3 and falls back to BOUNDED_DISCOVERY
    assert res_u3.mode == "BOUNDED_DISCOVERY"
    assert res_u3.policy_registry_version == 3
    assert res_u3.policy is None
    assert res_u3.candidate is not None
    assert res_u3.decision_record.resolution_status == "NO_QUALIFIED_POLICY"

    # 5. In-flight U1 and U2 COMPLETE their executions!
    cert_u1 = executor.execute_graph(res_u1.graph, req_u1, world_s1, decision=res_u1.decision_record)
    cert_u2 = executor.execute_graph(res_u2.graph, req_u2, world_s1, decision=res_u2.decision_record)

    # Invariant: In-flight executions retain Pi_2 and original policy context!
    assert cert_u1.policy_registry_version == 2
    assert cert_u1.policy_id == policy.policy_id
    assert cert_u1.world_snapshot_id == world_s1.snapshot_id
    assert cert_u1.decision_digest == res_u1.decision_record.decision_digest

    assert cert_u2.policy_registry_version == 2
    assert cert_u2.policy_id == policy.policy_id
    assert cert_u2.decision_digest == res_u2.decision_record.decision_digest

    # 6. Replay Invariant: U1 and U2 remain replayable against historical version 2!
    replayed_cert_u1 = executor.execute_graph(res_u1.graph, req_u1, world_s1, decision=res_u1.decision_record)
    assert replayed_cert_u1.composite_hash == cert_u1.composite_hash


def test_p3_6_and_7_replacement_qualification_and_monotonic_versioning(
    uow_stream_1: UoW,
    world_s1: WorldConditions,
    world_s2_constrained: WorldConditions,
):
    """P3.6 & P3.7: Discover & qualify replacement policy pi^{(2)} in changed region without overwriting pi^{(1)}."""
    registry = PolicyRegistry()
    discovery = DiscoveryEngine()
    qualifier = QualificationEngine(registry, min_observations=3)
    resolver = PolicyResolver(registry, discovery)
    executor = RealizationGraphExecutor()
    monitor = MultidimensionalDriftMonitor(registry, consecutive_violations_to_invalidate=1)

    req = WorkRequirement.from_uow(uow_stream_1, scale=500)
    res1 = resolver.resolve(req, world_s1)
    for _ in range(3):
        c = executor.execute_graph(res1.candidate.graph, req, world_s1, decision=res1.decision_record)
        qualifier.record_observation(res1.candidate.candidate_id, req, world_s1, c.measured_energy_wh, c.measured_latency_ms)

    pol_v1 = qualifier.promote(qualifier.qualify_candidate(res1.candidate, req, world_s1))
    assert pol_v1.policy_version == 1
    assert registry.version == 2

    # Invalidate policy v1 due to physical power budget drop (S2: 35W)
    monitor.record_and_evaluate(
        ExecutionCertificate(
            certificate_id="c_drop",
            uow_id=req.uow_id,
            graph_id=pol_v1.realization_graph.graph_id,
            state_hash="h",
            is_certified=True,
            measured_energy_wh=pol_v1.evidence.expected_energy_wh,
            measured_latency_ms=pol_v1.evidence.expected_latency_ms,
            authority_compliant=True,
        ),
        pol_v1,
        world_s2_constrained,
        measured_power_w=95.0,  # 95W >> 35W budget
    )
    assert registry.version == 3
    assert pol_v1.policy_id in registry._policies
    assert registry.get_policy(pol_v1.policy_id).is_active is False

    # New resolution in S2 constrained regime falls back to bounded discovery
    res2 = resolver.resolve(req, world_s2_constrained)
    assert res2.mode == "BOUNDED_DISCOVERY"
    candidate_s2 = res2.candidate

    # Accumulate evidence in new operating region S2
    for _ in range(3):
        c = executor.execute_graph(candidate_s2.graph, req, world_s2_constrained, decision=res2.decision_record)
        qualifier.record_observation(candidate_s2.candidate_id, req, world_s2_constrained, c.measured_energy_wh, c.measured_latency_ms)

    qualified_s2 = qualifier.qualify_candidate(candidate_s2, req, world_s2_constrained)
    assert qualified_s2 is not None

    # Promote replacement policy version 2!
    pol_v2 = qualifier.promote(qualified_s2, policy_id=pol_v1.policy_id)
    assert pol_v2.policy_id == pol_v1.policy_id
    assert pol_v2.policy_version == 2       # Monotonic version increment!
    assert registry.version == 4            # Registry advanced Pi_3 -> Pi_4
    assert pol_v2.is_active is True

    # Historical Invariant: pol_v1 is NOT overwritten!
    v1_historical = registry.get_policy(pol_v1.policy_id, version=1)
    assert v1_historical is not None
    assert v1_historical.policy_version == 1
    assert v1_historical.is_active is False  # v1 remains preserved as inactive/superseded
    assert v1_historical.evidence.evidence_digest == pol_v1.evidence.evidence_digest

    history = registry.get_policy_history(pol_v1.policy_id)
    assert len(history) >= 2


def test_p3_8_regime_restoration_and_requalification(
    uow_stream_1: UoW,
    world_s1: WorldConditions,
):
    """P3.8: Reactivate / requalify historical policy when prior operating regime returns."""
    registry = PolicyRegistry()
    discovery = DiscoveryEngine()
    qualifier = QualificationEngine(registry, min_observations=3)
    resolver = PolicyResolver(registry, discovery)
    executor = RealizationGraphExecutor()
    monitor = MultidimensionalDriftMonitor(registry, consecutive_violations_to_invalidate=1)

    req = WorkRequirement.from_uow(uow_stream_1, scale=500)
    res = resolver.resolve(req, world_s1)
    for _ in range(3):
        c = executor.execute_graph(res.candidate.graph, req, world_s1, decision=res.decision_record)
        qualifier.record_observation(res.candidate.candidate_id, req, world_s1, c.measured_energy_wh, c.measured_latency_ms)

    policy = qualifier.promote(qualifier.qualify_candidate(res.candidate, req, world_s1))
    assert registry.version == 2

    # Invalidate policy
    monitor.record_and_evaluate(
        ExecutionCertificate(
            certificate_id="c_inv",
            uow_id=req.uow_id,
            graph_id=policy.realization_graph.graph_id,
            state_hash="h",
            is_certified=True,
            measured_energy_wh=policy.evidence.expected_energy_wh * 2.0,
            measured_latency_ms=policy.evidence.expected_latency_ms,
            authority_compliant=True,
        ),
        policy,
        world_s1,
    )
    assert registry.version == 3
    assert registry.get_policy(policy.policy_id).is_active is False

    # Old regime S1 returns! Requalify historical policy
    requalified = qualifier.requalify_policy(
        policy=registry.get_policy(policy.policy_id),
        requirement=req,
        conditions=world_s1,
        observed_energies_wh=[policy.evidence.expected_energy_wh] * 3,
        observed_latencies_ms=[policy.evidence.expected_latency_ms] * 3,
        correctness_breaches=0,
    )
    assert requalified is not None
    assert requalified.is_active is True
    assert requalified.state == PolicyState.ACTIVE
    assert registry.version == 4  # Monotonic version advance Pi_3 -> Pi_4

    # Subsequent resolution uses reactivated policy directly
    res_restored = resolver.resolve(req, world_s1)
    assert res_restored.mode == "POLICY_REUSE"
    assert res_restored.policy.policy_id == policy.policy_id


def test_p3_9_complete_three_tier_audit_chain(
    uow_stream_1: UoW,
    world_s1: WorldConditions,
):
    """P3.9: Verify cryptographic audit chain: PolicyLifecycleRecord -> PolicyDecisionRecord -> ExecutionCertificate."""
    registry = PolicyRegistry()
    discovery = DiscoveryEngine()
    qualifier = QualificationEngine(registry, min_observations=3)
    resolver = PolicyResolver(registry, discovery)
    executor = RealizationGraphExecutor()

    # 1. Promote policy (creates PolicyLifecycleRecord with PROMOTED event)
    req = WorkRequirement.from_uow(uow_stream_1, scale=500)
    res_cand = resolver.resolve(req, world_s1)
    for _ in range(3):
        c = executor.execute_graph(res_cand.candidate.graph, req, world_s1, decision=res_cand.decision_record)
        qualifier.record_observation(res_cand.candidate.candidate_id, req, world_s1, c.measured_energy_wh, c.measured_latency_ms)

    policy = qualifier.promote(qualifier.qualify_candidate(res_cand.candidate, req, world_s1))
    assert policy.latest_lifecycle_digest != ""

    # Verify PolicyLifecycleRecord
    lc_records = registry.get_lifecycle_records(policy.policy_id)
    assert len(lc_records) >= 1
    lc_promoted = lc_records[-1]
    assert lc_promoted.event_type == PolicyLifecycleEvent.PROMOTED
    assert lc_promoted.lifecycle_digest == policy.latest_lifecycle_digest

    # 2. Fast-path resolution: DecisionRecord binds lifecycle_digest
    res_fast = resolver.resolve(req, world_s1)
    decision = res_fast.decision_record
    assert decision.lifecycle_digest == lc_promoted.lifecycle_digest
    assert decision.decision_digest != ""

    # 3. Execution: ExecutionCertificate binds decision_digest
    cert = executor.execute_graph(res_fast.graph, req, world_s1, decision=decision)
    assert cert.decision_digest == decision.decision_digest
    assert cert.composite_hash != ""

    # 4. Forensic Lineage Chain Verified:
    # ExecutionCertificate.decision_digest -> PolicyDecisionRecord.decision_digest
    # PolicyDecisionRecord.lifecycle_digest -> PolicyLifecycleRecord.lifecycle_digest
    assert cert.decision_digest == decision.decision_digest
    assert decision.lifecycle_digest == lc_promoted.lifecycle_digest
