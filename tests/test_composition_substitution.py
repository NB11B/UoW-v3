"""Qualification tests for Gate A2.1: Graph Substitution & Runtime Certification."""
from __future__ import annotations

import pytest

from uow.compat.v2 import (
    AdaptiveCompositionRuntime,
    AuthorityObligation,
    CausalConstraint,
    CompositionCertifier,
    EvidenceObligation,
    ExecutionRecord,
    FailureSemantics,
    GraphReplacementCertificate,
    GraphReplacementProposal,
    ParentContract,
    RealizationGraph,
    RealizationNode,
    ResourceConstraint,
    SubstitutionDecision,
    SubstitutionStrategy,
    TemporalConstraint,
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
    """Canonical Parent Contract U defining required outputs and invariant constraints."""
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
def graph_g0_sequential() -> RealizationGraph:
    """G0: Sequential baseline realization."""
    nodes = {
        "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
        "n_work_a": RealizationNode("n_work_a", role="worker", actor_class="cpu", duration_ms=80.0),
        "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
        "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
    }
    edges = (
        ("n_parse", "n_work_a"),
        ("n_work_a", "n_verify"),
        ("n_verify", "n_commit"),
    )
    return RealizationGraph("G0_sequential", nodes, edges)


@pytest.fixture
def graph_g1_parallel() -> RealizationGraph:
    """G1: Fork-join parallel realization."""
    nodes = {
        "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
        "n_work_a": RealizationNode("n_work_a", role="worker", actor_class="cpu", duration_ms=50.0),
        "n_work_b": RealizationNode("n_work_b", role="worker", actor_class="cpu", duration_ms=50.0),
        "n_resolver": RealizationNode("n_resolver", role="worker", actor_class="cpu", duration_ms=20.0),
        "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
        "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
    }
    edges = (
        ("n_parse", "n_work_a"),
        ("n_parse", "n_work_b"),
        ("n_work_a", "n_resolver"),
        ("n_work_b", "n_resolver"),
        ("n_resolver", "n_verify"),
        ("n_verify", "n_commit"),
    )
    return RealizationGraph("G1_parallel", nodes, edges)


@pytest.fixture
def graph_g2_accelerator() -> RealizationGraph:
    """G2: Accelerator offload realization (NPU worker)."""
    nodes = {
        "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
        "n_npu_work": RealizationNode("n_npu_work", role="worker", actor_class="npu", npu_slots=1, duration_ms=15.0),
        "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
        "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
    }
    edges = (
        ("n_parse", "n_npu_work"),
        ("n_npu_work", "n_verify"),
        ("n_verify", "n_commit"),
    )
    return RealizationGraph("G2_accelerator", nodes, edges)


@pytest.fixture
def graph_g3_distributed() -> RealizationGraph:
    """G3: Distributed quorum realization."""
    nodes = {
        "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
        "n_remote_work": RealizationNode("n_remote_work", role="worker", actor_class="remote", duration_ms=120.0),
        "n_quorum_auth": RealizationNode("n_quorum_auth", role="verifier", actor_class="physical_esp32", authority_tier="authority_quorum", duration_ms=40.0),
        "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
    }
    edges = (
        ("n_parse", "n_remote_work"),
        ("n_remote_work", "n_quorum_auth"),
        ("n_quorum_auth", "n_commit"),
    )
    return RealizationGraph("G3_distributed", nodes, edges)


# -----------------------------------------------------------------------------
# 1. Hashing Determinism Tests
# -----------------------------------------------------------------------------

def test_gate_a2_1_proposal_hash_determinism(canonical_contract, graph_g0_sequential, graph_g1_parallel):
    """Proposal hash is deterministically computable and sensitive to changes."""
    prop1 = GraphReplacementProposal(
        parent_contract_id=canonical_contract.contract_id,
        current_graph_hash=graph_g0_sequential.compute_hash(),
        candidate_graph=graph_g1_parallel,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        predicted_speedup=1.08,
        rationale="Decompose sequential worker into fork-join parallel workers",
        proposal_id="prop_001",
    )
    h1 = prop1.compute_hash()
    assert len(h1) == 64

    # Identical proposal produces identical hash
    prop1_clone = GraphReplacementProposal(
        parent_contract_id=canonical_contract.contract_id,
        current_graph_hash=graph_g0_sequential.compute_hash(),
        candidate_graph=graph_g1_parallel,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        predicted_speedup=1.08,
        rationale="Decompose sequential worker into fork-join parallel workers",
        proposal_id="prop_001",
    )
    assert prop1_clone.compute_hash() == h1

    # Altering speedup changes hash
    prop2 = GraphReplacementProposal(
        parent_contract_id=canonical_contract.contract_id,
        current_graph_hash=graph_g0_sequential.compute_hash(),
        candidate_graph=graph_g1_parallel,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        predicted_speedup=1.50,
        rationale="Decompose sequential worker into fork-join parallel workers",
        proposal_id="prop_001",
    )
    assert prop2.compute_hash() != h1


def test_gate_a2_1_certificate_hash_determinism(canonical_contract, graph_g0_sequential, graph_g1_parallel):
    """Certificate hash is deterministically computable and sensitive to decisions."""
    cert1 = GraphReplacementCertificate(
        certificate_id="cert_001",
        proposal_hash="a" * 64,
        parent_contract_hash=canonical_contract.contract_hash,
        original_graph_hash=graph_g0_sequential.compute_hash(),
        candidate_graph_hash=graph_g1_parallel.compute_hash(),
        projection_hash="b" * 64,
        decision=SubstitutionDecision.ACCEPTED,
        violations=(),
        epoch=1,
    )
    h1 = cert1.compute_hash()
    assert len(h1) == 64

    # Rejection changes hash
    cert2 = GraphReplacementCertificate(
        certificate_id="cert_001",
        proposal_hash="a" * 64,
        parent_contract_hash=canonical_contract.contract_hash,
        original_graph_hash=graph_g0_sequential.compute_hash(),
        candidate_graph_hash=graph_g1_parallel.compute_hash(),
        projection_hash="b" * 64,
        decision=SubstitutionDecision.REJECTED,
        violations=("SOME_VIOLATION",),
        epoch=1,
    )
    assert cert2.compute_hash() != h1


# -----------------------------------------------------------------------------
# 2. Composition Certifier Evaluation Tests
# -----------------------------------------------------------------------------

def test_gate_a2_1_certifier_accepts_valid_parallel_substitution(
    canonical_contract, graph_g0_sequential, graph_g1_parallel
):
    """Certifier issues ACCEPTED certificate for valid parallel graph substitution."""
    certifier = CompositionCertifier()
    proposal = GraphReplacementProposal(
        parent_contract_id=canonical_contract.contract_id,
        current_graph_hash=graph_g0_sequential.compute_hash(),
        candidate_graph=graph_g1_parallel,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        predicted_speedup=1.08,
        rationale="Fork-join parallel decomposition",
        proposal_id="p_parallel_01",
    )

    cert = certifier.certify_proposal(proposal, graph_g0_sequential, canonical_contract, current_epoch=1)
    assert cert.is_accepted
    assert cert.decision == SubstitutionDecision.ACCEPTED
    assert len(cert.violations) == 0
    assert cert.original_graph_hash == graph_g0_sequential.compute_hash()
    assert cert.candidate_graph_hash == graph_g1_parallel.compute_hash()
    assert len(cert.projection_hash) == 64


def test_gate_a2_1_certifier_accepts_accelerator_substitution(
    canonical_contract, graph_g0_sequential, graph_g2_accelerator
):
    """Certifier issues ACCEPTED certificate for accelerator offload substitution."""
    certifier = CompositionCertifier()
    proposal = GraphReplacementProposal(
        parent_contract_id=canonical_contract.contract_id,
        current_graph_hash=graph_g0_sequential.compute_hash(),
        candidate_graph=graph_g2_accelerator,
        strategy=SubstitutionStrategy.ACCELERATOR_OFFLOAD,
        predicted_speedup=1.87,
        rationale="Intel NPU accelerator offload",
        proposal_id="p_npu_01",
    )

    cert = certifier.certify_proposal(proposal, graph_g0_sequential, canonical_contract, current_epoch=2)
    assert cert.is_accepted
    assert cert.decision == SubstitutionDecision.ACCEPTED
    assert len(cert.violations) == 0
    assert cert.candidate_graph_hash == graph_g2_accelerator.compute_hash()


def test_gate_a2_1_certifier_accepts_distributed_quorum_substitution(
    canonical_contract, graph_g0_sequential, graph_g3_distributed
):
    """Certifier issues ACCEPTED certificate for distributed quorum substitution."""
    certifier = CompositionCertifier()
    proposal = GraphReplacementProposal(
        parent_contract_id=canonical_contract.contract_id,
        current_graph_hash=graph_g0_sequential.compute_hash(),
        candidate_graph=graph_g3_distributed,
        strategy=SubstitutionStrategy.DISTRIBUTED_QUORUM,
        predicted_speedup=0.74,
        rationale="Distributed 2-of-3 quorum verification",
        proposal_id="p_dist_01",
    )

    cert = certifier.certify_proposal(proposal, graph_g0_sequential, canonical_contract, current_epoch=3)
    assert cert.is_accepted
    assert cert.decision == SubstitutionDecision.ACCEPTED
    assert len(cert.violations) == 0


# -----------------------------------------------------------------------------
# 3. Adversarial Falsification & Negative Controls
# -----------------------------------------------------------------------------

def test_gate_a2_1_falsification_stale_current_graph_hash_rejection(
    canonical_contract, graph_g0_sequential, graph_g1_parallel
):
    """Proposal citing an out-of-date or forged current graph hash is strictly rejected."""
    certifier = CompositionCertifier()
    proposal = GraphReplacementProposal(
        parent_contract_id=canonical_contract.contract_id,
        current_graph_hash="0" * 64,  # Stale / wrong active graph hash
        candidate_graph=graph_g1_parallel,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        proposal_id="p_stale_01",
    )

    cert = certifier.certify_proposal(proposal, graph_g0_sequential, canonical_contract, current_epoch=1)
    assert not cert.is_accepted
    assert cert.decision == SubstitutionDecision.REJECTED
    assert any("STALE_CURRENT_GRAPH_HASH" in v for v in cert.violations)


def test_gate_a2_1_falsification_contract_id_mismatch_rejection(
    canonical_contract, graph_g0_sequential, graph_g1_parallel
):
    """Proposal targeting a different parent contract is strictly rejected."""
    certifier = CompositionCertifier()
    proposal = GraphReplacementProposal(
        parent_contract_id="other_foreign_contract_v99",
        current_graph_hash=graph_g0_sequential.compute_hash(),
        candidate_graph=graph_g1_parallel,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        proposal_id="p_mismatch_01",
    )

    cert = certifier.certify_proposal(proposal, graph_g0_sequential, canonical_contract, current_epoch=1)
    assert not cert.is_accepted
    assert cert.decision == SubstitutionDecision.REJECTED
    assert any("CONTRACT_ID_MISMATCH" in v for v in cert.violations)


def test_gate_a2_1_falsification_cyclic_candidate_rejection(
    canonical_contract, graph_g0_sequential
):
    """Candidate graph containing a dependency cycle is strictly rejected."""
    nodes = {
        "n_a": RealizationNode("n_a", role="worker"),
        "n_b": RealizationNode("n_b", role="worker"),
    }
    # Direct cycle: n_a -> n_b -> n_a
    edges = (("n_a", "n_b"), ("n_b", "n_a"))
    cyclic_graph = RealizationGraph("G_cyclic", nodes, edges, allow_cycle=True)

    certifier = CompositionCertifier()
    proposal = GraphReplacementProposal(
        parent_contract_id=canonical_contract.contract_id,
        current_graph_hash=graph_g0_sequential.compute_hash(),
        candidate_graph=cyclic_graph,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        proposal_id="p_cyclic_01",
    )

    cert = certifier.certify_proposal(proposal, graph_g0_sequential, canonical_contract, current_epoch=1)
    assert not cert.is_accepted
    assert cert.decision == SubstitutionDecision.REJECTED
    assert "CANDIDATE_GRAPH_CYCLIC" in cert.violations


def test_gate_a2_1_falsification_conformance_failure_rejection(
    canonical_contract, graph_g0_sequential
):
    """Candidate graph omitting authoritative verifier role is strictly rejected."""
    # Graph that bypasses verifier
    nodes = {
        "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu"),
        "n_work": RealizationNode("n_work", role="worker", actor_class="cpu"),
        "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",)),
    }
    edges = (("n_parse", "n_work"), ("n_work", "n_commit"))
    bypass_graph = RealizationGraph("G_bypass", nodes, edges)

    certifier = CompositionCertifier()
    proposal = GraphReplacementProposal(
        parent_contract_id=canonical_contract.contract_id,
        current_graph_hash=graph_g0_sequential.compute_hash(),
        candidate_graph=bypass_graph,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        proposal_id="p_bypass_01",
    )

    cert = certifier.certify_proposal(proposal, graph_g0_sequential, canonical_contract, current_epoch=1)
    assert not cert.is_accepted
    assert cert.decision == SubstitutionDecision.REJECTED
    assert any("A_AUTHORITY_ROLE_MISSING" in v for v in cert.violations)


# -----------------------------------------------------------------------------
# 4. Runtime Atomic State Transition & Fallback Tests
# -----------------------------------------------------------------------------

def test_gate_a2_1_runtime_atomic_graph_substitution(
    canonical_contract, graph_g0_sequential, graph_g1_parallel
):
    """Runtime updates active_graph only upon valid certificate; leaves active_graph untouched on rejection."""
    runtime = AdaptiveCompositionRuntime(
        contract=canonical_contract,
        baseline_graph=graph_g0_sequential,
    )
    assert runtime.current_graph_hash == graph_g0_sequential.compute_hash()

    # 1. Attempt invalid proposal (tampered current graph hash)
    bad_proposal = GraphReplacementProposal(
        parent_contract_id=canonical_contract.contract_id,
        current_graph_hash="wrong_hash" * 4,
        candidate_graph=graph_g1_parallel,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        proposal_id="p_bad_01",
    )
    cert_bad = runtime.propose_and_certify(bad_proposal)
    assert not cert_bad.is_accepted
    # Active graph remains strictly G0
    assert runtime.current_graph_hash == graph_g0_sequential.compute_hash()

    # 2. Submit valid proposal
    good_proposal = GraphReplacementProposal(
        parent_contract_id=canonical_contract.contract_id,
        current_graph_hash=runtime.current_graph_hash,
        candidate_graph=graph_g1_parallel,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        proposal_id="p_good_01",
    )
    cert_good = runtime.propose_and_certify(good_proposal)
    assert cert_good.is_accepted
    # Active graph atomically switched to G1
    assert runtime.current_graph_hash == graph_g1_parallel.compute_hash()


def test_gate_a2_1_runtime_execution_parity_across_certified_topologies(
    canonical_contract, graph_g0_sequential, graph_g1_parallel, graph_g2_accelerator
):
    """Runtime execution produces identical semantic outputs across G0, G1, and G2 topologies."""
    runtime = AdaptiveCompositionRuntime(
        contract=canonical_contract,
        baseline_graph=graph_g0_sequential,
    )
    input_payload = {"input_data_X": "sensor_telemetry_batch_001"}

    # Execute G0 (Sequential)
    rec0 = runtime.execute(input_payload)
    assert rec0.status == "SUCCESS"
    assert "certified_result_R" in rec0.final_outputs
    out0 = rec0.final_outputs["certified_result_R"]

    # Propose and switch to G1 (Parallel)
    prop_g1 = GraphReplacementProposal(
        parent_contract_id=canonical_contract.contract_id,
        current_graph_hash=runtime.current_graph_hash,
        candidate_graph=graph_g1_parallel,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        proposal_id="p_g1",
    )
    cert_g1 = runtime.propose_and_certify(prop_g1)
    assert cert_g1.is_accepted

    rec1 = runtime.execute(input_payload)
    assert rec1.status == "SUCCESS"
    assert "certified_result_R" in rec1.final_outputs
    assert rec1.final_outputs["certified_result_R"] == out0

    # Propose and switch to G2 (Accelerator)
    prop_g2 = GraphReplacementProposal(
        parent_contract_id=canonical_contract.contract_id,
        current_graph_hash=runtime.current_graph_hash,
        candidate_graph=graph_g2_accelerator,
        strategy=SubstitutionStrategy.ACCELERATOR_OFFLOAD,
        proposal_id="p_g2",
    )
    cert_g2 = runtime.propose_and_certify(prop_g2)
    assert cert_g2.is_accepted

    rec2 = runtime.execute(input_payload)
    assert rec2.status == "SUCCESS"
    assert "certified_result_R" in rec2.final_outputs
    assert rec2.final_outputs["certified_result_R"] == out0


def test_gate_a2_1_runtime_deterministic_fallback_on_injected_failure(
    canonical_contract, graph_g0_sequential, graph_g1_parallel
):
    """Injected execution failure in substituted graph triggers automatic rollback to baseline graph G0."""
    runtime = AdaptiveCompositionRuntime(
        contract=canonical_contract,
        baseline_graph=graph_g0_sequential,
    )

    # Transition to G1
    prop = GraphReplacementProposal(
        parent_contract_id=canonical_contract.contract_id,
        current_graph_hash=runtime.current_graph_hash,
        candidate_graph=graph_g1_parallel,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        proposal_id="p_to_g1",
    )
    cert = runtime.propose_and_certify(prop)
    assert cert.is_accepted
    assert runtime.current_graph_hash == graph_g1_parallel.compute_hash()

    # Execute with failure injected at node 'n_work_b'
    rec_fail = runtime.execute({"data": "payload"}, fail_node_id="n_work_b")
    assert rec_fail.status == "FAILED"
    assert "Injected execution failure at node n_work_b" in rec_fail.error_message

    # Verify runtime has automatically fallen back to baseline G0
    assert runtime.current_graph_hash == graph_g0_sequential.compute_hash()

    # Subsequent execution without error succeeds on baseline G0
    rec_recovery = runtime.execute({"data": "payload"})
    assert rec_recovery.status == "SUCCESS"
    assert "certified_result_R" in rec_recovery.final_outputs


# -----------------------------------------------------------------------------
# 5. Formal Qualification Claim Evaluation
# -----------------------------------------------------------------------------

def test_gate_a2_1_qualification_claim_portable(
    canonical_contract, graph_g0_sequential, graph_g1_parallel, graph_g2_accelerator
):
    """Validates registered claim A2.GRAPH_SUBSTITUTION.PORTABLE."""
    spec = get_claim("A2.GRAPH_SUBSTITUTION.PORTABLE")
    assert spec.required_level == EvidenceLevel.PORTABLE
    assert spec.requires_negative_control is True

    # 1. Evaluate runtime substitution positive passes
    runtime = AdaptiveCompositionRuntime(
        contract=canonical_contract,
        baseline_graph=graph_g0_sequential,
    )
    prop_g1 = GraphReplacementProposal(
        parent_contract_id=canonical_contract.contract_id,
        current_graph_hash=runtime.current_graph_hash,
        candidate_graph=graph_g1_parallel,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
    )
    cert1 = runtime.propose_and_certify(prop_g1)
    rec1 = runtime.execute({"test": 1})

    prop_g2 = GraphReplacementProposal(
        parent_contract_id=canonical_contract.contract_id,
        current_graph_hash=runtime.current_graph_hash,
        candidate_graph=graph_g2_accelerator,
        strategy=SubstitutionStrategy.ACCELERATOR_OFFLOAD,
    )
    cert2 = runtime.propose_and_certify(prop_g2)
    rec2 = runtime.execute({"test": 2})

    positive_pass = (
        cert1.is_accepted
        and rec1.status == "SUCCESS"
        and cert2.is_accepted
        and rec2.status == "SUCCESS"
        and rec1.final_outputs == rec2.final_outputs
    )

    # 2. Evaluate negative control (stale proposal rejection & fallback)
    prop_stale = GraphReplacementProposal(
        parent_contract_id=canonical_contract.contract_id,
        current_graph_hash="wrong_stale_hash",
        candidate_graph=graph_g0_sequential,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
    )
    cert_stale = runtime.propose_and_certify(prop_stale)
    negative_control_pass = (not cert_stale.is_accepted) and (runtime.current_graph_hash == graph_g2_accelerator.compute_hash())

    # Formally evaluate claim
    claim_res = evaluate_claim(
        observed_pass=(positive_pass and negative_control_pass),
        negative_control_pass=negative_control_pass,
        context=EvidenceContext(
            level=EvidenceLevel.PORTABLE,
            source="tests.test_composition_substitution",
            actual_components={"runtime": "AdaptiveCompositionRuntime", "certifier": "CompositionCertifier"},
            substitutions={},
        ),
        requirement=ClaimRequirement(spec.required_level, spec.required_components),
    )
    assert claim_res["qualified"]
    assert claim_res["passed"]
