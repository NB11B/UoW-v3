"""Qualification tests for Gate A2.3: Distributed Actor Fabric & Dynamic Network Churn."""
from __future__ import annotations

import time
import pytest

from uow import (
    ActorBinding,
    ActorDescriptor,
    ActorLease,
    ActorRegistry,
    AdaptiveCompositionRuntime,
    AdaptiveGraphProposer,
    AgentMessageKind,
    AuthorityClass,
    AuthorityObligation,
    CausalConstraint,
    CompositionCertifier,
    CompositionRuntimeState,
    DistributedActorFabric,
    EvidenceObligation,
    FailureSemantics,
    GraphReplacementProposal,
    NetworkAgent,
    ParentContract,
    RealizationGraph,
    RealizationNode,
    ResourceConstraint,
    SubstitutionStrategy,
    TemporalConstraint,
    validate_binding,
)
from qualification.claim_registry import get_claim
from qualification.evidence import (
    ClaimRequirement,
    EvidenceContext,
    EvidenceLevel,
    evaluate_claim,
)


@pytest.fixture
def canonical_contract() -> ParentContract:
    return ParentContract(
        contract_id="parent_certified_transform_v1",
        description="Transform input X into certified output R with immutable evidence.",
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
def sample_graphs() -> Tuple[RealizationGraph, RealizationGraph, RealizationGraph]:
    g0 = RealizationGraph(
        "G0_sequential",
        {
            "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
            "n_work_a": RealizationNode("n_work_a", role="worker", actor_class="cpu", duration_ms=80.0),
            "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
            "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
        },
        (("n_parse", "n_work_a"), ("n_work_a", "n_verify"), ("n_verify", "n_commit")),
    )

    g1 = RealizationGraph(
        "G1_parallel",
        {
            "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
            "n_work_a": RealizationNode("n_work_a", role="worker", actor_class="cpu", duration_ms=50.0),
            "n_work_b": RealizationNode("n_work_b", role="worker", actor_class="cpu", duration_ms=50.0),
            "n_resolver": RealizationNode("n_resolver", role="worker", actor_class="cpu", duration_ms=20.0),
            "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
            "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
        },
        (
            ("n_parse", "n_work_a"),
            ("n_parse", "n_work_b"),
            ("n_work_a", "n_resolver"),
            ("n_work_b", "n_resolver"),
            ("n_resolver", "n_verify"),
            ("n_verify", "n_commit"),
        ),
    )

    g2 = RealizationGraph(
        "G2_accelerator",
        {
            "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
            "n_npu_work": RealizationNode("n_npu_work", role="worker", actor_class="npu", npu_slots=1, duration_ms=15.0),
            "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
            "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
        },
        (("n_parse", "n_npu_work"), ("n_npu_work", "n_verify"), ("n_verify", "n_commit")),
    )

    return g0, g1, g2


# -----------------------------------------------------------------------------
# 1. Lease & Protocol Tests
# -----------------------------------------------------------------------------

def test_gate_a2_3_actor_lease_issuance_and_expiration():
    """ActorLease computes SHA-256 digest and enforces expiration."""
    lease = ActorLease(
        actor_id="agent_alpha",
        descriptor_hash="desc_hash_01",
        epoch=1,
        granted_at_ts=100.0,
        expires_at_ts=130.0,
        nonce="nonce_001",
    )
    assert len(lease.compute_hash()) == 64
    assert lease.is_valid(110.0)
    assert lease.is_valid(130.0)
    assert not lease.is_valid(130.01)


def test_gate_a2_3_network_agent_protocol_messages():
    """NetworkAgent produces ANNOUNCE and HEARTBEAT messages and executes work."""
    desc = ActorDescriptor("agent_worker", ("role:worker", "cpu_compute"), "cpu_x86", AuthorityClass.PROPOSER_ONLY)
    agent = NetworkAgent("agent_worker", desc)

    ann = agent.announce()
    assert ann.kind == AgentMessageKind.ANNOUNCE
    assert ann.payload["descriptor"]["actor_id"] == "agent_worker"

    hb = agent.heartbeat()
    assert hb.kind == AgentMessageKind.HEARTBEAT
    assert hb.payload["alive"] is True

    out, ev = agent.execute_step("node_1", "worker", {"task": "data_01"})
    assert "res_task" in out
    assert len(ev) == 16

    agent.terminate()
    assert agent.is_alive is False
    with pytest.raises(RuntimeError, match="terminated/offline"):
        agent.execute_step("node_1", "worker", {"task": "data_01"})


def test_gate_a2_3_discovery_vs_authority_qualification():
    """Validates Discover(A) != Qualify(A, U): untrusted verifier claim rejected."""
    fabric = DistributedActorFabric(
        trusted_authority_keys={"agent_esp32_trusted", "agent_laptop_judge"},
        lease_ttl_sec=20.0,
    )

    # 1. Honest worker agent
    worker_desc = ActorDescriptor("agent_worker", ("role:worker",), "cpu_x86", AuthorityClass.PROPOSER_ONLY)
    agent_worker = NetworkAgent("agent_worker", worker_desc)
    fabric.register_agent(agent_worker, current_ts=100.0)
    assert fabric.qualify_actor("agent_worker", AuthorityClass.PROPOSER_ONLY)

    # 2. Rogue untrusted agent claiming to be a VERIFIER
    rogue_desc = ActorDescriptor("agent_rogue", ("role:verifier",), "cloud_server", AuthorityClass.VERIFIER)
    agent_rogue = NetworkAgent("agent_rogue", rogue_desc)
    fabric.register_agent(agent_rogue, current_ts=100.0)
    # Rogue agent is discovered and leased, BUT NOT QUALIFIED for authority!
    assert fabric.qualify_actor("agent_rogue", AuthorityClass.PROPOSER_ONLY)
    assert not fabric.qualify_actor("agent_rogue", AuthorityClass.VERIFIER)

    # 3. Legitimate trusted authority agent
    esp32_desc = ActorDescriptor("agent_esp32_trusted", ("role:verifier",), "esp32_xtensa", AuthorityClass.VERIFIER)
    agent_esp32 = NetworkAgent("agent_esp32_trusted", esp32_desc)
    fabric.register_agent(agent_esp32, current_ts=100.0)
    assert fabric.qualify_actor("agent_esp32_trusted", AuthorityClass.VERIFIER)


def test_gate_a2_3_fabric_lease_reaping_on_timeout():
    """Fabric reaps expired leases and marks actors offline."""
    fabric = DistributedActorFabric(lease_ttl_sec=10.0)
    desc = ActorDescriptor("agent_temp", ("role:worker",), "cpu_x86", AuthorityClass.PROPOSER_ONLY)
    agent = NetworkAgent("agent_temp", desc)
    fabric.register_agent(agent, current_ts=50.0)

    # Valid at 55s
    assert fabric.get_valid_lease("agent_temp", current_ts=55.0) is not None

    # Expired at 65s
    expired = fabric.reap_expired_leases(current_ts=65.0)
    assert "agent_temp" in expired
    assert fabric.get_valid_lease("agent_temp", current_ts=65.0) is None
    assert fabric.registry.get("agent_temp").availability is False


# -----------------------------------------------------------------------------
# 2. Dynamic Churn: Rebinding vs. Graph Substitution
# -----------------------------------------------------------------------------

def test_gate_a2_3_rebinding_on_worker_loss_without_graph_change(sample_graphs, canonical_contract):
    """Tier 1: Worker actor loss triggers fast rebinding (B0 -> B1) with G0 == G1."""
    g0, _, _ = sample_graphs
    fabric = DistributedActorFabric(
        trusted_authority_keys={"act_verifier"},
        lease_ttl_sec=30.0,
    )

    # Register initial 4 actors (A, B, C, D)
    fabric.register_agent(NetworkAgent("act_parse", ActorDescriptor("act_parse", ("role:parser",), "cpu_x86")), current_ts=10.0)
    fabric.register_agent(NetworkAgent("act_work_b", ActorDescriptor("act_work_b", ("role:worker",), "cpu_x86")), current_ts=10.0)
    fabric.register_agent(NetworkAgent("act_work_d", ActorDescriptor("act_work_d", ("role:worker",), "cpu_x86")), current_ts=10.0)
    fabric.register_agent(NetworkAgent("act_verifier", ActorDescriptor("act_verifier", ("role:verifier",), "cpu_x86", AuthorityClass.VERIFIER)), current_ts=10.0)
    fabric.register_agent(NetworkAgent("act_commit", ActorDescriptor("act_commit", ("role:commit",), "cpu_x86")), current_ts=10.0)

    b0 = ActorBinding(
        "b0", g0.graph_id,
        {"n_parse": "act_parse", "n_work_a": "act_work_b", "n_verify": "act_verifier", "n_commit": "act_commit"},
    )

    runtime = AdaptiveCompositionRuntime(
        contract=canonical_contract,
        baseline_graph=g0,
        registry=fabric.registry,
        baseline_binding=b0,
        fabric=fabric,
    )

    # Execute B0
    rec0 = runtime.execute({"data": "nominal"}, current_ts=15.0)
    assert rec0.status == "SUCCESS"

    # Agent B crashes / disconnects
    fabric.registered_agents["act_work_b"].terminate()
    fabric.registry.update_status("act_work_b", availability=False)

    # Rebind worker node to Agent D (B0 -> B1) without changing G0
    b1 = ActorBinding(
        "b1", g0.graph_id,
        {"n_parse": "act_parse", "n_work_a": "act_work_d", "n_verify": "act_verifier", "n_commit": "act_commit"},
    )
    success, violations = runtime.rebind_active_graph(b1, current_ts=20.0)
    assert success
    assert runtime.active_graph.graph_id == g0.graph_id  # G0 unchanged!
    assert runtime.active_binding.node_to_actor["n_work_a"] == "act_work_d"

    # Execution with rebound actor succeeds
    rec1 = runtime.execute({"data": "rebound"}, current_ts=20.0)
    assert rec1.status == "SUCCESS"


def test_gate_a2_3_graph_substitution_on_npu_saturation(sample_graphs, canonical_contract):
    """Tier 2: When NPU saturates, proposer triggers graph substitution G2 -> G1."""
    g0, g1, g2 = sample_graphs
    fabric = DistributedActorFabric(
        trusted_authority_keys={"act_verifier"},
        lease_ttl_sec=30.0,
    )

    # Register actors
    fabric.register_agent(NetworkAgent("act_parse", ActorDescriptor("act_parse", ("role:parser",), "cpu_x86")), current_ts=10.0)
    fabric.register_agent(NetworkAgent("act_npu", ActorDescriptor("act_npu", ("role:worker", "npu_inference"), "intel_npu", load=0.98, latency_ms=80.0)), current_ts=10.0)
    fabric.register_agent(NetworkAgent("act_cpu_1", ActorDescriptor("act_cpu_1", ("role:worker",), "cpu_x86", load=0.1)), current_ts=10.0)
    fabric.register_agent(NetworkAgent("act_cpu_2", ActorDescriptor("act_cpu_2", ("role:worker",), "cpu_x86", load=0.1)), current_ts=10.0)
    fabric.register_agent(NetworkAgent("act_verifier", ActorDescriptor("act_verifier", ("role:verifier",), "cpu_x86", AuthorityClass.VERIFIER)), current_ts=10.0)
    fabric.register_agent(NetworkAgent("act_commit", ActorDescriptor("act_commit", ("role:commit",), "cpu_x86")), current_ts=10.0)

    runtime = AdaptiveCompositionRuntime(
        contract=canonical_contract,
        baseline_graph=g0,
        registry=fabric.registry,
        fabric=fabric,
    )
    proposer = AdaptiveGraphProposer()
    state = runtime.get_runtime_state()

    # Proposer evaluates saturated NPU and shifts to G1 (Parallel CPU)
    prop = proposer.propose_realization(state, canonical_contract, (g0, g1, g2), fabric.registry, runtime.current_graph_hash)
    assert prop is not None
    assert prop.candidate_graph.graph_id == "G1_parallel"
    assert prop.strategy == SubstitutionStrategy.PARALLEL_DECOMPOSITION

    cert = runtime.propose_and_certify(prop, current_ts=15.0)
    assert cert.is_accepted
    assert runtime.current_graph_hash == g1.compute_hash()


def test_gate_a2_3_fail_closed_on_authority_loss(sample_graphs, canonical_contract):
    """Tier 3: When authority actor lease expires with no replacement, runtime fails closed."""
    g0, _, _ = sample_graphs
    fabric = DistributedActorFabric(
        trusted_authority_keys={"act_verifier_esp32"},
        lease_ttl_sec=10.0,
    )

    fabric.register_agent(NetworkAgent("act_parse", ActorDescriptor("act_parse", ("role:parser",), "cpu_x86")), current_ts=10.0)
    fabric.register_agent(NetworkAgent("act_work", ActorDescriptor("act_work", ("role:worker",), "cpu_x86")), current_ts=10.0)
    fabric.register_agent(NetworkAgent("act_verifier_esp32", ActorDescriptor("act_verifier_esp32", ("role:verifier",), "esp32_xtensa", AuthorityClass.VERIFIER)), current_ts=10.0)
    fabric.register_agent(NetworkAgent("act_commit", ActorDescriptor("act_commit", ("role:commit",), "cpu_x86")), current_ts=10.0)

    b0 = ActorBinding(
        "b0", g0.graph_id,
        {"n_parse": "act_parse", "n_work_a": "act_work", "n_verify": "act_verifier_esp32", "n_commit": "act_commit"},
    )
    runtime = AdaptiveCompositionRuntime(
        contract=canonical_contract,
        baseline_graph=g0,
        registry=fabric.registry,
        baseline_binding=b0,
        fabric=fabric,
    )

    # Authority lease expires at ts=25s
    rec = runtime.execute({"data": "critical_payload"}, current_ts=25.0)
    assert rec.status == "FAILED"
    assert "AUTHORITY_ACTOR_UNAVAILABLE_FAIL_CLOSED" in rec.error_message


# -----------------------------------------------------------------------------
# 3. Formal Claim Evaluations
# -----------------------------------------------------------------------------

def test_gate_a2_3_qualification_claim_actor_fabric():
    """Qualifies Claim A2.ACTOR_FABRIC.PORTABLE."""
    spec = get_claim("A2.ACTOR_FABRIC.PORTABLE")
    fabric = DistributedActorFabric(trusted_authority_keys={"act_auth"})
    agent = NetworkAgent("act_auth", ActorDescriptor("act_auth", ("role:verifier",), "cpu_x86", AuthorityClass.VERIFIER))
    lease = fabric.register_agent(agent, current_ts=10.0)

    positive_pass = (
        lease.is_valid(15.0)
        and fabric.qualify_actor("act_auth", AuthorityClass.VERIFIER)
    )

    # Negative control: untrusted claim fails qualification
    untrusted = NetworkAgent("act_untrusted", ActorDescriptor("act_untrusted", ("role:verifier",), "cpu_x86", AuthorityClass.VERIFIER))
    fabric.register_agent(untrusted, current_ts=10.0)
    negative_pass = not fabric.qualify_actor("act_untrusted", AuthorityClass.VERIFIER)

    claim_res = evaluate_claim(
        observed_pass=(positive_pass and negative_pass),
        negative_control_pass=negative_pass,
        context=EvidenceContext(
            level=EvidenceLevel.PORTABLE,
            source="tests.test_composition_fabric",
            actual_components={"fabric": "DistributedActorFabric", "agent": "NetworkAgent"},
            substitutions={},
        ),
        requirement=ClaimRequirement(spec.required_level, spec.required_components),
    )
    assert claim_res["qualified"] and claim_res["passed"]


def test_gate_a2_3_qualification_claim_churn_resilience(sample_graphs, canonical_contract):
    """Qualifies Claim A2.CHURN_RESILIENCE.PORTABLE."""
    spec = get_claim("A2.CHURN_RESILIENCE.PORTABLE")
    g0, _, _ = sample_graphs
    fabric = DistributedActorFabric(trusted_authority_keys={"act_v"})
    fabric.register_agent(NetworkAgent("act_p", ActorDescriptor("act_p", ("role:parser",), "cpu_x86")), current_ts=10.0)
    fabric.register_agent(NetworkAgent("act_w1", ActorDescriptor("act_w1", ("role:worker",), "cpu_x86")), current_ts=10.0)
    fabric.register_agent(NetworkAgent("act_w2", ActorDescriptor("act_w2", ("role:worker",), "cpu_x86")), current_ts=10.0)
    fabric.register_agent(NetworkAgent("act_v", ActorDescriptor("act_v", ("role:verifier",), "cpu_x86", AuthorityClass.VERIFIER)), current_ts=10.0)
    fabric.register_agent(NetworkAgent("act_c", ActorDescriptor("act_c", ("role:commit",), "cpu_x86")), current_ts=10.0)

    b0 = ActorBinding("b0", g0.graph_id, {"n_parse": "act_p", "n_work_a": "act_w1", "n_verify": "act_v", "n_commit": "act_c"})
    runtime = AdaptiveCompositionRuntime(canonical_contract, g0, registry=fabric.registry, baseline_binding=b0, fabric=fabric)

    # Positive pass: rebinds w1 -> w2 without failure
    b1 = ActorBinding("b1", g0.graph_id, {"n_parse": "act_p", "n_work_a": "act_w2", "n_verify": "act_v", "n_commit": "act_c"})
    rebind_ok, _ = runtime.rebind_active_graph(b1, current_ts=15.0)
    rec = runtime.execute({"test": 1}, current_ts=15.0)
    positive_pass = rebind_ok and rec.status == "SUCCESS"

    # Negative control: authority loss fails closed
    fabric.active_leases["act_v"] = ActorLease("act_v", "h", 1, 10.0, 12.0, "n")  # Expired at 15.0
    rec_fail = runtime.execute({"test": 2}, current_ts=15.0)
    negative_pass = rec_fail.status == "FAILED" and "AUTHORITY_ACTOR_UNAVAILABLE_FAIL_CLOSED" in rec_fail.error_message

    claim_res = evaluate_claim(
        observed_pass=(positive_pass and negative_pass),
        negative_control_pass=negative_pass,
        context=EvidenceContext(
            level=EvidenceLevel.PORTABLE,
            source="tests.test_composition_fabric",
            actual_components={"runtime": "AdaptiveCompositionRuntime", "fabric": "DistributedActorFabric"},
            substitutions={},
        ),
        requirement=ClaimRequirement(spec.required_level, spec.required_components),
    )
    assert claim_res["qualified"] and claim_res["passed"]
