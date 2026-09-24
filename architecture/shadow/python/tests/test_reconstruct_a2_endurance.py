from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

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
    FixedBaselineRuntime,
    GraphAdaptationObservation,
    ObservationPoisoningEngine,
    RuleBasedRuntime,
    RuntimeObjectiveFunction,
)
from uow.composition.graph import RealizationGraph, RealizationNode
from uow.composition.host_node import DurableWAL
from uow.composition.policy import AdaptiveGraphProposer
from uow.composition.projection import project_semantics

from uow_shadow.endurance_reconstruction import ShadowEnduranceAdaptiveRuntime


def _contract() -> ParentContract:
    return ParentContract(
        contract_id="contract_uow_a28_endurance",
        description="A2.8 Continuous Autonomous Evolution Contract",
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


def _topologies():
    g_npu = RealizationGraph(
        "G_npu",
        {
            "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
            "n_npu_work": RealizationNode(
                "n_npu_work", role="worker", actor_class="npu", npu_slots=1, duration_ms=15.0
            ),
            "n_verify": RealizationNode(
                "n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0
            ),
            "n_commit": RealizationNode(
                "n_commit", role="commit", actor_class="cpu",
                outputs=("certified_result_R",), duration_ms=10.0
            ),
        },
        (
            ("n_parse", "n_npu_work"),
            ("n_npu_work", "n_verify"),
            ("n_verify", "n_commit"),
        ),
    )
    b_npu = ActorBinding(
        "bind_npu",
        "G_npu",
        {
            "n_parse": "actor_host_cpu",
            "n_npu_work": "actor_intel_npu",
            "n_verify": "actor_host_cpu",
            "n_commit": "actor_host_cpu",
        },
    )

    g_parallel = RealizationGraph(
        "G_parallel",
        {
            "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
            "n_work_a": RealizationNode("n_work_a", role="worker", actor_class="cpu", duration_ms=45.0),
            "n_work_b": RealizationNode("n_work_b", role="worker", actor_class="cpu", duration_ms=45.0),
            "n_verify": RealizationNode(
                "n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0
            ),
            "n_commit": RealizationNode(
                "n_commit", role="commit", actor_class="cpu",
                outputs=("certified_result_R",), duration_ms=10.0
            ),
        },
        (
            ("n_parse", "n_work_a"),
            ("n_parse", "n_work_b"),
            ("n_work_a", "n_verify"),
            ("n_work_b", "n_verify"),
            ("n_verify", "n_commit"),
        ),
    )
    b_parallel = ActorBinding(
        "bind_parallel",
        "G_parallel",
        {
            "n_parse": "actor_host_cpu",
            "n_work_a": "actor_host_cpu",
            "n_work_b": "actor_parallel_worker",
            "n_verify": "actor_host_cpu",
            "n_commit": "actor_host_cpu",
        },
    )

    g_seq = RealizationGraph(
        "G_sequential",
        {
            "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
            "n_work": RealizationNode("n_work", role="worker", actor_class="cpu", duration_ms=80.0),
            "n_verify": RealizationNode(
                "n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0
            ),
            "n_commit": RealizationNode(
                "n_commit", role="commit", actor_class="cpu",
                outputs=("certified_result_R",), duration_ms=10.0
            ),
        },
        (
            ("n_parse", "n_work"),
            ("n_work", "n_verify"),
            ("n_verify", "n_commit"),
        ),
    )
    b_seq = ActorBinding(
        "bind_sequential",
        "G_sequential",
        {
            "n_parse": "actor_host_cpu",
            "n_work": "actor_host_cpu",
            "n_verify": "actor_host_cpu",
            "n_commit": "actor_host_cpu",
        },
    )

    return (
        {"G_npu": g_npu, "G_parallel": g_parallel, "G_sequential": g_seq},
        {"G_npu": b_npu, "G_parallel": b_parallel, "G_sequential": b_seq},
    )


def _runtime(*, wal=None, proposer=None, hysteresis=None):
    contract = _contract()
    graphs, bindings = _topologies()
    return (
        ShadowEnduranceAdaptiveRuntime(
            initial_graph=graphs["G_npu"],
            initial_binding=bindings["G_npu"],
            candidate_graphs=graphs,
            candidate_bindings=bindings,
            parent_contract=contract,
            authority_keys={
                "auth_cpu": "secret_key_cpu_999",
                "auth_esp32": "secret_key_esp32_777",
                "auth_stm32": "secret_key_stm32_888",
            },
            objective=RuntimeObjectiveFunction(),
            hysteresis=hysteresis or AntiThrashingHysteresis(min_dwell_steps=2, delta_threshold=5.0),
            proposer=proposer,
            wal=wal,
        ),
        contract,
        graphs,
        bindings,
    )


def test_r4_a2_8_reconstructs_original_40_step_baseline_comparison():
    runtime, contract, graphs, bindings = _runtime()
    objective = RuntimeObjectiveFunction()
    b0 = FixedBaselineRuntime(graphs["G_sequential"], bindings["G_sequential"], contract, objective)
    b1 = RuleBasedRuntime(graphs, bindings, contract, objective)
    trace = ContinuousPerturbationTrace(total_steps=40, seed=42)

    for step, env in enumerate(trace.states):
        b0.execute_step(step, env)
        b1.execute_step(step, env)
        result = runtime.execute_step(step, env)
        assert result.ok
        assert project_semantics(runtime.active_graph, contract).conforms

    assert round(b0.cumulative_cost, 2) == 8299.78
    assert round(b1.cumulative_cost, 2) == 5934.51
    assert round(runtime.cumulative_cost, 2) == 5907.99
    assert runtime.cumulative_cost < b0.cumulative_cost
    assert len(runtime.lineage.edges) == 1

    assert runtime.wrong_commits == 0
    assert runtime.uncertified_mutations == 0
    assert runtime.double_commits == 0
    assert runtime.authority_inflations == 0
    assert runtime.stale_mutations == 0
    assert runtime.lost_tasks == 0
    assert runtime.history.verify_integrity()
    assert len(runtime.completed_steps) == 40


def test_r4_a2_8_lineage_preserves_quorum_and_generation_provenance():
    runtime, _contract_obj, graphs, _bindings = _runtime()
    trace = ContinuousPerturbationTrace(total_steps=30, seed=99)
    for step, env in enumerate(trace.states):
        runtime.execute_step(step, env)

    assert runtime.lineage.edges
    for edge in runtime.lineage.edges:
        assert edge.from_graph_id in graphs
        assert edge.to_graph_id in graphs
        assert edge.conformance_verified
        assert len(edge.signers) >= 2
        assert edge.qc_hash
        assert edge.generation_after > edge.generation_before


def test_r4_a2_8_hysteresis_and_duplicate_task_protection_remain_explicit():
    h = AntiThrashingHysteresis(min_dwell_steps=4, delta_threshold=15.0)
    should, _ = h.should_propose(100.0, 70.0, False, 0)
    assert should
    h.record_mutation(0)

    blocked, reason = h.should_propose(70.0, 50.0, False, 1)
    assert not blocked
    assert "DWELL_TIME_ENFORCED" in reason

    failover, fail_reason = h.should_propose(70.0, 50.0, True, 1)
    assert failover
    assert fail_reason == "FAILOVER_MANDATORY"

    runtime, _, _, _ = _runtime()
    env = ContinuousPerturbationTrace(total_steps=1, seed=42).states[0]
    runtime.execute_step(0, env)
    entries = len(runtime.history.entries)
    runtime.execute_step(0, env)

    assert runtime.double_commits == 1
    assert len(runtime.history.entries) == entries


def test_r4_a2_8_poisoned_learning_cannot_cross_quorum_authority_boundary():
    legit = [
        GraphAdaptationObservation(
            observation_id=f"obs_{i}",
            parent_contract_id=_contract().contract_id,
            state_snapshot_hash=f"snap_{i}",
            proposed_graph_id="G_npu",
            proposed_strategy="accelerator_offload",
            certification_outcome="ACCEPTED",
            execution_status="SUCCESS",
            observed_latency_ms=20.0,
        )
        for i in range(5)
    ]
    poisoned = ObservationPoisoningEngine.poison_observations(legit, "all")
    proposer = AdaptiveGraphProposer()
    for observation in poisoned:
        proposer.adapt(observation)

    runtime, contract, _, _ = _runtime(proposer=proposer)
    trace = ContinuousPerturbationTrace(total_steps=20, seed=777)
    for step, env in enumerate(trace.states):
        runtime.execute_step(step, env)
        assert project_semantics(runtime.active_graph, contract).conforms

    assert runtime.uncertified_mutations == 0
    assert runtime.wrong_commits == 0
    assert runtime.lost_tasks == 0
    assert runtime.history.verify_integrity()


def test_r4_a2_8_wal_replay_recovers_identical_authoritative_history():
    with tempfile.TemporaryDirectory() as tmp:
        wal = DurableWAL(Path(tmp))
        runtime, _, _, _ = _runtime(wal=wal)
        trace = ContinuousPerturbationTrace(total_steps=30, seed=555)

        for step, env in enumerate(trace.states):
            runtime.execute_step(step, env)

        before_digest = runtime.history.state_digest()
        before_entries = len(runtime.history.entries)
        before_generation = runtime.generation

        rebuilt = runtime.recover_history_from_wal()

        assert len(rebuilt.entries) == before_entries
        assert rebuilt.state_digest() == before_digest
        assert rebuilt.verify_integrity()
        assert max((e.generation for e in rebuilt.entries), default=0) == before_generation


def test_r4_a2_8_does_not_use_canonical_endurance_runtime(monkeypatch):
    import uow.composition.endurance as canonical

    def forbidden(*args, **kwargs):
        raise AssertionError("canonical EnduranceAdaptiveRuntime must not be used")

    monkeypatch.setattr(canonical.EnduranceAdaptiveRuntime, "execute_step", forbidden)

    runtime, _, _, _ = _runtime()
    trace = ContinuousPerturbationTrace(total_steps=5, seed=42)
    for step, env in enumerate(trace.states):
        runtime.execute_step(step, env)

    assert runtime.history.verify_integrity()
