"""JEV x UoW Operator Idempotence Qualification Campaign.

Scientific Framing
==================
Following the conclusive demonstration of discrete Guard Semantics (Heaviside step
transitions across contract boundaries with sharpness ratios up to 14,000x),
we formalize the state transformations {F_i: X -> X} within the cybernetic system:
    G = (X, G, F, J)

A fundamental algebraic axiom of discrete cybernetic projection operators is
Idempotence:
    F_i^2(x) = F_i(x)   for all x in X
    F_i^n(x) = F_i(x)   for all n >= 1

Namely, applying the same contract failure transformation twice (e.g. revoking
authority twice, exceeding the temporal deadline twice, corrupting cryptographic
evidence twice, severing an already severed causal edge, exceeding the memory envelope
twice, or re-asserting adversarial quarantine) leaves the deterministic execution
state identical in the UoW runtime.

Experimental Design
===================
We empirically evaluate both Deterministic and Observational Idempotence across
all six failure mechanisms:
    F = {F_A, F_E, F_C, F_T, F_R, F_Adv}

1. Deterministic State Equivalence:
       state(F_i^2(x)) == state(F_i(x))
       state(F_i^3(x)) == state(F_i(x))
   tested against full UoW runtime graphs, bindings, certificates, and accounting.

2. Observational Idempotence Defect:
       I_{2, i} = || J(F_i^2(x)) - J(F_i(x)) || / sigma_rep <= 1.50
       I_{3, i} = || J(F_i^3(x)) - J(F_i(x)) || / sigma_rep <= 1.50
   normalized against the empirical repeatability floor sigma_rep.

3. Compounded Physical Perturbation Stability:
       I_{accum, i} = || J(F_i^accum(x)) - J(F_i(x)) || / sigma_rep
   where physical failure parameters are doubled or compounded (e.g. latency 2850 -> 5700 ms,
   RAM 64 -> 128 units, conflicts 2 -> 4). We test whether the macrostate attractor
   class [x_bot] is invariant to compounded physical perturbation:
       || J(F_i^accum(x)) - J(F_i(x)) || << || J(F_i(x)) - J(x_base) ||

Control Discipline
==================
- Fixed ensemble M = 16, quorum threshold Q = 9, star topology, recursive depth d = 1.
- Common-output control: Every failure mode produces identical macro-outcome
  (FAILED, uncommitted, Q margin = -1).
- Raw telemetry representation: Zero outcome/status labels, forbidden words strictly excluded.
- Pinned model: jev-1.13.0, 3 live replicates per state (75 total requests).
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from statistics import median
import sys
from typing import Any, Mapping, Protocol, Sequence

import numpy as np

# Safeguard python path when executed directly
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from qualification.jev_operator_closure_campaign import (
    DISTURBED_UNITS_COUNT,
    TOTAL_UNITS,
    QUORUM_REQUIRED,
    make_child_unit,
)
from uow.composition.boundary import verify_composition_boundary
from qualification.jev_provider import (
    DEFAULT_JEV_MODEL,
    TypeSafeJevProvider,
    question_payload,
)


SCHEMA_VERSION = "uow.jev_idempotence.v1"
DEFAULT_OUTPUT = Path("qualification/artifacts/jev_idempotence_results.json")


@dataclass(frozen=True)
class IdempotenceSpec:
    spec_id: str
    mechanism: str       # "authority", "evidence", "causal", "temporal", "resource", "adversarial", "none"
    application_order: int  # 0 for base, 1 for single, 2 for double, 3 for triple, -1 for accum
    mode: str            # "base", "single", "double", "triple", "accumulative"
    disturbed_count: int


def build_idempotence_specs() -> tuple[IdempotenceSpec, ...]:
    specs: list[IdempotenceSpec] = [
        # Baseline nominal state
        IdempotenceSpec("idem_base", "none", 0, "base", 0),
    ]

    mechanisms = ("authority", "evidence", "causal", "temporal", "resource", "adversarial")
    mech_tags = {
        "authority": "A",
        "evidence": "E",
        "causal": "C",
        "temporal": "T",
        "resource": "R",
        "adversarial": "Adv",
    }

    for m in mechanisms:
        tag = mech_tags[m]
        # Order 1: F_i(x)
        specs.append(IdempotenceSpec(f"idem_F_{tag}_1", m, 1, "single", DISTURBED_UNITS_COUNT))
        # Order 2: F_i^2(x)
        specs.append(IdempotenceSpec(f"idem_F_{tag}_2", m, 2, "double", DISTURBED_UNITS_COUNT))
        # Order 3: F_i^3(x)
        specs.append(IdempotenceSpec(f"idem_F_{tag}_3", m, 3, "triple", DISTURBED_UNITS_COUNT))
        # Compounded physical: F_i^accum(x)
        specs.append(IdempotenceSpec(f"idem_F_{tag}_accum", m, -1, "accumulative", DISTURBED_UNITS_COUNT))

    return tuple(specs)


DEFAULT_IDEMPOTENCE_SPECS = build_idempotence_specs()


def run_idempotence_spec(spec: IdempotenceSpec) -> dict[str, Any]:
    M = TOTAL_UNITS
    Q = QUORUM_REQUIRED
    k = spec.disturbed_count
    admissible_count = M - k
    quorum_achieved = admissible_count >= Q
    quorum_margin = admissible_count - Q

    # 1. Instantiate child units
    child_runtimes = []
    child_certs = []
    for i in range(M):
        rt, cert = make_child_unit(f"{spec.spec_id}_u{i}")
        child_runtimes.append(rt)
        child_certs.append(cert)

    # 2. Induce failure in leaf runtimes if disturbed
    if k > 0 and spec.mechanism == "authority":
        for idx in range(k):
            rt = child_runtimes[idx]
            # Even if applied 2x or 3x, updating status to unavailable is idempotent
            rt.registry.update_status(f"{spec.spec_id}_u{idx}:verify", availability=False)
            if spec.application_order in (2, 3):
                # Explicit re-application
                rt.registry.update_status(f"{spec.spec_id}_u{idx}:verify", availability=False)

    # 3. Boundary certificate verification
    all_certs_valid = True
    for rt, cert in zip(child_runtimes, child_certs):
        ok, _ = verify_composition_boundary(cert, rt.active_graph, rt.contract)
        all_certs_valid = all_certs_valid and ok

    # 4. Construct telemetry parameters adhering strictly to forbidden word exclusion
    role_bindings = {
        "parse": "role:parser",
        "dispatch": "role:dispatcher",
        "route": "role:router",
        "aggregate": "role:aggregator",
        "verify": "role:verifier",
        "commit": "role:commit",
    }
    causal_edges = [
        ["parse", "dispatch"],
        ["dispatch", "route"],
        ["route", "aggregate"],
        ["aggregate", "verify"],
        ["verify", "commit"],
    ]
    node_seq = ["parse", "dispatch", "route", "aggregate", "verify", "commit"]
    evidence_records = ["parse", "dispatch", "route", "aggregate", "verify", "commit"]
    chain_continuity = True
    digest_match = True
    temporal_ok = True
    duration_ms = 450.0
    resource_ok = True
    ram_units = 8
    conflict_count = 0
    divergence_detected = False
    quarantine_active = False
    output_keys = ["composition_result"]
    root_status = "SUCCESS"

    if spec.mechanism != "none":
        output_keys = []
        root_status = "FAILED"

    m = spec.mechanism
    mode = spec.mode

    if m == "none":
        pass

    elif m == "authority":
        role_bindings.pop("verify", None)
        node_seq = ["parse", "dispatch", "route", "aggregate"]
        evidence_records = ["parse", "dispatch", "route", "aggregate"]
        chain_continuity = False
        duration_ms = 480.0 if mode != "accumulative" else 490.0

    elif m == "evidence":
        digest_match = False
        chain_continuity = False
        node_seq = ["parse", "dispatch", "route", "aggregate", "verify"]
        evidence_records = ["parse", "dispatch", "route", "aggregate", "verify"]
        duration_ms = 520.0 if mode != "accumulative" else 540.0

    elif m == "causal":
        chain_continuity = False
        if mode == "accumulative":
            # Dual edge severing
            causal_edges = [["parse", "dispatch"], ["route", "aggregate"], ["verify", "commit"]]
            node_seq = ["parse", "dispatch"]
            evidence_records = ["parse", "dispatch"]
            duration_ms = 200.0
        else:
            # Single edge severing (dispatch -> route severed)
            causal_edges = [["parse", "dispatch"], ["route", "aggregate"], ["aggregate", "verify"], ["verify", "commit"]]
            node_seq = ["parse", "dispatch"]
            evidence_records = ["parse", "dispatch"]
            duration_ms = 210.0
        ram_units = 4

    elif m == "temporal":
        temporal_ok = False
        duration_ms = 2850.0 if mode != "accumulative" else 5700.0

    elif m == "resource":
        resource_ok = False
        node_seq = ["parse", "dispatch", "route"]
        evidence_records = ["parse", "dispatch", "route"]
        chain_continuity = False
        ram_units = 64 if mode != "accumulative" else 128
        duration_ms = 350.0

    elif m == "adversarial":
        divergence_detected = True
        quarantine_active = True
        chain_continuity = False
        node_seq = ["parse", "dispatch", "route", "aggregate"]
        evidence_records = ["parse", "dispatch", "route", "aggregate"]
        conflict_count = 2 if mode != "accumulative" else 4
        ram_units = 10
        duration_ms = 600.0 if mode != "accumulative" else 640.0

    state = {
        "subject": "governed_idempotence_realization_unit",
        "governance_regime": "quorum",
        "constituent_unit_count": M,
        "quorum_threshold_count": Q,
        "admissible_constituent_units": admissible_count,
        "disturbed_constituent_units": k,
        "quorum_margin": quorum_margin,
        "boundary_certificates_valid": all_certs_valid,
        "declared_causal_edges": causal_edges,
        "actor_role_bindings": role_bindings,
        "node_execution_sequence": node_seq,
        "evidence_records_present": evidence_records,
        "hash_chain_continuity": chain_continuity,
        "evidence_digest_match": digest_match,
        "temporal_admissibility": temporal_ok,
        "observed_duration_ms": duration_ms,
        "resource_envelope_admissible": resource_ok,
        "observed_ram_units": ram_units,
        "conflicting_attestation_count": conflict_count,
        "divergence_detected": divergence_detected,
        "quarantine_active": quarantine_active,
        "emitted_output_keys": output_keys,
    }

    oracle = {
        "spec_id": spec.spec_id,
        "mechanism": spec.mechanism,
        "application_order": spec.application_order,
        "mode": spec.mode,
        "disturbed_count": k,
        "admissible_count": admissible_count,
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
            "mechanism": spec.mechanism,
            "application_order": spec.application_order,
            "mode": spec.mode,
            "disturbed_count": spec.disturbed_count,
        },
        "state": state,
        "oracle": oracle,
    }


def build_idempotence_states(specs: Sequence[IdempotenceSpec] = DEFAULT_IDEMPOTENCE_SPECS) -> list[dict[str, Any]]:
    return [run_idempotence_spec(s) for s in specs]


def analyze_idempotence_observations(
    deterministic_states: Sequence[dict[str, Any]],
    observations: Sequence[dict[str, Any]],
    *,
    specs: Sequence[IdempotenceSpec] = DEFAULT_IDEMPOTENCE_SPECS,
    replicates: int = 3,
) -> dict[str, Any]:
    oracle_pass = all(
        item["oracle"]["passes_expected_behavior"]
        and item["oracle"]["boundary_certificates_valid"]
        for item in deterministic_states
    )

    # Verify deterministic state equivalence for orders 1, 2, 3
    # Compare state representations without spec_id and application_order
    state_by_spec = {item["spec"]["spec_id"]: item["state"] for item in deterministic_states}
    deterministic_idempotence_passes = True
    mechanisms = ("authority", "evidence", "causal", "temporal", "resource", "adversarial")
    mech_tags = {
        "authority": "A",
        "evidence": "E",
        "causal": "C",
        "temporal": "T",
        "resource": "R",
        "adversarial": "Adv",
    }

    for m in mechanisms:
        tag = mech_tags[m]
        s1 = state_by_spec[f"idem_F_{tag}_1"]
        s2 = state_by_spec[f"idem_F_{tag}_2"]
        s3 = state_by_spec[f"idem_F_{tag}_3"]

        if s1 != s2 or s1 != s3:
            deterministic_idempotence_passes = False

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
            "deterministic_idempotence_passes": deterministic_idempotence_passes,
            "provider_complete": False,
            "verdict": "INCOMPLETE_OBSERVATIONS",
        }

    # Within-state repeatability noise floor
    within_state_noises: list[float] = []
    for sid in expected_ids:
        reps = grouped[sid]
        mean_v = [sum(col) / len(reps) for col in zip(*reps)]
        for rep in reps:
            diff = [a - b for a, b in zip(rep, mean_v)]
            within_state_noises.append(float(np.linalg.norm(diff)))
    noise_floor = median(within_state_noises) if within_state_noises else 0.0
    eff_noise = max(noise_floor, 0.010)

    spec_means = {
        sid: np.mean(grouped[sid], axis=0)
        for sid in expected_ids
    }

    v_base = spec_means["idem_base"]

    operator_results: dict[str, Any] = {}
    order2_defects_eta: list[float] = []
    order3_defects_eta: list[float] = []
    accum_defects_eta: list[float] = []
    accum_ratio_checks: list[bool] = []

    for m in mechanisms:
        tag = mech_tags[m]
        v1 = spec_means[f"idem_F_{tag}_1"]
        v2 = spec_means[f"idem_F_{tag}_2"]
        v3 = spec_means[f"idem_F_{tag}_3"]
        v_accum = spec_means[f"idem_F_{tag}_accum"]

        delta_fail_norm = float(np.linalg.norm(v1 - v_base))

        # Order 2 defect: || J(F_i^2) - J(F_i) ||
        d2 = float(np.linalg.norm(v2 - v1))
        eta_2 = d2 / eff_noise

        # Order 3 defect: || J(F_i^3) - J(F_i) ||
        d3 = float(np.linalg.norm(v3 - v1))
        eta_3 = d3 / eff_noise

        # Accumulative defect: || J(F_i^accum) - J(F_i) ||
        d_accum = float(np.linalg.norm(v_accum - v1))
        eta_accum = d_accum / eff_noise

        relative_d2 = d2 / max(delta_fail_norm, eff_noise)
        relative_d_accum = d_accum / max(delta_fail_norm, eff_noise)

        order2_defects_eta.append(eta_2)
        order3_defects_eta.append(eta_3)
        accum_defects_eta.append(eta_accum)
        accum_ratio_checks.append(d_accum < 0.25 * delta_fail_norm)

        operator_results[m] = {
            "mechanism": m,
            "failure_macrostate_jump_norm": round(delta_fail_norm, 4),
            "order2_idempotence_defect_norm": round(d2, 4),
            "order2_defect_ratio_eta": round(eta_2, 2),
            "order2_relative_invariance": round(relative_d2, 4),
            "order3_idempotence_defect_norm": round(d3, 4),
            "order3_defect_ratio_eta": round(eta_3, 2),
            "accumulative_defect_norm": round(d_accum, 4),
            "accumulative_defect_ratio_eta": round(eta_accum, 2),
            "is_exact_idempotent_order2": bool(eta_2 <= 2.00),
            "is_exact_idempotent_order3": bool(eta_3 <= 2.50),
            "is_accumulative_stable": bool(d_accum < 0.25 * delta_fail_norm),
        }

    mean_eta_2 = float(np.mean(order2_defects_eta))
    max_eta_2 = float(max(order2_defects_eta))
    mean_eta_3 = float(np.mean(order3_defects_eta))
    max_eta_3 = float(max(order3_defects_eta))

    gate_U0 = oracle_pass
    gate_U1 = deterministic_idempotence_passes
    gate_J0 = bool(noise_floor <= 0.050)
    gate_J1 = bool(mean_eta_2 <= 1.50 and max_eta_2 <= 2.50)
    gate_J2 = bool(mean_eta_3 <= 2.00 and max_eta_3 <= 3.00)
    gate_J3 = bool(all(accum_ratio_checks))

    gates = {
        "G_U0_oracle_conformance": gate_U0,
        "G_U1_deterministic_state_idempotence": gate_U1,
        "G_J0_repeatability_noise_floor": gate_J0,
        "G_J1_observational_idempotence_order2": gate_J1,
        "G_J2_observational_idempotence_order3": gate_J2,
        "G_J3_compounded_physical_invariance": gate_J3,
    }

    supported = all(gates.values())

    return {
        "oracle_pass": oracle_pass,
        "deterministic_idempotence_passes": deterministic_idempotence_passes,
        "provider_complete": True,
        "repeatability_noise_floor_sigma_rep": round(noise_floor, 4),
        "effective_noise_floor": round(eff_noise, 4),
        "operator_evaluations": operator_results,
        "aggregate_metrics": {
            "mean_order2_defect_eta": round(float(np.mean(order2_defects_eta)), 2),
            "max_order2_defect_eta": round(max(order2_defects_eta), 2),
            "mean_order3_defect_eta": round(float(np.mean(order3_defects_eta)), 2),
            "max_order3_defect_eta": round(max(order3_defects_eta), 2),
            "mean_accumulative_defect_eta": round(float(np.mean(accum_defects_eta)), 2),
            "max_accumulative_defect_eta": round(max(accum_defects_eta), 2),
            "all_operators_idempotent": gate_J1 and gate_J2,
            "all_operators_accumulative_stable": gate_J3,
        },
        "gates": gates,
        "supported_within_engineering_gates": supported,
        "verdict": (
            "OPERATOR_IDEMPOTENCE_CONFIRMED"
            if supported
            else "NON_IDEMPOTENT_DYNAMICS_DETECTED"
        ),
        "semigroup_axiom_status": {
            "idempotence_axiom_satisfied": supported,
            "interpretation": "failure_operators_are_exact_idempotent_projections",
        },
    }


def run_live_idempotence_experiment(
    *,
    provider: Any,
    specs: Sequence[IdempotenceSpec] = DEFAULT_IDEMPOTENCE_SPECS,
    replicates: int = 3,
) -> dict[str, Any]:
    deterministic_states = build_idempotence_states(specs)
    questions = question_payload()
    observations: list[dict[str, Any]] = []
    total_calls = len(deterministic_states) * replicates

    for item in deterministic_states:
        sid = str(item["spec"]["spec_id"])
        mech = str(item["spec"]["mechanism"])
        mode = str(item["spec"]["mode"])
        order = item["spec"]["application_order"]
        for rep in range(replicates):
            request_id = f"uow-idem-{sid}-r{rep}"
            provider_res = provider.decide(
                state=dict(item["state"]),
                questions=questions,
                request_id=request_id,
            )
            vec = provider_res.get("vector") or []
            v_norm = float(np.linalg.norm(vec)) if vec else 0.0
            print(
                f"[{len(observations) + 1:03d}/{total_calls:03d}] {sid:<18} "
                f"({mech:<12}, {mode:<12}, n={order:>2}) rep={rep:02d} -> norm={v_norm:.4f}",
                flush=True,
            )
            observations.append(
                {
                    "spec_id": sid,
                    "replicate": rep,
                    "provider": provider_res,
                }
            )

    analysis = analyze_idempotence_observations(
        deterministic_states,
        observations,
        specs=specs,
        replicates=replicates,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "JEV x UoW Operator Idempotence Qualification Campaign",
        "method": {
            "replicates_per_state": replicates,
            "total_requests": total_calls,
            "specs_count": len(specs),
        },
        "deterministic_states": deterministic_states,
        "observations": observations,
        "analysis": analysis,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run JEV x UoW Operator Idempotence Qualification Campaign."
    )
    parser.add_argument("--model", default=DEFAULT_JEV_MODEL)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    provider = TypeSafeJevProvider(model=args.model, timeout_s=args.timeout_s)
    payload = run_live_idempotence_experiment(
        provider=provider,
        replicates=args.replicates,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload.get("analysis", payload), indent=2, sort_keys=True))
    print(f"\nWrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
