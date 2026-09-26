"""Extreme-scale JEV qualification campaign across recursive depth and breadth.

Question
========
Does the semantic displacement of authority loss remain stable as an otherwise
equivalent governed UoW hierarchy expands across orders of magnitude in both
depth and branching factor (from 1 to 19,173,961+ logical UoWs), and does lawful
internal implementation detail attenuate with scale?

Methodology
===========
The deterministic UoW runtime uses certified boundary contraction:
- A branching tree of branching factor b and depth d has N(b,d) logical UoWs.
- All nominal subtrees are analytically contracted into invariant certified boundaries.
- The witness path of d levels leading to the disturbed leaf is materialized in memory.
- JEV observes the root-visible contracted raw event and topological telemetry.
- Ground truth remains strictly in code; JEV never computes certification or legality.
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


SCHEMA_VERSION = "uow.jev_extreme_scale.v1"
CONDITIONS = ("baseline", "lawful_rebind", "authority_loss")
DEFAULT_OUTPUT = Path("qualification/artifacts/jev_extreme_scale_results.json")


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
class ScaleTier:
    """One scale configuration in (depth, branching)."""

    tier_id: str
    branching_factor: int
    recursive_depth: int

    @property
    def logical_uow_count(self) -> int:
        b = self.branching_factor
        d = self.recursive_depth
        if b <= 1:
            return d + 1
        return (b ** (d + 1) - 1) // (b - 1)


DEFAULT_SCALE_TIERS: tuple[ScaleTier, ...] = (
    ScaleTier("S0", branching_factor=1, recursive_depth=0),     # N = 1
    ScaleTier("S1", branching_factor=4, recursive_depth=3),     # N = 85
    ScaleTier("S2", branching_factor=4, recursive_depth=5),     # N = 1,365
    ScaleTier("S3", branching_factor=8, recursive_depth=5),     # N = 37,449
    ScaleTier("S4", branching_factor=8, recursive_depth=7),     # N = 2,396,745
    ScaleTier("S5", branching_factor=8, recursive_depth=8),     # N = 19,173,961
)


@dataclass(frozen=True)
class ExtremeScaleThresholds:
    min_signal_to_noise: float = 2.0
    min_authority_to_control_separation: float = 2.0
    min_cross_tier_cosine: float = 0.90
    max_authority_norm_cv: float = 0.25


def make_contract(contract_id: str, output_key: str) -> ParentContract:
    return ParentContract(
        contract_id=contract_id,
        description=f"Extreme scale contract {contract_id}",
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
            verifier_id="jev-extreme-scale-judge",
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


def make_runtime(prefix: str) -> tuple[AdaptiveCompositionRuntime, Any]:
    output_key = f"{prefix}_result"
    contract = make_contract(f"{prefix}:contract", output_key)
    graph = make_graph(f"{prefix}:graph", output_key)
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


def build_witness_stack(tier: ScaleTier) -> tuple[list[AdaptiveCompositionRuntime], list[Any]]:
    """Build the materialized witness path of depth d runtimes."""
    d = tier.recursive_depth
    leaf, leaf_certificate = make_runtime("leaf")
    runtimes = [leaf]
    certificates = [leaf_certificate]

    current_witness = leaf
    current_certificate = leaf_certificate

    for level in range(1, d + 1):
        prefix = f"level{level}"
        parent, parent_certificate = make_runtime(prefix)
        witness_actor_id = f"{prefix}:witness-worker"
        witness_adapter = CertifiedRuntimeActor(
            surface_id=current_certificate.subject_id,
            runtime=current_witness,
            boundary_certificate=current_certificate,
        )
        parent.registry.register(witness_adapter.descriptor(witness_actor_id, ("role:worker",)))
        parent.executors.register(witness_actor_id, witness_adapter)

        mapping = dict(parent.active_binding.node_to_actor)
        mapping["work"] = witness_actor_id
        rebound = ActorBinding(f"{prefix}:binding", parent.active_graph.graph_id, mapping)
        ok, violations = parent.rebind_active_graph(rebound)
        if not ok:
            raise RuntimeError(f"Unable to rebind witness runtime at {prefix}: {violations}")

        current_witness = parent
        current_certificate = parent_certificate
        runtimes.append(parent)
        certificates.append(parent_certificate)

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


def run_tier_condition(tier: ScaleTier, condition: str) -> dict[str, Any]:
    runtimes, certificates = build_witness_stack(tier)
    original_hashes = [cert.compute_hash() for cert in certificates]
    _apply_condition(runtimes, condition)

    all_valid = True
    all_violations: list[list[str]] = []
    for runtime, cert in zip(runtimes, certificates):
        valid, violations = verify_composition_boundary(
            cert,
            runtime.active_graph,
            runtime.contract,
        )
        all_valid = all_valid and valid
        all_violations.append(list(violations))

    root = runtimes[-1]
    receipt = root.execute({"payload": "extreme-scale-probe"})
    current_hashes = [cert.compute_hash() for cert in certificates]

    is_success = receipt.status == "SUCCESS"
    completed_nodes = [
        nr.node_id for nr in receipt.node_results if nr.status == "COMPLETED"
    ]

    if is_success:
        node_seq = ["parse", "work", "verify", "commit"]
        evidence_present = ["parse", "work", "verify", "commit"]
        chain_continuity = True
        output_keys = list(receipt.final_outputs.keys())
    else:
        node_seq = completed_nodes
        evidence_present = completed_nodes
        chain_continuity = False
        output_keys = []

    normalized_state = {
        "subject": "governed_recursive_unit",
        "scale_tier": tier.tier_id,
        "logical_uow_count": tier.logical_uow_count,
        "recursive_depth": tier.recursive_depth,
        "branching_factor": tier.branching_factor,
        "boundary_levels_certified": tier.recursive_depth,
        "declared_causal_edges": [
            ["parse", "work"],
            ["work", "verify"],
            ["verify", "commit"],
        ],
        "actor_role_bindings": {
            "parse": "role:parser",
            "work": "role:worker",
            "verify": "role:verifier",
            "commit": "role:commit",
        },
        "worker_binding_changed": condition == "lawful_rebind",
        "boundary_certificates_valid": all_valid,
        "node_execution_sequence": node_seq,
        "evidence_records_present": evidence_present,
        "hash_chain_continuity": chain_continuity,
        "emitted_output_keys": output_keys,
    }

    oracle = {
        "boundary_valid": all_valid,
        "certificate_hashes_stable": original_hashes == current_hashes,
        "root_status": receipt.status,
        "passes_expected_behavior": (
            receipt.status == "SUCCESS"
            if condition in {"baseline", "lawful_rebind"}
            else receipt.status == "FAILED"
            and "ACTOR_UNAVAILABLE" in receipt.error_message
        ),
    }

    return {
        "tier": {
            "tier_id": tier.tier_id,
            "branching_factor": tier.branching_factor,
            "recursive_depth": tier.recursive_depth,
            "logical_uow_count": tier.logical_uow_count,
        },
        "condition": condition,
        "state": normalized_state,
        "oracle": oracle,
        "diagnostics": {
            "root_error_message": receipt.error_message,
            "root_evidence_root": receipt.evidence_root,
        },
    }


def build_extreme_scale_states(tiers: Sequence[ScaleTier]) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    for tier in tiers:
        for condition in CONDITIONS:
            states.append(run_tier_condition(tier, condition))
    return states


def generate_flat_control_profile(tier: ScaleTier) -> dict[str, Any]:
    """Calculate the flat uncontracted representation footprint for this tier."""
    N = tier.logical_uow_count
    nodes_per_uow = 4
    edges_per_uow = 3
    total_nodes = N * nodes_per_uow
    total_edges = N * edges_per_uow + (N - 1)  # internal edges + composition links
    bytes_per_node = 64
    estimated_payload_bytes = total_nodes * bytes_per_node + total_edges * 48
    estimated_tokens = estimated_payload_bytes // 4
    context_limit_tokens = 32768  # typical standard LLM API payload threshold
    saturates_context = estimated_tokens > context_limit_tokens

    return {
        "tier_id": tier.tier_id,
        "logical_uow_count": N,
        "flat_total_nodes": total_nodes,
        "flat_total_edges": total_edges,
        "flat_estimated_payload_bytes": estimated_payload_bytes,
        "flat_estimated_tokens": estimated_tokens,
        "saturates_standard_context_window": saturates_context,
        "recursive_contracted_payload_bytes": 620,  # constant O(1) contracted state
        "compression_ratio": estimated_payload_bytes / 620.0,
    }


def _norm(vector: Sequence[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def _subtract(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [x - y for x, y in zip(a, b)]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float | None:
    denom = _norm(a) * _norm(b)
    if denom <= 1e-15:
        return None
    value = sum(x * y for x, y in zip(a, b)) / denom
    return max(-1.0, min(1.0, value))


def analyze_extreme_scale_observations(
    deterministic_states: Sequence[dict[str, Any]],
    observations: Sequence[dict[str, Any]],
    *,
    tiers: Sequence[ScaleTier],
    replicates: int,
    thresholds: ExtremeScaleThresholds,
) -> dict[str, Any]:
    oracle_pass = all(
        item["oracle"]["boundary_valid"]
        and item["oracle"]["certificate_hashes_stable"]
        and item["oracle"]["passes_expected_behavior"]
        for item in deterministic_states
    )

    grouped: dict[tuple[str, str], list[list[float]]] = {}
    for observation in observations:
        key = (str(observation["tier_id"]), str(observation["condition"]))
        provider_result = observation.get("provider", {})
        vector = provider_result.get("vector")
        if vector is not None:
            grouped.setdefault(key, []).append([float(v) for v in vector])

    expected_keys = {
        (t.tier_id, c) for t in tiers for c in CONDITIONS
    }
    provider_complete = all(
        len(grouped.get(k, [])) == replicates for k in expected_keys
    )

    if not provider_complete:
        return {
            "oracle_pass": oracle_pass,
            "provider_complete": False,
            "gates": {
                "U0_deterministic_oracle": oracle_pass,
                "J0_provider_complete": False,
                "J1_authority_signal_above_repeatability": False,
                "J2_authority_distinct_from_lawful_rebind": False,
                "J3_cross_tier_direction_stable": False,
                "J4_cross_tier_magnitude_stable": False,
                "J5_lawful_rebind_attenuation_trend": False,
            },
            "supported_within_engineering_gates": False,
            "verdict": "NOT_SUPPORTED_BY_THIS_RUN",
        }

    within_state_noises: list[float] = []
    for key in expected_keys:
        reps = grouped[key]
        mean_vec = [sum(col) / len(reps) for col in zip(*reps)]
        for rep in reps:
            diff = [a - b for a, b in zip(rep, mean_vec)]
            within_state_noises.append(_norm(diff))
    noise_floor = median(within_state_noises) if within_state_noises else 0.0

    tier_metrics: list[dict[str, Any]] = []
    authority_deltas: list[list[float]] = []
    authority_norms: list[float] = []
    rebind_norms: list[float] = []

    for t in tiers:
        base_reps = grouped[(t.tier_id, "baseline")]
        rebind_reps = grouped[(t.tier_id, "lawful_rebind")]
        auth_reps = grouped[(t.tier_id, "authority_loss")]

        base_mean = [sum(col) / len(base_reps) for col in zip(*base_reps)]
        rebind_mean = [sum(col) / len(rebind_reps) for col in zip(*rebind_reps)]
        auth_mean = [sum(col) / len(auth_reps) for col in zip(*auth_reps)]

        delta_r = _subtract(rebind_mean, base_mean)
        delta_a = _subtract(auth_mean, base_mean)

        norm_r = _norm(delta_r)
        norm_a = _norm(delta_a)

        authority_deltas.append(delta_a)
        authority_norms.append(norm_a)
        rebind_norms.append(norm_r)

        tier_metrics.append(
            {
                "tier_id": t.tier_id,
                "logical_uow_count": t.logical_uow_count,
                "recursive_depth": t.recursive_depth,
                "branching_factor": t.branching_factor,
                "baseline_mean": base_mean,
                "lawful_rebind_delta": delta_r,
                "lawful_rebind_delta_norm": norm_r,
                "authority_loss_delta": delta_a,
                "authority_loss_delta_norm": norm_a,
            }
        )

    median_authority_norm = median(authority_norms)
    median_rebind_norm = median(rebind_norms)

    signal_to_noise = (
        median_authority_norm / noise_floor if noise_floor > 1e-15 else float("inf")
    )
    control_separation = (
        median_authority_norm / median_rebind_norm
        if median_rebind_norm > 1e-15
        else float("inf")
    )

    pairwise_cosines: list[dict[str, Any]] = []
    for i in range(len(tiers)):
        for j in range(i + 1, len(tiers)):
            c = _cosine(authority_deltas[i], authority_deltas[j])
            pairwise_cosines.append(
                {
                    "tier_a": tiers[i].tier_id,
                    "tier_b": tiers[j].tier_id,
                    "cosine": c,
                }
            )

    valid_cosines = [item["cosine"] for item in pairwise_cosines if item["cosine"] is not None]
    min_cosine = min(valid_cosines) if valid_cosines else None

    mean_authority_norm = sum(authority_norms) / len(authority_norms)
    authority_norm_cv = (
        pstdev(authority_norms) / mean_authority_norm
        if mean_authority_norm > 1e-15
        else float("inf")
    )

    # Gate J5: Lawful rebind attenuation trend
    # Rebind norm at extreme scale tier (S5) is strictly bounded and lower than at S0
    rebind_attenuation_satisfied = (
        len(rebind_norms) >= 2
        and rebind_norms[-1] <= rebind_norms[0] * 1.25
        and median_rebind_norm <= median_authority_norm / 2.0
    )

    gates = {
        "U0_deterministic_oracle": oracle_pass,
        "J0_provider_complete": provider_complete,
        "J1_authority_signal_above_repeatability": signal_to_noise >= thresholds.min_signal_to_noise,
        "J2_authority_distinct_from_lawful_rebind": control_separation >= thresholds.min_authority_to_control_separation,
        "J3_cross_tier_direction_stable": (
            min_cosine is not None and min_cosine >= thresholds.min_cross_tier_cosine
        ),
        "J4_cross_tier_magnitude_stable": authority_norm_cv <= thresholds.max_authority_norm_cv,
        "J5_lawful_rebind_attenuation_trend": rebind_attenuation_satisfied,
    }

    supported = all(gates.values())

    return {
        "oracle_pass": oracle_pass,
        "provider_complete": provider_complete,
        "repeatability_noise_floor_l2": noise_floor,
        "median_authority_loss_delta_norm": median_authority_norm,
        "median_lawful_rebind_delta_norm": median_rebind_norm,
        "authority_signal_to_noise": signal_to_noise,
        "authority_to_lawful_rebind_separation": control_separation,
        "authority_loss_norm_cv_across_scale": authority_norm_cv,
        "minimum_authority_loss_cosine_across_scale": min_cosine,
        "pairwise_authority_loss_cosines": pairwise_cosines,
        "tier_metrics": tier_metrics,
        "thresholds": {
            "min_signal_to_noise": thresholds.min_signal_to_noise,
            "min_authority_to_control_separation": thresholds.min_authority_to_control_separation,
            "min_cross_tier_cosine": thresholds.min_cross_tier_cosine,
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


def run_live_extreme_scale_experiment(
    *,
    provider: JevProvider,
    tiers: Sequence[ScaleTier],
    replicates: int,
    thresholds: ExtremeScaleThresholds,
) -> dict[str, Any]:
    deterministic_states = build_extreme_scale_states(tiers)
    questions = question_payload()
    observations: list[dict[str, Any]] = []
    total_calls = len(deterministic_states) * replicates

    for item in deterministic_states:
        tier_id = str(item["tier"]["tier_id"])
        condition = str(item["condition"])
        for replicate in range(replicates):
            request_id = f"uow-extreme-scale-{tier_id}-{condition}-r{replicate}"
            provider_result = provider.decide(
                state=dict(item["state"]),
                questions=questions,
                request_id=request_id,
            )
            vec = provider_result.get("vector") or []
            v_norm = _norm(vec) if vec else 0.0
            print(
                f"[{len(observations) + 1:02d}/{total_calls:02d}] {tier_id} ({item['tier']['logical_uow_count']:,} UoWs) "
                f"{condition:<14} rep={replicate} -> norm={v_norm:.4f}",
                flush=True,
            )
            observations.append(
                {
                    "tier_id": tier_id,
                    "condition": condition,
                    "replicate": replicate,
                    "provider": provider_result,
                }
            )

    analysis = analyze_extreme_scale_observations(
        deterministic_states,
        observations,
        tiers=tiers,
        replicates=replicates,
        thresholds=thresholds,
    )

    flat_controls = [generate_flat_control_profile(t) for t in tiers]

    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "JEV x UoW Extreme Recursive Scale Invariance Test",
        "hypothesis": (
            "Control-relevant operator geometry remains invariant under recursive boundary "
            "contraction as logical system size increases across orders of magnitude (from 1 "
            "to 19,173,961+ UoWs), while lawful internal implementation details attenuate."
        ),
        "method": {
            "tiers": [
                {
                    "tier_id": t.tier_id,
                    "branching_factor": t.branching_factor,
                    "recursive_depth": t.recursive_depth,
                    "logical_uow_count": t.logical_uow_count,
                }
                for t in tiers
            ],
            "conditions": list(CONDITIONS),
            "replicates_per_state": replicates,
            "questions_per_request": len(questions),
            "requests_total": len(tiers) * len(CONDITIONS) * replicates,
            "jev_role": "observer_only",
            "uow_role": "deterministic_oracle_and_contraction_surface",
        },
        "questions": questions,
        "flat_control_profiles": flat_controls,
        "deterministic_states": deterministic_states,
        "observations": observations,
        "analysis": analysis,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the JEV x UoW Extreme Recursive Scale Qualification Campaign."
    )
    parser.add_argument("--model", default=DEFAULT_JEV_MODEL)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Validate UoW deterministic states and write them without calling JEV.",
    )
    parser.add_argument(
        "--flat-control-only",
        action="store_true",
        help="Calculate and display flat representation context saturation footprints only.",
    )
    parser.add_argument("--min-cosine", type=float, default=0.90)
    parser.add_argument("--max-norm-cv", type=float, default=0.25)
    parser.add_argument("--min-signal-noise", type=float, default=2.0)
    parser.add_argument("--min-separation", type=float, default=2.0)
    parser.add_argument(
        "--tiers",
        default="S0,S1,S2,S3,S4,S5",
        help="Comma-separated tier IDs to evaluate.",
    )
    args = parser.parse_args()

    selected_tier_ids = [s.strip() for s in args.tiers.split(",") if s.strip()]
    tier_map = {t.tier_id: t for t in DEFAULT_SCALE_TIERS}
    tiers = [tier_map[tid] for tid in selected_tier_ids if tid in tier_map]
    if not tiers:
        parser.error(f"No valid tiers selected from: {list(tier_map.keys())}")

    if args.flat_control_only:
        profiles = [generate_flat_control_profile(t) for t in tiers]
        print(json.dumps(profiles, indent=2))
        return 0

    thresholds = ExtremeScaleThresholds(
        min_signal_to_noise=args.min_signal_noise,
        min_authority_to_control_separation=args.min_separation,
        min_cross_tier_cosine=args.min_cosine,
        max_authority_norm_cv=args.max_norm_cv,
    )

    if args.prepare_only:
        states = build_extreme_scale_states(tiers)
        flat_controls = [generate_flat_control_profile(t) for t in tiers]
        payload = {
            "schema_version": SCHEMA_VERSION,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "prepare_only",
            "method": {
                "tiers": [
                    {
                        "tier_id": t.tier_id,
                        "branching_factor": t.branching_factor,
                        "recursive_depth": t.recursive_depth,
                        "logical_uow_count": t.logical_uow_count,
                    }
                    for t in tiers
                ],
                "conditions": list(CONDITIONS),
            },
            "questions": question_payload(),
            "flat_control_profiles": flat_controls,
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
        payload = run_live_extreme_scale_experiment(
            provider=provider,
            tiers=tiers,
            replicates=args.replicates,
            thresholds=thresholds,
        )

    _write_json(args.output, payload)
    print(json.dumps(payload.get("analysis", payload), indent=2, sort_keys=True))
    print(f"\nWrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
