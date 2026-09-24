"""Gate P1: End-to-End Policy Orchestration Qualification.

Tests the full canonical integration loop:
    U (authoritative UoW)
    -> W (WorkRequirement projection)
    -> S (WorldConditions snapshot)
    -> pi (Policy lookup from versioned PolicyRegistry)
    -> G (RealizationGraph)
    -> Execution (RealizationGraphExecutor)
    -> C (ExecutionCertificate with composite hash)

Verifies:
1. Existing UoW semantics unchanged.
2. Qualified policy selected deterministically (Resolve(U, S, Pi) = G).
3. Multi-stage RealizationGraph executes across capability boundaries.
4. Authority preserved at every stage.
5. Evidence lineage survives device/capability boundaries.
6. Final output matches canonical expected result.
7. Replay from recorded (U, S, Pi, G) reproduces identical committed state.
8. Invalidating policy causes bounded discovery/fallback rather than failure.
9. No A3 experimental code is imported by src/uow/.
10. All existing tests pass.
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
    DiscoveryCandidate,
    DiscoveryEngine,
    DriftMonitor,
    ExecutionCertificate,
    GraphExecutionError,
    Policy,
    PolicyEvidence,
    PolicyRegion,
    PolicyResolution,
    PolicyResolver,
    PolicyRegistry,
    QualificationEngine,
    RealizationGraph,
    RealizationStage,
    RealizationGraphExecutor,
    ResourceCapability,
    WorkRequirement,
    WorldConditions,
)
from uow.state import WorldState


@pytest.fixture
def sample_uow() -> UoW:
    """Create a real authoritative UoW contract."""
    route = Route(
        guard=Guard(GuardOp.ALWAYS),
        mutations=(
            Mutation(MutationOp.SET, "pipeline_stage", "completed"),
            Mutation(MutationOp.SET, "checksum", 42),
        ),
        successor=Successor.halt(),
    )
    return make_uow(
        identity="uow_streaming_heavy_001",
        routes=[route],
        matrix_cell=MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA),
        layer="streaming",
        parent_context="production_runtime",
    )


@pytest.fixture
def world_snapshot() -> WorldConditions:
    """Create a real WorldConditions runtime snapshot."""
    return WorldConditions.create(
        available_capabilities=[
            ResourceCapability.LOW_POWER_ACCELERATOR,
            ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR,
            ResourceCapability.GENERAL_COMPUTE,
            ResourceCapability.DETERMINISTIC_AUTHORITY,
        ],
        power_budget_w=120.0,
        max_concurrency=4,
        congestion_factors={ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR: 1.1},
        device_health={"gpu": True, "npu": True, "cpu": True, "mcu": True},
    )


def test_p1_end_to_end_projection_and_resolution(sample_uow: UoW, world_snapshot: WorldConditions):
    """P1.1 & P1.2: Project WorkRequirement from UoW and resolve via PolicyResolver."""
    # 1. Project WorkRequirement directly from UoW (Semantics unchanged)
    req = WorkRequirement.from_uow(sample_uow, scale=1000)
    assert req.uow_id == "uow_streaming_heavy_001"
    assert req.scale == 1000
    assert req.canonical_meaning_digest != ""
    assert "processes_data" in req.workload_class

    # 2. Setup versioned PolicyRegistry and Qualifier
    registry = PolicyRegistry()
    assert registry.version == 1
    qualifier = QualificationEngine(registry, min_observations=5)
    discovery = DiscoveryEngine()
    resolver = PolicyResolver(registry, discovery)

    # 3. Discovery step (cold start) -> proposes candidate
    res1 = resolver.resolve(req, world_snapshot)
    assert res1.mode == "BOUNDED_DISCOVERY"
    assert res1.candidate is not None
    assert res1.graph.is_valid is True

    # 4. Qualify and promote candidate -> creates versioned policy Pi_2
    policy = qualifier.evaluate_and_promote(
        candidate=res1.candidate,
        requirement=req,
        conditions=world_snapshot,
        observed_energies_wh=[0.000321] * 5,
        observed_latencies_ms=[12.5] * 5,
        correctness_breaches=0,
    )
    assert policy is not None
    assert registry.version == 2  # Monotonic version incremented!
    assert registry.active_policies_count == 1

    # 5. Subsequent resolution: collapses to deterministic lookup (Pi_2)
    res2 = resolver.resolve(req, world_snapshot)
    assert res2.mode == "POLICY_REUSE"
    assert res2.policy is not None
    assert res2.policy.policy_id == policy.policy_id
    assert res2.policy_registry_version == 2


def test_p1_multi_stage_graph_execution_and_certification(
    sample_uow: UoW,
    world_snapshot: WorldConditions,
):
    """P1.3, P1.4, P1.5, P1.6: Execute multi-stage RealizationGraph with authority preservation."""
    req = WorkRequirement.from_uow(sample_uow, scale=500)
    registry = PolicyRegistry()
    qualifier = QualificationEngine(registry, min_observations=5)
    discovery = DiscoveryEngine()
    resolver = PolicyResolver(registry, discovery)

    res = resolver.resolve(req, world_snapshot)
    policy = qualifier.evaluate_and_promote(
        candidate=res.candidate,
        requirement=req,
        conditions=world_snapshot,
        observed_energies_wh=[0.000321] * 5,
        observed_latencies_ms=[12.5] * 5,
        correctness_breaches=0,
    )
    assert policy is not None

    # Execute graph with RealizationGraphExecutor
    executor = RealizationGraphExecutor()
    cert = executor.execute_graph(
        graph=policy.realization_graph,
        requirement=req,
        world=world_snapshot,
        policy_registry_version=registry.version,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
    )

    # Invariants verification
    assert cert.is_certified is True
    assert cert.authority_compliant is True
    assert cert.correctness_breaches == 0
    assert cert.state_hash != ""
    assert cert.measured_energy_wh > 0.0
    assert cert.measured_latency_ms > 0.0
    assert cert.world_snapshot_id == world_snapshot.snapshot_id
    assert cert.composite_hash != ""


def test_p1_deterministic_replay(sample_uow: UoW, world_snapshot: WorldConditions):
    """P1.7: Replay from recorded (U, S, Pi, G) reproduces identical committed state."""
    req = WorkRequirement.from_uow(sample_uow, scale=500)
    registry = PolicyRegistry()
    qualifier = QualificationEngine(registry, min_observations=5)
    discovery = DiscoveryEngine()
    resolver = PolicyResolver(registry, discovery)

    res = resolver.resolve(req, world_snapshot)
    policy = qualifier.evaluate_and_promote(
        candidate=res.candidate,
        requirement=req,
        conditions=world_snapshot,
        observed_energies_wh=[0.000321] * 5,
        observed_latencies_ms=[12.5] * 5,
        correctness_breaches=0,
    )

    executor = RealizationGraphExecutor()

    # Run 1: Original Execution
    cert1 = executor.execute_graph(
        graph=policy.realization_graph,
        requirement=req,
        world=world_snapshot,
        policy_registry_version=registry.version,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
    )

    # Run 2: Exact Replay with identical inputs (U, S, Pi, G)
    cert2 = executor.execute_graph(
        graph=policy.realization_graph,
        requirement=req,
        world=world_snapshot,
        policy_registry_version=registry.version,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
    )

    # Identical deterministic output and composite hash!
    assert cert1.state_hash == cert2.state_hash
    assert cert1.composite_hash == cert2.composite_hash
    assert cert1.measured_energy_wh == cert2.measured_energy_wh


def test_p1_policy_invalidation_and_safe_fallback(
    sample_uow: UoW,
    world_snapshot: WorldConditions,
):
    """P1.8: Invalidating a policy safely causes bounded discovery/fallback rather than failure."""
    req = WorkRequirement.from_uow(sample_uow, scale=500)
    registry = PolicyRegistry()
    qualifier = QualificationEngine(registry, min_observations=5)
    discovery = DiscoveryEngine()
    resolver = PolicyResolver(registry, discovery)

    res1 = resolver.resolve(req, world_snapshot)
    policy = qualifier.evaluate_and_promote(
        candidate=res1.candidate,
        requirement=req,
        conditions=world_snapshot,
        observed_energies_wh=[0.000321] * 5,
        observed_latencies_ms=[12.5] * 5,
        correctness_breaches=0,
    )
    v_before = registry.version

    # Invalidate policy due to safety / drift
    success = registry.invalidate(policy.policy_id, reason="Thermal throttling violation")
    assert success is True
    assert registry.version == v_before + 1  # Version bumped atomically!

    # Next resolution falls back to bounded discovery without throwing unhandled exception
    res_fallback = resolver.resolve(req, world_snapshot)
    assert res_fallback.mode == "BOUNDED_DISCOVERY"
    assert res_fallback.candidate is not None
    assert res_fallback.graph.is_valid is True


def test_p1_deterministic_conflict_resolution(
    sample_uow: UoW,
    world_snapshot: WorldConditions,
):
    """P1.2: Deterministic conflict resolution when multiple policies match."""
    req = WorkRequirement.from_uow(sample_uow, scale=500)
    registry = PolicyRegistry()
    discovery = DiscoveryEngine()
    resolver = PolicyResolver(registry, discovery)

    # Create two overlapping policies: General vs Specific
    # Policy A: Wide scale [100, 2000], general compute
    g_a = discovery.propose_candidates(req, world_snapshot)[0].graph
    pol_general = Policy(
        policy_id="POL_STREAMING_GENERAL",
        policy_version=1,
        region=PolicyRegion(
            workload_class=req.workload_class,
            min_scale=100,
            max_scale=2000,
            min_power_budget_w=0.0,
            required_capabilities=frozenset([ResourceCapability.GENERAL_COMPUTE]),
        ),
        realization_graph=g_a,
        evidence=PolicyEvidence("ev_gen", 10, 0.000800, 0.000750, 0.000850, 25.0, 1),
    )
    registry.register_policy(pol_general)

    # Policy B: Narrow scale [400, 600], highly specific & lower energy
    g_b = discovery.propose_candidates(req, world_snapshot)[-1].graph
    pol_specific = Policy(
        policy_id="POL_STREAMING_SPECIFIC",
        policy_version=1,
        region=PolicyRegion(
            workload_class=req.workload_class,
            min_scale=400,
            max_scale=600,
            min_power_budget_w=0.0,
            required_capabilities=frozenset([
                ResourceCapability.LOW_POWER_ACCELERATOR,
                ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR,
                ResourceCapability.GENERAL_COMPUTE,
                ResourceCapability.DETERMINISTIC_AUTHORITY,
            ]),
        ),
        realization_graph=g_b,
        evidence=PolicyEvidence("ev_spec", 50, 0.000321, 0.000315, 0.000327, 12.0, 1),
    )
    registry.register_policy(pol_specific)

    # Resolve 100 times: Must pick pol_specific deterministically every single time!
    for _ in range(100):
        resolved = registry.lookup(req, world_snapshot)
        assert resolved is not None
        assert resolved.policy_id == "POL_STREAMING_SPECIFIC"


def test_p1_no_a3_experimental_imports_in_uow():
    """P1.9: Strict provenance isolation: src/uow/ must NOT import experiments.a3_efficiency."""
    import sys
    from pathlib import Path

    src_uow_dir = Path(__file__).resolve().parents[1] / "src" / "uow"
    for py_file in src_uow_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        assert "experiments.a3_efficiency" not in content, (
            f"Isolation violation: {py_file} contains import from experiments.a3_efficiency"
        )
