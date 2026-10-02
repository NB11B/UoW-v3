"""Qualification tests for native cybernetic recursion in UoW v2."""
from __future__ import annotations

import pytest

from uow.compat.v2 import (
    ActorBinding,
    ActorDescriptor,
    ActorRegistry,
    AdaptiveCompositionRuntime,
    AuthorityClass,
    AuthorityObligation,
    CausalConstraint,
    EvidenceObligation,
    FailureSemantics,
    GraphReplacementProposal,
    ParentContract,
    RealizationGraph,
    RealizationNode,
    ResourceConstraint,
    SubstitutionStrategy,
    TemporalConstraint,
    are_equivalent,
)
from uow.composition.boundary import (
    boundary_equivalent,
    certify_composition_boundary,
    contract_scope,
    verify_composition_boundary,
)
from uow.implementations.composition.actor_execution import (
    ActorExecutionRegistry,
    CertifiedRuntimeActor,
)
from qualification.claim_registry import get_claim
from qualification.evidence import (
    ClaimRequirement,
    EvidenceContext,
    EvidenceLevel,
    evaluate_claim,
)


def make_contract(contract_id: str, output_key: str) -> ParentContract:
    return ParentContract(
        contract_id=contract_id,
        description=f"Recursive cybernetic contract {contract_id}",
        required_outputs=(output_key,),
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
            verifier_id="recursive-test-judge",
        ),
        temporal=TemporalConstraint(max_duration_ms=5000.0),
        resources=ResourceConstraint(
            max_cpu_cores=32,
            max_ram_units=64,
            max_gpu_slots=8,
            max_npu_slots=8,
            max_cost_units=500.0,
        ),
        failure_semantics=FailureSemantics.ROLLBACK,
    )


def make_graph(
    graph_id: str,
    output_key: str,
    *,
    worker_outputs: tuple[str, ...] = (),
) -> RealizationGraph:
    return RealizationGraph(
        graph_id,
        {
            "parse": RealizationNode("parse", role="parser"),
            "work": RealizationNode("work", role="worker", outputs=worker_outputs),
            "verify": RealizationNode(
                "verify",
                role="verifier",
                authority_tier="verifier",
            ),
            "commit": RealizationNode(
                "commit",
                role="commit",
                outputs=(output_key,),
            ),
        },
        (
            ("parse", "work"),
            ("work", "verify"),
            ("verify", "commit"),
        ),
    )


def make_registry_binding(
    prefix: str,
    graph_id: str,
) -> tuple[ActorRegistry, ActorBinding]:
    registry = ActorRegistry(
        [
            ActorDescriptor(f"{prefix}:parse", ("role:parser",), "cpu"),
            ActorDescriptor(f"{prefix}:work", ("role:worker",), "cpu"),
            ActorDescriptor(
                f"{prefix}:verify",
                ("role:verifier",),
                "cpu",
                authority_class=AuthorityClass.VERIFIER,
            ),
            ActorDescriptor(f"{prefix}:commit", ("role:commit",), "cpu"),
        ]
    )
    binding = ActorBinding(
        f"{prefix}:binding",
        graph_id,
        {
            "parse": f"{prefix}:parse",
            "work": f"{prefix}:work",
            "verify": f"{prefix}:verify",
            "commit": f"{prefix}:commit",
        },
    )
    return registry, binding


def make_runtime(
    prefix: str,
    *,
    worker_outputs: tuple[str, ...] = (),
) -> tuple[AdaptiveCompositionRuntime, object]:
    contract = make_contract(f"{prefix}:contract", f"{prefix}_result")
    graph = make_graph(
        f"{prefix}:graph",
        f"{prefix}_result",
        worker_outputs=worker_outputs,
    )
    registry, binding = make_registry_binding(prefix, graph.graph_id)
    runtime = AdaptiveCompositionRuntime(
        contract=contract,
        baseline_graph=graph,
        registry=registry,
        baseline_binding=binding,
        executors=ActorExecutionRegistry(),
    )
    cert = certify_composition_boundary(prefix, graph, contract)
    assert cert.is_accepted
    return runtime, cert


def wrap_runtime(
    child: AdaptiveCompositionRuntime,
    child_cert,
    level: int,
) -> tuple[AdaptiveCompositionRuntime, object, str]:
    prefix = f"level{level}"
    runtime, cert = make_runtime(prefix)
    actor_id = f"{prefix}:recursive-worker"
    adapter = CertifiedRuntimeActor(
        surface_id=child_cert.subject_id,
        runtime=child,
        boundary_certificate=child_cert,
    )
    runtime.registry.register(adapter.descriptor(actor_id, ("role:worker",)))
    runtime.executors.register(actor_id, adapter)

    mapping = dict(runtime.active_binding.node_to_actor)
    mapping["work"] = actor_id
    rebound = ActorBinding(
        f"{prefix}:recursive-binding",
        runtime.active_graph.graph_id,
        mapping,
    )
    ok, violations = runtime.rebind_active_graph(rebound)
    assert ok, violations
    return runtime, cert, actor_id


def test_recursive_scope_must_contract_before_parent_semantic_projection():
    parent = make_contract("parent:contract", "parent_result")
    contracted = make_graph("parent:contracted", "parent_result")

    expanded = RealizationGraph(
        "parent:expanded",
        {
            "p_parse": RealizationNode("p_parse", role="parser"),
            "c_parse": RealizationNode("c_parse", role="parser"),
            "c_work": RealizationNode("c_work", role="worker"),
            "c_verify": RealizationNode(
                "c_verify",
                role="verifier",
                authority_tier="verifier",
            ),
            "c_commit": RealizationNode(
                "c_commit",
                role="commit",
                outputs=("child_internal_result",),
            ),
            "p_verify": RealizationNode(
                "p_verify",
                role="verifier",
                authority_tier="verifier",
            ),
            "p_commit": RealizationNode(
                "p_commit",
                role="commit",
                outputs=("parent_result",),
            ),
        },
        (
            ("p_parse", "c_parse"),
            ("c_parse", "c_work"),
            ("c_work", "c_verify"),
            ("c_verify", "c_commit"),
            ("c_commit", "p_verify"),
            ("p_verify", "p_commit"),
        ),
    )

    assert not are_equivalent(contracted, expanded, parent)

    parent_view = contract_scope(
        expanded,
        scope_node_ids=("c_parse", "c_work", "c_verify", "c_commit"),
        replacement_node=RealizationNode("work", role="worker"),
        graph_id="parent:expanded:parent-view",
    )
    assert boundary_equivalent(contracted, parent_view, parent)
    assert are_equivalent(contracted, parent_view, parent)


def test_boundary_certificate_is_conformance_only_and_revalidates_current_graph():
    runtime, cert = make_runtime("leaf")
    ok, violations = verify_composition_boundary(
        cert,
        runtime.active_graph,
        runtime.contract,
    )
    assert ok
    assert violations == ()

    bad_graph = RealizationGraph(
        "leaf:bad",
        {
            "parse": RealizationNode("parse", role="parser"),
            "work": RealizationNode("work", role="worker"),
            "commit": RealizationNode(
                "commit",
                role="commit",
                outputs=("leaf_result",),
            ),
        },
        (("parse", "work"), ("work", "commit")),
    )
    rejected = certify_composition_boundary("bad", bad_graph, runtime.contract)
    assert not rejected.is_accepted
    assert any("A_AUTHORITY_ROLE_MISSING" in v for v in rejected.violations)


def test_native_runtime_recurses_six_levels_and_chains_child_evidence():
    leaf, leaf_cert = make_runtime("leaf")
    runtimes = [leaf]
    current = leaf
    current_cert = leaf_cert

    for level in range(1, 6):
        current, current_cert, _ = wrap_runtime(current, current_cert, level)
        runtimes.append(current)

    root = runtimes[-1]
    receipt = root.execute({"payload": "recursive-test"})

    assert receipt.status == "SUCCESS"
    assert receipt.final_outputs == {"level5_result": "computed_val_level5_result"}
    assert len(receipt.evidence_root) == 64

    for runtime in runtimes:
        assert len(runtime.execution_history) == 1
        assert len(runtime.execution_history[-1].evidence_root) == 64

    for parent_index in range(1, len(runtimes)):
        parent = runtimes[parent_index]
        child = runtimes[parent_index - 1]
        work_result = next(
            result
            for result in parent.execution_history[-1].node_results
            if result.node_id == "work"
        )
        assert work_result.evidence_hash == child.execution_history[-1].evidence_root
        assert work_result.child_record_hash


def test_new_agent_expands_child_control_variety_without_parent_recertification():
    leaf, leaf_cert = make_runtime("leaf")
    parent, parent_cert, _ = wrap_runtime(leaf, leaf_cert, 1)
    root, root_cert, _ = wrap_runtime(parent, parent_cert, 2)

    leaf_workers_before = leaf.registry.find_capable_actors(("role:worker",))
    parent_cert_hash = parent_cert.compute_hash()
    root_cert_hash = root_cert.compute_hash()

    leaf.registry.register(
        ActorDescriptor(
            "leaf:work:entrant",
            ("role:worker",),
            "new_agent",
            authority_class=AuthorityClass.PROPOSER_ONLY,
            latency_ms=0.5,
        )
    )

    leaf_workers_after = leaf.registry.find_capable_actors(("role:worker",))
    assert len(leaf_workers_after) > len(leaf_workers_before)
    assert parent_cert.compute_hash() == parent_cert_hash
    assert root_cert.compute_hash() == root_cert_hash
    assert root.execute({"payload": "after-admission"}).status == "SUCCESS"


def test_child_rebinds_after_actor_loss_without_parent_recertification():
    leaf, leaf_cert = make_runtime("leaf")
    parent, parent_cert, _ = wrap_runtime(leaf, leaf_cert, 1)
    root, root_cert, _ = wrap_runtime(parent, parent_cert, 2)

    leaf.registry.register(
        ActorDescriptor(
            "leaf:work:alternate",
            ("role:worker",),
            "new_agent",
            authority_class=AuthorityClass.PROPOSER_ONLY,
        )
    )
    leaf.registry.update_status("leaf:work", availability=False)

    mapping = dict(leaf.active_binding.node_to_actor)
    mapping["work"] = "leaf:work:alternate"
    rebound = ActorBinding(
        "leaf:rebound",
        leaf.active_graph.graph_id,
        mapping,
    )
    ok, violations = leaf.rebind_active_graph(rebound)
    assert ok, violations

    parent_hash = parent_cert.compute_hash()
    root_hash = root_cert.compute_hash()
    receipt = root.execute({"payload": "after-disturbance"})

    assert receipt.status == "SUCCESS"
    assert parent_cert.compute_hash() == parent_hash
    assert root_cert.compute_hash() == root_hash


def test_nested_authority_loss_fails_closed_through_parent_boundary():
    leaf, leaf_cert = make_runtime("leaf")
    parent, _, _ = wrap_runtime(leaf, leaf_cert, 1)

    leaf.registry.update_status("leaf:verify", availability=False)
    receipt = parent.execute({"payload": "authority-loss"})

    assert receipt.status == "FAILED"
    assert "CHILD_EXECUTION_FAILED" in receipt.error_message
    assert "ACTOR_UNAVAILABLE" in receipt.error_message


def test_recursive_cycle_is_detected_and_fails_closed():
    runtime, cert = make_runtime("cycle")
    actor_id = "cycle:self"
    adapter = CertifiedRuntimeActor(
        surface_id="cycle",
        runtime=runtime,
        boundary_certificate=cert,
    )
    runtime.registry.register(adapter.descriptor(actor_id, ("role:worker",)))
    runtime.executors.register(actor_id, adapter)

    mapping = dict(runtime.active_binding.node_to_actor)
    mapping["work"] = actor_id
    rebound = ActorBinding("cycle:self-binding", runtime.active_graph.graph_id, mapping)
    ok, violations = runtime.rebind_active_graph(rebound)
    assert ok, violations

    receipt = runtime.execute({"payload": "cycle"})
    assert receipt.status == "FAILED"
    assert "RECURSIVE_CYCLE_DETECTED" in receipt.error_message


def test_recursive_actor_maps_outputs_and_does_not_leak_child_namespace():
    child, child_cert = make_runtime("child")

    parent_contract = make_contract("parent:contract", "parent_result")
    parent_graph = make_graph(
        "parent:graph",
        "parent_result",
        worker_outputs=("parent_intermediate",),
    )
    registry, binding = make_registry_binding("parent", parent_graph.graph_id)
    executors = ActorExecutionRegistry()
    parent = AdaptiveCompositionRuntime(
        parent_contract,
        parent_graph,
        registry=registry,
        baseline_binding=binding,
        executors=executors,
    )

    actor_id = "parent:child-runtime"
    adapter = CertifiedRuntimeActor(
        surface_id="child",
        runtime=child,
        boundary_certificate=child_cert,
        output_mapping={"child_result": "parent_intermediate"},
    )
    registry.register(adapter.descriptor(actor_id, ("role:worker",)))
    executors.register(actor_id, adapter)

    mapping = dict(binding.node_to_actor)
    mapping["work"] = actor_id
    ok, violations = parent.rebind_active_graph(
        ActorBinding("parent:nested-binding", parent_graph.graph_id, mapping)
    )
    assert ok, violations

    receipt = parent.execute({"payload": "mapping"})
    assert receipt.status == "SUCCESS"

    work_result = next(r for r in receipt.node_results if r.node_id == "work")
    assert work_result.output_keys == ("parent_intermediate",)
    assert "child_result" not in receipt.final_outputs
    assert work_result.evidence_hash == child.execution_history[-1].evidence_root


def test_recursive_actor_fails_instead_of_synthesizing_missing_declared_output():
    child, child_cert = make_runtime("child")

    parent_contract = make_contract("parent:contract", "parent_result")
    parent_graph = make_graph(
        "parent:graph",
        "parent_result",
        worker_outputs=("parent_intermediate",),
    )
    registry, binding = make_registry_binding("parent", parent_graph.graph_id)
    executors = ActorExecutionRegistry()
    parent = AdaptiveCompositionRuntime(
        parent_contract,
        parent_graph,
        registry=registry,
        baseline_binding=binding,
        executors=executors,
    )

    actor_id = "parent:child-runtime"
    adapter = CertifiedRuntimeActor(
        surface_id="child",
        runtime=child,
        boundary_certificate=child_cert,
    )
    registry.register(adapter.descriptor(actor_id, ("role:worker",)))
    executors.register(actor_id, adapter)

    mapping = dict(binding.node_to_actor)
    mapping["work"] = actor_id
    ok, violations = parent.rebind_active_graph(
        ActorBinding("parent:nested-binding", parent_graph.graph_id, mapping)
    )
    assert ok, violations

    receipt = parent.execute({"payload": "missing-mapping"})
    assert receipt.status == "FAILED"
    assert "ACTOR_OUTPUT_DEFICIT" in receipt.error_message


def test_equivalent_internal_topology_can_change_without_parent_recertification():
    leaf, leaf_cert = make_runtime("leaf")
    parent, parent_cert, _ = wrap_runtime(leaf, leaf_cert, 1)

    alt_graph = RealizationGraph(
        "leaf:parallel",
        {
            "parse": RealizationNode("parse", role="parser"),
            "work_a": RealizationNode("work_a", role="worker"),
            "work_b": RealizationNode("work_b", role="worker"),
            "resolve": RealizationNode("resolve", role="worker"),
            "verify": RealizationNode(
                "verify",
                role="verifier",
                authority_tier="verifier",
            ),
            "commit": RealizationNode(
                "commit",
                role="commit",
                outputs=("leaf_result",),
            ),
        },
        (
            ("parse", "work_a"),
            ("parse", "work_b"),
            ("work_a", "resolve"),
            ("work_b", "resolve"),
            ("resolve", "verify"),
            ("verify", "commit"),
        ),
    )

    leaf.registry.register(ActorDescriptor("leaf:work:a", ("role:worker",), "cpu"))
    leaf.registry.register(ActorDescriptor("leaf:work:b", ("role:worker",), "cpu"))
    leaf.registry.register(ActorDescriptor("leaf:resolve", ("role:worker",), "cpu"))

    alt_binding = ActorBinding(
        "leaf:parallel-binding",
        alt_graph.graph_id,
        {
            "parse": "leaf:parse",
            "work_a": "leaf:work:a",
            "work_b": "leaf:work:b",
            "resolve": "leaf:resolve",
            "verify": "leaf:verify",
            "commit": "leaf:commit",
        },
    )

    proposal = GraphReplacementProposal(
        parent_contract_id=leaf.contract.contract_id,
        current_graph_hash=leaf.current_graph_hash,
        candidate_graph=alt_graph,
        strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
        proposal_id="leaf:parallelize",
        actor_binding=alt_binding,
    )
    replacement = leaf.propose_and_certify(proposal)
    assert replacement.is_accepted

    boundary_ok, violations = verify_composition_boundary(
        leaf_cert,
        leaf.active_graph,
        leaf.contract,
    )
    assert boundary_ok, violations

    parent_cert_hash = parent_cert.compute_hash()
    receipt = parent.execute({"payload": "after-internal-substitution"})
    assert receipt.status == "SUCCESS"
    assert parent_cert.compute_hash() == parent_cert_hash


def test_parent_rejects_child_boundary_drift_before_dispatch():
    child, child_cert = make_runtime("child")
    parent, _, _ = wrap_runtime(child, child_cert, 1)

    child.active_graph = RealizationGraph(
        "child:tampered",
        {
            "parse": RealizationNode("parse", role="parser"),
            "work": RealizationNode("work", role="worker"),
            "commit": RealizationNode(
                "commit",
                role="commit",
                outputs=("child_result",),
            ),
        },
        (("parse", "work"), ("work", "commit")),
    )

    receipt = parent.execute({"payload": "tamper"})
    assert receipt.status == "FAILED"
    assert "RECURSIVE_BOUNDARY_INVALID" in receipt.error_message


def test_recursive_boundary_portable_claim_is_qualified_with_negative_controls():
    spec = get_claim("A2.RECURSIVE_BOUNDARY.PORTABLE")

    leaf, leaf_cert = make_runtime("claim-leaf")
    parent, _, _ = wrap_runtime(leaf, leaf_cert, 1)
    positive = parent.execute({"payload": "claim-positive"}).status == "SUCCESS"

    # Negative control: authority loss inside the child must fail closed through
    # the parent boundary rather than being synthesized or silently bypassed.
    leaf.registry.update_status("claim-leaf:verify", availability=False)
    negative_record = parent.execute({"payload": "claim-negative"})
    negative = (
        negative_record.status == "FAILED"
        and "ACTOR_UNAVAILABLE" in negative_record.error_message
    )

    result = evaluate_claim(
        observed_pass=(positive and negative),
        negative_control_pass=negative,
        context=EvidenceContext(
            level=EvidenceLevel.PORTABLE,
            source="tests.test_composition_recursive_boundary",
            actual_components={
                "boundary": "CompositionBoundaryCertificate",
                "adapter": "CertifiedRuntimeActor",
                "runtime": "AdaptiveCompositionRuntime",
                "evidence": "ExecutionRecord.evidence_root",
            },
            substitutions={},
        ),
        requirement=ClaimRequirement(
            spec.required_level,
            spec.required_components,
        ),
    )
    assert result["qualified"]
    assert result["passed"]
