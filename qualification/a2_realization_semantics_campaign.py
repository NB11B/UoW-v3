#!/usr/bin/env python3
"""
A2.0: Realization Semantics & Semantic Projection Qualification Campaign
========================================================================

Proves that:
1. The Parent Contract U defines WHAT must remain true across seven invariant classes:
   Phi(G, U) = (O, D, A, E, T, R, F).
2. Four structurally distinct execution graphs:
   - G0: Sequential (CPU Parser -> Worker A -> Verifier -> Commit)
   - G1: Parallel (CPU Parser -> [Worker A, Worker B] -> Resolver -> Verifier -> Commit)
   - G2: Accelerator (CPU Parser -> NPU Worker -> Verifier -> Commit)
   - G3: Distributed Quorum (CPU Parser -> Remote Worker -> 2-of-3 Quorum Authority -> Commit)
   all satisfy Phi(G_i, U) = Phi(U) and are mutually equivalent under U:
   G0 equiv_U G1 equiv_U G2 equiv_U G3.
3. Every deliberate violation of each projection dimension (authority bypass, missing provenance,
   causal inversion, failure mode mismatch, deadline breach, budget breach) is strictly rejected.
4. Formally registers and qualifies Claim A2.SEMANTIC_PROJECTION.PORTABLE.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict

from uow import (
    AuthorityObligation,
    CausalConstraint,
    EvidenceObligation,
    FailureSemantics,
    ParentContract,
    RealizationGraph,
    RealizationNode,
    ResourceConstraint,
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


def run_campaign(artifacts_dir: Path | None = None) -> Dict[str, Any]:
    print("=" * 80)
    print("GATE A2.0: REALIZATION SEMANTICS & SEMANTIC PROJECTION QUALIFICATION")
    print("=" * 80)

    if artifacts_dir is None:
        artifacts_dir = Path(__file__).resolve().parent / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # 1. Define Parent Contract U
    U = ParentContract(
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
    print(f"Parent Contract U: id={U.contract_id}, hash={U.contract_hash[:16]}...")

    # 2. Build 4 Alternate Realization Graphs
    g0 = RealizationGraph("G0_sequential", {
        "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
        "n_work_a": RealizationNode("n_work_a", role="worker", actor_class="cpu", duration_ms=80.0),
        "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
        "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
    }, (("n_parse", "n_work_a"), ("n_work_a", "n_verify"), ("n_verify", "n_commit")))

    g1 = RealizationGraph("G1_parallel", {
        "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
        "n_work_a": RealizationNode("n_work_a", role="worker", actor_class="cpu", duration_ms=50.0),
        "n_work_b": RealizationNode("n_work_b", role="worker", actor_class="cpu", duration_ms=50.0),
        "n_resolver": RealizationNode("n_resolver", role="worker", actor_class="cpu", duration_ms=20.0),
        "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
        "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
    }, (
        ("n_parse", "n_work_a"), ("n_parse", "n_work_b"),
        ("n_work_a", "n_resolver"), ("n_work_b", "n_resolver"),
        ("n_resolver", "n_verify"), ("n_verify", "n_commit")
    ))

    g2 = RealizationGraph("G2_accelerator", {
        "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
        "n_npu_work": RealizationNode("n_npu_work", role="worker", actor_class="npu", npu_slots=1, duration_ms=15.0),
        "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
        "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
    }, (("n_parse", "n_npu_work"), ("n_npu_work", "n_verify"), ("n_verify", "n_commit")))

    g3 = RealizationGraph("G3_distributed", {
        "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
        "n_remote_work": RealizationNode("n_remote_work", role="worker", actor_class="remote", duration_ms=120.0),
        "n_quorum_auth": RealizationNode("n_quorum_auth", role="verifier", actor_class="physical_esp32", authority_tier="authority_quorum", duration_ms=40.0),
        "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
    }, (("n_parse", "n_remote_work"), ("n_remote_work", "n_quorum_auth"), ("n_quorum_auth", "n_commit")))

    # Evaluate Projections
    p0 = project_semantics(g0, U)
    p1 = project_semantics(g1, U)
    p2 = project_semantics(g2, U)
    p3 = project_semantics(g3, U)

    assert p0.conforms and p1.conforms and p2.conforms and p3.conforms
    assert are_equivalent(g0, g1, U)
    assert are_equivalent(g0, g2, U)
    assert are_equivalent(g0, g3, U)
    print("PASS: 4 alternate realization graphs verified semantically equivalent under U.")

    # 3. Evaluate Negative Controls Matrix
    nc_results = {}

    # NC1: Authority bypass
    g_no_auth = RealizationGraph("NC1_no_auth", {
        "n_parse": RealizationNode("n_parse", role="parser"),
        "n_work": RealizationNode("n_work", role="worker"),
        "n_commit": RealizationNode("n_commit", role="commit", outputs=("certified_result_R",)),
    }, (("n_parse", "n_work"), ("n_work", "n_commit")))
    p_no_auth = project_semantics(g_no_auth, U)
    assert not p_no_auth.conforms and not p_no_auth.authority_satisfied
    nc_results["authority_bypass_rejected"] = True

    # NC2: Missing provenance
    g_no_prov = RealizationGraph("NC2_no_prov", {
        "n_parse": RealizationNode("n_parse", role="parser"),
        "n_work": RealizationNode("n_work", role="worker", generates_provenance=False),
        "n_verify": RealizationNode("n_verify", role="verifier", authority_tier="verifier"),
        "n_commit": RealizationNode("n_commit", role="commit", outputs=("certified_result_R",)),
    }, (("n_parse", "n_work"), ("n_work", "n_verify"), ("n_verify", "n_commit")))
    p_no_prov = project_semantics(g_no_prov, U)
    assert not p_no_prov.conforms and not p_no_prov.evidence_satisfied
    nc_results["missing_provenance_rejected"] = True

    # NC3: Causal inversion
    contract_causal = ParentContract(
        contract_id="contract_approval_v1",
        description="Requires Approval before Payment",
        required_outputs=("settled",),
        causal_constraints=(CausalConstraint("approval", "payment"),),
        authority=AuthorityObligation(required_role="approval"),
    )
    g_inverted = RealizationGraph("NC3_inverted", {
        "n_pay": RealizationNode("n_pay", role="payment", outputs=("settled",)),
        "n_app": RealizationNode("n_app", role="approval", authority_tier="verifier"),
    }, (("n_pay", "n_app"),))
    p_inverted = project_semantics(g_inverted, contract_causal)
    assert not p_inverted.conforms and not p_inverted.causal_satisfied
    nc_results["causal_inversion_rejected"] = True

    # NC4: Failure mode mismatch
    g_part_commit = RealizationGraph("NC4_partial_commit", {
        "n_parse": RealizationNode("n_parse", role="parser"),
        "n_work": RealizationNode("n_work", role="worker", failure_mode="PARTIAL_COMMIT"),
        "n_verify": RealizationNode("n_verify", role="verifier", authority_tier="verifier"),
        "n_commit": RealizationNode("n_commit", role="commit", outputs=("certified_result_R",)),
    }, (("n_parse", "n_work"), ("n_work", "n_verify"), ("n_verify", "n_commit")))
    p_part_commit = project_semantics(g_part_commit, U)
    assert not p_part_commit.conforms and not p_part_commit.failure_satisfied
    nc_results["failure_semantics_mismatch_rejected"] = True

    # NC5: Temporal deadline breach
    g_slow = RealizationGraph("NC5_slow", {
        "n_parse": RealizationNode("n_parse", role="parser", duration_ms=20.0),
        "n_work": RealizationNode("n_work", role="worker", duration_ms=1200.0),
        "n_verify": RealizationNode("n_verify", role="verifier", authority_tier="verifier", duration_ms=30.0),
        "n_commit": RealizationNode("n_commit", role="commit", outputs=("certified_result_R",), duration_ms=10.0),
    }, (("n_parse", "n_work"), ("n_work", "n_verify"), ("n_verify", "n_commit")))
    p_slow = project_semantics(g_slow, U)
    assert not p_slow.conforms and not p_slow.temporal_satisfied
    nc_results["temporal_deadline_breach_rejected"] = True

    # NC6: Resource budget excess
    g_gpu_excess = RealizationGraph("NC6_gpu_excess", {
        "n_parse": RealizationNode("n_parse", role="parser"),
        "n_work": RealizationNode("n_work", role="worker", gpu_slots=3),
        "n_verify": RealizationNode("n_verify", role="verifier", authority_tier="verifier"),
        "n_commit": RealizationNode("n_commit", role="commit", outputs=("certified_result_R",)),
    }, (("n_parse", "n_work"), ("n_work", "n_verify"), ("n_verify", "n_commit")))
    p_gpu_excess = project_semantics(g_gpu_excess, U)
    assert not p_gpu_excess.conforms and not p_gpu_excess.resource_satisfied
    nc_results["resource_budget_excess_rejected"] = True

    print("PASS: All 6 negative control violations strictly rejected.")

    # 4. Formal Claim Evaluation
    claim_spec = get_claim("A2.SEMANTIC_PROJECTION.PORTABLE")
    res_claim = evaluate_claim(
        True,
        EvidenceContext(
            level=EvidenceLevel.PORTABLE,
            source="qualification.a2_realization_semantics_campaign",
            actual_components={"projection": "SemanticProjection", "contract": "ParentContract"},
            substitutions={},
        ),
        ClaimRequirement(claim_spec.required_level, claim_spec.required_components),
    )
    assert res_claim["qualified"] and res_claim["passed"]

    payload = {
        "schema_version": "uow-a2-semantic-projection-v1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "parent_contract": {
            "contract_id": U.contract_id,
            "contract_hash": U.contract_hash,
            "invariant_classes": ["O", "D", "A", "E", "T", "R", "F"],
        },
        "alternate_realizations": [
            {"graph_id": g0.graph_id, "graph_hash": g0.graph_hash, "projection_hash": p0.projection_hash, "critical_path_ms": p0.measured_critical_path_ms},
            {"graph_id": g1.graph_id, "graph_hash": g1.graph_hash, "projection_hash": p1.projection_hash, "critical_path_ms": p1.measured_critical_path_ms},
            {"graph_id": g2.graph_id, "graph_hash": g2.graph_hash, "projection_hash": p2.projection_hash, "critical_path_ms": p2.measured_critical_path_ms},
            {"graph_id": g3.graph_id, "graph_hash": g3.graph_hash, "projection_hash": p3.projection_hash, "critical_path_ms": p3.measured_critical_path_ms},
        ],
        "topological_equivalence_verified": True,
        "negative_controls": nc_results,
        "claims": {
            "A2.SEMANTIC_PROJECTION.PORTABLE": res_claim,
        },
        "passed": True,
    }

    artifact_file = artifacts_dir / "a2-realization-semantics-qualification.json"
    artifact_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved qualification artifact to: {artifact_file}")
    print("=" * 80)
    print("GATE A2.0 QUALIFICATION SUCCESS: SEMANTIC PROJECTION Phi(G, U) QUALIFIED")
    print("=" * 80)
    return payload


if __name__ == "__main__":
    run_campaign()
