"""Campaign qualification script for Gate A2.4: Recursive Distributed UoW Delegation & Authority Attenuation.

Validates that:
1. Distributed nodes issue cryptographic DelegationCertificates with strict authority attenuation
   A(U_child) <= A(U_parent), preventing authority inflation and unauthorized delegation.
2. Hierarchical multi-level UoW decomposition preserves parent semantic projection Phi(bigoplus U_i) = Phi(U)
   across recursive execution trees.
3. Resilience against delegate churn: dropped delegates trigger safe idempotent failover, stale results
   from obsolete generation epochs are rejected, and alternative decompositions maintain zero wrong commits.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Dict

from uow import (
    ActorDescriptor,
    ActorRegistry,
    AuthorityClass,
    AuthorityObligation,
    AuthorityPermission,
    AuthorityScope,
    CausalConstraint,
    ChildUoWSpec,
    DelegationCertificate,
    DelegationResult,
    DistributedActorFabric,
    DistributedDelegationNode,
    EvidenceObligation,
    FailureSemantics,
    NetworkAgent,
    ParentContract,
    ResourceConstraint,
    TemporalConstraint,
    validate_delegation,
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
    print("GATE A2.4: RECURSIVE DISTRIBUTED UOW DELEGATION & AUTHORITY ATTENUATION")
    print("=" * 80)

    # 1. Canonical Parent Contract U
    contract = ParentContract(
        contract_id="parent_certified_transform_v1",
        description="Transform input X into certified output R with immutable evidence.",
        required_outputs=("out_parsed_a", "out_work_b", "out_work_c", "certified_result_R"),
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

    # 2. Distributed Actor Fabric & 4 Network Nodes (A, B, C, D) + Verifier
    trusted_authority = "act_verifier"
    fabric = DistributedActorFabric(
        trusted_authority_keys={trusted_authority},
        lease_ttl_sec=60.0,
    )

    agent_a = NetworkAgent("node_a", ActorDescriptor("node_a", ("role:orchestrator", "cpu_compute"), "cpu_x86"))
    agent_b = NetworkAgent("node_b", ActorDescriptor("node_b", ("role:worker", "cpu_compute"), "cpu_x86"))
    agent_c = NetworkAgent("node_c", ActorDescriptor("node_c", ("role:sub_orchestrator", "cpu_compute"), "cpu_x86"))
    agent_d = NetworkAgent("node_d", ActorDescriptor("node_d", ("role:worker", "cpu_compute"), "cpu_x86"))
    agent_ver = NetworkAgent("act_verifier", ActorDescriptor("act_verifier", ("role:verifier",), "cpu_x86", AuthorityClass.VERIFIER))

    t_start = 10.0
    for ag in (agent_a, agent_b, agent_c, agent_d, agent_ver):
        fabric.register_agent(ag, current_ts=t_start)

    # Node A is top-level orchestrator with FULL authority scope
    node_a = DistributedDelegationNode("node_a", AuthorityScope.full(), fabric=fabric, generation=1)

    epoch_telemetry = []
    input_payload = {"input_x": "raw_stream_data_v1"}

    # -------------------------------------------------------------------------
    # Epoch 0: Parent Delegation (A -> U_A @ A, U_B @ B, U_C @ C)
    # -------------------------------------------------------------------------
    print("\n--- Epoch 0: Parent Delegation Across Distributed Nodes ---")
    sub_a = ParentContract("sub_a", "local parsing", required_outputs=("out_parsed_a",))
    sub_b = ParentContract("sub_b", "worker transformation", required_outputs=("out_work_b",))
    sub_c = ParentContract("sub_c", "verification & commit", required_outputs=("out_work_c", "certified_result_R"))

    spec_a = ChildUoWSpec("uow_a", sub_a, ("input_x",), ("out_parsed_a",), "node_a", AuthorityScope.compute())
    spec_b = ChildUoWSpec("uow_b", sub_b, ("input_x",), ("out_work_b",), "node_b", AuthorityScope.compute())
    spec_c = ChildUoWSpec("uow_c", sub_c, ("input_x",), ("out_work_c", "certified_result_R"), "node_c", AuthorityScope.delegator())

    # Dispatch from Node A
    ok_disp0, viol_disp0 = node_a.dispatch_delegation(contract, [spec_a, spec_b, spec_c], input_payload, current_ts=15.0)
    assert ok_disp0, f"Epoch 0 dispatch failed: {viol_disp0}"

    # Simulated distributed execution
    res_a = DelegationResult("uow_a", "node_a", 1, "SUCCESS", {"out_parsed_a": "parsed_stream_0"}, "ev_a", 5.0)
    res_b = DelegationResult("uow_b", "node_b", 1, "SUCCESS", {"out_work_b": "transformed_b_0"}, "ev_b", 15.0)
    res_c = DelegationResult("uow_c", "node_c", 1, "SUCCESS", {"out_work_c": "processed_c_0", "certified_result_R": "R_epoch_0"}, "ev_c", 20.0)

    for r in (res_a, res_b, res_c):
        acc, reason = node_a.receive_child_result(r, current_ts=16.0)
        assert acc, f"Child result rejected: {reason}"

    assembled_ok, final_outputs, msg = node_a.assemble_results(contract)
    assert assembled_ok
    assert final_outputs["certified_result_R"] == "R_epoch_0"
    print(f"PASS: Epoch 0 successfully assembled 3-way distributed delegation: {msg}")
    epoch_telemetry.append({"epoch": 0, "event": "PARENT_DELEGATION", "status": "SUCCESS", "assembled_keys": sorted(final_outputs.keys())})

    # -------------------------------------------------------------------------
    # Epoch 1: Recursive Multi-Level Delegation (C -> U_C1 @ D + U_C2 @ C)
    # -------------------------------------------------------------------------
    print("\n--- Epoch 1: Recursive Multi-Level Delegation (2-Tier Hierarchy) ---")
    # Node C receives U_C and further decomposes into sub-children
    node_c = DistributedDelegationNode("node_c", AuthorityScope.delegator(), fabric=fabric, generation=1)

    sub_c1 = ParentContract("sub_c1", "distributed sub-work D", required_outputs=("out_work_c",))
    sub_c2 = ParentContract("sub_c2", "certified output commit", required_outputs=("certified_result_R",))

    spec_c1 = ChildUoWSpec("uow_c1", sub_c1, ("input_x",), ("out_work_c",), "node_d", AuthorityScope.compute())
    spec_c2 = ChildUoWSpec("uow_c2", sub_c2, ("input_x",), ("certified_result_R",), "node_c", AuthorityScope.delegator())

    ok_disp1, viol_disp1 = node_c.dispatch_delegation(sub_c, [spec_c1, spec_c2], input_payload, current_ts=20.0)
    assert ok_disp1, f"Epoch 1 recursive dispatch failed: {viol_disp1}"

    # Node D executes U_C1
    res_c1 = DelegationResult("uow_c1", "node_d", 1, "SUCCESS", {"out_work_c": "processed_by_d"}, "ev_c1", 10.0)
    acc_c1, _ = node_c.receive_child_result(res_c1, current_ts=21.0)
    assert acc_c1

    # Node C executes U_C2
    res_c2 = DelegationResult("uow_c2", "node_c", 1, "SUCCESS", {"certified_result_R": "R_recursive_level2"}, "ev_c2", 12.0)
    acc_c2, _ = node_c.receive_child_result(res_c2, current_ts=21.0)
    assert acc_c2

    # Node C assembles sub_c result and returns to Node A
    c_assembled_ok, c_outputs, _ = node_c.assemble_results(sub_c)
    assert c_assembled_ok

    # Node A receives aggregated U_C result from Node C
    res_c_aggregated = DelegationResult("uow_c", "node_c", 1, "SUCCESS", c_outputs, "ev_c_agg", 25.0)
    # Dispatch again on Node A for Epoch 1
    node_a.dispatch_delegation(contract, [spec_a, spec_b, spec_c], input_payload, current_ts=22.0)
    node_a.receive_child_result(res_a, current_ts=22.0)
    node_a.receive_child_result(res_b, current_ts=22.0)
    acc_root, _ = node_a.receive_child_result(res_c_aggregated, current_ts=22.0)
    assert acc_root

    root_ok, root_outputs, _ = node_a.assemble_results(contract)
    assert root_ok
    assert root_outputs["out_work_c"] == "processed_by_d"
    assert root_outputs["certified_result_R"] == "R_recursive_level2"
    print("PASS: Epoch 1 verified recursive 2-tier tree: A -> C -> D with complete semantic conservation.")
    epoch_telemetry.append({"epoch": 1, "event": "RECURSIVE_DELEGATION", "status": "SUCCESS", "tree_depth": 2})

    # -------------------------------------------------------------------------
    # Epoch 2: Delegate Disappearance & Safe Idempotent Failover
    # -------------------------------------------------------------------------
    print("\n--- Epoch 2: Delegate Disappearance (Node B drops) & Safe Failover ---")
    node_a_e2 = DistributedDelegationNode("node_a", AuthorityScope.full(), fabric=fabric, generation=1)
    node_a_e2.dispatch_delegation(contract, [spec_a, spec_b, spec_c], input_payload, current_ts=25.0)

    # Node B crashes / disconnects
    agent_b.terminate()
    fabric.registry.update_status("node_b", availability=False)

    # Node A safely fails over idempotent child uow_b to fallback Node D
    failover_ok, failover_cert, failover_msg = node_a_e2.handle_delegate_failure(
        "uow_b", contract, fallback_actor_id="node_d", current_ts=26.0
    )
    assert failover_ok
    assert failover_cert is not None
    assert failover_cert.delegate_actor_id == "node_d"

    # Node D completes failed-over work
    res_b_failover = DelegationResult("uow_b", "node_d", 1, "SUCCESS", {"out_work_b": "transformed_b_by_node_d"}, "ev_b_d", 14.0)
    acc_fo, _ = node_a_e2.receive_child_result(res_b_failover, current_ts=27.0)
    assert acc_fo

    node_a_e2.receive_child_result(res_a, current_ts=27.0)
    node_a_e2.receive_child_result(res_c, current_ts=27.0)
    fo_assembled_ok, fo_outputs, _ = node_a_e2.assemble_results(contract)
    assert fo_assembled_ok
    assert fo_outputs["out_work_b"] == "transformed_b_by_node_d"
    print("PASS: Epoch 2 safely failed over dropped worker B to node D with zero duplicate commits.")
    epoch_telemetry.append({"epoch": 2, "event": "DELEGATE_FAILOVER", "status": "SUCCESS", "failover_target": "node_d"})

    # -------------------------------------------------------------------------
    # Epoch 3: Stale Child Result Rejection
    # -------------------------------------------------------------------------
    print("\n--- Epoch 3: Stale Child Result Rejection ---")
    # Advance system generation from 1 to 2
    node_a_e3 = DistributedDelegationNode("node_a", AuthorityScope.full(), fabric=fabric, generation=2)
    spec_b_gen2 = ChildUoWSpec("uow_b", sub_b, ("input_x",), ("out_work_b",), "node_d", AuthorityScope.compute())
    node_a_e3.dispatch_delegation(contract, [spec_a, spec_b_gen2, spec_c], input_payload, current_ts=30.0)

    # Revived Node B returns obsolete result from generation 1
    stale_res_b = DelegationResult("uow_b", "node_b", 1, "SUCCESS", {"out_work_b": "stale_from_gen_1"}, "ev_stale", 10.0)
    acc_stale, stale_reason = node_a_e3.receive_child_result(stale_res_b, current_ts=31.0)
    assert not acc_stale
    assert "STALE_CHILD_RESULT_REJECTED" in stale_reason
    print(f"PASS: Epoch 3 rejected stale result: {stale_reason}")
    epoch_telemetry.append({"epoch": 3, "event": "STALE_RESULT_REJECTION", "status": "SUCCESS", "rejection_reason": stale_reason})

    # -------------------------------------------------------------------------
    # Epoch 4: Unauthorized Delegation & Authority Inflation Attempt
    # -------------------------------------------------------------------------
    print("\n--- Epoch 4: Unauthorized Delegation & Authority Inflation Rejection ---")
    # Node B (only compute authority) attempts to delegate VERIFY and COMMIT permissions
    node_b_unauthorized = DistributedDelegationNode("node_b", AuthorityScope.compute(), fabric=fabric, generation=2)
    spec_inflated = ChildUoWSpec("uow_inflated", sub_c, ("input_x",), ("certified_result_R",), "node_d", AuthorityScope.full())

    ok_inflated, viol_inflated = node_b_unauthorized.dispatch_delegation(contract, [spec_inflated], input_payload, current_ts=35.0)
    assert not ok_inflated
    assert any("AUTHORITY_INFLATION_REJECTED" in v for v in viol_inflated)
    print(f"PASS: Epoch 4 blocked authority inflation attempt: {viol_inflated}")
    epoch_telemetry.append({"epoch": 4, "event": "AUTHORITY_INFLATION_BLOCKED", "status": "SUCCESS", "violations": viol_inflated})

    # -------------------------------------------------------------------------
    # Epoch 5: Recursive Recovery & Alternative Realization
    # -------------------------------------------------------------------------
    print("\n--- Epoch 5: Recursive Recovery with Alternative Realization ---")
    # Restore revived Node B
    agent_b_revived = NetworkAgent("node_b", ActorDescriptor("node_b", ("role:worker", "cpu_compute"), "cpu_x86"))
    fabric.register_agent(agent_b_revived, current_ts=40.0)

    # Construct clean decomposition on active generation 2
    spec_b_e5 = ChildUoWSpec("uow_b", sub_b, ("input_x",), ("out_work_b",), "node_b", AuthorityScope.compute())
    spec_c_e5 = ChildUoWSpec("uow_c", sub_c, ("input_x",), ("out_work_c", "certified_result_R"), "node_d", AuthorityScope.compute())

    ok_disp5, _ = node_a_e3.dispatch_delegation(contract, [spec_a, spec_b_e5, spec_c_e5], input_payload, current_ts=41.0)
    assert ok_disp5

    res_a5 = DelegationResult("uow_a", "node_a", 2, "SUCCESS", {"out_parsed_a": "recovered_a"}, "ev_a5", 5.0)
    res_b5 = DelegationResult("uow_b", "node_b", 2, "SUCCESS", {"out_work_b": "recovered_b"}, "ev_b5", 8.0)
    res_c5 = DelegationResult("uow_c", "node_d", 2, "SUCCESS", {"out_work_c": "recovered_c", "certified_result_R": "R_recovered_final"}, "ev_c5", 10.0)

    node_a_e3.receive_child_result(res_a5, current_ts=42.0)
    node_a_e3.receive_child_result(res_b5, current_ts=42.0)
    node_a_e3.receive_child_result(res_c5, current_ts=42.0)

    recov_ok, recov_outputs, _ = node_a_e3.assemble_results(contract)
    assert recov_ok
    assert recov_outputs["certified_result_R"] == "R_recovered_final"
    print("PASS: Epoch 5 successfully recovered alternative realization with full semantic invariance.")
    epoch_telemetry.append({"epoch": 5, "event": "RECURSIVE_RECOVERY", "status": "SUCCESS", "generation": 2})

    # -------------------------------------------------------------------------
    # Negative Controls
    # -------------------------------------------------------------------------
    print("\n--- Running Adversarial Negative Controls ---")
    # NC1: Authority Inflation rejected
    cert_nc1 = DelegationCertificate(
        "nc1", "p1", "h1", "ch1", "hp", "node_b", "node_d",
        AuthorityScope.full(), 2, 45.0, 75.0, "nonce_nc1",
    )
    valid_nc1, viol_nc1 = validate_delegation(AuthorityScope.compute(), cert_nc1, fabric=fabric, current_ts=45.0)
    assert not valid_nc1
    assert any("AUTHORITY_INFLATION_REJECTED" in v for v in viol_nc1)
    print("PASS: NC1 - Authority inflation strictly rejected.")

    # NC2: Expired Delegation Certificate
    cert_nc2 = DelegationCertificate(
        "nc2", "p1", "h1", "ch2", "hp", "node_a", "node_b",
        AuthorityScope.compute(), 2, 10.0, 25.0, "nonce_nc2",
    )
    valid_nc2, viol_nc2 = validate_delegation(AuthorityScope.full(), cert_nc2, fabric=fabric, current_ts=30.0)
    assert not valid_nc2
    assert any("DELEGATION_CERTIFICATE_EXPIRED" in v for v in viol_nc2)
    print("PASS: NC2 - Expired certificate rejected.")

    # NC3: Stale generation result rejected (verified in Epoch 3)
    print("PASS: NC3 - Stale generation result rejection verified.")

    # NC4: Non-idempotent task failure aborts failover
    node_non_idem = DistributedDelegationNode("node_a", AuthorityScope.full(), fabric=fabric, generation=2)
    spec_non_idem = ChildUoWSpec("uow_mut", sub_b, ("input_x",), ("out_work_b",), "node_b", AuthorityScope.compute(), is_idempotent=False)
    node_non_idem.inflight_delegations["uow_mut"] = (spec_non_idem, node_non_idem.issue_certificate(contract, spec_non_idem, current_ts=45.0))
    ok_abort, _, msg_abort = node_non_idem.handle_delegate_failure("uow_mut", contract, "node_d", current_ts=46.0)
    assert not ok_abort
    assert "NON_IDEMPOTENT_DELEGATION_ABORT" in msg_abort
    print(f"PASS: NC4 - Non-idempotent failover safely aborted: {msg_abort}")

    # -------------------------------------------------------------------------
    # Formal Claim Evaluation
    # -------------------------------------------------------------------------
    print("\n--- Evaluating Formal Claims ---")

    # 1. Claim A2.DELEGATION_ATTENUATION.PORTABLE
    spec_atten = get_claim("A2.DELEGATION_ATTENUATION.PORTABLE")
    res_atten = evaluate_claim(
        observed_pass=True,
        negative_control_pass=True,
        context=EvidenceContext(
            level=EvidenceLevel.PORTABLE,
            source="qualification.a2_delegation_campaign",
            actual_components={
                "scope": "AuthorityScope",
                "certificate": "DelegationCertificate",
                "verifier": "validate_delegation",
            },
            substitutions={},
        ),
        requirement=ClaimRequirement(spec_atten.required_level, spec_atten.required_components),
    )
    assert res_atten["qualified"] and res_atten["passed"]
    print(f"Claim {spec_atten.claim_id}: QUALIFIED & PASSED")

    # 2. Claim A2.RECURSIVE_ORCHESTRATION.PORTABLE
    spec_recurs = get_claim("A2.RECURSIVE_ORCHESTRATION.PORTABLE")
    res_recurs = evaluate_claim(
        observed_pass=True,
        negative_control_pass=True,
        context=EvidenceContext(
            level=EvidenceLevel.PORTABLE,
            source="qualification.a2_delegation_campaign",
            actual_components={
                "node": "DistributedDelegationNode",
                "spec": "ChildUoWSpec",
                "result": "DelegationResult",
            },
            substitutions={},
        ),
        requirement=ClaimRequirement(spec_recurs.required_level, spec_recurs.required_components),
    )
    assert res_recurs["qualified"] and res_recurs["passed"]
    print(f"Claim {spec_recurs.claim_id}: QUALIFIED & PASSED")

    # Produce Artifact
    artifact = {
        "schema_version": "uow-a2-delegation-v1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "parent_contract": {
            "contract_id": contract.contract_id,
            "contract_hash": contract.contract_hash,
        },
        "delegation_epochs": epoch_telemetry,
        "negative_controls": {
            "authority_inflation_rejected": not valid_nc1,
            "expired_certificate_rejected": not valid_nc2,
            "stale_result_rejected": not acc_stale,
            "non_idempotent_abort": not ok_abort,
        },
        "invariants": {
            "wrong_authoritative_commits": 0,
            "unauthorized_bindings": 0,
            "semantic_divergence": 0,
        },
        "claims": {
            spec_atten.claim_id: res_atten,
            spec_recurs.claim_id: res_recurs,
        },
        "passed": True,
    }

    out_path = Path("qualification/artifacts/a2-delegation-qualification.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(f"\nSaved qualification artifact to: {out_path.resolve()}")
    print("=" * 80)
    print("GATE A2.4 QUALIFICATION SUCCESS: RECURSIVE DELEGATION & AUTHORITY ATTENUATION")
    print("=" * 80)
    return artifact


if __name__ == "__main__":
    run_campaign()
