"""Qualification tests for Gate A2.2: Adaptive Graph Proposer & Actor Descriptors."""
from __future__ import annotations

import pytest

from uow.compat.v2 import (
    ActorBinding,
    ActorDescriptor,
    ActorRegistry,
    AdaptiveCompositionRuntime,
    AdaptiveGraphProposer,
    AuthorityClass,
    AuthorityObligation,
    CausalConstraint,
    CompositionCertifier,
    CompositionRuntimeState,
    EvidenceObligation,
    FailureSemantics,
    GraphAdaptationObservation,
    GraphReplacementProposal,
    ParentContract,
    RealizationGraph,
    RealizationNode,
    ResourceConstraint,
    SubstitutionDecision,
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
def candidate_graphs() -> Tuple[RealizationGraph, RealizationGraph, RealizationGraph]:
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


@pytest.fixture
def heterogeneous_actor_registry() -> ActorRegistry:
    """Registry with a rich pool of heterogeneous actors: CPU cores, NPU, verifiers, and committers."""
    actors = [
        ActorDescriptor("act_cpu_parse", ("role:parser", "cpu_compute"), "cpu_x86", AuthorityClass.PROPOSER_ONLY, load=0.1),
        ActorDescriptor("act_cpu_work_1", ("role:worker", "cpu_compute"), "cpu_x86", AuthorityClass.PROPOSER_ONLY, load=0.2),
        ActorDescriptor("act_cpu_work_2", ("role:worker", "cpu_compute"), "cpu_x86", AuthorityClass.PROPOSER_ONLY, load=0.25),
        ActorDescriptor("act_npu_work", ("role:worker", "npu_inference"), "intel_npu", AuthorityClass.PROPOSER_ONLY, load=0.1, latency_ms=0.8),
        ActorDescriptor("act_verifier", ("role:verifier", "deterministic_verifier"), "cpu_x86", AuthorityClass.VERIFIER, load=0.15),
        ActorDescriptor("act_commit", ("role:commit", "authority_commit"), "cpu_x86", AuthorityClass.PROPOSER_ONLY, load=0.05),
    ]
    return ActorRegistry(actors)


# -----------------------------------------------------------------------------
# 1. Actor Descriptor & Registry Tests
# -----------------------------------------------------------------------------

def test_gate_a2_2_actor_descriptor_and_registry_determinism(heterogeneous_actor_registry):
    """ActorDescriptor computes canonical hash and queries actors by capability."""
    act = heterogeneous_actor_registry.get("act_npu_work")
    assert act is not None
    assert len(act.compute_hash()) == 64
    assert act.has_capabilities(("role:worker", "npu_inference"))
    assert not act.has_capabilities(("cpu_compute",))

    # Query actors capable of 'role:worker'
    workers = heterogeneous_actor_registry.find_capable_actors(
        required_capabilities=("role:worker",),
        min_authority=AuthorityClass.PROPOSER_ONLY,
    )
    assert len(workers) == 3  # act_cpu_work_1, act_cpu_work_2, act_npu_work

    # Verifier query requires VERIFIER class
    verifiers = heterogeneous_actor_registry.find_capable_actors(
        required_capabilities=("role:verifier",),
        min_authority=AuthorityClass.VERIFIER,
    )
    assert len(verifiers) == 1
    assert verifiers[0].actor_id == "act_verifier"


# -----------------------------------------------------------------------------
# 2. Dynamic Actor Binding & Falsification Tests
# -----------------------------------------------------------------------------

def test_gate_a2_2_valid_actor_binding_passes(candidate_graphs, heterogeneous_actor_registry):
    """Valid actor binding matching capabilities and authority passes validation."""
    g0, _, _ = candidate_graphs
    binding = ActorBinding(
        binding_id="bind_g0_01",
        graph_id=g0.graph_id,
        node_to_actor={
            "n_parse": "act_cpu_parse",
            "n_work_a": "act_cpu_work_1",
            "n_verify": "act_verifier",
            "n_commit": "act_commit",
        },
    )
    valid, violations = validate_binding(g0, binding, heterogeneous_actor_registry)
    assert valid
    assert len(violations) == 0
    assert len(binding.compute_hash()) == 64


def test_gate_a2_2_falsification_missing_node_unbound_rejection(candidate_graphs, heterogeneous_actor_registry):
    """Binding that omits an active graph node is strictly rejected."""
    g0, _, _ = candidate_graphs
    binding = ActorBinding(
        binding_id="bind_incomplete",
        graph_id=g0.graph_id,
        node_to_actor={
            "n_parse": "act_cpu_parse",
            "n_work_a": "act_cpu_work_1",
            # n_verify missing!
            "n_commit": "act_commit",
        },
    )
    valid, violations = validate_binding(g0, binding, heterogeneous_actor_registry)
    assert not valid
    assert any("UNBOUND_NODE" in v for v in violations)


def test_gate_a2_2_falsification_unknown_actor_rejection(candidate_graphs, heterogeneous_actor_registry):
    """Binding referencing an unregistered actor ID is strictly rejected."""
    g0, _, _ = candidate_graphs
    binding = ActorBinding(
        binding_id="bind_unknown_act",
        graph_id=g0.graph_id,
        node_to_actor={
            "n_parse": "act_cpu_parse",
            "n_work_a": "act_ghost_actor_99",
            "n_verify": "act_verifier",
            "n_commit": "act_commit",
        },
    )
    valid, violations = validate_binding(g0, binding, heterogeneous_actor_registry)
    assert not valid
    assert any("UNKNOWN_ACTOR" in v for v in violations)


def test_gate_a2_2_falsification_actor_offline_rejection(candidate_graphs, heterogeneous_actor_registry):
    """Binding referencing an unavailable/offline actor is strictly rejected."""
    g0, _, _ = candidate_graphs
    heterogeneous_actor_registry.update_status("act_cpu_work_1", availability=False)

    binding = ActorBinding(
        binding_id="bind_offline",
        graph_id=g0.graph_id,
        node_to_actor={
            "n_parse": "act_cpu_parse",
            "n_work_a": "act_cpu_work_1",
            "n_verify": "act_verifier",
            "n_commit": "act_commit",
        },
    )
    valid, violations = validate_binding(g0, binding, heterogeneous_actor_registry)
    assert not valid
    assert any("ACTOR_UNAVAILABLE" in v for v in violations)


def test_gate_a2_2_falsification_capability_deficit_rejection(candidate_graphs, heterogeneous_actor_registry):
    """Binding assigning a CPU actor to an NPU node requiring 'npu_inference' is strictly rejected."""
    _, _, g2 = candidate_graphs  # G2 accelerator requires npu_inference
    binding = ActorBinding(
        binding_id="bind_cap_deficit",
        graph_id=g2.graph_id,
        node_to_actor={
            "n_parse": "act_cpu_parse",
            "n_npu_work": "act_cpu_work_1",  # act_cpu_work_1 lacks npu_inference!
            "n_verify": "act_verifier",
            "n_commit": "act_commit",
        },
    )
    valid, violations = validate_binding(g2, binding, heterogeneous_actor_registry)
    assert not valid
    assert any("ACTOR_CAPABILITY_DEFICIT" in v for v in violations)


def test_gate_a2_2_falsification_authority_downgrade_rejection(candidate_graphs, heterogeneous_actor_registry):
    """Binding assigning a PROPOSER_ONLY actor to a verifier node is strictly rejected."""
    g0, _, _ = candidate_graphs
    binding = ActorBinding(
        binding_id="bind_auth_downgrade",
        graph_id=g0.graph_id,
        node_to_actor={
            "n_parse": "act_cpu_parse",
            "n_work_a": "act_cpu_work_1",
            "n_verify": "act_cpu_work_2",  # act_cpu_work_2 is PROPOSER_ONLY!
            "n_commit": "act_commit",
        },
    )
    valid, violations = validate_binding(g0, binding, heterogeneous_actor_registry)
    assert not valid
    assert any("ACTOR_AUTHORITY_INSUFFICIENT" in v for v in violations)


# -----------------------------------------------------------------------------
# 3. Adaptive Proposer Policy Selection under Environmental Drift
# -----------------------------------------------------------------------------

def test_gate_a2_2_adaptive_proposer_selects_accelerator_when_idle(
    canonical_contract, candidate_graphs, heterogeneous_actor_registry
):
    """Proposer selects G2 (accelerator offload) when NPU is idle and available."""
    proposer = AdaptiveGraphProposer()
    state = CompositionRuntimeState(
        actor_availability={"act_npu_work": True, "act_cpu_work_1": True, "act_cpu_work_2": True},
        actor_loads={"act_npu_work": 0.05, "act_cpu_work_1": 0.2, "act_cpu_work_2": 0.2},
        actor_latencies={"act_npu_work": 0.8, "act_cpu_work_1": 5.0, "act_cpu_work_2": 5.0},
        actor_failure_counts={"act_npu_work": 0, "act_cpu_work_1": 0, "act_cpu_work_2": 0},
        active_graph_id="G0_sequential",
    )

    prop = proposer.propose_realization(
        state=state,
        contract=canonical_contract,
        candidate_graphs=candidate_graphs,
        registry=heterogeneous_actor_registry,
        current_graph_hash="current_hash",
    )
    assert prop is not None
    assert prop.candidate_graph.graph_id == "G2_accelerator"
    assert prop.strategy == SubstitutionStrategy.ACCELERATOR_OFFLOAD
    assert prop.actor_binding is not None
    assert prop.actor_binding.node_to_actor["n_npu_work"] == "act_npu_work"


def test_gate_a2_2_adaptive_proposer_selects_parallel_when_npu_saturated(
    canonical_contract, candidate_graphs, heterogeneous_actor_registry
):
    """Proposer shifts from G2 to G1 (parallel fork-join) when NPU load is saturated."""
    proposer = AdaptiveGraphProposer()

    # NPU saturated (load=0.98, latency=80ms)
    heterogeneous_actor_registry.update_status("act_npu_work", load=0.98, latency_ms=80.0)

    state = CompositionRuntimeState(
        actor_availability={"act_npu_work": True, "act_cpu_work_1": True, "act_cpu_work_2": True},
        actor_loads={"act_npu_work": 0.98, "act_cpu_work_1": 0.1, "act_cpu_work_2": 0.1},
        actor_latencies={"act_npu_work": 80.0, "act_cpu_work_1": 2.0, "act_cpu_work_2": 2.0},
        actor_failure_counts={"act_npu_work": 0, "act_cpu_work_1": 0, "act_cpu_work_2": 0},
        active_graph_id="G2_accelerator",
    )

    prop = proposer.propose_realization(
        state=state,
        contract=canonical_contract,
        candidate_graphs=candidate_graphs,
        registry=heterogeneous_actor_registry,
        current_graph_hash="current_hash",
    )
    assert prop is not None
    assert prop.candidate_graph.graph_id == "G1_parallel"
    assert prop.strategy == SubstitutionStrategy.PARALLEL_DECOMPOSITION
    assert prop.actor_binding is not None


# -----------------------------------------------------------------------------
# 4. Online Policy Learning & Weight Adaptation
# -----------------------------------------------------------------------------

def test_gate_a2_2_adaptive_proposer_online_learning_and_lineage():
    """Online feedback adapts proposer weights and updates model lineage artifact hash."""
    proposer = AdaptiveGraphProposer()
    gen0_hash = proposer.model_artifact_hash
    initial_npu_weight = proposer.weights["w_npu_affinity"]

    # 1. Reinforce on successful NPU execution
    obs_success = GraphAdaptationObservation(
        observation_id="obs_001",
        parent_contract_id="contract_01",
        state_snapshot_hash="state_hash",
        proposed_graph_id="G2_accelerator",
        proposed_strategy=SubstitutionStrategy.ACCELERATOR_OFFLOAD.value,
        certification_outcome="ACCEPTED",
        execution_status="SUCCESS",
        observed_latency_ms=15.0,
    )
    proposer.adapt(obs_success)
    assert proposer.generation == 1
    assert proposer.weights["w_npu_affinity"] > initial_npu_weight
    assert proposer.model_artifact_hash != gen0_hash

    # 2. Penalize on rejection
    obs_reject = GraphAdaptationObservation(
        observation_id="obs_002",
        parent_contract_id="contract_01",
        state_snapshot_hash="state_hash",
        proposed_graph_id="G2_accelerator",
        proposed_strategy=SubstitutionStrategy.ACCELERATOR_OFFLOAD.value,
        certification_outcome="REJECTED",
        execution_status="NOT_EXECUTED",
        violations=("A_AUTHORITY_ROLE_MISSING",),
    )
    gen1_npu_weight = proposer.weights["w_npu_affinity"]
    proposer.adapt(obs_reject)
    assert proposer.generation == 2
    assert proposer.weights["w_npu_affinity"] < gen1_npu_weight


# -----------------------------------------------------------------------------
# 5. Full End-to-End Closed Loop Runtime Execution
# -----------------------------------------------------------------------------

def test_gate_a2_2_runtime_end_to_end_adaptive_selection_and_execution(
    canonical_contract, candidate_graphs, heterogeneous_actor_registry
):
    """End-to-end: runtime obtains proposal with binding, certifies it, and executes on assigned actors."""
    g0, g1, g2 = candidate_graphs

    base_binding = ActorBinding(
        binding_id="bind_base_g0",
        graph_id=g0.graph_id,
        node_to_actor={
            "n_parse": "act_cpu_parse",
            "n_work_a": "act_cpu_work_1",
            "n_verify": "act_verifier",
            "n_commit": "act_commit",
        },
    )

    runtime = AdaptiveCompositionRuntime(
        contract=canonical_contract,
        baseline_graph=g0,
        registry=heterogeneous_actor_registry,
        baseline_binding=base_binding,
    )

    # Runtime state vector
    state = runtime.get_runtime_state()
    proposer = AdaptiveGraphProposer()

    # Generate proposal
    prop = proposer.propose_realization(
        state=state,
        contract=canonical_contract,
        candidate_graphs=candidate_graphs,
        registry=heterogeneous_actor_registry,
        current_graph_hash=runtime.current_graph_hash,
    )
    assert prop is not None
    assert prop.candidate_graph.graph_id == "G2_accelerator"

    # Runtime certifies and atomically swaps graph and binding
    cert = runtime.propose_and_certify(prop)
    assert cert.is_accepted
    assert runtime.current_graph_hash == g2.compute_hash()
    assert runtime.active_binding.node_to_actor["n_npu_work"] == "act_npu_work"

    # Execute
    rec = runtime.execute({"input_data": "sample_batch"})
    assert rec.status == "SUCCESS"
    assert "certified_result_R" in rec.final_outputs

    # Verify executing actor logged in node results
    npu_node_result = [r for r in rec.node_results if r.node_id == "n_npu_work"][0]
    assert npu_node_result.actor_id == "act_npu_work"
    assert npu_node_result.status == "COMPLETED"


# -----------------------------------------------------------------------------
# 6. Formal Claim Evaluations
# -----------------------------------------------------------------------------

def test_gate_a2_2_qualification_claim_actor_binding(
    canonical_contract, candidate_graphs, heterogeneous_actor_registry
):
    """Qualifies Claim A2.ACTOR_BINDING.PORTABLE."""
    g0, _, _ = candidate_graphs
    spec = get_claim("A2.ACTOR_BINDING.PORTABLE")

    valid_binding = ActorBinding(
        "b_val",
        g0.graph_id,
        {"n_parse": "act_cpu_parse", "n_work_a": "act_cpu_work_1", "n_verify": "act_verifier", "n_commit": "act_commit"},
    )
    is_valid, _ = validate_binding(g0, valid_binding, heterogeneous_actor_registry)

    # Negative control: missing capability
    bad_binding = ActorBinding(
        "b_bad",
        g0.graph_id,
        {"n_parse": "act_cpu_parse", "n_work_a": "act_cpu_work_1", "n_verify": "act_cpu_work_2", "n_commit": "act_commit"},
    )
    is_bad_valid, _ = validate_binding(g0, bad_binding, heterogeneous_actor_registry)

    positive_pass = is_valid
    negative_pass = not is_bad_valid

    claim_res = evaluate_claim(
        observed_pass=(positive_pass and negative_pass),
        negative_control_pass=negative_pass,
        context=EvidenceContext(
            level=EvidenceLevel.PORTABLE,
            source="tests.test_composition_adaptive_proposer",
            actual_components={"binding": "ActorBinding", "registry": "ActorRegistry"},
            substitutions={},
        ),
        requirement=ClaimRequirement(spec.required_level, spec.required_components),
    )
    assert claim_res["qualified"]
    assert claim_res["passed"]


def test_gate_a2_2_qualification_claim_adaptive_proposer(
    canonical_contract, candidate_graphs, heterogeneous_actor_registry
):
    """Qualifies Claim A2.ADAPTIVE_PROPOSER.PORTABLE."""
    spec = get_claim("A2.ADAPTIVE_PROPOSER.PORTABLE")
    proposer = AdaptiveGraphProposer()

    # Condition 1: NPU available
    state1 = CompositionRuntimeState(
        {"act_npu_work": True, "act_cpu_work_1": True, "act_cpu_work_2": True},
        {"act_npu_work": 0.1, "act_cpu_work_1": 0.2, "act_cpu_work_2": 0.2},
        {"act_npu_work": 1.0, "act_cpu_work_1": 5.0, "act_cpu_work_2": 5.0},
        {"act_npu_work": 0, "act_cpu_work_1": 0, "act_cpu_work_2": 0},
        "G0_sequential",
    )
    p1 = proposer.propose_realization(state1, canonical_contract, candidate_graphs, heterogeneous_actor_registry, "curr_hash")

    # Condition 2: NPU offline -> shifts to parallel CPU
    heterogeneous_actor_registry.update_status("act_npu_work", availability=False)
    state2 = CompositionRuntimeState(
        {"act_npu_work": False, "act_cpu_work_1": True, "act_cpu_work_2": True},
        {"act_npu_work": 1.0, "act_cpu_work_1": 0.1, "act_cpu_work_2": 0.1},
        {"act_npu_work": 999.0, "act_cpu_work_1": 2.0, "act_cpu_work_2": 2.0},
        {"act_npu_work": 1, "act_cpu_work_1": 0, "act_cpu_work_2": 0},
        "G0_sequential",
    )
    p2 = proposer.propose_realization(state2, canonical_contract, candidate_graphs, heterogeneous_actor_registry, "curr_hash")

    positive_pass = (
        p1 is not None and p1.candidate_graph.graph_id == "G2_accelerator"
        and p2 is not None and p2.candidate_graph.graph_id == "G1_parallel"
    )

    # Negative control: wrong substitution blocked
    certifier = CompositionCertifier()
    g0, _, _ = candidate_graphs
    forged_prop = GraphReplacementProposal(
        parent_contract_id="wrong_contract",
        current_graph_hash="curr_hash",
        candidate_graph=g0,
        strategy=SubstitutionStrategy.FALLBACK_BASELINE,
    )
    cert = certifier.certify_proposal(forged_prop, g0, canonical_contract, 1, heterogeneous_actor_registry)
    negative_pass = not cert.is_accepted

    claim_res = evaluate_claim(
        observed_pass=(positive_pass and negative_pass),
        negative_control_pass=negative_pass,
        context=EvidenceContext(
            level=EvidenceLevel.PORTABLE,
            source="tests.test_composition_adaptive_proposer",
            actual_components={"proposer": "AdaptiveGraphProposer", "certifier": "CompositionCertifier"},
            substitutions={},
        ),
        requirement=ClaimRequirement(spec.required_level, spec.required_components),
    )
    assert claim_res["qualified"]
    assert claim_res["passed"]
