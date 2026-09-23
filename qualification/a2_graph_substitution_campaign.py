"""Campaign qualification script for Gate A2.1: Graph Substitution & Runtime Certification.

Validates that candidate realization graphs can be dynamically proposed, certified
against parent contract semantics Phi(G, U) prior to activation, executed with
exact output parity, and safely rolled back to baseline upon failure or rejection.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from uow import (
    AdaptiveCompositionRuntime,
    AuthorityObligation,
    CausalConstraint,
    CompositionCertifier,
    EvidenceObligation,
    FailureSemantics,
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


def run_campaign() -> dict:
    print("=" * 80)
    print("GATE A2.1: GRAPH SUBSTITUTION & RUNTIME CERTIFICATION QUALIFICATION")
    print("=" * 80)

    # 1. Canonical Parent Contract U
    contract = ParentContract(
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

    # 2. Topologies G0 (sequential), G1 (parallel), G2 (accelerator NPU), G3 (distributed)
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

    g3 = RealizationGraph(
        "G3_distributed",
        {
            "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
            "n_remote_work": RealizationNode("n_remote_work", role="worker", actor_class="remote", duration_ms=120.0),
            "n_quorum_auth": RealizationNode("n_quorum_auth", role="verifier", actor_class="physical_esp32", authority_tier="authority_quorum", duration_ms=40.0),
            "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("certified_result_R",), duration_ms=10.0),
        },
        (("n_parse", "n_remote_work"), ("n_remote_work", "n_quorum_auth"), ("n_quorum_auth", "n_commit")),
    )

    # Initialize Runtime with Baseline G0
    runtime = AdaptiveCompositionRuntime(contract=contract, baseline_graph=g0)
    input_data = {"input_data_X": "canonical_payload_01"}

    # Execute G0 Baseline
    rec0 = runtime.execute(input_data)
    assert rec0.status == "SUCCESS"
    expected_output = rec0.final_outputs["certified_result_R"]
    print(f"PASS: Baseline G0 executed successfully (output={expected_output!r})")

    # Substitution 1: G0 -> G1 (Parallel)
    prop1 = GraphReplacementProposal(
        parent_contract_id=contract.contract_id,
        current_graph_hash=runtime.current_graph_hash,
        candidate_graph=g1,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        predicted_speedup=1.08,
        rationale="Parallel fork-join decomposition",
        proposal_id="p1_parallel",
    )
    cert1 = runtime.propose_and_certify(prop1)
    assert cert1.is_accepted
    assert runtime.current_graph_hash == g1.compute_hash()
    rec1 = runtime.execute(input_data)
    assert rec1.status == "SUCCESS"
    assert rec1.final_outputs["certified_result_R"] == expected_output
    print("PASS: Substitution 1 (G0 -> G1 Parallel) certified and executed with exact output parity.")

    # Substitution 2: G1 -> G2 (Accelerator NPU)
    prop2 = GraphReplacementProposal(
        parent_contract_id=contract.contract_id,
        current_graph_hash=runtime.current_graph_hash,
        candidate_graph=g2,
        strategy=SubstitutionStrategy.ACCELERATOR_OFFLOAD,
        predicted_speedup=1.87,
        rationale="NPU accelerator offload",
        proposal_id="p2_npu",
    )
    cert2 = runtime.propose_and_certify(prop2)
    assert cert2.is_accepted
    assert runtime.current_graph_hash == g2.compute_hash()
    rec2 = runtime.execute(input_data)
    assert rec2.status == "SUCCESS"
    assert rec2.final_outputs["certified_result_R"] == expected_output
    print("PASS: Substitution 2 (G1 -> G2 Accelerator) certified and executed with exact output parity.")

    # Substitution 3: G2 -> G3 (Distributed Quorum)
    prop3 = GraphReplacementProposal(
        parent_contract_id=contract.contract_id,
        current_graph_hash=runtime.current_graph_hash,
        candidate_graph=g3,
        strategy=SubstitutionStrategy.DISTRIBUTED_QUORUM,
        predicted_speedup=0.74,
        rationale="Distributed 2-of-3 quorum authority",
        proposal_id="p3_quorum",
    )
    cert3 = runtime.propose_and_certify(prop3)
    assert cert3.is_accepted
    assert runtime.current_graph_hash == g3.compute_hash()
    rec3 = runtime.execute(input_data)
    assert rec3.status == "SUCCESS"
    assert rec3.final_outputs["certified_result_R"] == expected_output
    print("PASS: Substitution 3 (G2 -> G3 Distributed Quorum) certified and executed with exact output parity.")

    # Negative Controls Falsification Matrix
    print("\nExecuting Adversarial Negative Controls Matrix...")

    # NC-1: Stale / forged current graph hash
    prop_nc1 = GraphReplacementProposal(
        parent_contract_id=contract.contract_id,
        current_graph_hash="0" * 64,
        candidate_graph=g1,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        proposal_id="nc1_stale",
    )
    cert_nc1 = runtime.propose_and_certify(prop_nc1)
    assert not cert_nc1.is_accepted
    assert runtime.current_graph_hash == g3.compute_hash()
    print("PASS: NC-1 Stale graph hash strictly rejected; active graph undisturbed.")

    # NC-2: Foreign / mismatched contract ID
    prop_nc2 = GraphReplacementProposal(
        parent_contract_id="unrelated_foreign_contract_v9",
        current_graph_hash=runtime.current_graph_hash,
        candidate_graph=g1,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        proposal_id="nc2_mismatch",
    )
    cert_nc2 = runtime.propose_and_certify(prop_nc2)
    assert not cert_nc2.is_accepted
    assert runtime.current_graph_hash == g3.compute_hash()
    print("PASS: NC-2 Foreign contract ID strictly rejected; active graph undisturbed.")

    # NC-3: Cyclic candidate graph
    g_cyclic = RealizationGraph(
        "G_cyclic_candidate",
        {"n_a": RealizationNode("n_a", role="worker"), "n_b": RealizationNode("n_b", role="worker")},
        (("n_a", "n_b"), ("n_b", "n_a")),
        allow_cycle=True,
    )
    prop_nc3 = GraphReplacementProposal(
        parent_contract_id=contract.contract_id,
        current_graph_hash=runtime.current_graph_hash,
        candidate_graph=g_cyclic,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        proposal_id="nc3_cyclic",
    )
    cert_nc3 = runtime.propose_and_certify(prop_nc3)
    assert not cert_nc3.is_accepted
    assert "CANDIDATE_GRAPH_CYCLIC" in cert_nc3.violations
    print("PASS: NC-3 Cyclic candidate graph strictly rejected; active graph undisturbed.")

    # NC-4: Invariant violation (authority role missing)
    g_bypass = RealizationGraph(
        "G_bypass",
        {
            "n_parse": RealizationNode("n_parse", role="parser"),
            "n_work": RealizationNode("n_work", role="worker"),
            "n_commit": RealizationNode("n_commit", role="commit", outputs=("certified_result_R",)),
        },
        (("n_parse", "n_work"), ("n_work", "n_commit")),
    )
    prop_nc4 = GraphReplacementProposal(
        parent_contract_id=contract.contract_id,
        current_graph_hash=runtime.current_graph_hash,
        candidate_graph=g_bypass,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        proposal_id="nc4_bypass",
    )
    cert_nc4 = runtime.propose_and_certify(prop_nc4)
    assert not cert_nc4.is_accepted
    assert any("A_AUTHORITY_ROLE_MISSING" in v for v in cert_nc4.violations)
    print("PASS: NC-4 Authority bypass strictly rejected; active graph undisturbed.")

    # NC-5: Injected execution failure & automatic fallback
    rec_fail = runtime.execute(input_data, fail_node_id="n_remote_work")
    assert rec_fail.status == "FAILED"
    assert runtime.current_graph_hash == g0.compute_hash()
    rec_recov = runtime.execute(input_data)
    assert rec_recov.status == "SUCCESS"
    assert rec_recov.final_outputs["certified_result_R"] == expected_output
    print("PASS: NC-5 Injected execution failure triggered automatic rollback to baseline G0.")

    # Claim Qualification Evaluation
    spec = get_claim("A2.GRAPH_SUBSTITUTION.PORTABLE")
    positive_pass = (
        cert1.is_accepted
        and cert2.is_accepted
        and cert3.is_accepted
        and rec0.status == "SUCCESS"
        and rec1.status == "SUCCESS"
        and rec2.status == "SUCCESS"
        and rec3.status == "SUCCESS"
    )
    negative_pass = (
        (not cert_nc1.is_accepted)
        and (not cert_nc2.is_accepted)
        and (not cert_nc3.is_accepted)
        and (not cert_nc4.is_accepted)
        and (rec_fail.status == "FAILED")
        and (runtime.current_graph_hash == g0.compute_hash())
    )

    claim_res = evaluate_claim(
        observed_pass=(positive_pass and negative_pass),
        negative_control_pass=negative_pass,
        context=EvidenceContext(
            level=EvidenceLevel.PORTABLE,
            source="qualification.a2_graph_substitution_campaign",
            actual_components={"runtime": "AdaptiveCompositionRuntime", "certifier": "CompositionCertifier"},
            substitutions={},
        ),
        requirement=ClaimRequirement(spec.required_level, spec.required_components),
    )
    assert claim_res["qualified"]
    assert claim_res["passed"]
    print(f"\nClaim {spec.claim_id}: QUALIFIED & PASSED (Level: {spec.required_level.value})")

    # Produce Artifact
    artifact = {
        "schema_version": "uow-a2-graph-substitution-v1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "parent_contract": {
            "contract_id": contract.contract_id,
            "contract_hash": contract.contract_hash,
        },
        "baseline_graph": {
            "graph_id": g0.graph_id,
            "graph_hash": g0.graph_hash,
        },
        "certified_substitutions": [
            {
                "strategy": SubstitutionStrategy.PARALLEL_DECOMPOSITION.value,
                "target_graph_id": g1.graph_id,
                "target_graph_hash": g1.graph_hash,
                "certificate_hash": cert1.compute_hash(),
                "execution_status": rec1.status,
            },
            {
                "strategy": SubstitutionStrategy.ACCELERATOR_OFFLOAD.value,
                "target_graph_id": g2.graph_id,
                "target_graph_hash": g2.graph_hash,
                "certificate_hash": cert2.compute_hash(),
                "execution_status": rec2.status,
            },
            {
                "strategy": SubstitutionStrategy.DISTRIBUTED_QUORUM.value,
                "target_graph_id": g3.graph_id,
                "target_graph_hash": g3.graph_hash,
                "certificate_hash": cert3.compute_hash(),
                "execution_status": rec3.status,
            },
        ],
        "negative_controls": {
            "stale_graph_hash_rejected": not cert_nc1.is_accepted,
            "foreign_contract_rejected": not cert_nc2.is_accepted,
            "cyclic_candidate_rejected": not cert_nc3.is_accepted,
            "authority_bypass_rejected": not cert_nc4.is_accepted,
            "injected_failure_fallback_to_baseline": rec_fail.status == "FAILED" and runtime.current_graph_hash == g0.compute_hash(),
        },
        "claims": {
            spec.claim_id: claim_res,
        },
        "passed": True,
    }

    out_path = Path("qualification/artifacts/a2-graph-substitution-qualification.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(f"\nSaved qualification artifact to: {out_path.resolve()}")
    print("=" * 80)
    print("GATE A2.1 QUALIFICATION SUCCESS: GRAPH SUBSTITUTION & RUNTIME CERTIFICATION")
    print("=" * 80)
    return artifact


if __name__ == "__main__":
    run_campaign()
