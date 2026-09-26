"""Single-surface JEV test of recursive UoW operator invariance.

Question
========
Does the semantic displacement associated with a bounded authority-loss
perturbation remain directionally and approximately magnitude-stable as the same
UoW control structure is embedded at greater recursive depth?

The UoW runtime remains the deterministic oracle. JEV never decides legality,
conformance, PASS/FAIL, arithmetic, or certification. It only observes the
canonical state snapshot through a fixed eight-coordinate probability battery.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import median, pstdev
from typing import Any, Mapping, Protocol, Sequence

from uow import (
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


SCHEMA_VERSION = "uow.jev_recursive_scale.v1"
CONDITIONS = ("baseline", "lawful_rebind", "authority_loss")
DEFAULT_OUTPUT = Path("qualification/artifacts/jev_recursive_scale_results.json")


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
class ExperimentThresholds:
    min_signal_to_noise: float = 2.0
    min_authority_to_control_separation: float = 2.0
    min_cross_depth_cosine: float = 0.90
    max_authority_norm_cv: float = 0.25


def make_contract(contract_id: str, output_key: str) -> ParentContract:
    return ParentContract(
        contract_id=contract_id,
        description=f"Recursive JEV scale contract {contract_id}",
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
            verifier_id="jev-recursive-scale-judge",
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


def make_graph(graph_id: str, output_key: str) -> RealizationGraph:
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


def make_runtime(prefix: str) -> tuple[AdaptiveCompositionRuntime, Any]:
    contract = make_contract(f"{prefix}:contract", f"{prefix}_result")
    graph = make_graph(f"{prefix}:graph", f"{prefix}_result")
    registry, binding = make_registry_binding(prefix, graph.graph_id)
    runtime = AdaptiveCompositionRuntime(
        contract=contract,
        baseline_graph=graph,
        registry=registry,
        baseline_binding=binding,
        executors=ActorExecutionRegistry(),
    )
    certificate = certify_composition_boundary(prefix, graph, contract)
    if not certificate.is_accepted:
        raise RuntimeError(f"Unable to certify test runtime {prefix}: {certificate.violations}")
    return runtime, certificate


def wrap_runtime(
    child: AdaptiveCompositionRuntime,
    child_certificate: Any,
    level: int,
) -> tuple[AdaptiveCompositionRuntime, Any]:
    prefix = f"level{level}"
    runtime, certificate = make_runtime(prefix)
    actor_id = f"{prefix}:recursive-worker"
    adapter = CertifiedRuntimeActor(
        surface_id=child_certificate.subject_id,
        runtime=child,
        boundary_certificate=child_certificate,
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
    if not ok:
        raise RuntimeError(f"Unable to bind recursive runtime {prefix}: {violations}")
    return runtime, certificate


def build_stack(depth: int) -> tuple[list[AdaptiveCompositionRuntime], list[Any]]:
    if depth < 0:
        raise ValueError("depth must be >= 0")

    leaf, leaf_certificate = make_runtime("leaf")
    runtimes = [leaf]
    certificates = [leaf_certificate]
    current = leaf
    current_certificate = leaf_certificate
    for level in range(1, depth + 1):
        current, current_certificate = wrap_runtime(
            current,
            current_certificate,
            level,
        )
        runtimes.append(current)
        certificates.append(current_certificate)
    return runtimes, certificates


def _apply_condition(
    runtimes: list[AdaptiveCompositionRuntime],
    condition: str,
) -> None:
    leaf = runtimes[0]
    if condition == "baseline":
        return
    if condition == "lawful_rebind":
        leaf.registry.register(
            ActorDescriptor(
                "leaf:work:alternate",
                ("role:worker",),
                "cpu",
                authority_class=AuthorityClass.PROPOSER_ONLY,
            )
        )
        mapping = dict(leaf.active_binding.node_to_actor)
        mapping["work"] = "leaf:work:alternate"
        ok, violations = leaf.rebind_active_graph(
            ActorBinding(
                "leaf:binding:alternate",
                leaf.active_graph.graph_id,
                mapping,
            )
        )
        if not ok:
            raise RuntimeError(f"Lawful worker rebind unexpectedly rejected: {violations}")
        return
    if condition == "authority_loss":
        leaf.registry.update_status("leaf:verify", availability=False)
        return
    raise ValueError(f"Unknown condition: {condition}")


def _error_class(error_message: str) -> str:
    if not error_message:
        return "none"
    for marker, label in (
        ("ACTOR_UNAVAILABLE", "actor_unavailable"),
        ("RECURSIVE_BOUNDARY_INVALID", "recursive_boundary_invalid"),
        ("RECURSIVE_CYCLE_DETECTED", "recursive_cycle"),
        ("ACTOR_OUTPUT_DEFICIT", "actor_output_deficit"),
        ("CHILD_EXECUTION_FAILED", "child_execution_failed"),
    ):
        if marker in error_message:
            return label
    return "other_failure"


def _count_unavailable_verifiers(runtimes: Sequence[AdaptiveCompositionRuntime]) -> int:
    count = 0
    for runtime in runtimes:
        for actor in runtime.registry.all_actors():
            if "role:verifier" in actor.capabilities and not actor.availability:
                count += 1
    return count


def _count_recursive_evidence_links(
    runtimes: Sequence[AdaptiveCompositionRuntime],
) -> int:
    links = 0
    for runtime in runtimes[1:]:
        if not runtime.execution_history:
            continue
        record = runtime.execution_history[-1]
        for node in record.node_results:
            if node.node_id == "work" and node.child_record_hash:
                links += 1
    return links


def _boundary_status(
    runtimes: Sequence[AdaptiveCompositionRuntime],
    certificates: Sequence[Any],
) -> tuple[bool, list[list[str]]]:
    all_valid = True
    all_violations: list[list[str]] = []
    for runtime, certificate in zip(runtimes, certificates):
        valid, violations = verify_composition_boundary(
            certificate,
            runtime.active_graph,
            runtime.contract,
        )
        all_valid = all_valid and valid
        all_violations.append(list(violations))
    return all_valid, all_violations


def run_uow_condition(depth: int, condition: str) -> dict[str, Any]:
    runtimes, certificates = build_stack(depth)
    original_certificate_hashes = [certificate.compute_hash() for certificate in certificates]
    _apply_condition(runtimes, condition)
    boundary_valid, boundary_violations = _boundary_status(runtimes, certificates)

    root = runtimes[-1]
    receipt = root.execute({"payload": "jev-recursive-scale"})
    current_certificate_hashes = [certificate.compute_hash() for certificate in certificates]

    successful_runtime_count = sum(
        bool(runtime.execution_history)
        and runtime.execution_history[-1].status == "SUCCESS"
        for runtime in runtimes
    )
    failed_runtime_count = sum(
        bool(runtime.execution_history)
        and runtime.execution_history[-1].status != "SUCCESS"
        for runtime in runtimes
    )

    normalized_state = {
        "subject": "governed_recursive_unit",
        "recursive_level_count": len(runtimes),
        "nested_boundary_count": max(0, len(runtimes) - 1),
        "all_composition_boundaries_valid": boundary_valid,
        "boundary_violation_count": sum(len(v) for v in boundary_violations),
        "parent_contract_changed": False,
        "composition_certificate_changed": original_certificate_hashes
        != current_certificate_hashes,
        "worker_binding_change_count": 1 if condition == "lawful_rebind" else 0,
        "unavailable_verifier_count": _count_unavailable_verifiers(runtimes),
        "root_execution_status": receipt.status.lower(),
        "declared_root_output_emitted": bool(receipt.final_outputs),
        "successful_runtime_count": successful_runtime_count,
        "failed_runtime_count": failed_runtime_count,
        "recursive_evidence_link_count": _count_recursive_evidence_links(runtimes),
        "execution_error_class": _error_class(receipt.error_message),
    }

    oracle = {
        "boundary_valid": boundary_valid,
        "certificate_hashes_stable": original_certificate_hashes
        == current_certificate_hashes,
        "root_status": receipt.status,
        "error_class": _error_class(receipt.error_message),
        "passes_expected_behavior": (
            receipt.status == "SUCCESS"
            if condition in {"baseline", "lawful_rebind"}
            else receipt.status == "FAILED"
            and "ACTOR_UNAVAILABLE" in receipt.error_message
        ),
    }

    return {
        "depth": depth,
        "condition": condition,
        "state": normalized_state,
        "oracle": oracle,
        "diagnostics": {
            "boundary_violations": boundary_violations,
            "root_evidence_root": receipt.evidence_root,
            "root_error_message": receipt.error_message,
        },
    }


def build_deterministic_states(max_depth: int) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    for depth in range(max_depth + 1):
        for condition in CONDITIONS:
            states.append(run_uow_condition(depth, condition))
    return states


def _mean_vector(vectors: Sequence[Sequence[float]]) -> list[float]:
    if not vectors:
        raise ValueError("Cannot average an empty vector set")
    width = len(vectors[0])
    if width == 0 or any(len(vector) != width for vector in vectors):
        raise ValueError("JEV vector dimensions are inconsistent")
    return [sum(vector[i] for vector in vectors) / len(vectors) for i in range(width)]


def _subtract(a: Sequence[float], b: Sequence[float]) -> list[float]:
    if len(a) != len(b):
        raise ValueError("Vector dimensions differ")
    return [x - y for x, y in zip(a, b)]


def _norm(vector: Sequence[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def _distance(a: Sequence[float], b: Sequence[float]) -> float:
    return _norm(_subtract(a, b))


def _cosine(a: Sequence[float], b: Sequence[float]) -> float | None:
    denom = _norm(a) * _norm(b)
    if denom <= 1e-15:
        return None
    value = sum(x * y for x, y in zip(a, b)) / denom
    return max(-1.0, min(1.0, value))


def analyze_observations(
    deterministic_states: Sequence[dict[str, Any]],
    observations: Sequence[dict[str, Any]],
    *,
    max_depth: int,
    replicates: int,
    thresholds: ExperimentThresholds,
) -> dict[str, Any]:
    state_by_key = {
        (int(item["depth"]), str(item["condition"])): item
        for item in deterministic_states
    }
    oracle_pass = all(
        item["oracle"]["boundary_valid"]
        and item["oracle"]["certificate_hashes_stable"]
        and item["oracle"]["passes_expected_behavior"]
        for item in deterministic_states
    )

    grouped: dict[tuple[int, str], list[list[float]]] = {}
    for observation in observations:
        key = (int(observation["depth"]), str(observation["condition"]))
        vector = [float(value) for value in observation["provider"]["vector"]]
        grouped.setdefault(key, []).append(vector)

    expected_groups = (max_depth + 1) * len(CONDITIONS)
    provider_complete = (
        len(grouped) == expected_groups
        and all(len(vectors) == replicates for vectors in grouped.values())
    )

    repeatability_distances: list[float] = []
    for vectors in grouped.values():
        for i in range(len(vectors)):
            for j in range(i + 1, len(vectors)):
                repeatability_distances.append(_distance(vectors[i], vectors[j]))
    noise_floor = median(repeatability_distances) if repeatability_distances else 0.0

    means = {key: _mean_vector(vectors) for key, vectors in grouped.items()}
    depth_metrics: list[dict[str, Any]] = []
    authority_deltas: list[list[float]] = []
    authority_norms: list[float] = []
    control_norms: list[float] = []

    if provider_complete:
        for depth in range(max_depth + 1):
            baseline = means[(depth, "baseline")]
            rebind = means[(depth, "lawful_rebind")]
            authority_loss = means[(depth, "authority_loss")]
            control_delta = _subtract(rebind, baseline)
            authority_delta = _subtract(authority_loss, baseline)
            control_norm = _norm(control_delta)
            authority_norm = _norm(authority_delta)
            control_norms.append(control_norm)
            authority_norms.append(authority_norm)
            authority_deltas.append(authority_delta)
            depth_metrics.append(
                {
                    "depth": depth,
                    "baseline_mean": baseline,
                    "lawful_rebind_delta": control_delta,
                    "lawful_rebind_delta_norm": control_norm,
                    "authority_loss_delta": authority_delta,
                    "authority_loss_delta_norm": authority_norm,
                    "deterministic_state": state_by_key[(depth, "authority_loss")]["state"],
                }
            )

    pairwise_cosines: list[dict[str, Any]] = []
    numeric_cosines: list[float] = []
    for i in range(len(authority_deltas)):
        for j in range(i + 1, len(authority_deltas)):
            cosine = _cosine(authority_deltas[i], authority_deltas[j])
            pairwise_cosines.append(
                {"depth_a": i, "depth_b": j, "cosine": cosine}
            )
            if cosine is not None:
                numeric_cosines.append(cosine)

    min_cosine = min(numeric_cosines) if numeric_cosines else None
    mean_authority_norm = (
        sum(authority_norms) / len(authority_norms) if authority_norms else 0.0
    )
    authority_norm_cv = (
        pstdev(authority_norms) / mean_authority_norm
        if len(authority_norms) > 1 and mean_authority_norm > 1e-15
        else 0.0
    )
    median_authority_norm = median(authority_norms) if authority_norms else 0.0
    median_control_norm = median(control_norms) if control_norms else 0.0
    denominator_floor = 1e-12
    signal_to_noise = median_authority_norm / max(noise_floor, denominator_floor)
    authority_to_control = median_authority_norm / max(
        median_control_norm,
        noise_floor,
        denominator_floor,
    )

    gates = {
        "U0_deterministic_oracle": oracle_pass,
        "J0_provider_complete": provider_complete,
        "J1_authority_signal_above_repeatability": provider_complete
        and signal_to_noise >= thresholds.min_signal_to_noise,
        "J2_authority_distinct_from_lawful_rebind": provider_complete
        and authority_to_control >= thresholds.min_authority_to_control_separation,
        "J3_cross_depth_direction_stable": provider_complete
        and min_cosine is not None
        and min_cosine >= thresholds.min_cross_depth_cosine,
        "J4_cross_depth_magnitude_stable": provider_complete
        and authority_norm_cv <= thresholds.max_authority_norm_cv,
    }
    supported = all(gates.values())

    return {
        "oracle_pass": oracle_pass,
        "provider_complete": provider_complete,
        "repeatability_noise_floor_l2": noise_floor,
        "median_lawful_rebind_delta_norm": median_control_norm,
        "median_authority_loss_delta_norm": median_authority_norm,
        "authority_signal_to_noise": signal_to_noise,
        "authority_to_lawful_rebind_separation": authority_to_control,
        "authority_loss_norm_cv_across_depth": authority_norm_cv,
        "minimum_authority_loss_cosine_across_depth": min_cosine,
        "pairwise_authority_loss_cosines": pairwise_cosines,
        "depth_metrics": depth_metrics,
        "thresholds": {
            "min_signal_to_noise": thresholds.min_signal_to_noise,
            "min_authority_to_control_separation": thresholds.min_authority_to_control_separation,
            "min_cross_depth_cosine": thresholds.min_cross_depth_cosine,
            "max_authority_norm_cv": thresholds.max_authority_norm_cv,
        },
        "gates": gates,
        "supported_within_engineering_gates": supported,
        "verdict": (
            "SUPPORTED_WITHIN_PREREGISTERED_ENGINEERING_GATES"
            if supported
            else "NOT_SUPPORTED_BY_THIS_RUN"
        ),
    }


def run_live_experiment(
    *,
    provider: JevProvider,
    max_depth: int,
    replicates: int,
    thresholds: ExperimentThresholds,
) -> dict[str, Any]:
    deterministic_states = build_deterministic_states(max_depth)
    questions = question_payload()
    observations: list[dict[str, Any]] = []

    for item in deterministic_states:
        depth = int(item["depth"])
        condition = str(item["condition"])
        for replicate in range(replicates):
            request_id = f"uow-recursive-scale-d{depth}-{condition}-r{replicate}"
            provider_result = provider.decide(
                state=dict(item["state"]),
                questions=questions,
                request_id=request_id,
            )
            observations.append(
                {
                    "depth": depth,
                    "condition": condition,
                    "replicate": replicate,
                    "provider": provider_result,
                }
            )

    analysis = analyze_observations(
        deterministic_states,
        observations,
        max_depth=max_depth,
        replicates=replicates,
        thresholds=thresholds,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "JEV recursive UoW authority-loss scale invariance",
        "hypothesis": (
            "The JEV probability displacement produced by the same bounded "
            "authority-loss perturbation remains directionally and approximately "
            "magnitude-stable as recursive UoW depth increases."
        ),
        "method": {
            "depths": list(range(max_depth + 1)),
            "conditions": list(CONDITIONS),
            "replicates_per_state": replicates,
            "questions_per_request": len(questions),
            "requests_total": (max_depth + 1) * len(CONDITIONS) * replicates,
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
        description="Run the bounded JEV recursive-scale UoW qualification experiment."
    )
    parser.add_argument("--model", default=DEFAULT_JEV_MODEL)
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Validate UoW deterministic states and write them without calling JEV.",
    )
    parser.add_argument("--min-cosine", type=float, default=0.90)
    parser.add_argument("--max-norm-cv", type=float, default=0.25)
    parser.add_argument("--min-signal-noise", type=float, default=2.0)
    parser.add_argument("--min-separation", type=float, default=2.0)
    args = parser.parse_args()

    if args.max_depth < 1:
        parser.error("--max-depth must be >= 1 so cross-depth invariance is testable")
    if args.replicates < 2:
        parser.error("--replicates must be >= 2 so repeatability can be measured")

    thresholds = ExperimentThresholds(
        min_signal_to_noise=args.min_signal_noise,
        min_authority_to_control_separation=args.min_separation,
        min_cross_depth_cosine=args.min_cosine,
        max_authority_norm_cv=args.max_norm_cv,
    )

    if args.prepare_only:
        states = build_deterministic_states(args.max_depth)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "prepare_only",
            "method": {
                "depths": list(range(args.max_depth + 1)),
                "conditions": list(CONDITIONS),
            },
            "questions": question_payload(),
            "deterministic_states": states,
            "oracle_pass": all(
                item["oracle"]["boundary_valid"]
                and item["oracle"]["certificate_hashes_stable"]
                and item["oracle"]["passes_expected_behavior"]
                for item in states
            ),
        }
    else:
        provider = TypeSafeJevProvider(model=args.model, timeout_s=args.timeout_s)
        payload = run_live_experiment(
            provider=provider,
            max_depth=args.max_depth,
            replicates=args.replicates,
            thresholds=thresholds,
        )

    _write_json(args.output, payload)
    print(json.dumps(payload.get("analysis", payload), indent=2, sort_keys=True))
    print(f"\nWrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
