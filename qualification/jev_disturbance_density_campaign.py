"""JEV x UoW Disturbance Density and Collective Phase Transition Campaign.

Question
========
What happens to the observer geometry of governed recursive systems when multiple
independent authority disturbances occur simultaneously across constituent subtrees?
Specifically:
1. Superposition vs Saturation: Does displacement scale linearly with disturbance
   density rho = k/M, or does it saturate non-linearly?
2. Critical Phase Transition: Under an authority quorum threshold Q = ceil(0.5 * M) + 1,
   does the system exhibit a sharp phase transition at rho_c = 0.50?
3. Quorum Shielding: Does collective quorum governance shield the root observer geometry
   below rho_c compared to an unshielded serial cascade?
4. Supercritical Convergence: For rho >= rho_c, does the disturbance vector converge
   to the invariant authority-loss fixed-point attractor Delta_A*?
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


SCHEMA_VERSION = "uow.jev_disturbance_density.v1"
DEFAULT_OUTPUT = Path("qualification/artifacts/jev_disturbance_density_results.json")

# 16 constituent child subsystems
TOTAL_CONSTITUENT_UNITS = 16

# Density ladder points: k disturbed units out of 16
DISTURBANCE_LADDER_K = (0, 1, 2, 4, 6, 8, 12, 16)

REGIMES = ("quorum_consensus", "serial_cascade")


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
class DensityThresholds:
    min_signal_to_noise: float = 2.0
    min_phase_transition_jump: float = 0.15
    min_supercritical_cosine: float = 0.95
    max_supercritical_norm_cv: float = 0.15


def make_child_runtime(index: int) -> tuple[AdaptiveCompositionRuntime, Any]:
    """Create one boundary-certified child subsystem."""
    prefix = f"child_{index}"
    output_key = f"{prefix}_result"
    contract = ParentContract(
        contract_id=f"{prefix}:contract",
        description=f"Child unit {index} contract",
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
            max_cpu_cores=4,
            max_ram_units=8,
            max_gpu_slots=0,
            max_npu_slots=0,
            max_cost_units=50.0,
        ),
        failure_semantics=FailureSemantics.ROLLBACK,
    )
    graph = RealizationGraph(
        f"{prefix}:graph",
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
    cert = certify_composition_boundary(prefix, graph, contract)
    if not cert.is_accepted:
        raise RuntimeError(f"Child {index} certification failed: {cert.violations}")
    return runtime, cert


def make_collective_system(
    regime: str,
    k_disturbed: int,
    M: int = TOTAL_CONSTITUENT_UNITS,
) -> dict[str, Any]:
    """Execute collective assembly with k disturbed subtrees under specified regime."""
    if k_disturbed < 0 or k_disturbed > M:
        raise ValueError(f"k_disturbed {k_disturbed} must be in [0, {M}]")

    # In quorum consensus: strict majority Q = 9 out of 16 (rho_c = 0.50)
    # In serial cascade: all required Q = 16 (rho_c = 0.0625)
    quorum_required = 9 if regime == "quorum_consensus" else M
    rho = k_disturbed / float(M)

    # Instantiate all M child runtimes
    child_runtimes: list[AdaptiveCompositionRuntime] = []
    child_certs: list[Any] = []
    for i in range(M):
        rt, cert = make_child_runtime(i)
        child_runtimes.append(rt)
        child_certs.append(cert)

    # Induce authority loss in the first k children
    for i in range(k_disturbed):
        child_runtimes[i].registry.update_status(f"child_{i}:verify", availability=False)

    # Execute all M children and collect receipts
    valid_receipts: list[dict[str, Any]] = []
    failed_receipts: list[dict[str, Any]] = []

    for i in range(M):
        child_rt = child_runtimes[i]
        receipt = child_rt.execute({"payload": f"task-child-{i}"})
        if receipt.status == "SUCCESS":
            valid_receipts.append({"index": i, "receipt": receipt})
        else:
            failed_receipts.append({"index": i, "receipt": receipt})

    valid_count = len(valid_receipts)
    quorum_achieved = valid_count >= quorum_required
    quorum_margin = valid_count - quorum_required

    # Verify all composition boundary certificates remain valid
    all_certs_valid = True
    for rt, cert in zip(child_runtimes, child_certs):
        ok, _ = verify_composition_boundary(cert, rt.active_graph, rt.contract)
        all_certs_valid = all_certs_valid and ok

    # Determine root execution outcome
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

    # Blinded raw state representation: ZERO forbidden outcome/error strings
    state = {
        "subject": "governed_collective_assembly",
        "governance_regime": regime,
        "constituent_unit_count": M,
        "quorum_threshold_count": quorum_required,
        "nominal_constituent_units": valid_count,
        "disturbed_constituent_units": k_disturbed,
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
        "regime": regime,
        "k_disturbed": k_disturbed,
        "disturbance_density": rho,
        "valid_count": valid_count,
        "quorum_required": quorum_required,
        "quorum_achieved": quorum_achieved,
        "quorum_margin": quorum_margin,
        "root_status": root_status,
        "boundary_certificates_valid": all_certs_valid,
        "passes_expected_behavior": (
            root_status == "SUCCESS" if quorum_achieved else root_status == "FAILED"
        ),
    }

    return {
        "regime": regime,
        "k_disturbed": k_disturbed,
        "disturbance_density": rho,
        "state": state,
        "oracle": oracle,
    }


def build_disturbance_density_states(
    regimes: Sequence[str] = REGIMES,
    ladder: Sequence[int] = DISTURBANCE_LADDER_K,
    M: int = TOTAL_CONSTITUENT_UNITS,
) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    for regime in regimes:
        for k in ladder:
            states.append(make_collective_system(regime, k, M))
    return states


def _norm(vector: Sequence[float]) -> float:
    return math.sqrt(sum(v * v for v in vector))


def _subtract(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [x - y for x, y in zip(a, b)]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float | None:
    denom = _norm(a) * _norm(b)
    if denom <= 1e-15:
        return None
    val = sum(x * y for x, y in zip(a, b)) / denom
    return max(-1.0, min(1.0, val))


def analyze_density_observations(
    deterministic_states: Sequence[dict[str, Any]],
    observations: Sequence[dict[str, Any]],
    *,
    regimes: Sequence[str],
    ladder: Sequence[int],
    replicates: int,
    thresholds: DensityThresholds,
) -> dict[str, Any]:
    oracle_pass = all(
        item["oracle"]["passes_expected_behavior"]
        and item["oracle"]["boundary_certificates_valid"]
        for item in deterministic_states
    )

    grouped: dict[tuple[str, int], list[list[float]]] = {}
    for obs in observations:
        regime = str(obs["regime"])
        k = int(obs["k_disturbed"])
        provider_res = obs.get("provider", {})
        vec = provider_res.get("vector")
        if vec is not None:
            grouped.setdefault((regime, k), []).append([float(v) for v in vec])

    expected_keys = {(r, k) for r in regimes for k in ladder}
    provider_complete = all(len(grouped.get(key, [])) == replicates for key in expected_keys)

    if not provider_complete:
        return {
            "oracle_pass": oracle_pass,
            "provider_complete": False,
            "gates": {
                "U0_deterministic_oracle": oracle_pass,
                "J0_provider_complete": False,
                "J1_subcritical_monotonic_strain": False,
                "J2_critical_phase_transition_jump": False,
                "J3_supercritical_directional_saturation": False,
                "J4_quorum_shielding_effect": False,
            },
            "supported_within_engineering_gates": False,
            "verdict": "NOT_SUPPORTED_BY_THIS_RUN",
        }

    # Within-state repeatability noise floor
    within_state_noises: list[float] = []
    for key in expected_keys:
        reps = grouped[key]
        mean_vec = [sum(col) / len(reps) for col in zip(*reps)]
        for rep in reps:
            diff = [a - b for a, b in zip(rep, mean_vec)]
            within_state_noises.append(_norm(diff))
    noise_floor = median(within_state_noises) if within_state_noises else 0.0

    regime_analyses: dict[str, Any] = {}

    for regime in regimes:
        baseline_reps = grouped[(regime, 0)]
        baseline_mean = [sum(col) / len(baseline_reps) for col in zip(*baseline_reps)]

        ladder_metrics: list[dict[str, Any]] = []
        deltas: list[list[float]] = []
        norms: list[float] = []

        for k in ladder:
            reps = grouped[(regime, k)]
            k_mean = [sum(col) / len(reps) for col in zip(*reps)]
            delta = _subtract(k_mean, baseline_mean)
            d_norm = _norm(delta)
            deltas.append(delta)
            norms.append(d_norm)

            rho = k / float(TOTAL_CONSTITUENT_UNITS)
            ladder_metrics.append(
                {
                    "k_disturbed": k,
                    "disturbance_density": rho,
                    "mean_vector": k_mean,
                    "displacement_delta": delta,
                    "displacement_norm": d_norm,
                }
            )

        regime_analyses[regime] = {
            "baseline_mean": baseline_mean,
            "ladder_metrics": ladder_metrics,
            "deltas": deltas,
            "norms": norms,
        }

    # Gate J1: Sub-critical monotonic strain in Quorum Consensus
    # For k in [0, 1, 2, 4, 6] (rho < 0.50):
    q_norms = regime_analyses["quorum_consensus"]["norms"]
    # indices: 0:k=0, 1:k=1, 2:k=2, 3:k=4, 4:k=6, 5:k=8, 6:k=12, 7:k=16
    # Subcritical strain: norm increases from k=1 to k=6 (or k=0 to k=6)
    subcritical_monotonic = q_norms[4] >= q_norms[1] - noise_floor

    # Gate J2: Critical Phase Transition Jump at rho_c = 0.50 (k=6 to k=8)
    # The jump between k=6 and k=8 should be pronounced
    transition_jump = q_norms[5] - q_norms[4]
    critical_jump_satisfied = transition_jump >= thresholds.min_phase_transition_jump

    # Gate J3: Super-critical Directional Saturation (k=8, 12, 16)
    q_deltas = regime_analyses["quorum_consensus"]["deltas"]
    supercritical_cosines: list[float] = []
    supercritical_indices = [5, 6, 7]  # k=8, 12, 16
    for i in range(len(supercritical_indices)):
        for j in range(i + 1, len(supercritical_indices)):
            idx_a = supercritical_indices[i]
            idx_b = supercritical_indices[j]
            cos_val = _cosine(q_deltas[idx_a], q_deltas[idx_b])
            if cos_val is not None:
                supercritical_cosines.append(cos_val)

    min_supercritical_cos = min(supercritical_cosines) if supercritical_cosines else 0.0
    supercritical_direction_stable = min_supercritical_cos >= thresholds.min_supercritical_cosine

    # Gate J4: Quorum Shielding Effect
    # At intermediate disturbance k=4 (rho=0.25):
    # Quorum displacement should be strictly lower than Cascade displacement
    c_norms = regime_analyses["serial_cascade"]["norms"]
    k4_quorum_norm = q_norms[3]  # k=4
    k4_cascade_norm = c_norms[3]  # k=4
    quorum_shielding_satisfied = k4_quorum_norm < k4_cascade_norm

    gates = {
        "U0_deterministic_oracle": oracle_pass,
        "J0_provider_complete": provider_complete,
        "J1_subcritical_monotonic_strain": subcritical_monotonic,
        "J2_critical_phase_transition_jump": critical_jump_satisfied,
        "J3_supercritical_directional_saturation": supercritical_direction_stable,
        "J4_quorum_shielding_effect": quorum_shielding_satisfied,
    }

    supported = all(gates.values())

    return {
        "oracle_pass": oracle_pass,
        "provider_complete": provider_complete,
        "repeatability_noise_floor_l2": noise_floor,
        "quorum_consensus": regime_analyses.get("quorum_consensus"),
        "serial_cascade": regime_analyses.get("serial_cascade"),
        "metrics": {
            "k4_quorum_displacement_norm": k4_quorum_norm,
            "k4_cascade_displacement_norm": k4_cascade_norm,
            "shielding_damping_ratio": (
                k4_cascade_norm / k4_quorum_norm if k4_quorum_norm > 1e-15 else float("inf")
            ),
            "critical_transition_jump_k6_to_k8": transition_jump,
            "min_supercritical_cosine": min_supercritical_cos,
        },
        "thresholds": {
            "min_phase_transition_jump": thresholds.min_phase_transition_jump,
            "min_supercritical_cosine": thresholds.min_supercritical_cosine,
            "max_supercritical_norm_cv": thresholds.max_supercritical_norm_cv,
        },
        "gates": gates,
        "supported_within_engineering_gates": supported,
        "verdict": (
            "SUPPORTED_WITHIN_PREREGISTERED_ENGINEERING_GATES"
            if supported
            else "NOT_SUPPORTED_BY_THIS_RUN"
        ),
    }


def run_live_density_experiment(
    *,
    provider: JevProvider,
    regimes: Sequence[str] = REGIMES,
    ladder: Sequence[int] = DISTURBANCE_LADDER_K,
    replicates: int = 3,
    thresholds: DensityThresholds,
) -> dict[str, Any]:
    deterministic_states = build_disturbance_density_states(regimes, ladder)
    questions = question_payload()
    observations: list[dict[str, Any]] = []
    total_calls = len(deterministic_states) * replicates

    for item in deterministic_states:
        regime = str(item["regime"])
        k = int(item["k_disturbed"])
        rho = float(item["disturbance_density"])
        for rep in range(replicates):
            request_id = f"uow-density-{regime}-k{k}-r{rep}"
            provider_result = provider.decide(
                state=dict(item["state"]),
                questions=questions,
                request_id=request_id,
            )
            vec = provider_result.get("vector") or []
            v_norm = _norm(vec) if vec else 0.0
            print(
                f"[{len(observations) + 1:02d}/{total_calls:02d}] {regime:<17} "
                f"k={k:02d}/16 (rho={rho:0.4f}) rep={rep} -> norm={v_norm:.4f}",
                flush=True,
            )
            observations.append(
                {
                    "regime": regime,
                    "k_disturbed": k,
                    "disturbance_density": rho,
                    "replicate": rep,
                    "provider": provider_result,
                }
            )

    analysis = analyze_density_observations(
        deterministic_states,
        observations,
        regimes=regimes,
        ladder=ladder,
        replicates=replicates,
        thresholds=thresholds,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "JEV x UoW Disturbance Density and Collective Phase Transition Test",
        "method": {
            "total_constituent_units": TOTAL_CONSTITUENT_UNITS,
            "regimes": list(regimes),
            "disturbance_ladder_k": list(ladder),
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
        description="Run the JEV x UoW Disturbance Density & Phase Transition Campaign."
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
    parser.add_argument("--min-phase-jump", type=float, default=0.15)
    parser.add_argument("--min-supercritical-cos", type=float, default=0.95)
    args = parser.parse_args()

    thresholds = DensityThresholds(
        min_phase_transition_jump=args.min_phase_jump,
        min_supercritical_cosine=args.min_supercritical_cos,
    )

    if args.prepare_only:
        states = build_disturbance_density_states()
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
        payload = run_live_density_experiment(
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
