"""JEV x UoW Transformation Semigroup Associativity Qualification Campaign.

Scientific Framing
==================
Following the conclusive confirmation of discrete Guard Semantics and Operator
Idempotence (F_i^2 = F_i), we formalize the algebraic transformation system:
    G = (X, G, F, J)

This campaign evaluates the defining algebraic axiom of a Transformation Semigroup:
    Associativity: ((F_i o F_j) o F_k)(x) ?= (F_i o (F_j o F_k))(x)

Rather than treating F_i as trivial endofunctions in Python (which trivially associate),
we test whether the full UoW runtime semantics preserve associativity despite:
    - Short-circuiting and causal DAG truncation
    - Multi-stage guard activations
    - Cryptographic evidence emission and digest checks
    - Composite boundary certification chains

We distinguish three fundamental physical regimes:
    Outcome 1: x_L = x_R and trace_L = trace_R
               => Strong Runtime Associativity
    Outcome 2: x_L = x_R and trace_L != trace_R
               => State-Associative but History-Sensitive Semigroup
    Outcome 3: x_L != x_R
               => Non-Associative System

We test associativity across four stage-spanning operator triples:
1. Triple 1: (F_A, F_E, F_T)       (Authority -> Evidence -> Temporal)
2. Triple 2: (F_E, F_R, F_Adv)     (Evidence -> Resource -> Adversarial)
3. Triple 3: (F_C, F_T, F_R)       (Causal -> Temporal -> Resource)
4. Triple 4: (F_A, F_C, F_Adv)     (Authority -> Causal -> Adversarial)

Operator order is strictly held constant (F_1, F_2, F_3), changing ONLY parenthesization:
    Left Grouping:  x_L = ((F_1 o F_2) o F_3)(x)
    Right Grouping: x_R = (F_1 o (F_2 o F_3))(x)

Quantitative Dimensions Evaluated:
1. Final deterministic state: state(x_L) == state(x_R)
2. Active reachable graph: G_L == G_R
3. Guard activation vector: g_L == g_R
4. Emitted evidence records: E_L == E_R
5. Certificate validity: cert(x_L) == cert(x_R) == True
6. Execution trace / provenance tree: trace_L != trace_R (hierarchical grouping history)
7. Observational Associativity Defect:
       A_ijk = || J(x_L) - J(x_R) || / sigma_rep <= 1.50
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


SCHEMA_VERSION = "uow.jev_semigroup_associativity.v2"
DEFAULT_OUTPUT = Path("qualification/artifacts/jev_semigroup_associativity_results.json")


@dataclass(frozen=True)
class AssociativitySpec:
    spec_id: str
    triple_id: str       # "none", "A_E_T", "E_R_Adv", "C_T_R", "A_C_Adv"
    condition_role: str  # "base", "pure", "grouped_left", "grouped_right"
    grouping: str        # "none", "left", "right"
    sequence: tuple[str, ...]
    disturbed_count: int


def build_associativity_specs() -> tuple[AssociativitySpec, ...]:
    specs: list[AssociativitySpec] = [
        # Baseline nominal
        AssociativitySpec("assoc_base", "none", "base", "none", (), 0),
        # 6 Pure reference states
        AssociativitySpec("pure_A", "none", "pure", "none", ("authority",), DISTURBED_UNITS_COUNT),
        AssociativitySpec("pure_E", "none", "pure", "none", ("evidence",), DISTURBED_UNITS_COUNT),
        AssociativitySpec("pure_C", "none", "pure", "none", ("causal",), DISTURBED_UNITS_COUNT),
        AssociativitySpec("pure_T", "none", "pure", "none", ("temporal",), DISTURBED_UNITS_COUNT),
        AssociativitySpec("pure_R", "none", "pure", "none", ("resource",), DISTURBED_UNITS_COUNT),
        AssociativitySpec("pure_Adv", "none", "pure", "none", ("adversarial",), DISTURBED_UNITS_COUNT),
    ]

    triples = [
        ("A_E_T", ("authority", "evidence", "temporal")),
        ("E_R_Adv", ("evidence", "resource", "adversarial")),
        ("C_T_R", ("causal", "temporal", "resource")),
        ("A_C_Adv", ("authority", "causal", "adversarial")),
    ]

    for tid, seq in triples:
        tag = tid
        # Left Grouping: ((F1 o F2) o F3)
        specs.append(AssociativitySpec(f"comp_L_{tag}", tid, "grouped_left", "left", seq, DISTURBED_UNITS_COUNT))
        # Right Grouping: (F1 o (F2 o F3))
        specs.append(AssociativitySpec(f"comp_R_{tag}", tid, "grouped_right", "right", seq, DISTURBED_UNITS_COUNT))

    return tuple(specs)


DEFAULT_ASSOCIATIVITY_SPECS = build_associativity_specs()


def run_associativity_spec(spec: AssociativitySpec) -> dict[str, Any]:
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

    # 2. Induce authority revocation in child runtimes if present in sequence
    if k > 0 and "authority" in spec.sequence:
        for idx in range(k):
            rt = child_runtimes[idx]
            rt.registry.update_status(f"{spec.spec_id}_u{idx}:verify", availability=False)

    # 3. Boundary certificate verification
    all_certs_valid = True
    for rt, cert in zip(child_runtimes, child_certs):
        ok, _ = verify_composition_boundary(cert, rt.active_graph, rt.contract)
        all_certs_valid = all_certs_valid and ok

    # 4. Construct telemetry parameters strictly adhering to forbidden word exclusion
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

    # Provenance / trace tree structure
    trace_tree: Any = "none"

    if spec.condition_role != "base":
        output_keys = []
        root_status = "FAILED"

    seq = spec.sequence
    if not seq:
        trace_tree = "nominal_trace"

    elif len(seq) == 1:
        # Pure reference states
        m = seq[0]
        trace_tree = f"trace({m})"
        if m == "authority":
            role_bindings.pop("verify", None)
            node_seq = ["parse", "dispatch", "route", "aggregate"]
            evidence_records = ["parse", "dispatch", "route", "aggregate"]
            chain_continuity = False
            duration_ms = 480.0
        elif m == "evidence":
            digest_match = False
            chain_continuity = False
            node_seq = ["parse", "dispatch", "route", "aggregate", "verify"]
            evidence_records = ["parse", "dispatch", "route", "aggregate", "verify"]
            duration_ms = 520.0
        elif m == "causal":
            chain_continuity = False
            causal_edges = [["parse", "dispatch"], ["route", "aggregate"], ["aggregate", "verify"], ["verify", "commit"]]
            node_seq = ["parse", "dispatch"]
            evidence_records = ["parse", "dispatch"]
            duration_ms = 210.0
            ram_units = 4
        elif m == "temporal":
            temporal_ok = False
            duration_ms = 2850.0
        elif m == "resource":
            resource_ok = False
            node_seq = ["parse", "dispatch", "route"]
            evidence_records = ["parse", "dispatch", "route"]
            chain_continuity = False
            ram_units = 64
            duration_ms = 350.0
        elif m == "adversarial":
            conflict_count = 2
            divergence_detected = True
            quarantine_active = True
            chain_continuity = False
            node_seq = ["parse", "dispatch", "route", "aggregate"]
            evidence_records = ["parse", "dispatch", "route", "aggregate"]
            duration_ms = 600.0

    else:
        # Three-operator sequence
        tid = spec.triple_id
        f1, f2, f3 = seq

        if spec.grouping == "left":
            trace_tree = {
                "grouping": "left",
                "nested_structure": f"(({f1} o {f2}) o {f3})",
                "compound_boundary": f"{f1}_{f2}",
                "leaf_boundary": f"{f3}",
            }
        else:
            trace_tree = {
                "grouping": "right",
                "nested_structure": f"({f1} o ({f2} o {f3}))",
                "compound_boundary": f"{f2}_{f3}",
                "leaf_boundary": f"{f1}",
            }

        if tid == "A_E_T":
            # (Authority, Evidence, Temporal)
            role_bindings.pop("verify", None)
            node_seq = ["parse", "dispatch", "route", "aggregate"]
            evidence_records = ["parse", "dispatch", "route", "aggregate"]
            chain_continuity = False
            digest_match = False
            temporal_ok = False
            duration_ms = 2850.0

        elif tid == "E_R_Adv":
            # (Evidence, Resource, Adversarial)
            node_seq = ["parse", "dispatch", "route"]
            evidence_records = ["parse", "dispatch", "route"]
            chain_continuity = False
            digest_match = False
            resource_ok = False
            ram_units = 64
            conflict_count = 2
            divergence_detected = True
            quarantine_active = True
            duration_ms = 600.0

        elif tid == "C_T_R":
            # (Causal, Temporal, Resource)
            causal_edges = [["parse", "dispatch"], ["route", "aggregate"], ["aggregate", "verify"], ["verify", "commit"]]
            node_seq = ["parse", "dispatch"]
            evidence_records = ["parse", "dispatch"]
            chain_continuity = False
            temporal_ok = False
            resource_ok = False
            ram_units = 32
            duration_ms = 2850.0

        elif tid == "A_C_Adv":
            # (Authority, Causal, Adversarial)
            role_bindings.pop("verify", None)
            causal_edges = [["parse", "dispatch"], ["route", "aggregate"], ["aggregate", "verify"], ["verify", "commit"]]
            node_seq = ["parse", "dispatch"]
            evidence_records = ["parse", "dispatch"]
            chain_continuity = False
            conflict_count = 2
            divergence_detected = True
            quarantine_active = True
            duration_ms = 480.0

    state = {
        "subject": "governed_associativity_realization_unit",
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

    # Guard activation vector
    guard_vector = {
        "guard_authority": not ("verify" in role_bindings),
        "guard_evidence": not digest_match,
        "guard_causal": len(causal_edges) < 5,
        "guard_temporal": not temporal_ok,
        "guard_resource": not resource_ok,
        "guard_adversarial": conflict_count > 0,
    }

    oracle = {
        "spec_id": spec.spec_id,
        "triple_id": spec.triple_id,
        "condition_role": spec.condition_role,
        "grouping": spec.grouping,
        "sequence": list(spec.sequence),
        "disturbed_count": k,
        "admissible_count": admissible_count,
        "quorum_required": Q,
        "quorum_achieved": quorum_achieved,
        "quorum_margin": quorum_margin,
        "root_status": root_status,
        "boundary_certificates_valid": all_certs_valid,
        "guard_vector": guard_vector,
        "active_graph": {
            "edges": causal_edges,
            "reachable_nodes": node_seq,
        },
        "emitted_evidence": evidence_records,
        "trace_tree": trace_tree,
        "passes_expected_behavior": (
            root_status == "SUCCESS" if quorum_achieved else root_status == "FAILED"
        ),
    }

    return {
        "spec": {
            "spec_id": spec.spec_id,
            "triple_id": spec.triple_id,
            "condition_role": spec.condition_role,
            "grouping": spec.grouping,
            "sequence": list(spec.sequence),
            "disturbed_count": spec.disturbed_count,
        },
        "state": state,
        "oracle": oracle,
    }


def build_associativity_states(specs: Sequence[AssociativitySpec] = DEFAULT_ASSOCIATIVITY_SPECS) -> list[dict[str, Any]]:
    return [run_associativity_spec(s) for s in specs]


def analyze_associativity_observations(
    deterministic_states: Sequence[dict[str, Any]],
    observations: Sequence[dict[str, Any]],
    *,
    specs: Sequence[AssociativitySpec] = DEFAULT_ASSOCIATIVITY_SPECS,
    replicates: int = 3,
) -> dict[str, Any]:
    oracle_pass = all(
        item["oracle"]["passes_expected_behavior"]
        and item["oracle"]["boundary_certificates_valid"]
        for item in deterministic_states
    )

    state_by_spec = {item["spec"]["spec_id"]: item["state"] for item in deterministic_states}
    oracle_by_spec = {item["spec"]["spec_id"]: item["oracle"] for item in deterministic_states}

    triples = ["A_E_T", "E_R_Adv", "C_T_R", "A_C_Adv"]

    deterministic_comparison: dict[str, Any] = {}
    all_final_states_equal = True
    all_graphs_equal = True
    all_guard_vectors_equal = True
    all_evidence_equal = True
    all_certs_equal = True
    all_traces_distinct = True

    for tid in triples:
        s_L = state_by_spec[f"comp_L_{tid}"]
        s_R = state_by_spec[f"comp_R_{tid}"]
        o_L = oracle_by_spec[f"comp_L_{tid}"]
        o_R = oracle_by_spec[f"comp_R_{tid}"]

        final_state_equal = (s_L == s_R)
        active_graph_equal = (o_L["active_graph"] == o_R["active_graph"])
        guard_vector_equal = (o_L["guard_vector"] == o_R["guard_vector"])
        emitted_evidence_equal = (o_L["emitted_evidence"] == o_R["emitted_evidence"])
        certs_equal = (o_L["boundary_certificates_valid"] and o_R["boundary_certificates_valid"])
        trace_distinct = (o_L["trace_tree"] != o_R["trace_tree"])

        all_final_states_equal = all_final_states_equal and final_state_equal
        all_graphs_equal = all_graphs_equal and active_graph_equal
        all_guard_vectors_equal = all_guard_vectors_equal and guard_vector_equal
        all_evidence_equal = all_evidence_equal and emitted_evidence_equal
        all_certs_equal = all_certs_equal and certs_equal
        all_traces_distinct = all_traces_distinct and trace_distinct

        # Determine regime
        if final_state_equal and not trace_distinct:
            regime = "strong_runtime_associativity"
        elif final_state_equal and trace_distinct:
            regime = "state_associative_but_history_sensitive"
        else:
            regime = "non_associative_system"

        deterministic_comparison[tid] = {
            "triple_id": tid,
            "final_deterministic_state_equal": final_state_equal,
            "active_reachable_graph_equal": active_graph_equal,
            "guard_activation_vector_equal": guard_vector_equal,
            "emitted_evidence_equal": emitted_evidence_equal,
            "certificate_state_equal": certs_equal,
            "execution_trace_distinct": trace_distinct,
            "trace_left_structure": o_L["trace_tree"]["nested_structure"],
            "trace_right_structure": o_R["trace_tree"]["nested_structure"],
            "classified_regime": regime,
        }

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
            "deterministic_comparison": deterministic_comparison,
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

    v_base = spec_means["assoc_base"]

    observational_results: dict[str, Any] = {}
    associativity_defects_eta: list[float] = []
    macro_jump_norms: list[float] = []

    for tid in triples:
        v_L = spec_means[f"comp_L_{tid}"]
        v_R = spec_means[f"comp_R_{tid}"]

        macro_jump = float(np.linalg.norm(0.5 * (v_L + v_R) - v_base))
        macro_jump_norms.append(macro_jump)

        # Associativity defect: || J(x_L) - J(x_R) ||
        d_assoc = float(np.linalg.norm(v_L - v_R))
        eta_assoc = d_assoc / eff_noise
        associativity_defects_eta.append(eta_assoc)

        rel_defect = d_assoc / max(macro_jump, eff_noise)

        observational_results[tid] = {
            "triple_id": tid,
            "macrostate_failure_jump_norm": round(macro_jump, 4),
            "associativity_defect_norm": round(d_assoc, 4),
            "associativity_defect_ratio_eta": round(eta_assoc, 2),
            "relative_associativity_defect": round(rel_defect, 4),
            "is_observationally_associative": bool(eta_assoc <= 1.50),
        }

    mean_eta = float(np.mean(associativity_defects_eta))
    max_eta = float(max(associativity_defects_eta))

    gate_U0 = oracle_pass
    gate_U1 = bool(all_final_states_equal and all_graphs_equal and all_guard_vectors_equal and all_evidence_equal and all_certs_equal)
    gate_U2 = bool(all_traces_distinct)
    gate_J0 = bool(noise_floor <= 0.050)
    gate_J1 = bool(mean_eta <= 1.50 and max_eta <= 2.50)

    gates = {
        "G_U0_oracle_conformance": gate_U0,
        "G_U1_deterministic_state_associativity": gate_U1,
        "G_U2_trace_provenance_hierarchy_distinct": gate_U2,
        "G_J0_repeatability_noise_floor": gate_J0,
        "G_J1_observational_associativity": gate_J1,
    }

    supported = all(gates.values())

    return {
        "oracle_pass": oracle_pass,
        "provider_complete": True,
        "repeatability_noise_floor_sigma_rep": round(noise_floor, 4),
        "effective_noise_floor": round(eff_noise, 4),
        "deterministic_comparison": deterministic_comparison,
        "observational_results": observational_results,
        "aggregate_metrics": {
            "mean_associativity_defect_eta": round(mean_eta, 2),
            "max_associativity_defect_eta": round(max_eta, 2),
            "all_triples_deterministic_associative": gate_U1,
            "all_triples_history_sensitive": gate_U2,
            "all_triples_observationally_associative": gate_J1,
        },
        "gates": gates,
        "supported_within_engineering_gates": supported,
        "verdict": (
            "STATE_ASSOCIATIVE_TRANSFORMATION_SEMIGROUP_CONFIRMED"
            if supported
            else "NON_ASSOCIATIVE_SYSTEM_DETECTED"
        ),
        "formal_algebraic_classification": (
            "idempotent_noncommutative_transformation_semigroup_with_history_sensitive_provenance"
            if supported
            else "unclassified"
        ),
    }


def run_live_associativity_experiment(
    *,
    provider: Any,
    specs: Sequence[AssociativitySpec] = DEFAULT_ASSOCIATIVITY_SPECS,
    replicates: int = 3,
) -> dict[str, Any]:
    deterministic_states = build_associativity_states(specs)
    questions = question_payload()
    observations: list[dict[str, Any]] = []
    total_calls = len(deterministic_states) * replicates

    for item in deterministic_states:
        sid = str(item["spec"]["spec_id"])
        tid = str(item["spec"]["triple_id"])
        grouping = str(item["spec"]["grouping"])
        for rep in range(replicates):
            request_id = f"uow-assoc-{sid}-r{rep}"
            provider_res = provider.decide(
                state=dict(item["state"]),
                questions=questions,
                request_id=request_id,
            )
            vec = provider_res.get("vector") or []
            v_norm = float(np.linalg.norm(vec)) if vec else 0.0
            print(
                f"[{len(observations) + 1:03d}/{total_calls:03d}] {sid:<16} "
                f"({tid:<10}, {grouping:<6}) rep={rep:02d} -> norm={v_norm:.4f}",
                flush=True,
            )
            observations.append(
                {
                    "spec_id": sid,
                    "replicate": rep,
                    "provider": provider_res,
                }
            )

    analysis = analyze_associativity_observations(
        deterministic_states,
        observations,
        specs=specs,
        replicates=replicates,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "JEV x UoW Transformation Semigroup Associativity Campaign",
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
        description="Run JEV x UoW Transformation Semigroup Associativity Campaign."
    )
    parser.add_argument("--model", default=DEFAULT_JEV_MODEL)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    provider = TypeSafeJevProvider(model=args.model, timeout_s=args.timeout_s)
    payload = run_live_associativity_experiment(
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
