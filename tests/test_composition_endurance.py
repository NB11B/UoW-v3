"""Tests for Gate A2.8: Autonomous Continuous Topology Evolution Endurance.

Validates:
1. Continuous Non-Stationary Perturbation Trace: S_t progression without artificial resets.
2. Objective Function Evaluation: J(G, B, S) capturing latency, energy, cost, and failure risk.
3. Anti-Thrashing Hysteresis: Minimum dwell period and delta threshold suppressing oscillation.
4. Comparative Baselines (B0, B1, A2): J_adaptive < J_static (Delta J < 0).
5. Topology Lineage Forensics: Every certified mutation is auditable with full provenance.
6. Learning Loop Poisoning Resilience: Corrupted/delayed feedback cannot breach authority boundary.
7. Durable Crash Recovery Across Continuous Mutations: Zero lost history or state divergence.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from uow.composition.actor import ActorDescriptor, ActorRegistry, AuthorityClass
from uow.composition.binding import ActorBinding
from uow.composition.contract import (
    AuthorityObligation,
    CausalConstraint,
    EvidenceObligation,
    FailureSemantics,
    ParentContract,
    ResourceConstraint,
    TemporalConstraint,
)
from uow.composition.endurance import (
    AntiThrashingHysteresis,
    ContinuousPerturbationTrace,
    EnduranceAdaptiveRuntime,
    EnvironmentalState,
    FixedBaselineRuntime,
    LineageEdge,
    ObservationPoisoningEngine,
    RuleBasedRuntime,
    RuntimeObjectiveFunction,
    TopologyLineage,
)
from uow.composition.graph import RealizationGraph, RealizationNode
from uow.composition.host_node import PhysicalHostNode
from uow.composition.policy import AdaptiveGraphProposer, GraphAdaptationObservation


@pytest.fixture
def parent_contract() -> ParentContract:
    return ParentContract(
        contract_id="contract_uow_a28_endurance",
        description="A2.8 Continuous Endurance Contract",
        required_outputs=("certified_result_R",),
        causal_constraints=(
            CausalConstraint("parser", "worker"),
            CausalConstraint("worker", "verifier"),
            CausalConstraint("verifier", "commit"),
        ),
        authority=AuthorityObligation(
            required_role="verifier",
            min_evidence_level="portable",
            quorum_threshold=1,
        ),
        evidence=EvidenceObligation(
            require_provenance=True,
            require_hash_chain=True,
            min_evidence_level="portable",
            verifier_id="deterministic-judge",
        ),
        temporal=TemporalConstraint(max_duration_ms=1000.0),
        resources=ResourceConstraint(
            max_cpu_cores=8,
            max_ram_units=16,
            max_gpu_slots=2,
            max_npu_slots=2,
            max_cost_units=100.0,
        ),
        failure_semantics=FailureSemantics.ROLLBACK,
    )


@pytest.fixture
def candidate_topologies() -> tuple[dict[str, RealizationGraph], dict[str, ActorBinding]]:
    # 1. G_npu: Accelerator offload
    g_npu = RealizationGraph(
        "G_npu",
        nodes={
            "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
            "n_npu_work": RealizationNode("n_npu_work", role="worker", actor_class="npu", npu_slots=1, duration_ms=15.0),
            "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
            "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
        },
        edges=(
            ("n_parse", "n_npu_work"),
            ("n_npu_work", "n_verify"),
            ("n_verify", "n_commit"),
        ),
    )
    b_npu = ActorBinding(
        binding_id="bind_npu",
        graph_id="G_npu",
        node_to_actor={
            "n_parse": "actor_host_cpu",
            "n_npu_work": "actor_intel_npu",
            "n_verify": "actor_host_cpu",
            "n_commit": "actor_host_cpu",
        },
    )

    # 2. G_parallel: Parallel CPU execution
    g_parallel = RealizationGraph(
        "G_parallel",
        nodes={
            "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
            "n_work_a": RealizationNode("n_work_a", role="worker", actor_class="cpu", duration_ms=45.0),
            "n_work_b": RealizationNode("n_work_b", role="worker", actor_class="cpu", duration_ms=45.0),
            "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
            "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
        },
        edges=(
            ("n_parse", "n_work_a"),
            ("n_parse", "n_work_b"),
            ("n_work_a", "n_verify"),
            ("n_work_b", "n_verify"),
            ("n_verify", "n_commit"),
        ),
    )
    b_parallel = ActorBinding(
        binding_id="bind_parallel",
        graph_id="G_parallel",
        node_to_actor={
            "n_parse": "actor_host_cpu",
            "n_work_a": "actor_host_cpu",
            "n_work_b": "actor_parallel_worker",
            "n_verify": "actor_host_cpu",
            "n_commit": "actor_host_cpu",
        },
    )

    # 3. G_sequential: Simple sequential CPU baseline
    g_sequential = RealizationGraph(
        "G_sequential",
        nodes={
            "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
            "n_work": RealizationNode("n_work", role="worker", actor_class="cpu", duration_ms=80.0),
            "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
            "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
        },
        edges=(
            ("n_parse", "n_work"),
            ("n_work", "n_verify"),
            ("n_verify", "n_commit"),
        ),
    )
    b_sequential = ActorBinding(
        binding_id="bind_sequential",
        graph_id="G_sequential",
        node_to_actor={
            "n_parse": "actor_host_cpu",
            "n_work": "actor_host_cpu",
            "n_verify": "actor_host_cpu",
            "n_commit": "actor_host_cpu",
        },
    )

    graphs = {"G_npu": g_npu, "G_parallel": g_parallel, "G_sequential": g_sequential}
    bindings = {"G_npu": b_npu, "G_parallel": b_parallel, "G_sequential": b_sequential}
    return graphs, bindings


@pytest.fixture
def authority_keys() -> dict[str, str]:
    return {
        "auth_esp32": "secret_key_esp32_777",
        "auth_stm32": "secret_key_stm32_888",
        "auth_cpu": "secret_key_cpu_999",
    }


def test_continuous_perturbation_trace_generation() -> None:
    trace = ContinuousPerturbationTrace(total_steps=50, seed=123)
    assert len(trace.states) == 50

    # Ensure deterministic replay
    trace_replayed = ContinuousPerturbationTrace(total_steps=50, seed=123)
    for s1, s2 in zip(trace.states, trace_replayed.states):
        assert s1.compute_hash() == s2.compute_hash()

    # Verify presence of varied conditions
    loads = [s.npu_load for s in trace.states]
    assert min(loads) < 0.20
    assert max(loads) > 0.70


def test_runtime_objective_function(
    candidate_topologies: tuple[dict[str, RealizationGraph], dict[str, ActorBinding]],
) -> None:
    graphs, bindings = candidate_topologies
    objective = RuntimeObjectiveFunction()

    # 1. Under nominal conditions, NPU graph has lower cost than sequential
    nominal_env = EnvironmentalState(
        step_index=0,
        npu_load=0.10,
        cpu_load=0.15,
        network_loss=0.01,
        network_latency_ms=5.0,
        actor_availability={"actor_host_cpu": True, "actor_intel_npu": True, "actor_parallel_worker": True},
        active_failures=(),
    )
    cost_npu = objective.evaluate(graphs["G_npu"], bindings["G_npu"], nominal_env)
    cost_seq = objective.evaluate(graphs["G_sequential"], bindings["G_sequential"], nominal_env)
    assert cost_npu < cost_seq

    # 2. When NPU is saturated, NPU cost increases
    saturated_env = EnvironmentalState(
        step_index=1,
        npu_load=0.95,
        cpu_load=0.20,
        network_loss=0.01,
        network_latency_ms=5.0,
        actor_availability={"actor_host_cpu": True, "actor_intel_npu": True, "actor_parallel_worker": True},
        active_failures=(),
    )
    cost_npu_sat = objective.evaluate(graphs["G_npu"], bindings["G_npu"], saturated_env)
    assert cost_npu_sat > cost_npu

    # 3. When an actor is unavailable, failure risk spikes heavily
    broken_env = EnvironmentalState(
        step_index=2,
        npu_load=0.10,
        cpu_load=0.15,
        network_loss=0.01,
        network_latency_ms=5.0,
        actor_availability={"actor_host_cpu": True, "actor_intel_npu": False, "actor_parallel_worker": True},
        active_failures=("actor_intel_npu",),
    )
    cost_broken = objective.evaluate(graphs["G_npu"], bindings["G_npu"], broken_env)
    assert cost_broken > cost_npu + 50.0


def test_anti_thrashing_hysteresis() -> None:
    hysteresis = AntiThrashingHysteresis(min_dwell_steps=4, delta_threshold=15.0)

    # 1. First mutation allowed
    should, _ = hysteresis.should_propose(current_cost=100.0, candidate_cost=70.0, current_broken=False, current_step=0)
    assert should is True
    hysteresis.record_mutation(step=0)

    # 2. At step 1 (elapsed=1 < 4), dwell time blocks mutation despite improvement
    should, reason = hysteresis.should_propose(current_cost=70.0, candidate_cost=50.0, current_broken=False, current_step=1)
    assert should is False
    assert "DWELL_TIME_ENFORCED" in reason

    # 3. At step 1, if current topology is structurally broken, dwell time is waived!
    should_broken, reason_broken = hysteresis.should_propose(current_cost=70.0, candidate_cost=50.0, current_broken=True, current_step=1)
    assert should_broken is True
    assert reason_broken == "FAILOVER_MANDATORY"

    # 4. At step 5 (elapsed=5 >= 4), but improvement < threshold (delta=5 < 15) -> Blocked
    should_insuf, reason_insuf = hysteresis.should_propose(current_cost=70.0, candidate_cost=65.0, current_broken=False, current_step=5)
    assert should_insuf is False
    assert "INSUFFICIENT_IMPROVEMENT" in reason_insuf

    # 5. At step 5, improvement >= threshold (delta=20 >= 15) -> Allowed
    should_ok, _ = hysteresis.should_propose(current_cost=70.0, candidate_cost=50.0, current_broken=False, current_step=5)
    assert should_ok is True


def test_comparative_baselines_performance(
    parent_contract: ParentContract,
    candidate_topologies: tuple[dict[str, RealizationGraph], dict[str, ActorBinding]],
    authority_keys: dict[str, str],
) -> None:
    graphs, bindings = candidate_topologies
    trace = ContinuousPerturbationTrace(total_steps=40, seed=42)
    objective = RuntimeObjectiveFunction()

    # B0: Static fixed baseline
    b0 = FixedBaselineRuntime(graphs["G_sequential"], bindings["G_sequential"], parent_contract, objective)

    # B1: Rule-based heuristic failover
    b1 = RuleBasedRuntime(graphs, bindings, parent_contract, objective)

    # A2: Learned adaptive runtime with physical host node & WAL
    with tempfile.TemporaryDirectory() as tmpdir:
        node = PhysicalHostNode(
            "host_a2_eval",
            Path(tmpdir),
            secret_key="a2_secret",
            active_graph=graphs["G_npu"],
            active_binding=bindings["G_npu"],
        )
        node.startup()

        a2 = EnduranceAdaptiveRuntime(
            node=node,
            candidate_graphs=graphs,
            candidate_bindings=bindings,
            parent_contract=parent_contract,
            authority_keys=authority_keys,
            objective=objective,
        )

        for step, env in enumerate(trace.states):
            b0.execute_step(step, env)
            b1.execute_step(step, env)
            a2.execute_step(step, env)

        # Performance evaluation: J_adaptive < J_static
        assert a2.cumulative_cost < b0.cumulative_cost
        delta_j = a2.cumulative_cost - b0.cumulative_cost
        assert delta_j < 0.0

        # Safety evaluation: strictly zero errors
        assert a2.wrong_commits == 0
        assert a2.uncertified_mutations == 0
        assert a2.lost_tasks == 0
        assert a2.node.history.verify_integrity() is True


def test_topology_lineage_forensics(
    parent_contract: ParentContract,
    candidate_topologies: tuple[dict[str, RealizationGraph], dict[str, ActorBinding]],
    authority_keys: dict[str, str],
) -> None:
    graphs, bindings = candidate_topologies
    trace = ContinuousPerturbationTrace(total_steps=30, seed=99)
    objective = RuntimeObjectiveFunction()

    with tempfile.TemporaryDirectory() as tmpdir:
        node = PhysicalHostNode(
            "host_lineage_test",
            Path(tmpdir),
            secret_key="secret_lineage",
            active_graph=graphs["G_npu"],
            active_binding=bindings["G_npu"],
        )
        node.startup()

        runtime = EnduranceAdaptiveRuntime(
            node=node,
            candidate_graphs=graphs,
            candidate_bindings=bindings,
            parent_contract=parent_contract,
            authority_keys=authority_keys,
            objective=objective,
            hysteresis=AntiThrashingHysteresis(min_dwell_steps=2, delta_threshold=5.0),
        )

        for step, env in enumerate(trace.states):
            runtime.execute_step(step, env)

        lineage_edges = runtime.lineage.edges
        assert len(lineage_edges) > 0

        # Verify edge structure and provenance
        for edge in lineage_edges:
            assert edge.from_graph_id in graphs
            assert edge.to_graph_id in graphs
            assert edge.conformance_verified is True
            assert len(edge.signers) >= 2
            assert edge.qc_hash != ""
            assert edge.generation_after > edge.generation_before


def test_observation_poisoning_attack_resilience(
    parent_contract: ParentContract,
    candidate_topologies: tuple[dict[str, RealizationGraph], dict[str, ActorBinding]],
    authority_keys: dict[str, str],
) -> None:
    """Deliberately attacks the feedback loop with delayed, reordered, and corrupt observations.
    
    Verifies the invariant:
    poor policy -> rejected or suboptimal proposals != incorrect authoritative state.
    """
    graphs, bindings = candidate_topologies
    objective = RuntimeObjectiveFunction()

    # Generate initial legitimate observations
    legit_obs = [
        GraphAdaptationObservation(
            observation_id=f"obs_{i}",
            parent_contract_id=parent_contract.contract_id,
            state_snapshot_hash=f"hash_{i}",
            proposed_graph_id="G_npu",
            proposed_strategy="accelerator_offload",
            certification_outcome="ACCEPTED",
            execution_status="SUCCESS",
            observed_latency_ms=25.0 + i,
        )
        for i in range(5)
    ]

    # Poison observations
    poisoned_obs = ObservationPoisoningEngine.poison_observations(legit_obs, attack_type="all")
    assert len(poisoned_obs) >= len(legit_obs)

    # Proposer adapts on poisoned observations
    proposer = AdaptiveGraphProposer()
    for o in poisoned_obs:
        proposer.adapt(o)

    with tempfile.TemporaryDirectory() as tmpdir:
        node = PhysicalHostNode(
            "host_poison_test",
            Path(tmpdir),
            secret_key="secret_poison",
            active_graph=graphs["G_npu"],
            active_binding=bindings["G_npu"],
        )
        node.startup()

        runtime = EnduranceAdaptiveRuntime(
            node=node,
            candidate_graphs=graphs,
            candidate_bindings=bindings,
            parent_contract=parent_contract,
            authority_keys=authority_keys,
            objective=objective,
            proposer=proposer,
        )

        trace = ContinuousPerturbationTrace(total_steps=20, seed=777)
        for step, env in enumerate(trace.states):
            runtime.execute_step(step, env)

        # Invariant: Despite poisoned learning, zero wrong commits and zero uncertified mutations!
        assert runtime.wrong_commits == 0
        assert runtime.uncertified_mutations == 0
        assert runtime.lost_tasks == 0
        assert runtime.node.history.verify_integrity() is True


def test_crash_recovery_during_continuous_endurance(
    parent_contract: ParentContract,
    candidate_topologies: tuple[dict[str, RealizationGraph], dict[str, ActorBinding]],
    authority_keys: dict[str, str],
) -> None:
    graphs, bindings = candidate_topologies
    objective = RuntimeObjectiveFunction()
    trace = ContinuousPerturbationTrace(total_steps=25, seed=555)

    with tempfile.TemporaryDirectory() as tmpdir:
        node = PhysicalHostNode(
            "host_crash_endurance",
            Path(tmpdir),
            secret_key="secret_crash_endurance",
            active_graph=graphs["G_npu"],
            active_binding=bindings["G_npu"],
        )
        node.startup()

        runtime = EnduranceAdaptiveRuntime(
            node=node,
            candidate_graphs=graphs,
            candidate_bindings=bindings,
            parent_contract=parent_contract,
            authority_keys=authority_keys,
            objective=objective,
            hysteresis=AntiThrashingHysteresis(min_dwell_steps=2, delta_threshold=5.0),
        )

        for step, env in enumerate(trace.states):
            runtime.execute_step(step, env)
            # Inject periodic sudden crashes mid-execution
            if step in (7, 18):
                pre_crash_digest = node.history.state_digest()
                pre_crash_entries = len(node.history.entries)
                node.crash()
                assert not node.is_alive

                replayed = node.restart()
                assert node.is_alive
                assert replayed == pre_crash_entries
                assert node.history.state_digest() == pre_crash_digest
                assert node.history.verify_integrity() is True

        # Final verification
        assert runtime.wrong_commits == 0
        assert runtime.uncertified_mutations == 0
        assert node.history.verify_integrity() is True
