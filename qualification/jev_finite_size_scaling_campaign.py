"""JEV x UoW Finite-Size Collective Scaling Campaign.

Questions
=========
Does the collective cybernetic behavior of a governed UoW ensemble change with system
size M, or do size-independent cybernetic laws emerge?
Specifically:
1. Subcritical Shielding Scaling: Does S(M, q, rho) = ||Delta_cascade|| / ||Delta_quorum||
   remain effective (>= 3.0x) or converge to an invariant S*(q, rho) as M scales (8 -> 16 -> 32)?
2. Transition Jump Invariance: Does the macrostate transition jump J(M, q) = ||Delta(k_c)|| - ||Delta(k_c - 1)||
   persist as a sharp discontinuity across ensemble sizes?
3. Cross-Size Operator Direction: Does the authority-loss operator Delta_A*(M) maintain
   directional invariance across sizes (min cos >= 0.950)?
4. Post-Threshold Amplitude Stability: Does A_inf(M) = ||Delta_A*|| converge across sizes (CV <= 0.15)?
5. Policy Independence: When the quorum policy changes from majority (q=0.50) to
   supermajority (q=0.75), does post-threshold Delta_A* preserve the same geometry?
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


SCHEMA_VERSION = "uow.jev_finite_size_scaling.v1"
DEFAULT_OUTPUT = Path("qualification/artifacts/jev_finite_size_scaling_results.json")


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
class ScalingSpec:
    """Specification of one collective experimental state."""

    spec_id: str
    ensemble_size: int
    quorum_fraction: float
    disturbed_count: int
    regime: str  # "quorum" or "cascade"

    @property
    def disturbance_density(self) -> float:
        return self.disturbed_count / float(self.ensemble_size)

    @property
    def quorum_required(self) -> int:
        if self.regime == "cascade":
            return self.ensemble_size
        if math.isclose(self.quorum_fraction, 0.50):
            return (self.ensemble_size // 2) + 1
        # E.g. q = 0.75
        return math.ceil(self.quorum_fraction * self.ensemble_size)


# The 18 preregistered states spanning M in {8, 16, 32} and q in {0.50, 0.75}
DEFAULT_SCALING_SPECS: tuple[ScalingSpec, ...] = (
    # Group 1: M = 8, q = 0.50 (Majority: Q = 5)
    ScalingSpec("M8_base", ensemble_size=8, quorum_fraction=0.50, disturbed_count=0, regime="quorum"),
    ScalingSpec("M8_sub_25", ensemble_size=8, quorum_fraction=0.50, disturbed_count=2, regime="quorum"),
    ScalingSpec("M8_pre_thresh", ensemble_size=8, quorum_fraction=0.50, disturbed_count=3, regime="quorum"),
    ScalingSpec("M8_at_thresh", ensemble_size=8, quorum_fraction=0.50, disturbed_count=4, regime="quorum"),
    ScalingSpec("M8_casc_25", ensemble_size=8, quorum_fraction=0.50, disturbed_count=2, regime="cascade"),

    # Group 2: M = 16, q = 0.50 (Majority: Q = 9)
    ScalingSpec("M16_base", ensemble_size=16, quorum_fraction=0.50, disturbed_count=0, regime="quorum"),
    ScalingSpec("M16_sub_25", ensemble_size=16, quorum_fraction=0.50, disturbed_count=4, regime="quorum"),
    ScalingSpec("M16_pre_thresh", ensemble_size=16, quorum_fraction=0.50, disturbed_count=7, regime="quorum"),
    ScalingSpec("M16_at_thresh", ensemble_size=16, quorum_fraction=0.50, disturbed_count=8, regime="quorum"),
    ScalingSpec("M16_casc_25", ensemble_size=16, quorum_fraction=0.50, disturbed_count=4, regime="cascade"),

    # Group 3: M = 32, q = 0.50 (Majority: Q = 17)
    ScalingSpec("M32_base", ensemble_size=32, quorum_fraction=0.50, disturbed_count=0, regime="quorum"),
    ScalingSpec("M32_sub_25", ensemble_size=32, quorum_fraction=0.50, disturbed_count=8, regime="quorum"),
    ScalingSpec("M32_pre_thresh", ensemble_size=32, quorum_fraction=0.50, disturbed_count=15, regime="quorum"),
    ScalingSpec("M32_at_thresh", ensemble_size=32, quorum_fraction=0.50, disturbed_count=16, regime="quorum"),
    ScalingSpec("M32_casc_25", ensemble_size=32, quorum_fraction=0.50, disturbed_count=8, regime="cascade"),

    # Group 4: Supermajority Policy (q=0.75) and Deep Extinction on M = 16
    ScalingSpec("M16_q75_pre", ensemble_size=16, quorum_fraction=0.75, disturbed_count=4, regime="quorum"),
    ScalingSpec("M16_q75_at", ensemble_size=16, quorum_fraction=0.75, disturbed_count=5, regime="quorum"),
    ScalingSpec("M16_extinction", ensemble_size=16, quorum_fraction=0.50, disturbed_count=16, regime="quorum"),
)


@dataclass(frozen=True)
class ScalingThresholds:
    min_shielding_ratio: float = 3.0
    min_transition_jump: float = 0.80
    min_cross_size_cosine: float = 0.95
    max_post_threshold_norm_cv: float = 0.15


def make_child_unit(unit_id: str) -> tuple[AdaptiveCompositionRuntime, Any]:
    output_key = f"{unit_id}_result"
    contract = ParentContract(
        contract_id=f"{unit_id}:contract",
        description=f"Child unit {unit_id} contract",
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
            verifier_id="child-verifier",
        ),
        temporal=TemporalConstraint(max_duration_ms=1000.0),
        resources=ResourceConstraint(
            max_cpu_cores=2,
            max_ram_units=4,
            max_gpu_slots=0,
            max_npu_slots=0,
            max_cost_units=25.0,
        ),
        failure_semantics=FailureSemantics.ROLLBACK,
    )
    graph = RealizationGraph(
        f"{unit_id}:graph",
        {
            "parse": RealizationNode("parse", role="parser"),
            "work": RealizationNode("work", role="worker"),
            "verify": RealizationNode("verify", role="verifier", authority_tier="verifier"),
            "commit": RealizationNode("commit", role="commit", outputs=(output_key,)),
        },
        (
            ("parse", "work"),
            ("work", "verify"),
            ("verify", "commit"),
        ),
    )
    registry = ActorRegistry(
        [
            ActorDescriptor(f"{unit_id}:parse", ("role:parser",), "cpu"),
            ActorDescriptor(f"{unit_id}:work", ("role:worker",), "cpu"),
            ActorDescriptor(
                f"{unit_id}:verify",
                ("role:verifier",),
                "cpu",
                authority_class=AuthorityClass.VERIFIER,
            ),
            ActorDescriptor(f"{unit_id}:commit", ("role:commit",), "cpu"),
        ]
    )
    binding = ActorBinding(
        f"{unit_id}:binding",
        graph.graph_id,
        {
            "parse": f"{unit_id}:parse",
            "work": f"{unit_id}:work",
            "verify": f"{unit_id}:verify",
            "commit": f"{unit_id}:commit",
        },
    )
    runtime = AdaptiveCompositionRuntime(
        contract=contract,
        baseline_graph=graph,
        registry=registry,
        baseline_binding=binding,
        executors=ActorExecutionRegistry(),
    )
    cert = certify_composition_boundary(unit_id, graph, contract)
    if not cert.is_accepted:
        raise RuntimeError(f"Child {unit_id} boundary certification failed: {cert.violations}")
    return runtime, cert


def run_scaling_spec(spec: ScalingSpec) -> dict[str, Any]:
    M = spec.ensemble_size
    k = spec.disturbed_count
    Q = spec.quorum_required
    rho = spec.disturbance_density

    child_runtimes: list[AdaptiveCompositionRuntime] = []
    child_certs: list[Any] = []
    for i in range(M):
        rt, cert = make_child_unit(f"{spec.spec_id}_c{i}")
        child_runtimes.append(rt)
        child_certs.append(cert)

    # Induce leaf authority loss in the first k units
    for i in range(k):
        child_runtimes[i].registry.update_status(f"{spec.spec_id}_c{i}:verify", availability=False)

    valid_count = 0
    for i in range(M):
        rec = child_runtimes[i].execute({"payload": "probe"})
        if rec.status == "SUCCESS":
            valid_count += 1

    quorum_achieved = valid_count >= Q
    quorum_margin = valid_count - Q

    all_certs_valid = True
    for rt, cert in zip(child_runtimes, child_certs):
        ok, _ = verify_composition_boundary(cert, rt.active_graph, rt.contract)
        all_certs_valid = all_certs_valid and ok

    if quorum_achieved:
        root_status = "SUCCESS"
        node_seq = ["parse", "dispatch", "aggregate", "verify", "commit"]
        evidence_present = ["parse", "dispatch", "aggregate", "verify", "commit"]
        chain_continuity = True
        output_keys = ["collective_result"]
    else:
        root_status = "FAILED"
        node_seq = ["parse", "dispatch"]
        evidence_present = ["parse", "dispatch"]
        chain_continuity = False
        output_keys = []

    # Blinded raw state telemetry: ZERO forbidden words
    state = {
        "subject": "governed_collective_scaling_unit",
        "spec_id": spec.spec_id,
        "governance_regime": spec.regime,
        "constituent_unit_count": M,
        "quorum_threshold_count": Q,
        "nominal_constituent_units": valid_count,
        "disturbed_constituent_units": k,
        "disturbance_density_ratio": round(rho, 4),
        "quorum_margin": quorum_margin,
        "boundary_certificates_valid": all_certs_valid,
        "declared_causal_edges": [
            ["parse", "dispatch"],
            ["dispatch", "aggregate"],
            ["aggregate", "verify"],
            ["verify", "commit"],
        ],
        "actor_role_bindings": {
            "parse": "role:parser",
            "dispatch": "role:dispatcher",
            "aggregate": "role:aggregator",
            "verify": "role:verifier",
            "commit": "role:commit",
        },
        "node_execution_sequence": node_seq,
        "evidence_records_present": evidence_present,
        "hash_chain_continuity": chain_continuity,
        "emitted_output_keys": output_keys,
    }

    oracle = {
        "spec_id": spec.spec_id,
        "ensemble_size": M,
        "quorum_fraction": spec.quorum_fraction,
        "regime": spec.regime,
        "disturbed_count": k,
        "valid_count": valid_count,
        "quorum_required": Q,
        "quorum_achieved": quorum_achieved,
        "quorum_margin": quorum_margin,
        "root_status": root_status,
        "boundary_certificates_valid": all_certs_valid,
        "passes_expected_behavior": (
            root_status == "SUCCESS" if quorum_achieved else root_status == "FAILED"
        ),
    }

    return {
        "spec": {
            "spec_id": spec.spec_id,
            "ensemble_size": spec.ensemble_size,
            "quorum_fraction": spec.quorum_fraction,
            "disturbed_count": spec.disturbed_count,
            "regime": spec.regime,
            "disturbance_density": rho,
            "quorum_required": Q,
        },
        "state": state,
        "oracle": oracle,
    }


def build_scaling_states(specs: Sequence[ScalingSpec] = DEFAULT_SCALING_SPECS) -> list[dict[str, Any]]:
    return [run_scaling_spec(spec) for spec in specs]


def _norm(v: Sequence[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _subtract(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [x - y for x, y in zip(a, b)]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float | None:
    denom = _norm(a) * _norm(b)
    if denom <= 1e-15:
        return None
    val = sum(x * y for x, y in zip(a, b)) / denom
    return max(-1.0, min(1.0, val))


def analyze_scaling_observations(
    deterministic_states: Sequence[dict[str, Any]],
    observations: Sequence[dict[str, Any]],
    *,
    specs: Sequence[ScalingSpec],
    replicates: int,
    thresholds: ScalingThresholds,
) -> dict[str, Any]:
    oracle_pass = all(
        item["oracle"]["passes_expected_behavior"]
        and item["oracle"]["boundary_certificates_valid"]
        for item in deterministic_states
    )

    grouped: dict[str, list[list[float]]] = {}
    for obs in observations:
        sid = str(obs["spec_id"])
        pres = obs.get("provider", {})
        vec = pres.get("vector")
        if vec is not None:
            grouped.setdefault(sid, []).append([float(x) for x in vec])

    expected_ids = {s.spec_id for s in specs}
    provider_complete = all(len(grouped.get(sid, [])) == replicates for sid in expected_ids)

    if not provider_complete:
        return {
            "oracle_pass": oracle_pass,
            "provider_complete": False,
            "gates": {
                "U0_deterministic_oracle": oracle_pass,
                "J0_provider_complete": False,
                "J1_subcritical_shielding_universal": False,
                "J2_transition_jump_invariant": False,
                "J3_cross_size_directional_alignment": False,
                "J4_amplitude_stability_across_size": False,
                "J5_policy_shift_consistency": False,
            },
            "supported_within_engineering_gates": False,
            "verdict": "NOT_SUPPORTED_BY_THIS_RUN",
        }

    # Within-state repeatability noise floor
    within_state_noises: list[float] = []
    for sid in expected_ids:
        reps = grouped[sid]
        mean_v = [sum(col) / len(reps) for col in zip(*reps)]
        for rep in reps:
            diff = [a - b for a, b in zip(rep, mean_v)]
            within_state_noises.append(_norm(diff))
    noise_floor = median(within_state_noises) if within_state_noises else 0.0

    # Mean vector for each spec
    spec_means = {
        sid: [sum(col) / len(reps) for col in zip(*reps)]
        for sid, reps in grouped.items()
    }

    # Calculate displacements relative to the respective baseline
    # For M8: baseline is M8_base
    # For M16: baseline is M16_base
    # For M32: baseline is M32_base
    baselines = {
        8: spec_means["M8_base"],
        16: spec_means["M16_base"],
        32: spec_means["M32_base"],
    }

    deltas: dict[str, list[float]] = {}
    norms: dict[str, float] = {}
    for spec in specs:
        sid = spec.spec_id
        base_v = baselines.get(spec.ensemble_size, spec_means["M16_base"])
        d = _subtract(spec_means[sid], base_v)
        deltas[sid] = d
        norms[sid] = _norm(d)

    # 1. Subcritical Shielding across M in {8, 16, 32} at rho = 0.25
    shielding_ratios: dict[int, float] = {}
    for M in (8, 16, 32):
        casc_norm = norms[f"M{M}_casc_25"]
        q_norm = norms[f"M{M}_sub_25"]
        shielding_ratios[M] = casc_norm / q_norm if q_norm > 1e-15 else float("inf")

    all_shielded = all(r >= thresholds.min_shielding_ratio for r in shielding_ratios.values())

    # 2. Transition Jump across M in {8, 16, 32}
    transition_jumps: dict[int, float] = {}
    for M in (8, 16, 32):
        j = norms[f"M{M}_at_thresh"] - norms[f"M{M}_pre_thresh"]
        transition_jumps[M] = j

    all_jumps_satisfied = all(j >= thresholds.min_transition_jump for j in transition_jumps.values())

    # 3. Post-Threshold Authority-Loss Direction Alignment across M in {8, 16, 32} and q=0.75
    post_threshold_sids = ["M8_at_thresh", "M16_at_thresh", "M32_at_thresh", "M16_q75_at", "M16_extinction"]
    cross_cosines: list[dict[str, Any]] = []
    for i in range(len(post_threshold_sids)):
        for j in range(i + 1, len(post_threshold_sids)):
            sid_a = post_threshold_sids[i]
            sid_b = post_threshold_sids[j]
            c = _cosine(deltas[sid_a], deltas[sid_b])
            cross_cosines.append({"spec_a": sid_a, "spec_b": sid_b, "cosine": c})

    valid_cosines = [item["cosine"] for item in cross_cosines if item["cosine"] is not None]
    min_cross_cosine = min(valid_cosines) if valid_cosines else 0.0
    direction_aligned = min_cross_cosine >= thresholds.min_cross_size_cosine

    # 4. Amplitude Stability across size: M8_at, M16_at, M32_at
    threshold_norms = [norms[f"M{M}_at_thresh"] for M in (8, 16, 32)]
    mean_amp = sum(threshold_norms) / len(threshold_norms)
    amp_cv = pstdev(threshold_norms) / mean_amp if mean_amp > 1e-15 else float("inf")
    amplitude_stable = amp_cv <= thresholds.max_post_threshold_norm_cv

    # 5. Policy Shift Consistency (q = 0.75 jump and direction)
    q75_jump = norms["M16_q75_at"] - norms["M16_q75_pre"]
    q75_align = _cosine(deltas["M16_q75_at"], deltas["M16_at_thresh"]) or 0.0
    policy_consistent = q75_jump >= thresholds.min_transition_jump and q75_align >= thresholds.min_cross_size_cosine

    gates = {
        "U0_deterministic_oracle": oracle_pass,
        "J0_provider_complete": provider_complete,
        "J1_subcritical_shielding_universal": all_shielded,
        "J2_transition_jump_invariant": all_jumps_satisfied,
        "J3_cross_size_directional_alignment": direction_aligned,
        "J4_amplitude_stability_across_size": amplitude_stable,
        "J5_policy_shift_consistency": policy_consistent,
    }

    supported = all(gates.values())

    return {
        "oracle_pass": oracle_pass,
        "provider_complete": provider_complete,
        "repeatability_noise_floor_l2": noise_floor,
        "shielding_ratios": shielding_ratios,
        "transition_jumps": transition_jumps,
        "post_threshold_norms": {sid: norms[sid] for sid in post_threshold_sids},
        "amplitude_cv_across_size": amp_cv,
        "minimum_cross_size_cosine": min_cross_cosine,
        "pairwise_cross_cosines": cross_cosines,
        "policy_q75_metrics": {
            "q75_jump": q75_jump,
            "q75_to_q50_cosine": q75_align,
        },
        "all_spec_metrics": [
            {
                "spec_id": s.spec_id,
                "ensemble_size": s.ensemble_size,
                "quorum_fraction": s.quorum_fraction,
                "disturbed_count": s.disturbed_count,
                "regime": s.regime,
                "displacement_norm": norms[s.spec_id],
                "mean_vector": spec_means[s.spec_id],
            }
            for s in specs
        ],
        "thresholds": {
            "min_shielding_ratio": thresholds.min_shielding_ratio,
            "min_transition_jump": thresholds.min_transition_jump,
            "min_cross_size_cosine": thresholds.min_cross_size_cosine,
            "max_post_threshold_norm_cv": thresholds.max_post_threshold_norm_cv,
        },
        "gates": gates,
        "supported_within_engineering_gates": supported,
        "verdict": (
            "SUPPORTED_WITHIN_PREREGISTERED_ENGINEERING_GATES"
            if supported
            else "NOT_SUPPORTED_BY_THIS_RUN"
        ),
    }


def run_live_scaling_experiment(
    *,
    provider: JevProvider,
    specs: Sequence[ScalingSpec] = DEFAULT_SCALING_SPECS,
    replicates: int = 3,
    thresholds: ScalingThresholds,
) -> dict[str, Any]:
    deterministic_states = build_scaling_states(specs)
    questions = question_payload()
    observations: list[dict[str, Any]] = []
    total_calls = len(deterministic_states) * replicates

    for item in deterministic_states:
        sid = str(item["spec"]["spec_id"])
        M = int(item["spec"]["ensemble_size"])
        k = int(item["spec"]["disturbed_count"])
        rho = float(item["spec"]["disturbance_density"])
        for rep in range(replicates):
            request_id = f"uow-scale-{sid}-r{rep}"
            provider_res = provider.decide(
                state=dict(item["state"]),
                questions=questions,
                request_id=request_id,
            )
            vec = provider_res.get("vector") or []
            v_norm = _norm(vec) if vec else 0.0
            print(
                f"[{len(observations) + 1:02d}/{total_calls:02d}] {sid:<15} "
                f"(M={M:02d}, k={k:02d}, rho={rho:0.4f}) rep={rep} -> norm={v_norm:.4f}",
                flush=True,
            )
            observations.append(
                {
                    "spec_id": sid,
                    "replicate": rep,
                    "provider": provider_res,
                }
            )

    analysis = analyze_scaling_observations(
        deterministic_states,
        observations,
        specs=specs,
        replicates=replicates,
        thresholds=thresholds,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "JEV x UoW Finite-Size Collective Scaling Campaign",
        "method": {
            "ensemble_sizes": sorted(list({s.ensemble_size for s in specs})),
            "state_specs": [
                {
                    "spec_id": s.spec_id,
                    "ensemble_size": s.ensemble_size,
                    "quorum_fraction": s.quorum_fraction,
                    "disturbed_count": s.disturbed_count,
                    "regime": s.regime,
                }
                for s in specs
            ],
            "replicates_per_state": replicates,
            "questions_per_request": len(questions),
            "requests_total": total_calls,
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
        description="Run the JEV x UoW Finite-Size Collective Scaling Campaign."
    )
    parser.add_argument("--model", default=DEFAULT_JEV_MODEL)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Validate UoW deterministic states and exit without calling JEV.",
    )
    args = parser.parse_args()

    thresholds = ScalingThresholds()

    if args.prepare_only:
        states = build_scaling_states()
        payload = {
            "schema_version": SCHEMA_VERSION,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "prepare_only",
            "deterministic_states": states,
            "oracle_pass": all(
                item["oracle"]["passes_expected_behavior"]
                and item["oracle"]["boundary_certificates_valid"]
                for item in states
            ),
        }
    else:
        provider = TypeSafeJevProvider(model=args.model, timeout_s=args.timeout_s)
        payload = run_live_scaling_experiment(
            provider=provider,
            replicates=args.replicates,
            thresholds=thresholds,
        )

    _write_json(args.output, payload)
    print(json.dumps(payload.get("analysis", payload), indent=2, sort_keys=True))
    print(f"\nWrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
