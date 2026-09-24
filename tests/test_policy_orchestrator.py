"""Test suite for Policy-Aware UoW Orchestrator architecture.

Validates the first milestone of the integration branch:
1. Capability decoupling (Architecture understands capabilities; Drivers understand devices).
2. RealizationGraph composition and semantic equivalence preservation.
3. Policy serialization, deserialization, and registry operations.
4. Authority boundary: Discovery produces candidates, never authority.
5. QualificationEngine gates: ROI break-even, CI bounds, zero correctness breaches.
6. PolicyResolver fast path (O(1) policy reuse) and policy residency R_policy -> 1.0.
7. Continuous DriftMonitor invalidation loop.
"""
from __future__ import annotations

import pytest

from uow.policy import (
    DiscoveryCandidate,
    DiscoveryEngine,
    DriftMonitor,
    ExecutionCertificate,
    Policy,
    PolicyEvidence,
    PolicyRegion,
    PolicyResolution,
    PolicyResolver,
    PolicyRegistry,
    QualificationEngine,
    RealizationGraph,
    RealizationStage,
    ResourceCapability,
    WorkRequirement,
    WorldConditions,
)


@pytest.fixture
def available_capabilities() -> frozenset[ResourceCapability]:
    return frozenset([
        ResourceCapability.LOW_POWER_ACCELERATOR,
        ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR,
        ResourceCapability.GENERAL_COMPUTE,
        ResourceCapability.DETERMINISTIC_AUTHORITY,
    ])


@pytest.fixture
def world_conditions(available_capabilities) -> WorldConditions:
    return WorldConditions.create(
        available_capabilities=available_capabilities,
        power_budget_w=120.0,
        max_concurrency=4,
    )


@pytest.fixture
def requirement() -> WorkRequirement:
    return WorkRequirement(
        workload_class="streaming_pipeline",
        scale=500,
        required_authority="AUTHORIZED_CONTRACT_VERIFIED",
    )


def test_work_requirement_semantic_invariance(requirement: WorkRequirement):
    """Verify WorkRequirement produces deterministic canonical meaning digest."""
    assert requirement.canonical_meaning_digest != ""
    req2 = WorkRequirement(
        workload_class="streaming_pipeline",
        scale=500,
        required_authority="AUTHORIZED_CONTRACT_VERIFIED",
    )
    assert requirement.canonical_meaning_digest == req2.canonical_meaning_digest


def test_discovery_produces_candidates_not_authority(
    requirement: WorkRequirement,
    world_conditions: WorldConditions,
):
    """Architectural invariant: DiscoveryEngine produces candidates, never operational policy."""
    registry = PolicyRegistry()
    assert registry.total_policies == 0

    engine = DiscoveryEngine()
    candidates = engine.propose_candidates(requirement, world_conditions)
    assert len(candidates) >= 2

    # Verify discovery produced candidates without modifying registry
    assert registry.total_policies == 0
    for cand in candidates:
        assert isinstance(cand, DiscoveryCandidate)
        assert cand.graph.is_valid is True
        assert cand.graph.matches_meaning(requirement.canonical_meaning_digest)


def test_composition_advantage_in_discovered_graphs(
    requirement: WorkRequirement,
    world_conditions: WorldConditions,
):
    """Verify DiscoveryEngine discovers heterogeneous hybrid that outperforms monolithic compute."""
    engine = DiscoveryEngine()
    candidates = engine.propose_candidates(requirement, world_conditions)

    cands_by_id = {c.candidate_id: c for c in candidates}
    assert "cand_heterogeneous_optimal" in cands_by_id
    assert "cand_monolithic_general_compute" in cands_by_id

    hetero = cands_by_id["cand_heterogeneous_optimal"]
    mono_cpu = cands_by_id["cand_monolithic_general_compute"]

    # Hybrid composition beats monolithic CPU
    assert hetero.estimated_energy_wh < mono_cpu.estimated_energy_wh
    savings_pct = (mono_cpu.estimated_energy_wh - hetero.estimated_energy_wh) / mono_cpu.estimated_energy_wh * 100.0
    assert savings_pct > 50.0


def test_qualification_engine_promotion_and_rejection(
    requirement: WorkRequirement,
    world_conditions: WorldConditions,
):
    """Verify QualificationEngine only promotes candidates with zero correctness breaches."""
    registry = PolicyRegistry()
    qualifier = QualificationEngine(registry, min_observations=5)
    engine = DiscoveryEngine()

    candidates = engine.propose_candidates(requirement, world_conditions)
    candidate = candidates[0]

    # Case 1: Rejected if correctness breaches > 0
    rejected = qualifier.evaluate_and_promote(
        candidate=candidate,
        requirement=requirement,
        conditions=world_conditions,
        observed_energies_wh=[0.00032, 0.00031, 0.00033, 0.00032, 0.00031],
        observed_latencies_ms=[10.0, 10.2, 9.8, 10.1, 10.0],
        correctness_breaches=1,  # Gate violation
    )
    assert rejected is None
    assert registry.total_policies == 0

    # Case 2: Promoted when clean
    promoted = qualifier.evaluate_and_promote(
        candidate=candidate,
        requirement=requirement,
        conditions=world_conditions,
        observed_energies_wh=[0.00032, 0.00031, 0.00033, 0.00032, 0.00031],
        observed_latencies_ms=[10.0, 10.2, 9.8, 10.1, 10.0],
        correctness_breaches=0,
    )
    assert promoted is not None
    assert registry.total_policies == 1
    assert promoted.evidence.correctness_breaches == 0
    assert promoted.evidence.break_even_uows >= 1


def test_policy_serialization_roundtrip(
    requirement: WorkRequirement,
    world_conditions: WorldConditions,
):
    """Verify Policy is machine-readable and serializes to/from JSON dictionary."""
    registry = PolicyRegistry()
    qualifier = QualificationEngine(registry, min_observations=5)
    engine = DiscoveryEngine()

    candidates = engine.propose_candidates(requirement, world_conditions)
    policy = qualifier.evaluate_and_promote(
        candidate=candidates[0],
        requirement=requirement,
        conditions=world_conditions,
        observed_energies_wh=[0.00032] * 5,
        observed_latencies_ms=[10.0] * 5,
        correctness_breaches=0,
    )
    assert policy is not None

    p_dict = policy.to_dict()
    restored = Policy.from_dict(p_dict)
    assert restored.policy_id == policy.policy_id
    assert restored.policy_version == policy.policy_version
    assert restored.evidence.expected_energy_wh == policy.evidence.expected_energy_wh
    assert len(restored.realization_graph.stages) == len(policy.realization_graph.stages)


def test_resolver_fast_path_and_policy_residency(
    requirement: WorkRequirement,
    world_conditions: WorldConditions,
):
    """Verify resolution collapses to O(1) lookup and policy residency R_policy -> 1.0."""
    registry = PolicyRegistry()
    qualifier = QualificationEngine(registry, min_observations=5)
    engine = DiscoveryEngine()
    resolver = PolicyResolver(registry, engine)

    # 1. First resolution with empty registry: triggers BOUNDED_DISCOVERY
    res1 = resolver.resolve(requirement, world_conditions)
    assert res1.mode == "BOUNDED_DISCOVERY"
    assert res1.policy is None
    assert res1.candidate is not None

    # Qualify and promote the candidate
    policy = qualifier.evaluate_and_promote(
        candidate=res1.candidate,
        requirement=requirement,
        conditions=world_conditions,
        observed_energies_wh=[res1.estimated_energy_wh] * 5,
        observed_latencies_ms=[10.0] * 5,
        correctness_breaches=0,
    )
    assert policy is not None

    # 2. Subsequent 100 executions: All resolve via POLICY_REUSE with O(1) lookup
    for _ in range(100):
        res = resolver.resolve(requirement, world_conditions)
        assert res.mode == "POLICY_REUSE"
        assert res.policy is not None
        assert res.policy.policy_id == policy.policy_id

    # Verify residency metric
    assert resolver.total_resolutions == 101
    assert resolver.policy_reuse_count == 100
    assert resolver.policy_residency == pytest.approx(100 / 101)  # >99% residency!
    assert resolver.learning_residency == pytest.approx(1 / 101)


def test_drift_monitor_and_policy_invalidation(
    requirement: WorkRequirement,
    world_conditions: WorldConditions,
):
    """Verify DriftMonitor detects telemetry degradation, invalidates policy, and triggers re-discovery."""
    registry = PolicyRegistry()
    qualifier = QualificationEngine(registry, min_observations=5)
    engine = DiscoveryEngine()
    resolver = PolicyResolver(registry, engine)
    drift_monitor = DriftMonitor(registry, energy_drift_threshold=0.20, consecutive_violations_to_invalidate=3)

    # Resolve and promote initial policy
    res1 = resolver.resolve(requirement, world_conditions)
    policy = qualifier.evaluate_and_promote(
        candidate=res1.candidate,
        requirement=requirement,
        conditions=world_conditions,
        observed_energies_wh=[0.00030] * 5,
        observed_latencies_ms=[10.0] * 5,
        correctness_breaches=0,
    )
    assert policy.is_active is True

    # Execution 1 & 2: degraded telemetry (+50% energy)
    cert_degraded = ExecutionCertificate(
        certificate_id="cert_1",
        uow_id="uow_1",
        graph_id=policy.realization_graph.graph_id,
        policy_id=policy.policy_id,
        state_hash="hash_1",
        is_certified=True,
        measured_energy_wh=0.00050,  # +66% above 0.00030
        measured_latency_ms=10.0,
        authority_compliant=True,
    )

    drifted_1 = drift_monitor.record_and_evaluate(cert_degraded, policy)
    assert drifted_1 is False  # Not yet 3 consecutive violations

    drifted_2 = drift_monitor.record_and_evaluate(cert_degraded, policy)
    assert drifted_2 is False

    # Execution 3: third violation -> Triggers invalidation!
    drifted_3 = drift_monitor.record_and_evaluate(cert_degraded, policy)
    assert drifted_3 is True
    assert policy.policy_id in registry._policies
    assert registry.get_policy(policy.policy_id).is_active is False

    # Next resolution now falls back to BOUNDED_DISCOVERY because active policy was invalidated
    res_after_drift = resolver.resolve(requirement, world_conditions)
    assert res_after_drift.mode == "BOUNDED_DISCOVERY"
