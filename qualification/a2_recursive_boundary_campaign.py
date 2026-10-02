"""Portable qualification campaign for the native recursive composition boundary."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

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
    ParentContract,
    RealizationGraph,
    RealizationNode,
    ResourceConstraint,
    TemporalConstraint,
)
from uow.composition.boundary import (
    boundary_equivalent,
    certify_composition_boundary,
    contract_scope,
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


def _contract(contract_id: str, output_key: str) -> ParentContract:
    return ParentContract(
        contract_id=contract_id,
        description=f"Recursive boundary qualification contract {contract_id}",
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
            verifier_id="recursive-boundary-judge",
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


def _graph(graph_id: str, output_key: str) -> RealizationGraph:
    return RealizationGraph(
        graph_id,
        {
            "parse": RealizationNode("parse", role="parser"),
            "work": RealizationNode("work", role="worker"),
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
        (("parse", "work"), ("work", "verify"), ("verify", "commit")),
    )


def _runtime(prefix: str) -> tuple[AdaptiveCompositionRuntime, object]:
    contract = _contract(f"{prefix}:contract", f"{prefix}_result")
    graph = _graph(f"{prefix}:graph", f"{prefix}_result")
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
        graph.graph_id,
        {
            "parse": f"{prefix}:parse",
            "work": f"{prefix}:work",
            "verify": f"{prefix}:verify",
            "commit": f"{prefix}:commit",
        },
    )
    runtime = AdaptiveCompositionRuntime(
        contract,
        graph,
        registry=registry,
        baseline_binding=binding,
        executors=ActorExecutionRegistry(),
    )
    cert = certify_composition_boundary(prefix, graph, contract)
    assert cert.is_accepted
    return runtime, cert


def run_campaign() -> dict:
    print("=" * 80)
    print("A2 RECURSIVE BOUNDARY PORTABLE QUALIFICATION")
    print("=" * 80)

    # 1. Scope contraction proves that child-local roles are hidden before
    # parent semantic projection.
    parent_contract = _contract("scope:parent", "scope_result")
    contracted = _graph("scope:contracted", "scope_result")
    expanded = RealizationGraph(
        "scope:expanded",
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
                outputs=("child_private_result",),
            ),
            "p_verify": RealizationNode(
                "p_verify",
                role="verifier",
                authority_tier="verifier",
            ),
            "p_commit": RealizationNode(
                "p_commit",
                role="commit",
                outputs=("scope_result",),
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
    parent_view = contract_scope(
        expanded,
        scope_node_ids=("c_parse", "c_work", "c_verify", "c_commit"),
        replacement_node=RealizationNode("work", role="worker"),
        graph_id="scope:parent-view",
    )
    scope_conservation = boundary_equivalent(
        contracted,
        parent_view,
        parent_contract,
    )
    assert scope_conservation

    # 2. Native child runtime as one parent actor.
    child, child_boundary = _runtime("child")
    parent, parent_boundary = _runtime("parent")
    nested_actor_id = "parent:child-runtime"
    nested = CertifiedRuntimeActor(
        surface_id="child",
        runtime=child,
        boundary_certificate=child_boundary,
    )
    parent.registry.register(nested.descriptor(nested_actor_id, ("role:worker",)))
    parent.executors.register(nested_actor_id, nested)
    nested_binding_map = dict(parent.active_binding.node_to_actor)
    nested_binding_map["work"] = nested_actor_id
    ok, violations = parent.rebind_active_graph(
        ActorBinding(
            "parent:nested-binding",
            parent.active_graph.graph_id,
            nested_binding_map,
        )
    )
    assert ok, violations

    positive = parent.execute({"payload": "qualification-positive"})
    assert positive.status == "SUCCESS"
    child_record = child.execution_history[-1]
    parent_work = next(r for r in positive.node_results if r.node_id == "work")
    evidence_chained = parent_work.evidence_hash == child_record.evidence_root
    assert evidence_chained

    # 3. Internal recovery does not invalidate the parent boundary.
    parent_boundary_hash = parent_boundary.compute_hash()
    child.registry.register(
        ActorDescriptor(
            "child:work:alternate",
            ("role:worker",),
            "new_agent",
        )
    )
    child.registry.update_status("child:work", availability=False)
    child_map = dict(child.active_binding.node_to_actor)
    child_map["work"] = "child:work:alternate"
    rebound_ok, rebound_violations = child.rebind_active_graph(
        ActorBinding(
            "child:rebound",
            child.active_graph.graph_id,
            child_map,
        )
    )
    assert rebound_ok, rebound_violations

    recovered = parent.execute({"payload": "qualification-recovered"})
    internal_recovery = (
        recovered.status == "SUCCESS"
        and parent_boundary.compute_hash() == parent_boundary_hash
    )
    assert internal_recovery

    # 4. Negative control: nested authority loss must fail closed.
    child.registry.update_status("child:verify", availability=False)
    negative = parent.execute({"payload": "qualification-negative"})
    negative_control = (
        negative.status == "FAILED"
        and "ACTOR_UNAVAILABLE" in negative.error_message
    )
    assert negative_control

    spec = get_claim("A2.RECURSIVE_BOUNDARY.PORTABLE")
    claim = evaluate_claim(
        observed_pass=(
            scope_conservation
            and positive.status == "SUCCESS"
            and evidence_chained
            and internal_recovery
            and negative_control
        ),
        negative_control_pass=negative_control,
        context=EvidenceContext(
            level=EvidenceLevel.PORTABLE,
            source="qualification.a2_recursive_boundary_campaign",
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
    assert claim["qualified"] and claim["passed"]

    artifact = {
        "schema_version": "uow-a2-recursive-boundary-v1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scope_conservation": scope_conservation,
        "child_boundary_hash": child_boundary.compute_hash(),
        "parent_boundary_hash": parent_boundary.compute_hash(),
        "positive_status": positive.status,
        "positive_evidence_root": positive.evidence_root,
        "child_evidence_root": child_record.evidence_root,
        "evidence_chained": evidence_chained,
        "internal_recovery": internal_recovery,
        "negative_status": negative.status,
        "negative_error": negative.error_message,
        "negative_control": negative_control,
        "claim": {spec.claim_id: claim},
        "passed": True,
    }

    out_path = Path(
        "qualification/artifacts/a2-recursive-boundary-qualification.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(f"Saved qualification artifact to: {out_path}")
    print("A2.RECURSIVE_BOUNDARY.PORTABLE: QUALIFIED & PASSED")
    return artifact


if __name__ == "__main__":
    run_campaign()
