"""Continuous verification test exercising all 10 architectural levels (Levels 0 through 9).

Ensures that public API surfaces and quickstart examples remain executable and
synchronized with canonical contracts and realizations.
"""
from __future__ import annotations

import pytest
import uow


def test_public_api_symbol_freeze():
    """Verify v3 top-level API freeze remains minimal: root primitives and namespaces."""
    expected_v3_root = {
        "UoW",
        "WorldState",
        "execute",
        "authority",
        "runtime",
        "autonomy",
        "semantic",
        "economics",
        "protocol",
        "adapters",
    }
    assert set(uow.__all__) == expected_v3_root


def test_level_0_core_transition_algebra():
    """Level 0: Core Transition Algebra & Lifecycle."""
    from uow import (
        MatrixCell,
        Mutation,
        MutationOp,
        Guard,
        GuardOp,
        Route,
        Successor,
        WorkCategory,
        WorldState,
        certify,
        commit,
        make_uow,
        propose,
    )

    s0 = WorldState(attributes={"balance": 100, "status": "ACTIVE", "transfers_completed": 0})
    u0 = make_uow(
        "tx_001",
        routes=[
            Route(
                guard=Guard(GuardOp.GTE, "balance", 30),
                mutations=(
                    Mutation(MutationOp.SUB, "balance", 30),
                    Mutation(MutationOp.ADD, "transfers_completed", 1),
                ),
                successor=Successor.halt(),
            )
        ],
        matrix_cell=MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA),
    )
    p0 = propose(u0, s0)
    assert p0.uow_id == "tx_001"
    c0 = certify(u0, s0, p0)
    assert c0.is_valid
    s1, rec = commit(u0, s0, p0, c0, prev_evidence_hash="0" * 64, step_number=1)
    assert s1.require("balance") == 70
    assert s1.require("transfers_completed") == 1


def test_level_1_occ_transactions_and_sequencing():
    """Level 1: OCC Transactions & Sequencing."""
    from uow import Guard, GuardOp, Mutation, MutationOp, Route, Successor, WorldState, certify, make_uow, propose
    from uow.transactions import DeterministicSequencer, create_transaction_descriptor, validate_occ

    state = WorldState(attributes={"account_A": 500, "account_B": 200})
    sequencer = DeterministicSequencer(state)

    tx_uow = make_uow(
        "tx_transfer_01",
        routes=[
            Route(
                guard=Guard(GuardOp.ALWAYS),
                mutations=(
                    Mutation(MutationOp.SUB, "account_A", 100),
                    Mutation(MutationOp.ADD, "account_B", 100),
                ),
                successor=Successor.halt(),
            )
        ],
    )
    proposal = propose(tx_uow, state)
    tx_desc = create_transaction_descriptor(tx_uow, state)
    cert = certify(tx_uow, state, proposal)

    is_valid, hazard, _ = validate_occ(state, tx_desc)
    assert is_valid
    new_state, evidence = sequencer.commit(tx_uow, proposal, tx_desc, cert)
    assert new_state.require("account_A") == 400
    assert new_state.require("account_B") == 300


def test_level_2_self_hosted_dag_orchestration():
    """Level 2: Self-Hosted DAG Orchestration."""
    from uow import Guard, GuardOp, Mutation, MutationOp, Route
    from uow.orchestration import create_initial_orchestration_state, make_domain_task, run_orchestration

    task_a = make_domain_task("extract_features", [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 10),))])
    task_b = make_domain_task("train_model", [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 20),))])
    orch_init = create_initial_orchestration_state(["extract_features", "train_model"], {"train_model": ["extract_features"]}, attributes={"r0": 0})
    orch_final, orch_seq = run_orchestration({"extract_features": task_a, "train_model": task_b}, orch_init)
    assert orch_final.require("r0") == 30
    assert orch_final.status == "HALTED"


def test_level_3_resource_governance_and_leases():
    """Level 3: Multi-Dimensional Resource Governance & Leases."""
    from uow import Guard, GuardOp, Mutation, MutationOp, Route
    from uow.orchestration import create_initial_orchestration_state
    from uow.resources import (
        FIFOSchedulingPolicy,
        ResourceRequirement,
        ResourceState,
        get_authoritative_resource_state,
        make_resource_domain_task,
        run_resource_orchestration,
        set_authoritative_resource_state,
    )

    cluster_resources = ResourceState(capacities={"cpu_cores": 16.0, "ram_units": 16.0, "gpu_slots": 2})
    npu_task = make_resource_domain_task(
        "inference_batch",
        [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "inferences", 10),))],
        requirement=ResourceRequirement(cpu_cores=2, ram_units=4),
    )
    initial_base = create_initial_orchestration_state(["inference_batch"], {}, attributes={"inferences": 0})
    initial_state = set_authoritative_resource_state(initial_base, cluster_resources)
    final_state, seq = run_resource_orchestration({"inference_batch": npu_task}, initial_state, FIFOSchedulingPolicy())

    assert final_state.require("inferences") == 10
    assert len(get_authoritative_resource_state(final_state).leases) == 0


def test_level_4_external_effects_and_sagas():
    """Level 4: External Effects & Sagas."""
    from uow import WorldState
    from uow.effects import EffectRunner, MockExternalClient, SagaCoordinator, SagaStep, create_effect_descriptor
    from uow.transactions import DeterministicSequencer

    client = MockExternalClient()
    sequencer = DeterministicSequencer(WorldState(attributes={}))
    runner = EffectRunner(sequencer, client)
    coordinator = SagaCoordinator(runner)

    step = SagaStep(
        "provision_storage",
        lambda state: create_effect_descriptor(
            uow_id="provision_storage",
            pre_state_hash=state.state_hash,
            intent="allocate_volume",
            request={"volume_id": "vol_42", "size_gb": 100},
            compensation_intent="deallocate_volume",
            compensation_request={"volume_id": "vol_42"},
        ),
    )
    coordinator.execute_saga([step], saga_id="storage_saga_01")
    assert len(client.call_log) > 0


def test_level_5_replaceable_and_adaptive_proposers():
    """Level 5: Replaceable & Adaptive Proposers."""
    from uow import Guard, GuardOp, Mutation, MutationOp, Route
    from uow.orchestration import create_initial_orchestration_state
    from uow.proposer import PortableAdaptiveProposer, ProposerOrchestrationEngine
    from uow.resources import ResourceRequirement, ResourceState, make_resource_domain_task, set_authoritative_resource_state

    res_caps = ResourceState(capacities={"cpu_cores": 8, "ram_units": 16})
    res_req = ResourceRequirement(cpu_cores=2, ram_units=4)
    res_task = make_resource_domain_task("res_1", [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "out", 42),))], res_req)
    res_base = create_initial_orchestration_state(["res_1"], {}, attributes={"out": 0})
    res_init = set_authoritative_resource_state(res_base, res_caps)

    proposer = PortableAdaptiveProposer(initial_weights={"cpu_affinity": 1.0, "cpu_capacity": 8.0}, learning_rate=1.0)
    engine = ProposerOrchestrationEngine(proposer=proposer)
    final_state, seq, telem = engine.run_dag({"res_1": res_task}, res_init)
    assert final_state.status == "HALTED"


def test_level_6_recursive_composition_and_system_as_actor():
    """Level 6: Recursive Composition & System-as-Actor."""
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
    )
    from uow.composition.boundary import certify_composition_boundary, verify_composition_boundary

    pc = ParentContract(
        contract_id="pc_01",
        description="Cybernetic boundary",
        required_outputs=("out",),
        causal_constraints=(
            CausalConstraint("parser", "worker"),
            CausalConstraint("worker", "verifier"),
            CausalConstraint("verifier", "commit"),
        ),
        authority=AuthorityObligation(required_role="verifier", min_evidence_level="portable", quorum_threshold=1),
        evidence=EvidenceObligation(require_provenance=True, require_hash_chain=True, min_evidence_level="portable", verifier_id="recursive-test-judge"),
        temporal=TemporalConstraint(max_duration_ms=5000.0),
        resources=ResourceConstraint(max_cpu_cores=32, max_ram_units=64, max_gpu_slots=8, max_npu_slots=8, max_cost_units=500.0),
        failure_semantics=FailureSemantics.ROLLBACK,
    )
    rg = RealizationGraph(
        "rg_01",
        {
            "parse": RealizationNode("parse", role="parser"),
            "work": RealizationNode("work", role="worker"),
            "verify": RealizationNode("verify", role="verifier", authority_tier="verifier"),
            "commit": RealizationNode("commit", role="commit", outputs=("out",)),
        },
        (("parse", "work"), ("work", "verify"), ("verify", "commit")),
    )
    bc = certify_composition_boundary("child-01", rg, pc)
    assert bc.is_accepted and verify_composition_boundary(bc, rg, pc)


def test_level_7_distributed_authority_and_quorum():
    """Level 7: Distributed Authority & Quorum Consensus."""
    from uow import (
        ActorBinding,
        AuthoritativeHistory,
        AuthorityObligation,
        CausalConstraint,
        EvidenceObligation,
        FailureSemantics,
        ParentContract,
        RealizationGraph,
        RealizationNode,
        ResourceConstraint,
        TemporalConstraint,
    )
    from uow.composition import QuorumMutationCoordinator, assemble_mutation_qc

    pc = ParentContract(
        contract_id="pc_01",
        description="Cybernetic boundary",
        required_outputs=("out",),
        causal_constraints=(
            CausalConstraint("parser", "worker"),
            CausalConstraint("worker", "verifier"),
            CausalConstraint("verifier", "commit"),
        ),
        authority=AuthorityObligation(required_role="verifier", min_evidence_level="portable", quorum_threshold=1),
        evidence=EvidenceObligation(require_provenance=True, require_hash_chain=True, min_evidence_level="portable", verifier_id="recursive-test-judge"),
        temporal=TemporalConstraint(max_duration_ms=5000.0),
        resources=ResourceConstraint(max_cpu_cores=32, max_ram_units=64, max_gpu_slots=8, max_npu_slots=8, max_cost_units=500.0),
        failure_semantics=FailureSemantics.ROLLBACK,
    )
    rg = RealizationGraph(
        "rg_01",
        {
            "parse": RealizationNode("parse", role="parser"),
            "work": RealizationNode("work", role="worker"),
            "verify": RealizationNode("verify", role="verifier", authority_tier="verifier"),
            "commit": RealizationNode("commit", role="commit", outputs=("out",)),
        },
        (("parse", "work"), ("work", "verify"), ("verify", "commit")),
    )
    binding_0 = ActorBinding("b0", "rg_01", {"parse": "a1", "work": "a1", "verify": "a1", "commit": "a1"})
    binding_1 = ActorBinding("b1", "rg_01", {"parse": "a1", "work": "a1", "verify": "a1", "commit": "a1"})
    auth_keys = {"a1": "k1_secret", "a2": "k2_secret", "a3": "k3_secret"}

    qmc = QuorumMutationCoordinator(
        parent_contract=pc,
        active_graph=rg,
        active_binding=binding_0,
        history=AuthoritativeHistory(),
        authority_keys=auth_keys,
        generation=0,
        quorum_threshold=2,
    )
    prop = qmc.propose_mutation("npu_proposer", rg, binding_1)
    votes = qmc.collect_votes(prop)
    qc, msg = assemble_mutation_qc(prop, votes[:2], threshold=2)
    assert qc is not None and msg == "QUORUM_CERTIFICATE_ASSEMBLED"
    ok, status = qmc.apply_mutation(qc, rg, binding_1)
    assert ok is True and status == "MUTATION_COMMITTED"
    assert qmc.generation == 1


def test_level_8_bounded_semantic_mediation():
    """Level 8: Bounded Semantic Mediation & Governed Egress."""
    from uow import WorldState
    from uow.semantic import (
        DefaultSemanticAdmissibilityValidator,
        GovernedEgressEngine,
        IngressContext,
        RecipientProfile,
        SemanticApplicationAdapter,
        SemanticDisposition,
        SemanticHarness,
        SemanticRequirement,
        TransferUoWCompiler,
    )
    from uow.transactions import DeterministicSequencer

    state_sem = WorldState(attributes={"default_operator": "transfer", "default_quantity": 10})
    ingress = IngressContext(principal_id="user-1", session_id="s1", channel="text", metadata={"recipient": "Bob"})
    sh = SemanticHarness(admissibility_validator=DefaultSemanticAdmissibilityValidator())
    sem_res = sh.interpret(
        "Execute standard transfer",
        state=state_sem,
        ingress=ingress,
        requirements=(
            SemanticRequirement("operator", state_key="default_operator"),
            SemanticRequirement("quantity", state_key="default_quantity"),
            SemanticRequirement("recipient", ingress_key="recipient"),
        ),
    )
    assert sem_res.disposition is SemanticDisposition.YES
    adapter = SemanticApplicationAdapter()
    prep = adapter.prepare(sem_res, state_sem, TransferUoWCompiler())
    sem_seq = DeterministicSequencer(state_sem)
    app_res = adapter.execute(prep, sem_seq)
    assert app_res.state.attributes["transfers.Bob"] == 10

    eg = GovernedEgressEngine()
    eg_msg = eg.emit(sem_res, RecipientProfile.default_human(), status="COMMITTED")
    assert eg_msg.mode == "DETERMINISTIC"


def test_level_9_design_policy_plane():
    """Level 9: Design / Policy Plane."""
    from uow.policy import DiscoveryEngine, DriftMonitor, PolicyRegistry, PolicyResolver, QualificationEngine

    policy_reg = PolicyRegistry()
    policy_res = PolicyResolver(policy_reg)
    discovery = DiscoveryEngine()
    qual_eng = QualificationEngine(policy_reg)
    drift_mon = DriftMonitor(registry=policy_reg)

    assert policy_reg.total_policies == 0
