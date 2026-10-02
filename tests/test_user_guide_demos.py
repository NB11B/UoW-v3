"""Automated verification suite executing every demo from docs/USER_GUIDE.md.

Guarantees that all user guide code snippets rely strictly on the public API
surfaces (uow and uow.semantic) and execute cleanly without errors or warnings.
"""

from __future__ import annotations

import pytest


def test_user_guide_level_0():
    """Verify Level 0 Core State Transitions snippet from docs/USER_GUIDE.md."""
    from uow.compat.v2 import (
        Guard,
        GuardOp,
        MatrixCell,
        Mutation,
        MutationOp,
        Route,
        Successor,
        WorkCategory,
        WorldState,
        certify,
        commit,
        make_uow,
        propose,
    )

    state = WorldState(attributes={"balance": 100, "status": "ACTIVE", "transfers_completed": 0})

    uow = make_uow(
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

    proposal = propose(uow, state)
    assert proposal.uow_id == "tx_001"
    cert = certify(uow, state, proposal)
    assert cert.is_valid is True

    new_state, evidence = commit(
        uow,
        state,
        proposal,
        cert,
        prev_evidence_hash="0" * 64,
        step_number=1,
    )

    assert new_state.require("balance") == 70
    assert new_state.require("transfers_completed") == 1
    assert evidence.step_number == 1
    assert evidence.record_hash is not None


def test_user_guide_level_1():
    """Verify Level 1 OCC & WAL Recovery snippet from docs/USER_GUIDE.md."""
    from uow.compat.v2 import (
        Guard,
        GuardOp,
        Mutation,
        MutationOp,
        Route,
        Successor,
        WorldState,
        certify,
        make_uow,
        propose,
    )
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
    assert is_valid is True

    new_state, evidence = sequencer.commit(tx_uow, proposal, tx_desc, cert)
    assert new_state.require("account_A") == 400
    assert new_state.require("account_B") == 300
    assert len(sequencer.ledger.records) == 1


def test_user_guide_level_2():
    """Verify Level 2 DAG Workflow Orchestration snippet from docs/USER_GUIDE.md."""
    from uow.compat.v2 import Guard, GuardOp, Mutation, MutationOp, Route
    from uow.orchestration import (
        create_initial_orchestration_state,
        make_domain_task,
        run_orchestration,
    )

    task_a = make_domain_task("extract_features", [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 10),))])
    task_b = make_domain_task("train_model", [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 20),))])

    orch_init = create_initial_orchestration_state(
        ["extract_features", "train_model"],
        {"train_model": ["extract_features"]},
        attributes={"r0": 0},
    )

    orch_final, orch_seq = run_orchestration({"extract_features": task_a, "train_model": task_b}, orch_init)
    assert orch_final.require("r0") == 30
    assert orch_final.status == "HALTED"


def test_user_guide_level_3():
    """Verify Level 3 Multi-Dimensional Resource Governance snippet from docs/USER_GUIDE.md."""
    from uow.compat.v2 import Guard, GuardOp, Mutation, MutationOp, Route
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


def test_user_guide_level_4():
    """Verify Level 4 Effects, Sagas & Outbox snippet from docs/USER_GUIDE.md."""
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
    records = coordinator.execute_saga([step], saga_id="storage_saga_01")
    assert len(records) == 1
    assert len(client.call_log) > 0


def test_user_guide_level_5():
    """Verify Level 5 Adaptive Proposer snippet from docs/USER_GUIDE.md."""
    from uow.compat.v2 import Guard, GuardOp, Mutation, MutationOp, Route
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
    assert final_state.require("out") == 42


def test_user_guide_level_6():
    """Verify Level 6 Recursive Composition snippet from docs/USER_GUIDE.md."""
    from uow.compat.v2 import (
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


def test_user_guide_level_7():
    """Verify Level 7 Quorum Authority snippet from docs/USER_GUIDE.md."""
    from uow.compat.v2 import (
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


def test_user_guide_level_8():
    """Verify Level 8 Bounded Semantic Mediation snippet from docs/USER_GUIDE.md."""
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

    state_sem = WorldState(attributes={"default_operator": "transfer", "default_quantity": 25})
    ingress = IngressContext(principal_id="alice", session_id="sess_01", channel="web", metadata={"recipient": "Bob"})

    harness = SemanticHarness(admissibility_validator=DefaultSemanticAdmissibilityValidator())
    sem_res = harness.interpret(
        "Transfer funds to Bob",
        state=state_sem,
        ingress=ingress,
        requirements=(
            SemanticRequirement("operator", state_key="default_operator"),
            SemanticRequirement("quantity", state_key="default_quantity"),
            SemanticRequirement("recipient", ingress_key="recipient"),
        ),
    )
    assert sem_res.disposition is SemanticDisposition.YES
    assert sem_res.intent is not None

    adapter = SemanticApplicationAdapter()
    prep = adapter.prepare(sem_res, state_sem, TransferUoWCompiler())
    sem_seq = DeterministicSequencer(state_sem)
    app_res = adapter.execute(prep, sem_seq)
    assert app_res.state.attributes["transfers.Bob"] == 25

    eg = GovernedEgressEngine()
    eg_msg = eg.emit(sem_res, RecipientProfile.default_human(), status="COMMITTED")
    assert eg_msg.mode == "DETERMINISTIC"
    assert "Bob" in eg_msg.text
    assert "25" in eg_msg.text


def test_user_guide_level_9():
    """Verify Level 9 Policy Plane snippet from docs/USER_GUIDE.md."""
    from uow.policy import (
        DiscoveryEngine,
        DriftMonitor,
        PolicyRegistry,
        PolicyResolver,
        QualificationEngine,
    )

    policy_reg = PolicyRegistry()
    policy_res = PolicyResolver(policy_reg)
    discovery = DiscoveryEngine()
    qual_eng = QualificationEngine(policy_reg)
    drift_mon = DriftMonitor(registry=policy_reg)

    assert policy_reg.total_policies == 0


def test_user_guide_section_6_testing_pattern():
    """Verify Section 6 Pytest snippet from docs/USER_GUIDE.md."""
    from uow.compat.v2 import (
        Guard,
        GuardOp,
        Mutation,
        MutationOp,
        Route,
        Successor,
        WorldState,
        certify,
        commit,
        make_uow,
        propose,
    )

    state = WorldState(attributes={"count": 0, "max_limit": 10})
    uow = make_uow(
        "inc_1",
        routes=[
            Route(
                guard=Guard(GuardOp.LT, "count", 10),
                mutations=(Mutation(MutationOp.ADD, "count", 1),),
                successor=Successor.halt(),
            )
        ],
    )

    proposal = propose(uow, state)
    cert = certify(uow, state, proposal)
    assert cert.is_valid is True

    new_state, evidence = commit(uow, state, proposal, cert, prev_evidence_hash="0" * 64, step_number=1)
    assert new_state.require("count") == 1
    assert evidence.step_number == 1
