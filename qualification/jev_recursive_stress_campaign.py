"""Phase-2 recursive scale stress campaign on the native UoW substrate.

The deterministic UoW runtime is the oracle. JEV is an optional observer only.
This experiment varies four scale dimensions with a bounded preregistered matrix:
recursive depth, recursive fan-out, actor population, and certified internal
substitution history.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import median, pstdev
from typing import Any, Mapping, Protocol, Sequence

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
)
from uow.composition.boundary import (
    certify_composition_boundary,
    verify_composition_boundary,
)
from uow.implementations.composition.actor_execution import (
    ActorExecutionRegistry,
    CertifiedRuntimeActor,
)
from qualification.jev_provider import (
    DEFAULT_JEV_MODEL,
    TypeSafeJevProvider,
    question_payload,
)


SCHEMA_VERSION = "uow.jev_recursive_stress.v1"
CONDITIONS = ("baseline", "lawful_rebind", "authority_loss")
DEFAULT_OUTPUT = Path("qualification/artifacts/jev_recursive_stress_results.json")


class JevProvider(Protocol):
    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class StressProfile:
    name: str
    axis: str
    depth: int
    branching: int
    extra_actors_per_runtime: int
    substitutions: int


DEFAULT_STRESS_PROFILES: tuple[StressProfile, ...] = (
    StressProfile("origin", "baseline", 0, 1, 0, 0),
    StressProfile("depth_4", "depth", 4, 1, 0, 0),
    StressProfile("depth_8", "depth", 8, 1, 0, 0),
    StressProfile("branch_2", "branching", 3, 2, 0, 0),
    StressProfile("branch_4", "branching", 3, 4, 0, 0),
    StressProfile("actors_16", "actors", 2, 2, 16, 0),
    StressProfile("actors_64", "actors", 2, 2, 64, 0),
    StressProfile("substitutions_4", "substitutions", 2, 2, 8, 4),
    StressProfile("substitutions_16", "substitutions", 2, 2, 8, 16),
    StressProfile("combined_corner", "combined", 4, 3, 16, 16),
)


@dataclass(frozen=True)
class StressThresholds:
    min_signal_to_noise: float = 2.0
    min_authority_to_control_separation: float = 2.0
    min_cross_profile_cosine: float = 0.90
    max_authority_norm_cv: float = 0.25


@dataclass
class RuntimeTree:
    runtime: AdaptiveCompositionRuntime
    certificate: Any
    children: list["RuntimeTree"]
    path: str

    def flatten(self) -> list["RuntimeTree"]:
        nodes = [self]
        for child in self.children:
            nodes.extend(child.flatten())
        return nodes

    def leftmost_leaf(self) -> "RuntimeTree":
        current = self
        while current.children:
            current = current.children[0]
        return current


def make_contract(contract_id: str, output_key: str) -> ParentContract:
    return ParentContract(
        contract_id=contract_id,
        description=f"Recursive stress contract {contract_id}",
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
            verifier_id="jev-recursive-stress-judge",
        ),
        temporal=TemporalConstraint(max_duration_ms=100000.0),
        resources=ResourceConstraint(
            max_cpu_cores=128,
            max_ram_units=256,
            max_gpu_slots=16,
            max_npu_slots=16,
            max_cost_units=10000.0,
        ),
        failure_semantics=FailureSemantics.ROLLBACK,
    )


def make_leaf_graph(graph_id: str, output_key: str) -> RealizationGraph:
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


def make_parent_graph(
    graph_id: str,
    output_key: str,
    branching: int,
) -> RealizationGraph:
    nodes: dict[str, RealizationNode] = {
        "parse": RealizationNode("parse", role="parser"),
        "resolve": RealizationNode("resolve", role="worker"),
        "verify": RealizationNode(
            "verify",
            role="verifier",
            authority_tier="verifier",
        ),
        "commit": RealizationNode("commit", role="commit", outputs=(output_key,)),
    }
    edges: list[tuple[str, str]] = []
    for index in range(branching):
        node_id = f"child_{index}"
        nodes[node_id] = RealizationNode(node_id, role="worker")
        edges.append(("parse", node_id))
        edges.append((node_id, "resolve"))
    edges.extend((("resolve", "verify"), ("verify", "commit")))
    return RealizationGraph(graph_id, nodes, tuple(edges))


def _descriptor_for_node(prefix: str, node: RealizationNode) -> ActorDescriptor:
    authority = (
        AuthorityClass.VERIFIER
        if node.required_authority_class == "VERIFIER"
        else AuthorityClass.AUTHORITY_SUBSTRATE
        if node.required_authority_class == "AUTHORITY_SUBSTRATE"
        else AuthorityClass.PROPOSER_ONLY
    )
    return ActorDescriptor(
        f"{prefix}:{node.node_id}",
        tuple(node.required_capabilities),
        "cpu",
        authority_class=authority,
    )


def make_runtime(
    *,
    path: str,
    branching: int,
    is_leaf: bool,
    extra_actors: int,
) -> tuple[AdaptiveCompositionRuntime, Any]:
    output_key = "root_result" if path == "root" else f"{path.replace('/', '_')}_result"
    contract = make_contract(f"{path}:contract", output_key)
    graph = (
        make_leaf_graph(f"{path}:graph", output_key)
        if is_leaf
        else make_parent_graph(f"{path}:graph", output_key, branching)
    )
    registry = ActorRegistry(
        [_descriptor_for_node(path, node) for node in graph.nodes.values()]
    )
    for index in range(extra_actors):
        registry.register(
            ActorDescriptor(
                f"{path}:extra-worker:{index}",
                ("role:worker",),
                "cpu_pool",
                authority_class=AuthorityClass.PROPOSER_ONLY,
                load=(index % 10) / 20.0,
                latency_ms=1.0 + (index % 7) * 0.1,
            )
        )
    binding = ActorBinding(
        f"{path}:binding",
        graph.graph_id,
        {node_id: f"{path}:{node_id}" for node_id in graph.nodes},
    )
    runtime = AdaptiveCompositionRuntime(
        contract=contract,
        baseline_graph=graph,
        registry=registry,
        baseline_binding=binding,
        executors=ActorExecutionRegistry(),
    )
    certificate = certify_composition_boundary(path, graph, contract)
    if not certificate.is_accepted:
        raise RuntimeError(f"Boundary certification failed at {path}: {certificate.violations}")
    return runtime, certificate


def build_tree(profile: StressProfile) -> RuntimeTree:
    if profile.depth < 0:
        raise ValueError("depth must be >= 0")
    if profile.branching < 1:
        raise ValueError("branching must be >= 1")

    def build(level: int, path: str) -> RuntimeTree:
        is_leaf = level == 0
        runtime, certificate = make_runtime(
            path=path,
            branching=profile.branching,
            is_leaf=is_leaf,
            extra_actors=profile.extra_actors_per_runtime,
        )
        if is_leaf:
            return RuntimeTree(runtime, certificate, [], path)

        children = [
            build(level - 1, f"{path}/c{index}")
            for index in range(profile.branching)
        ]
        mapping = dict(runtime.active_binding.node_to_actor)
        for index, child in enumerate(children):
            node_id = f"child_{index}"
            actor_id = f"{path}:recursive:{index}"
            adapter = CertifiedRuntimeActor(
                surface_id=child.certificate.subject_id,
                runtime=child.runtime,
                boundary_certificate=child.certificate,
            )
            runtime.registry.register(
                adapter.descriptor(actor_id, ("role:worker",))
            )
            runtime.executors.register(actor_id, adapter)
            mapping[node_id] = actor_id

        rebound = ActorBinding(
            f"{path}:recursive-binding",
            runtime.active_graph.graph_id,
            mapping,
        )
        ok, violations = runtime.rebind_active_graph(rebound)
        if not ok:
            raise RuntimeError(f"Recursive binding failed at {path}: {violations}")
        return RuntimeTree(runtime, certificate, children, path)

    return build(profile.depth, "root")


def _parallel_leaf_graph(path: str, output_key: str) -> RealizationGraph:
    return RealizationGraph(
        f"{path}:parallel",
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
            "commit": RealizationNode("commit", role="commit", outputs=(output_key,)),
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


def apply_substitutions(tree: RuntimeTree, count: int) -> int:
    if count <= 0:
        return 0
    leaf = tree.leftmost_leaf()
    runtime = leaf.runtime
    baseline_graph = runtime.baseline_graph
    baseline_binding = runtime.baseline_binding
    output_key = runtime.contract.required_outputs[0]
    alt_graph = _parallel_leaf_graph(leaf.path, output_key)

    for node_id in ("work_a", "work_b", "resolve"):
        runtime.registry.register(
            ActorDescriptor(
                f"{leaf.path}:{node_id}",
                ("role:worker",),
                "cpu",
            )
        )
    alt_binding = ActorBinding(
        f"{leaf.path}:parallel-binding",
        alt_graph.graph_id,
        {
            "parse": f"{leaf.path}:parse",
            "work_a": f"{leaf.path}:work_a",
            "work_b": f"{leaf.path}:work_b",
            "resolve": f"{leaf.path}:resolve",
            "verify": f"{leaf.path}:verify",
            "commit": f"{leaf.path}:commit",
        },
    )

    accepted = 0
    for index in range(count):
        use_alt = runtime.active_graph.graph_id == baseline_graph.graph_id
        candidate_graph = alt_graph if use_alt else baseline_graph
        candidate_binding = alt_binding if use_alt else baseline_binding
        proposal = GraphReplacementProposal(
            parent_contract_id=runtime.contract.contract_id,
            current_graph_hash=runtime.current_graph_hash,
            candidate_graph=candidate_graph,
            strategy=SubstitutionStrategy.PARALLEL_DECOMPOSITION,
            proposal_id=f"{leaf.path}:stress-substitution:{index}",
            actor_binding=candidate_binding,
        )
        certificate = runtime.propose_and_certify(proposal)
        if not certificate.is_accepted:
            raise RuntimeError(
                f"Stress substitution {index} rejected at {leaf.path}: {certificate.violations}"
            )
        accepted += 1
    return accepted


def apply_lawful_rebind(tree: RuntimeTree) -> int:
    leaf = tree.leftmost_leaf()
    runtime = leaf.runtime
    worker_nodes = [
        node
        for node in runtime.active_graph.nodes.values()
        if node.role == "worker"
    ]
    if not worker_nodes:
        raise RuntimeError("No worker node available for lawful rebind")
    target = sorted(worker_nodes, key=lambda node: node.node_id)[0]
    actor_id = f"{leaf.path}:lawful-rebind"
    runtime.registry.register(
        ActorDescriptor(
            actor_id,
            tuple(target.required_capabilities),
            "cpu_replacement",
            authority_class=AuthorityClass.PROPOSER_ONLY,
        )
    )
    mapping = dict(runtime.active_binding.node_to_actor)
    mapping[target.node_id] = actor_id
    rebound = ActorBinding(
        f"{leaf.path}:lawful-rebind-binding",
        runtime.active_graph.graph_id,
        mapping,
    )
    ok, violations = runtime.rebind_active_graph(rebound)
    if not ok:
        raise RuntimeError(f"Lawful stress rebind rejected: {violations}")
    return 1


def apply_authority_loss(tree: RuntimeTree) -> None:
    leaf = tree.leftmost_leaf()
    verifier_nodes = [
        node
        for node in leaf.runtime.active_graph.nodes.values()
        if node.role == "verifier"
    ]
    if not verifier_nodes:
        raise RuntimeError("No verifier node found for authority-loss control")
    verifier = verifier_nodes[0]
    actor_id = leaf.runtime.active_binding.node_to_actor[verifier.node_id]
    leaf.runtime.registry.update_status(actor_id, availability=False)


def _boundary_status(nodes: Sequence[RuntimeTree]) -> tuple[bool, list[list[str]]]:
    all_valid = True
    violations_all: list[list[str]] = []
    for node in nodes:
        valid, violations = verify_composition_boundary(
            node.certificate,
            node.runtime.active_graph,
            node.runtime.contract,
        )
        all_valid = all_valid and valid
        violations_all.append(list(violations))
    return all_valid, violations_all


def _count_evidence_links(nodes: Sequence[RuntimeTree]) -> int:
    links = 0
    for node in nodes:
        if not node.runtime.execution_history:
            continue
        record = node.runtime.execution_history[-1]
        links += sum(bool(result.child_record_hash) for result in record.node_results)
    return links


def _error_class(message: str) -> str:
    if not message:
        return "none"
    for marker, label in (
        ("ACTOR_UNAVAILABLE", "actor_unavailable"),
        ("RECURSIVE_BOUNDARY_INVALID", "recursive_boundary_invalid"),
        ("RECURSIVE_CYCLE_DETECTED", "recursive_cycle"),
        ("ACTOR_OUTPUT_DEFICIT", "actor_output_deficit"),
        ("CHILD_EXECUTION_FAILED", "child_execution_failed"),
    ):
        if marker in message:
            return label
    return "other_failure"


def run_profile_condition(
    profile: StressProfile,
    condition: str,
) -> dict[str, Any]:
    tree = build_tree(profile)
    nodes = tree.flatten()
    original_certificate_hashes = [
        node.certificate.compute_hash() for node in nodes
    ]

    substitutions_accepted = apply_substitutions(tree, profile.substitutions)
    rebind_count = 0
    if condition == "lawful_rebind":
        rebind_count = apply_lawful_rebind(tree)
    elif condition == "authority_loss":
        apply_authority_loss(tree)
    elif condition != "baseline":
        raise ValueError(f"Unknown condition: {condition}")

    boundary_valid, boundary_violations = _boundary_status(nodes)
    current_certificate_hashes = [
        node.certificate.compute_hash() for node in nodes
    ]

    root_record = tree.runtime.execute({"payload": "jev-recursive-stress"})
    actor_population = sum(
        len(node.runtime.registry.all_actors()) for node in nodes
    )
    recursive_edges = max(0, len(nodes) - 1)
    evidence_links = _count_evidence_links(nodes)
    expected_success = condition in {"baseline", "lawful_rebind"}
    behavior_ok = (
        root_record.status == "SUCCESS"
        if expected_success
        else root_record.status == "FAILED"
        and "ACTOR_UNAVAILABLE" in root_record.error_message
    )
    evidence_ok = (
        evidence_links == recursive_edges
        if expected_success
        else evidence_links <= recursive_edges
    )
    certificates_stable = original_certificate_hashes == current_certificate_hashes

    normalized_state = {
        "subject": "governed_recursive_unit",
        "stress_profile_axis": profile.axis,
        "recursive_depth": profile.depth,
        "branching_factor": profile.branching,
        "runtime_count": len(nodes),
        "actor_population": actor_population,
        "extra_actor_population_per_runtime": profile.extra_actors_per_runtime,
        "certified_substitution_count": substitutions_accepted,
        "worker_binding_change_count": rebind_count,
        "unavailable_verifier_count": 1 if condition == "authority_loss" else 0,
        "all_composition_boundaries_valid": boundary_valid,
        "composition_certificate_changed": not certificates_stable,
        "root_execution_status": root_record.status.lower(),
        "declared_root_output_emitted": bool(root_record.final_outputs),
        "recursive_evidence_link_count": evidence_links,
        "expected_recursive_evidence_link_count": recursive_edges,
        "execution_error_class": _error_class(root_record.error_message),
    }

    oracle = {
        "boundary_valid": boundary_valid,
        "certificate_hashes_stable": certificates_stable,
        "substitutions_accepted": substitutions_accepted == profile.substitutions,
        "evidence_links_valid": evidence_ok,
        "root_output_signature_valid": (
            tuple(root_record.final_outputs.keys()) == ("root_result",)
            if expected_success
            else not root_record.final_outputs
        ),
        "passes_expected_behavior": behavior_ok,
    }

    return {
        "profile": asdict(profile),
        "condition": condition,
        "state": normalized_state,
        "oracle": oracle,
        "diagnostics": {
            "boundary_violations": boundary_violations,
            "root_evidence_root": root_record.evidence_root,
            "root_error_message": root_record.error_message,
        },
    }


def build_stress_states(
    profiles: Sequence[StressProfile] = DEFAULT_STRESS_PROFILES,
) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    for profile in profiles:
        for condition in CONDITIONS:
            states.append(run_profile_condition(profile, condition))
    return states


def deterministic_summary(states: Sequence[dict[str, Any]]) -> dict[str, Any]:
    gates = {
        "S0_all_boundaries_valid": all(
            item["oracle"]["boundary_valid"] for item in states
        ),
        "S1_certificate_hashes_stable": all(
            item["oracle"]["certificate_hashes_stable"] for item in states
        ),
        "S2_all_substitutions_certified": all(
            item["oracle"]["substitutions_accepted"] for item in states
        ),
        "S3_recursive_evidence_consistent": all(
            item["oracle"]["evidence_links_valid"] for item in states
        ),
        "S4_root_semantics_invariant": all(
            item["oracle"]["root_output_signature_valid"] for item in states
        ),
        "S5_expected_behavior_all_profiles": all(
            item["oracle"]["passes_expected_behavior"] for item in states
        ),
    }
    return {
        "profile_count": len({item["profile"]["name"] for item in states}),
        "state_count": len(states),
        "maximum_runtime_count": max(item["state"]["runtime_count"] for item in states),
        "maximum_actor_population": max(item["state"]["actor_population"] for item in states),
        "maximum_certified_substitution_count": max(
            item["state"]["certified_substitution_count"] for item in states
        ),
        "gates": gates,
        "passed": all(gates.values()),
    }


def _mean_vector(vectors: Sequence[Sequence[float]]) -> list[float]:
    width = len(vectors[0])
    return [sum(vector[i] for vector in vectors) / len(vectors) for i in range(width)]


def _subtract(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [x - y for x, y in zip(a, b)]


def _norm(vector: Sequence[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def _distance(a: Sequence[float], b: Sequence[float]) -> float:
    return _norm(_subtract(a, b))


def _cosine(a: Sequence[float], b: Sequence[float]) -> float | None:
    denom = _norm(a) * _norm(b)
    if denom <= 1e-15:
        return None
    return max(
        -1.0,
        min(1.0, sum(x * y for x, y in zip(a, b)) / denom),
    )


def analyze_observations(
    deterministic_states: Sequence[dict[str, Any]],
    observations: Sequence[dict[str, Any]],
    *,
    profiles: Sequence[StressProfile],
    replicates: int,
    thresholds: StressThresholds,
) -> dict[str, Any]:
    summary = deterministic_summary(deterministic_states)
    grouped: dict[tuple[str, str], list[list[float]]] = {}
    for observation in observations:
        key = (str(observation["profile"]), str(observation["condition"]))
        vector = [float(value) for value in observation["provider"]["vector"]]
        grouped.setdefault(key, []).append(vector)

    expected_groups = len(profiles) * len(CONDITIONS)
    provider_complete = (
        len(grouped) == expected_groups
        and all(len(vectors) == replicates for vectors in grouped.values())
    )

    repeatability: list[float] = []
    for vectors in grouped.values():
        for i in range(len(vectors)):
            for j in range(i + 1, len(vectors)):
                repeatability.append(_distance(vectors[i], vectors[j]))
    noise_floor = median(repeatability) if repeatability else 0.0

    means = {key: _mean_vector(vectors) for key, vectors in grouped.items()}
    authority_deltas: dict[str, list[float]] = {}
    authority_norms: dict[str, float] = {}
    control_norms: dict[str, float] = {}

    if provider_complete:
        for profile in profiles:
            baseline = means[(profile.name, "baseline")]
            lawful = means[(profile.name, "lawful_rebind")]
            loss = means[(profile.name, "authority_loss")]
            control = _subtract(lawful, baseline)
            authority = _subtract(loss, baseline)
            authority_deltas[profile.name] = authority
            authority_norms[profile.name] = _norm(authority)
            control_norms[profile.name] = _norm(control)

    pairwise: list[dict[str, Any]] = []
    numeric_cosines: list[float] = []
    names = [profile.name for profile in profiles]
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            cosine = _cosine(
                authority_deltas.get(names[i], []),
                authority_deltas.get(names[j], []),
            ) if provider_complete else None
            pairwise.append(
                {"profile_a": names[i], "profile_b": names[j], "cosine": cosine}
            )
            if cosine is not None:
                numeric_cosines.append(cosine)

    min_cosine = min(numeric_cosines) if numeric_cosines else None
    norms = list(authority_norms.values())
    mean_norm = sum(norms) / len(norms) if norms else 0.0
    norm_cv = (
        pstdev(norms) / mean_norm
        if len(norms) > 1 and mean_norm > 1e-15
        else 0.0
    )
    median_authority = median(norms) if norms else 0.0
    controls = list(control_norms.values())
    median_control = median(controls) if controls else 0.0
    floor = 1e-12
    signal_to_noise = median_authority / max(noise_floor, floor)
    separation = median_authority / max(median_control, noise_floor, floor)

    axis_metrics: dict[str, dict[str, Any]] = {}
    for axis in sorted({profile.axis for profile in profiles}):
        axis_names = [profile.name for profile in profiles if profile.axis == axis]
        axis_cosines = [
            item["cosine"]
            for item in pairwise
            if item["cosine"] is not None
            and item["profile_a"] in axis_names
            and item["profile_b"] in axis_names
        ]
        axis_norms = [authority_norms[name] for name in axis_names if name in authority_norms]
        axis_mean = sum(axis_norms) / len(axis_norms) if axis_norms else 0.0
        axis_metrics[axis] = {
            "profiles": axis_names,
            "minimum_cosine": min(axis_cosines) if axis_cosines else None,
            "norm_cv": (
                pstdev(axis_norms) / axis_mean
                if len(axis_norms) > 1 and axis_mean > 1e-15
                else 0.0
            ),
        }

    gates = {
        "S0_native_stress_oracle": summary["passed"],
        "J0_provider_complete": provider_complete,
        "J1_authority_signal_above_repeatability": provider_complete
        and signal_to_noise >= thresholds.min_signal_to_noise,
        "J2_authority_distinct_from_lawful_rebind": provider_complete
        and separation >= thresholds.min_authority_to_control_separation,
        "J3_cross_profile_direction_stable": provider_complete
        and min_cosine is not None
        and min_cosine >= thresholds.min_cross_profile_cosine,
        "J4_cross_profile_magnitude_stable": provider_complete
        and norm_cv <= thresholds.max_authority_norm_cv,
    }

    return {
        "deterministic_summary": summary,
        "provider_complete": provider_complete,
        "repeatability_noise_floor_l2": noise_floor,
        "median_lawful_rebind_delta_norm": median_control,
        "median_authority_loss_delta_norm": median_authority,
        "authority_signal_to_noise": signal_to_noise,
        "authority_to_lawful_rebind_separation": separation,
        "minimum_authority_loss_cosine_across_profiles": min_cosine,
        "authority_loss_norm_cv_across_profiles": norm_cv,
        "axis_metrics": axis_metrics,
        "pairwise_authority_loss_cosines": pairwise,
        "thresholds": asdict(thresholds),
        "gates": gates,
        "supported_within_engineering_gates": all(gates.values()),
        "verdict": (
            "SUPPORTED_WITHIN_PREREGISTERED_STRESS_GATES"
            if all(gates.values())
            else "NOT_SUPPORTED_BY_THIS_STRESS_RUN"
        ),
    }


def run_live_experiment(
    *,
    provider: JevProvider,
    profiles: Sequence[StressProfile],
    replicates: int,
    thresholds: StressThresholds,
) -> dict[str, Any]:
    deterministic_states = build_stress_states(profiles)
    questions = question_payload()
    observations: list[dict[str, Any]] = []

    for item in deterministic_states:
        profile_name = str(item["profile"]["name"])
        condition = str(item["condition"])
        for replicate in range(replicates):
            request_id = f"uow-recursive-stress-{profile_name}-{condition}-r{replicate}"
            provider_result = provider.decide(
                state=dict(item["state"]),
                questions=questions,
                request_id=request_id,
            )
            observations.append(
                {
                    "profile": profile_name,
                    "condition": condition,
                    "replicate": replicate,
                    "provider": provider_result,
                }
            )

    analysis = analyze_observations(
        deterministic_states,
        observations,
        profiles=profiles,
        replicates=replicates,
        thresholds=thresholds,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "JEV recursive UoW multi-axis scale stress invariance",
        "hypothesis": (
            "The authority-loss observer displacement remains directionally and "
            "approximately magnitude-stable across bounded increases in recursion "
            "depth, fan-out, actor population, and certified substitution history."
        ),
        "method": {
            "profiles": [asdict(profile) for profile in profiles],
            "conditions": list(CONDITIONS),
            "replicates_per_state": replicates,
            "questions_per_request": len(questions),
            "requests_total": len(profiles) * len(CONDITIONS) * replicates,
            "jev_role": "observer_only",
            "uow_role": "deterministic_oracle_and_execution_surface",
        },
        "questions": questions,
        "deterministic_states": deterministic_states,
        "observations": observations,
        "analysis": analysis,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Phase-2 JEV recursive multi-axis stress experiment."
    )
    parser.add_argument("--model", default=DEFAULT_JEV_MODEL)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--min-cosine", type=float, default=0.90)
    parser.add_argument("--max-norm-cv", type=float, default=0.25)
    parser.add_argument("--min-signal-noise", type=float, default=2.0)
    parser.add_argument("--min-separation", type=float, default=2.0)
    args = parser.parse_args()

    if args.replicates < 2:
        parser.error("--replicates must be >= 2")

    thresholds = StressThresholds(
        min_signal_to_noise=args.min_signal_noise,
        min_authority_to_control_separation=args.min_separation,
        min_cross_profile_cosine=args.min_cosine,
        max_authority_norm_cv=args.max_norm_cv,
    )

    if args.prepare_only:
        states = build_stress_states()
        payload = {
            "schema_version": SCHEMA_VERSION,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "prepare_only",
            "profiles": [asdict(profile) for profile in DEFAULT_STRESS_PROFILES],
            "conditions": list(CONDITIONS),
            "deterministic_states": states,
            "deterministic_summary": deterministic_summary(states),
        }
    else:
        provider = TypeSafeJevProvider(model=args.model, timeout_s=args.timeout_s)
        payload = run_live_experiment(
            provider=provider,
            profiles=DEFAULT_STRESS_PROFILES,
            replicates=args.replicates,
            thresholds=thresholds,
        )

    _write_json(args.output, payload)
    summary = payload.get("analysis") or payload.get("deterministic_summary")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"\nWrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
