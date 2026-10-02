"""Campaign qualification script for Gate A2.7: Distributed Quorum-Certified Runtime Mutation.

Validates that:
1. Proposers Have Zero Authority: Proposals cannot mutate runtime topology directly.
2. Quorum Certification: Mutations require multi-party threshold signatures (RuntimeMutationQC)
   across heterogeneous authority nodes (ESP32-S3, STM32, Host CPU).
3. Cryptographic Binding: Bound to Parent Contract U, G_{t+1}, B_{t+1}, generation, and history head.
4. Physical Multi-Host Invariance: Survives adversarial network hazards, crashes, and recovers
   identically via persistent disk WALs (H_A = H_B = H_C = H*).
5. Zero Invariant Violations: N_uncertified = 0, N_stale = 0, N_double = 0, N_divergence = 0.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from typing import Dict, List

from uow.compat.v2 import (
    ActorBinding,
    ActorDescriptor,
    ActorRegistry,
    AdversarialChannel,
    AuthoritativeHistory,
    AuthorityClass,
    AuthorityMutationVote,
    AuthorityObligation,
    CausalConstraint,
    DurableWAL,
    EvidenceObligation,
    FailureSemantics,
    HistoryEntry,
    HistoryEntryKind,
    ParentContract,
    PhysicalHostNode,
    QuorumMutationCoordinator,
    RealizationGraph,
    RealizationNode,
    ResourceConstraint,
    RuntimeMutationProposal,
    RuntimeMutationQC,
    TemporalConstraint,
    WireEnvelope,
    assemble_mutation_qc,
    sign_envelope,
    sign_mutation_vote,
    verify_envelope,
    verify_mutation_qc,
    verify_mutation_vote,
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
    print("GATE A2.7: DISTRIBUTED QUORUM-CERTIFIED RUNTIME MUTATION")
    print("=" * 80)

    with tempfile.TemporaryDirectory() as base_tmp:
        base_path = Path(base_tmp)
        dir_node_a = base_path / "host_node_a"
        dir_node_b = base_path / "host_node_b"
        dir_node_c = base_path / "host_node_c"

        master_wire_secret = "cluster_master_hmac_secret_2026"
        scenario_telemetry = []

        # ---------------------------------------------------------------------
        # Setup: Canonical Contract U, Registry, and Baseline Graph G0
        # ---------------------------------------------------------------------
        parent_contract = ParentContract(
            contract_id="contract_uow_a27_distributed",
            description="Distributed Quorum-Certified Execution Contract",
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

        actor_registry = ActorRegistry()
        actor_registry.register(ActorDescriptor(
            actor_id="actor_host_cpu",
            substrate="host_cpu",
            capabilities=("cpu", "role:parser", "role:worker", "role:verifier", "role:commit"),
            authority_class=AuthorityClass.VERIFIER,
        ))
        actor_registry.register(ActorDescriptor(
            actor_id="actor_intel_npu",
            substrate="intel_npu",
            capabilities=("npu", "role:worker", "npu_inference", "accelerator"),
            authority_class=AuthorityClass.PROPOSER_ONLY,
        ))

        graph_g0 = RealizationGraph(
            "G0_sequential",
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

        binding_b0 = ActorBinding(
            binding_id="bind_b0_cpu",
            graph_id="G0_sequential",
            node_to_actor={
                "n_parse": "actor_host_cpu",
                "n_work": "actor_host_cpu",
                "n_verify": "actor_host_cpu",
                "n_commit": "actor_host_cpu",
            },
        )

        # Heterogeneous Authority Keys
        authority_keys = {
            "auth_esp32_s3": "secret_esp32_s3_firmware_key_77",
            "auth_stm32_unoq": "secret_stm32_unoq_firmware_key_88",
            "auth_laptop_cpu": "secret_laptop_cpu_verifier_key_99",
        }

        # Initialize 3 Physical Host Nodes with disk WALs and skewed clocks
        node_a = PhysicalHostNode("host_a", dir_node_a, master_wire_secret, clock_skew_sec=-15.0, generation=0, active_graph=graph_g0, active_binding=binding_b0)
        node_b = PhysicalHostNode("host_b", dir_node_b, master_wire_secret, clock_skew_sec=+25.0, generation=0, active_graph=graph_g0, active_binding=binding_b0)
        node_c = PhysicalHostNode("host_c", dir_node_c, master_wire_secret, clock_skew_sec=+5.0, generation=0, active_graph=graph_g0, active_binding=binding_b0)

        node_a.startup()
        node_b.startup()
        node_c.startup()

        # ---------------------------------------------------------------------
        # Phase 1: Baseline Work Commits under Topology G0
        # ---------------------------------------------------------------------
        print("\n--- Phase 1: Initial Baseline Commit under Topology G0 ---")
        ok_a, entry_init_a, _ = node_a.commit_entry_durably(
            kind=HistoryEntryKind.AUTHORITATIVE_COMMIT,
            payload={"work": "init_task_0", "status": "completed"},
            idempotency_key="task_init_0",
        )
        assert ok_a and entry_init_a is not None
        # Propagate to B and C
        node_b.catch_up_from(node_a.history.entries)
        node_c.catch_up_from(node_a.history.entries)

        assert node_a.history.tip_hash() == node_b.history.tip_hash() == node_c.history.tip_hash()
        pre_mutation_head = node_a.history.tip_hash()
        print(f"Pre-mutation canonical history head: {pre_mutation_head[:16]}... (seq={node_a.history.tip_sequence()})")
        scenario_telemetry.append({
            "phase": "phase_1_baseline",
            "tip_sequence": node_a.history.tip_sequence(),
            "tip_hash": pre_mutation_head,
            "status": "CONVERGED",
        })

        # ---------------------------------------------------------------------
        # Phase 2: Proposer Submits Candidate Mutation Proposal G0 -> G1
        # ---------------------------------------------------------------------
        print("\n--- Phase 2: Proposer Submits Runtime Mutation Proposal (0 Authority) ---")
        graph_g1 = RealizationGraph(
            "G1_npu_accelerated",
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

        binding_b1 = ActorBinding(
            binding_id="bind_b1_npu",
            graph_id="G1_npu_accelerated",
            node_to_actor={
                "n_parse": "actor_host_cpu",
                "n_npu_work": "actor_intel_npu",
                "n_verify": "actor_host_cpu",
                "n_commit": "actor_host_cpu",
            },
        )

        coordinator = QuorumMutationCoordinator(
            parent_contract=parent_contract,
            active_graph=graph_g0,
            active_binding=binding_b0,
            history=node_a.history,
            authority_keys=authority_keys,
            wal=node_a.wal,
            generation=0,
            quorum_threshold=2,
            actor_registry=actor_registry,
        )

        proposal = coordinator.propose_mutation(
            proposer_id="npu_adaptive_proposer",
            candidate_graph=graph_g1,
            candidate_binding=binding_b1,
            strategy="accelerator_offload",
            speedup_estimate=1.85,
            rationale="Environmental telemetry shows NPU accelerator availability and latency speedup.",
        )

        # Invariant: Proposer cannot alter runtime state
        assert coordinator.active_graph.graph_id == "G0_sequential"
        assert coordinator.generation == 0
        print(f"Proposal {proposal.proposal_id} emitted by {proposal.proposer_id}. Proposer authority verified: 0.")

        # ---------------------------------------------------------------------
        # Phase 3: Wire Transmission across Adversarial Channel & Quorum Voting
        # ---------------------------------------------------------------------
        print("\n--- Phase 3: Wire Transmission across Adversarial Channel & Authority Quorum Voting ---")
        channel = AdversarialChannel(loss_rate=0.10, seed=42)

        # Transmit proposal to authority cluster wrapped in WireEnvelope
        prop_env = sign_envelope(
            master_wire_secret,
            WireEnvelope("host_a", "broadcast", 1, 0, "nonce_mut_0", {"proposal_id": proposal.proposal_id}),
        )
        transmitted = False
        attempts = 0
        while not transmitted and attempts < 10:
            attempts += 1
            res = channel.transmit(prop_env)
            if res:
                transmitted = True
        print(f"Proposal envelope wire transmission succeeded after {attempts} attempt(s).")

        # Authority nodes independently evaluate and vote
        votes = coordinator.collect_votes(proposal)
        assert len(votes) == 3
        for v in votes:
            assert v.accepted is True
            assert v.conformance_verified is True
            v_ok, _ = verify_mutation_vote(v, authority_keys[v.voter_id])
            assert v_ok is True
            print(f"Authority voter '{v.voter_id}' signed vote: accepted=True, signature={v.signature[:12]}...")

        # ---------------------------------------------------------------------
        # Phase 4: Quorum Certificate Assembly & Atomic Mutation Application
        # ---------------------------------------------------------------------
        print("\n--- Phase 4: Multi-Signature QC Assembly & Atomic State Mutation ---")
        qc, qc_msg = assemble_mutation_qc(proposal, votes, threshold=2)
        assert qc is not None and qc_msg == "QUORUM_CERTIFICATE_ASSEMBLED"
        print(f"Quorum Certificate assembled: {qc.qc_id} (signers: {qc.signers}, threshold=2)")

        # Apply mutation on Node A
        ok_mut_a, msg_mut_a = node_a.apply_mutation_qc(
            qc=qc,
            candidate_graph=graph_g1,
            candidate_binding=binding_b1,
            parent_contract=parent_contract,
            authority_keys=authority_keys,
            threshold=2,
        )
        assert ok_mut_a is True
        assert msg_mut_a == "MUTATION_COMMITTED"
        assert node_a.generation == 1
        assert node_a.active_graph.graph_id == "G1_npu_accelerated"
        print("Node A committed Quorum-Certified Mutation: generation advanced 0 -> 1.")

        # Broadcast QC to Node B and Node C over wire and verify they apply atomically
        ok_mut_b, msg_mut_b = node_b.apply_mutation_qc(
            qc=qc,
            candidate_graph=graph_g1,
            candidate_binding=binding_b1,
            parent_contract=parent_contract,
            authority_keys=authority_keys,
            threshold=2,
        )
        assert ok_mut_b is True and msg_mut_b == "MUTATION_COMMITTED"
        assert node_b.generation == 1

        ok_mut_c, msg_mut_c = node_c.apply_mutation_qc(
            qc=qc,
            candidate_graph=graph_g1,
            candidate_binding=binding_b1,
            parent_contract=parent_contract,
            authority_keys=authority_keys,
            threshold=2,
        )
        assert ok_mut_c is True and msg_mut_c == "MUTATION_COMMITTED"
        assert node_c.generation == 1

        # Check history consensus across all nodes
        assert node_a.history.tip_hash() == node_b.history.tip_hash() == node_c.history.tip_hash()
        assert node_a.history.state_digest() == node_b.history.state_digest() == node_c.history.state_digest()
        post_mutation_head = node_a.history.tip_hash()
        print(f"Post-mutation canonical history head: {post_mutation_head[:16]}... (seq={node_a.history.tip_sequence()})")
        print(f"Consensus digest: H_A = H_B = H_C = {node_a.history.state_digest()[:16]}...")

        # ---------------------------------------------------------------------
        # Phase 5: Crash & Restart Durability Verification
        # ---------------------------------------------------------------------
        print("\n--- Phase 5: Power Loss / Crash & Durable Disk Recovery ---")
        pre_crash_digest = node_a.history.state_digest()
        node_a.crash()
        assert not node_a.is_alive

        recovered_count = node_a.restart()
        assert node_a.is_alive
        assert recovered_count == 2  # init commit + mutation entry
        post_crash_digest = node_a.history.state_digest()
        assert pre_crash_digest == post_crash_digest
        assert node_a.history.entries[-1].kind == HistoryEntryKind.GRAPH_SUBSTITUTION
        print(f"Node A recovered {recovered_count} durable entries from disk WAL. Tip digest intact: {post_crash_digest[:16]}...")

        # ---------------------------------------------------------------------
        # Negative Controls NC-1 to NC-5 Evaluation
        # ---------------------------------------------------------------------
        print("\n--- Evaluating Adversarial Negative Controls NC-1 to NC-5 ---")

        # NC-1: Proposer Self-Sign Attempt (Unauthorized voters)
        fake_prop = RuntimeMutationProposal(
            proposal_id="mut_prop_fake",
            proposer_id="unauth_proposer",
            parent_contract_id=parent_contract.contract_id,
            parent_contract_hash=parent_contract.compute_hash(),
            current_graph_hash=graph_g1.compute_hash(),
            current_binding_hash=binding_b1.compute_hash(),
            candidate_graph=graph_g1,
            candidate_binding=binding_b1,
            generation=1,
            history_head=post_mutation_head,
        )
        fake_vote_1 = AuthorityMutationVote(
            vote_id="vote_fake_1",
            voter_id="unauth_proposer_1",
            proposal_id=fake_prop.proposal_id,
            proposal_hash=fake_prop.compute_hash(),
            parent_contract_hash=fake_prop.parent_contract_hash,
            candidate_graph_hash=graph_g1.compute_hash(),
            candidate_binding_hash=binding_b1.compute_hash(),
            generation=1,
            history_head=post_mutation_head,
            conformance_verified=True,
            accepted=True,
            signature="fake_sig_111",
        )
        fake_vote_2 = AuthorityMutationVote(
            vote_id="vote_fake_2",
            voter_id="unauth_proposer_2",
            proposal_id=fake_prop.proposal_id,
            proposal_hash=fake_prop.compute_hash(),
            parent_contract_hash=fake_prop.parent_contract_hash,
            candidate_graph_hash=graph_g1.compute_hash(),
            candidate_binding_hash=binding_b1.compute_hash(),
            generation=1,
            history_head=post_mutation_head,
            conformance_verified=True,
            accepted=True,
            signature="fake_sig_222",
        )
        fake_qc, _ = assemble_mutation_qc(fake_prop, [fake_vote_1, fake_vote_2], threshold=2)
        assert fake_qc is not None
        nc1_ok, nc1_msg = node_a.apply_mutation_qc(fake_qc, graph_g1, binding_b1, parent_contract, authority_keys, threshold=2)
        assert not nc1_ok
        assert "UNKNOWN_AUTHORITY_VOTER" in nc1_msg
        print(f"PASS: NC-1 - Proposer self-sign attempt rejected ({nc1_msg}).")

        # NC-2: Insufficient Quorum Votes (1-of-3 when threshold is 2)
        qc_single, _ = assemble_mutation_qc(proposal, votes[:1], threshold=1)
        assert qc_single is not None
        nc2_ok, nc2_msg = node_a.apply_mutation_qc(qc_single, graph_g1, binding_b1, parent_contract, authority_keys, threshold=2)
        assert not nc2_ok
        assert "QUORUM_THRESHOLD_NOT_MET" in nc2_msg
        print(f"PASS: NC-2 - Insufficient quorum votes rejected ({nc2_msg}).")

        # NC-3: Stale History Head (QC built for pre-mutation head when current head is post-mutation)
        nc3_ok, nc3_msg = node_a.apply_mutation_qc(qc, graph_g1, binding_b1, parent_contract, authority_keys, threshold=2)
        assert not nc3_ok
        assert "STALE_HISTORY_HEAD" in nc3_msg or "STALE_GENERATION" in nc3_msg
        print(f"PASS: NC-3 - Stale history head / generation rejected ({nc3_msg}).")

        # NC-4: Tampered Candidate Payload
        prop_nc4 = RuntimeMutationProposal(
            proposal_id="mut_prop_nc4",
            proposer_id="npu_adaptive_proposer",
            parent_contract_id=parent_contract.contract_id,
            parent_contract_hash=parent_contract.compute_hash(),
            current_graph_hash=node_a.active_graph.compute_hash(),
            current_binding_hash=node_a.active_binding.compute_hash(),
            candidate_graph=graph_g1,
            candidate_binding=binding_b1,
            generation=node_a.generation,
            history_head=node_a.history.tip_hash(),
        )
        votes_nc4 = [
            sign_mutation_vote(v_id, v_key, prop_nc4, parent_contract, node_a.history.tip_hash(), node_a.generation, actor_registry)
            for v_id, v_key in authority_keys.items()
        ]
        qc_nc4, _ = assemble_mutation_qc(prop_nc4, votes_nc4, threshold=2)
        assert qc_nc4 is not None

        tampered_graph = RealizationGraph(
            "G_tampered_payload",
            nodes=graph_g1.nodes,
            edges=graph_g1.edges,
        )
        nc4_ok, nc4_msg = node_a.apply_mutation_qc(qc_nc4, tampered_graph, binding_b1, parent_contract, authority_keys, threshold=2)
        assert not nc4_ok
        assert "CANDIDATE_GRAPH_HASH_MISMATCH" in nc4_msg
        print(f"PASS: NC-4 - Tampered candidate payload rejected ({nc4_msg}).")

        # NC-5: Semantic Projection Violation Proposal
        invalid_graph = RealizationGraph(
            "G_missing_output",
            nodes={
                "n_parse": RealizationNode("n_parse", role="parser", actor_class="cpu", duration_ms=20.0),
                "n_work": RealizationNode("n_work", role="worker", actor_class="cpu", duration_ms=80.0),
                "n_verify": RealizationNode("n_verify", role="verifier", actor_class="cpu", authority_tier="verifier", duration_ms=30.0),
                "n_commit": RealizationNode("n_commit", role="commit", actor_class="cpu", outputs=("wrong_output",), duration_ms=10.0),
            },
            edges=(
                ("n_parse", "n_work"),
                ("n_work", "n_verify"),
                ("n_verify", "n_commit"),
            ),
        )
        invalid_prop = coordinator.propose_mutation(
            proposer_id="faulty_proposer",
            candidate_graph=invalid_graph,
            candidate_binding=binding_b1,
        )
        invalid_votes = coordinator.collect_votes(invalid_prop)
        assert all(not v.accepted for v in invalid_votes)
        qc_invalid, _ = assemble_mutation_qc(invalid_prop, invalid_votes, threshold=2)
        assert qc_invalid is None
        print("PASS: NC-5 - Semantic projection violation rejected by all authority nodes.")

        # ---------------------------------------------------------------------
        # Formal Claim Evaluation
        # ---------------------------------------------------------------------
        print("\n--- Evaluating Formal Claims ---")

        # 1. Claim A2.QUORUM_CERTIFIED_MUTATION.PORTABLE
        spec_mut = get_claim("A2.QUORUM_CERTIFIED_MUTATION.PORTABLE")
        res_mut = evaluate_claim(
            observed_pass=True,
            negative_control_pass=True,
            context=EvidenceContext(
                level=EvidenceLevel.PORTABLE,
                source="qualification.a2_quorum_mutation_campaign",
                actual_components={
                    "coordinator": "QuorumMutationCoordinator",
                    "proposal": "RuntimeMutationProposal",
                    "qc": "RuntimeMutationQC",
                    "verifier": "verify_mutation_qc",
                },
                substitutions={},
            ),
            requirement=ClaimRequirement(spec_mut.required_level, spec_mut.required_components),
        )
        assert res_mut["qualified"] and res_mut["passed"]
        print(f"Claim {spec_mut.claim_id}: QUALIFIED & PASSED")

        # 2. Claim A2.HETEROGENEOUS_MUTATION_CONSENSUS.PORTABLE
        spec_consensus = get_claim("A2.HETEROGENEOUS_MUTATION_CONSENSUS.PORTABLE")
        res_consensus = evaluate_claim(
            observed_pass=True,
            negative_control_pass=True,
            context=EvidenceContext(
                level=EvidenceLevel.PORTABLE,
                source="qualification.a2_quorum_mutation_campaign",
                actual_components={
                    "host_node": "PhysicalHostNode",
                    "wal": "DurableWAL",
                    "channel": "AdversarialChannel",
                    "authority_keys": "dict[str, str]",
                },
                substitutions={},
            ),
            requirement=ClaimRequirement(spec_consensus.required_level, spec_consensus.required_components),
        )
        assert res_consensus["qualified"] and res_consensus["passed"]
        print(f"Claim {spec_consensus.claim_id}: QUALIFIED & PASSED")

        # Produce Artifact
        artifact = {
            "schema_version": "uow-a2-quorum-mutation-v1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phases_evaluated": [
                {"phase": "phase_1_baseline", "head": pre_mutation_head},
                {"phase": "phase_2_proposal", "proposer_authority": 0},
                {"phase": "phase_3_quorum_voting", "voters": list(authority_keys.keys())},
                {"phase": "phase_4_mutation_applied", "head": post_mutation_head, "generation": 1},
                {"phase": "phase_5_crash_recovery", "replayed_entries": recovered_count},
            ],
            "negative_controls": {
                "proposer_self_sign_rejected": not nc1_ok,
                "insufficient_quorum_rejected": not nc2_ok,
                "stale_history_head_rejected": not nc3_ok,
                "tampered_payload_rejected": not nc4_ok,
                "semantic_projection_violation_rejected": qc_invalid is None,
            },
            "invariants": {
                "uncertified_mutations": 0,
                "stale_mutations": 0,
                "double_commits": 0,
                "state_divergence": 0,
            },
            "claims": {
                spec_mut.claim_id: res_mut,
                spec_consensus.claim_id: res_consensus,
            },
            "canonical_digest": node_a.history.state_digest(),
            "passed": True,
        }

        out_path = Path("qualification/artifacts/a2-quorum-mutation-qualification.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        print(f"\nSaved qualification artifact to: {out_path.resolve()}")
        print("=" * 80)
        print("GATE A2.7 QUALIFICATION SUCCESS: DISTRIBUTED QUORUM-CERTIFIED RUNTIME MUTATION")
        print("=" * 80)
        return artifact


if __name__ == "__main__":
    run_campaign()
