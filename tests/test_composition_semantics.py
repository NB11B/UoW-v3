"""Qualification tests for Gate A2.0: Realization Semantics & Semantic Projection Phi(G, U)."""
from __future__ import annotations

import pytest

from uow import (
    AuthorityObligation,
    CausalConstraint,
    EvidenceObligation,
    FailureSemantics,
    ParentContract,
    RealizationGraph,
    RealizationNode,
    ResourceConstraint,
    SemanticProjection,
    TemporalConstraint,
    are_equivalent,
    check_conformance,
    project_semantics,
)
from qualification.claim_registry import get_claim
from qualification.evidence import (
    ClaimRequirement,
    EvidenceContext,
    EvidenceLevel,
    evaluate_claim,
)


@pytest.fixture
def canonical_parent_contract() -> ParentContract:
    """Canonical Parent Contract U defining:

    'Produce certified result R from input X before deadline D using authorized
    actors with complete evidence lineage and rollback failure semantics.'
    """
    return ParentContract(
        contract_id="parent_certified_transform_v1",
        description="Transform input X into certified output R with immutable evidence and strict causal verification.",
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


def test_gate_a2_0_parent_contract_hash_determinism(canonical_parent_contract):
    """ParentContract generates an unforgeable canonical SHA-256 digest over (O, D, A, E, T, R, F)."""
    assert len(canonical_parent_contract.contract_hash) == 64
    # Re-creating an identical contract produces the exact same hash
    identical = ParentContract(
        contract_id="parent_certified_transform_v1",
        description="Transform input X into certified output R with immutable evidence and strict causal verification.",
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
    assert identical.contract_hash == canonical_parent_contract.contract_hash


def test_gate_a2_0_four_alternate_topologies_satisfy_parent_contract(canonical_parent_contract):
    """Validates that 4 structurally distinct realization graphs satisfy Phi(G_i, U) = Phi(U).

    G0: Sequential (CPU Parser -> Worker A -> Verifier -> Commit)
    G1: Parallel (CPU Parser -> [Worker A, Worker B] -> Resolver -> Verifier -> Commit)
    G2: Accelerator (CPU Parser -> NPU Worker -> Verifier -> Commit)
    G3: Distributed Quorum (CPU Parser -> Remote Worker -> 2-of-3 Quorum Authority -> Commit)
    """
    U = canonical_parent_contract

    # -------------------------------------------------------------------------
    # Graph 0 — Sequential
    # -------------------------------------------------------------------------
    nodes_g0 = {
        "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
        "n_work_a": RealizationNode("n_work_a", role="worker", actor_class="cpu", duration_ms=80.0),
        "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
        "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
    }
    edges_g0 = (
        ("n_parse", "n_work_a"),
        ("n_work_a", "n_verify"),
        ("n_verify", "n_commit"),
    )
    g0 = RealizationGraph("G0_sequential", nodes_g0, edges_g0)

    # -------------------------------------------------------------------------
    # Graph 1 — Parallel
    # -------------------------------------------------------------------------
    nodes_g1 = {
        "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
        "n_work_a": RealizationNode("n_work_a", role="worker", actor_class="cpu", duration_ms=50.0),
        "n_work_b": RealizationNode("n_work_b", role="worker", actor_class="cpu", duration_ms=50.0),
        "n_resolver": RealizationNode("n_resolver", role="worker", actor_class="cpu", duration_ms=20.0),
        "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
        "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
    }
    edges_g1 = (
        ("n_parse", "n_work_a"),
        ("n_parse", "n_work_b"),
        ("n_work_a", "n_resolver"),
        ("n_work_b", "n_resolver"),
        ("n_resolver", "n_verify"),
        ("n_verify", "n_commit"),
    )
    g1 = RealizationGraph("G1_parallel", nodes_g1, edges_g1)

    # -------------------------------------------------------------------------
    # Graph 2 — Accelerator (NPU)
    # -------------------------------------------------------------------------
    nodes_g2 = {
        "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
        "n_npu_work": RealizationNode("n_npu_work", role="worker", actor_class="npu", npu_slots=1, duration_ms=15.0),
        "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
        "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
    }
    edges_g2 = (
        ("n_parse", "n_npu_work"),
        ("n_npu_work", "n_verify"),
        ("n_verify", "n_commit"),
    )
    g2 = RealizationGraph("G2_accelerator", nodes_g2, edges_g2)

    # -------------------------------------------------------------------------
    # Graph 3 — Distributed Quorum
    # -------------------------------------------------------------------------
    nodes_g3 = {
        "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
        "n_remote_work": RealizationNode("n_remote_work", role="worker", actor_class="remote", duration_ms=120.0),
        "n_quorum_auth": RealizationNode("n_quorum_auth", role="verifier", actor_class="physical_esp32", authority_tier="authority_quorum", duration_ms=40.0),
        "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
    }
    edges_g3 = (
        ("n_parse", "n_remote_work"),
        ("n_remote_work", "n_quorum_auth"),
        ("n_quorum_auth", "n_commit"),
    )
    g3 = RealizationGraph("G3_distributed", nodes_g3, edges_g3)

    # 1. All graphs individually conform: G_i |= U
    assert check_conformance(g0, U)
    assert check_conformance(g1, U)
    assert check_conformance(g2, U)
    assert check_conformance(g3, U)

    # 2. All 4 graphs project to the EXACT same semantic projection under U!
    assert are_equivalent(g0, g1, U)
    assert are_equivalent(g0, g2, U)
    assert are_equivalent(g0, g3, U)
    assert are_equivalent(g1, g2, U)
    assert are_equivalent(g2, g3, U)

    proj0 = project_semantics(g0, U)
    proj2 = project_semantics(g2, U)
    assert proj0.projection_hash == proj2.projection_hash
    assert proj0.conforms and proj2.conforms


def test_gate_a2_0_negative_control_authority_bypassed(canonical_parent_contract):
    """Negative Control: Graph omitting authority role (Worker -> Commit) is strictly rejected."""
    U = canonical_parent_contract
    nodes = {
        "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu"),
        "n_work": RealizationNode("n_work", role="worker", actor_class="cpu"),
        "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",)),
    }
    edges = (
        ("n_parse", "n_work"),
        ("n_work", "n_commit"),  # Bypasses required 'verifier' role!
    )
    g_bad = RealizationGraph("G_authority_bypass", nodes, edges)

    proj = project_semantics(g_bad, U)
    assert not proj.conforms
    assert not proj.authority_satisfied
    assert any("A_AUTHORITY_ROLE_MISSING" in v for v in proj.violations)


def test_gate_a2_0_negative_control_evidence_provenance_missing(canonical_parent_contract):
    """Negative Control: Graph omitting cryptographic provenance is rejected despite valid output."""
    U = canonical_parent_contract
    nodes = {
        "n_parse": RealizationNode("n_parse", role="parser", generates_provenance=True),
        "n_work": RealizationNode("n_work", role="worker", generates_provenance=False),  # Missing provenance!
        "n_verify": RealizationNode("n_verify", role="verifier", authority_tier="verifier", generates_provenance=True),
        "n_commit": RealizationNode("n_commit", role="commit", outputs=("certified_result_R",), generates_provenance=True),
    }
    edges = (
        ("n_parse", "n_work"),
        ("n_work", "n_verify"),
        ("n_verify", "n_commit"),
    )
    g_bad = RealizationGraph("G_evidence_missing", nodes, edges)

    proj = project_semantics(g_bad, U)
    assert not proj.conforms
    assert not proj.evidence_satisfied
    assert any("E_PROVENANCE_MISSING" in v for v in proj.violations)


def test_gate_a2_0_negative_control_causal_order_inverted():
    """Negative Control: Causal inversion (Payment -> Approval) is rejected despite correct database state."""
    contract = ParentContract(
        contract_id="financial_settlement_v1",
        description="Requires Approval before Payment",
        required_outputs=("settled",),
        causal_constraints=(
            CausalConstraint("approval", "payment"),
        ),
        authority=AuthorityObligation(required_role="approval", min_evidence_level="portable"),
    )

    # Inverted causality: Payment -> Approval
    nodes = {
        "n_pay": RealizationNode("n_pay", role="payment", outputs=("settled",)),
        "n_app": RealizationNode("n_app", role="approval", authority_tier="verifier"),
    }
    edges = (
        ("n_pay", "n_app"),  # Inverted!
    )
    g_inverted = RealizationGraph("G_inverted", nodes, edges)

    proj = project_semantics(g_inverted, contract)
    assert not proj.conforms
    assert not proj.causal_satisfied
    assert any("D_CAUSAL_ORDER_VIOLATION" in v for v in proj.violations)


def test_gate_a2_0_negative_control_failure_semantics_mismatch(canonical_parent_contract):
    """Negative Control: Node implementing PARTIAL_COMMIT under ROLLBACK contract is rejected."""
    U = canonical_parent_contract
    nodes = {
        "n_parse": RealizationNode("n_parse", role="parser"),
        "n_work": RealizationNode("n_work", role="worker", failure_mode="PARTIAL_COMMIT"),  # Illegal failure mode!
        "n_verify": RealizationNode("n_verify", role="verifier", authority_tier="verifier"),
        "n_commit": RealizationNode("n_commit", role="commit", outputs=("certified_result_R",)),
    }
    edges = (
        ("n_parse", "n_work"),
        ("n_work", "n_verify"),
        ("n_verify", "n_commit"),
    )
    g_bad = RealizationGraph("G_partial_commit", nodes, edges)

    proj = project_semantics(g_bad, U)
    assert not proj.conforms
    assert not proj.failure_satisfied
    assert any("F_FAILURE_SEMANTICS_MISMATCH" in v for v in proj.violations)


def test_gate_a2_0_negative_control_budget_and_deadline_exceeded(canonical_parent_contract):
    """Negative Control: Graphs exceeding temporal deadline or GPU capacity limits are rejected."""
    U = canonical_parent_contract

    # 1. Temporal violation (>1000ms deadline)
    nodes_slow = {
        "n_parse": RealizationNode("n_parse", role="parser", duration_ms=20.0),
        "n_work": RealizationNode("n_work", role="worker", duration_ms=1200.0),  # Exceeds 1000ms max!
        "n_verify": RealizationNode("n_verify", role="verifier", authority_tier="verifier", duration_ms=30.0),
        "n_commit": RealizationNode("n_commit", role="commit", outputs=("certified_result_R",), duration_ms=10.0),
    }
    edges = (("n_parse", "n_work"), ("n_work", "n_verify"), ("n_verify", "n_commit"))
    g_slow = RealizationGraph("G_slow", nodes_slow, edges)
    proj_slow = project_semantics(g_slow, U)
    assert not proj_slow.conforms
    assert not proj_slow.temporal_satisfied
    assert any("T_DEADLINE_EXCEEDED" in v for v in proj_slow.violations)

    # 2. Resource violation (3 GPUs requested when budget is 2)
    nodes_gpu = {
        "n_parse": RealizationNode("n_parse", role="parser"),
        "n_work": RealizationNode("n_work", role="worker", gpu_slots=3),  # Exceeds max 2 GPU slots!
        "n_verify": RealizationNode("n_verify", role="verifier", authority_tier="verifier"),
        "n_commit": RealizationNode("n_commit", role="commit", outputs=("certified_result_R",)),
    }
    g_gpu = RealizationGraph("G_gpu_excess", nodes_gpu, edges)
    proj_gpu = project_semantics(g_gpu, U)
    assert not proj_gpu.conforms
    assert not proj_gpu.resource_satisfied
    assert any("R_GPU_EXCEEDED" in v for v in proj_gpu.violations)


def test_gate_a2_0_claim_qualification_evaluation(canonical_parent_contract):
    """Formally evaluates and qualifies Claim A2.SEMANTIC_PROJECTION.PORTABLE."""
    U = canonical_parent_contract
    nodes = {
        "n_parse": RealizationNode("n_parse", role="parser"),
        "n_work": RealizationNode("n_work", role="worker"),
        "n_verify": RealizationNode("n_verify", role="verifier", authority_tier="verifier"),
        "n_commit": RealizationNode("n_commit", role="commit", outputs=("certified_result_R",)),
    }
    edges = (("n_parse", "n_work"), ("n_work", "n_verify"), ("n_verify", "n_commit"))
    g = RealizationGraph("G_claim_eval", nodes, edges)

    proj = project_semantics(g, U)
    assert proj.conforms

    claim_spec = get_claim("A2.SEMANTIC_PROJECTION.PORTABLE")
    claim_res = evaluate_claim(
        observed_pass=proj.conforms,
        context=EvidenceContext(
            level=EvidenceLevel.PORTABLE,
            source="tests.test_composition_semantics",
            actual_components={"projection": "SemanticProjection", "contract": "ParentContract"},
            substitutions={},
        ),
        requirement=ClaimRequirement(claim_spec.required_level, claim_spec.required_components),
    )
    assert claim_res["qualified"]
    assert claim_res["passed"]
