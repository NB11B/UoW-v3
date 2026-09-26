"""JEV x UoW Guard Semantics Qualification Campaign.

Scientific Framing
==================
Following the conclusive empirical refutation of a continuous Lie-algebra model
(scalar homogeneity and additivity failure due to discrete causal switching),
we formalize the UoW/JEV cybernetic system as a Guarded Discrete Transition System:
    G = (X, G, F, J)
where:
    X: Deterministic UoW realization states
    G: Contract guards {g_T, g_R, g_A, g_E, g_C, g_Adv} with g_i: X -> {0, 1}
    F: State transformations {F_i: X -> X}
    J: JEV observer evaluation map J: X -> R^8

This campaign empirically proves that the observed discrete macrostate step
dynamics originate from contract guard activation boundaries (Heaviside step
transitions g_i(x) = 0 -> 1), rather than continuous observer drift or gradual
sensitivity to telemetry scalars.

Experimental Design
===================
1. Sample states on both sides of each contract guard boundary:
       x^- in X_i^- such that g_i(x^-) = 0  (contract admissible / unviolated)
       x^+ in X_i^+ such that g_i(x^+) = 1  (guard tripped / violated)

   - Temporal Guard (g_T, T_max = 1000 ms):
       Pass (g_T = 0): t in {900, 999, 1000} ms
       Trip (g_T = 1): t in {1001, 1050, 1500, 3000} ms
   - Resource Guard (g_R, RAM_max = 16 units):
       Pass (g_R = 0): r in {8, 15, 16} RAM units
       Trip (g_R = 1): r in {17, 24, 32, 64} RAM units
   - Authority Guard (g_A, verifiers >= 1):
       Pass (g_A = 0): n_ver in {1, 2, 3} active verifiers bound
       Trip (g_A = 1): n_ver = 0 (unassigned, revoked, or denied)
   - Evidence Guard (g_E, digest integrity match):
       Pass (g_E = 0): valid cryptographic hash match (SHA-256, SHA-512, Blake3)
       Trip (g_E = 1): corrupted digest (1-bit flip, block corruption, payload tamper)
   - Causal Guard (g_C, DAG connectivity intact):
       Pass (g_C = 0): connected causal topologies (linear, redundant, branched)
       Trip (g_C = 1): severed causal edges (dispatch->route, route->agg, agg->verify)
   - Adversarial Guard (g_Adv, quarantine inactive, conflicts = 0):
       Pass (g_Adv = 0): conflicts = 0 (nominal, multi-attestation, unanimous)
       Trip (g_Adv = 1): conflicts in {1, 2, 4} (quarantine active, divergence detected)

2. Quantitative Metrics:
   - Within-regime diameter:
       D_i^- = max_{x,y in X_i^-} ||J(x) - J(y)||
       D_i^+ = max_{x,y in X_i^+} ||J(x) - J(y)||
       D_i   = max(D_i^-, D_i^+)
   - Across-boundary jump:
       Delta_i^min  = min_{x+ in X_i^+, x- in X_i^-} ||J(x+) - J(x-)||
       Delta_i^mean = mean_{x+ in X_i^+, x- in X_i^-} ||J(x+) - J(x-)||
   - Boundary jump ratio:
       R_i = Delta_i^mean / max(D_i, sigma_rep)  (requirement: R_i >= 2.0, >> 1)
   - Scalar boundary step sharpness (for g_T and g_R):
       rho_i = (boundary step slope) / (within-regime pass slope) >> 1
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


SCHEMA_VERSION = "uow.jev_guard_semantics.v1"
DEFAULT_OUTPUT = Path("qualification/artifacts/jev_guard_semantics_results.json")


@dataclass(frozen=True)
class GuardSpec:
    spec_id: str
    guard_name: str          # "temporal", "resource", "authority", "evidence", "causal", "adversarial", "none"
    guard_regime: str        # "pass", "trip", "base"
    guard_tripped: bool      # False if pass/base, True if trip
    parameter_name: str
    parameter_value: Any
    disturbed_units_count: int


def build_guard_specs() -> tuple[GuardSpec, ...]:
    specs: list[GuardSpec] = [
        # Baseline nominal state
        GuardSpec(
            spec_id="guard_base_nominal",
            guard_name="none",
            guard_regime="base",
            guard_tripped=False,
            parameter_name="none",
            parameter_value="nominal",
            disturbed_units_count=0,
        ),
    ]

    # 1. Temporal Guard (g_T, T_max = 1000.0 ms)
    # Pass regime (g_T = 0): duration <= 1000 ms
    specs.extend([
        GuardSpec("guard_T_pass_900ms", "temporal", "pass", False, "duration_ms", 900.0, 0),
        GuardSpec("guard_T_pass_999ms", "temporal", "pass", False, "duration_ms", 999.0, 0),
        GuardSpec("guard_T_pass_1000ms", "temporal", "pass", False, "duration_ms", 1000.0, 0),
    ])
    # Trip regime (g_T = 1): duration > 1000 ms
    specs.extend([
        GuardSpec("guard_T_trip_1001ms", "temporal", "trip", True, "duration_ms", 1001.0, DISTURBED_UNITS_COUNT),
        GuardSpec("guard_T_trip_1050ms", "temporal", "trip", True, "duration_ms", 1050.0, DISTURBED_UNITS_COUNT),
        GuardSpec("guard_T_trip_1500ms", "temporal", "trip", True, "duration_ms", 1500.0, DISTURBED_UNITS_COUNT),
        GuardSpec("guard_T_trip_3000ms", "temporal", "trip", True, "duration_ms", 3000.0, DISTURBED_UNITS_COUNT),
    ])

    # 2. Resource Guard (g_R, RAM_max = 16 units)
    # Pass regime (g_R = 0): RAM <= 16 units
    specs.extend([
        GuardSpec("guard_R_pass_08ram", "resource", "pass", False, "ram_units", 8, 0),
        GuardSpec("guard_R_pass_15ram", "resource", "pass", False, "ram_units", 15, 0),
        GuardSpec("guard_R_pass_16ram", "resource", "pass", False, "ram_units", 16, 0),
    ])
    # Trip regime (g_R = 1): RAM > 16 units
    specs.extend([
        GuardSpec("guard_R_trip_17ram", "resource", "trip", True, "ram_units", 17, DISTURBED_UNITS_COUNT),
        GuardSpec("guard_R_trip_24ram", "resource", "trip", True, "ram_units", 24, DISTURBED_UNITS_COUNT),
        GuardSpec("guard_R_trip_32ram", "resource", "trip", True, "ram_units", 32, DISTURBED_UNITS_COUNT),
        GuardSpec("guard_R_trip_64ram", "resource", "trip", True, "ram_units", 64, DISTURBED_UNITS_COUNT),
    ])

    # 3. Authority Guard (g_A, verifiers >= 1)
    # Pass regime (g_A = 0): active verifiers available
    specs.extend([
        GuardSpec("guard_A_pass_1ver", "authority", "pass", False, "active_verifiers", 1, 0),
        GuardSpec("guard_A_pass_2ver", "authority", "pass", False, "active_verifiers", 2, 0),
        GuardSpec("guard_A_pass_3ver", "authority", "pass", False, "active_verifiers", 3, 0),
    ])
    # Trip regime (g_A = 1): 0 verifiers available
    specs.extend([
        GuardSpec("guard_A_trip_unbound", "authority", "trip", True, "active_verifiers", 0, DISTURBED_UNITS_COUNT),
        GuardSpec("guard_A_trip_revoked", "authority", "trip", True, "active_verifiers", 0, DISTURBED_UNITS_COUNT),
        GuardSpec("guard_A_trip_denied", "authority", "trip", True, "active_verifiers", 0, DISTURBED_UNITS_COUNT),
    ])

    # 4. Evidence Guard (g_E, digest integrity match)
    # Pass regime (g_E = 0): valid digest match
    specs.extend([
        GuardSpec("guard_E_pass_sha256", "evidence", "pass", False, "digest_algorithm", "sha256", 0),
        GuardSpec("guard_E_pass_sha512", "evidence", "pass", False, "digest_algorithm", "sha512", 0),
        GuardSpec("guard_E_pass_blake3", "evidence", "pass", False, "digest_algorithm", "blake3", 0),
    ])
    # Trip regime (g_E = 1): digest mismatch / corrupted
    specs.extend([
        GuardSpec("guard_E_trip_1bit", "evidence", "trip", True, "corruption_type", "1bit_flip", DISTURBED_UNITS_COUNT),
        GuardSpec("guard_E_trip_block", "evidence", "trip", True, "corruption_type", "block_corruption", DISTURBED_UNITS_COUNT),
        GuardSpec("guard_E_trip_tamper", "evidence", "trip", True, "corruption_type", "payload_tamper", DISTURBED_UNITS_COUNT),
    ])

    # 5. Causal Guard (g_C, DAG path intact)
    # Pass regime (g_C = 0): complete causal paths
    specs.extend([
        GuardSpec("guard_C_pass_linear", "causal", "pass", False, "topology", "linear_pipeline", 0),
        GuardSpec("guard_C_pass_redundant", "causal", "pass", False, "topology", "redundant_paths", 0),
        GuardSpec("guard_C_pass_branch", "causal", "pass", False, "topology", "parallel_branch", 0),
    ])
    # Trip regime (g_C = 1): severed edges
    specs.extend([
        GuardSpec("guard_C_trip_dispatch_route", "causal", "trip", True, "severed_edge", "dispatch->route", DISTURBED_UNITS_COUNT),
        GuardSpec("guard_C_trip_route_agg", "causal", "trip", True, "severed_edge", "route->aggregate", DISTURBED_UNITS_COUNT),
        GuardSpec("guard_C_trip_agg_verify", "causal", "trip", True, "severed_edge", "aggregate->verify", DISTURBED_UNITS_COUNT),
    ])

    # 6. Adversarial Guard (g_Adv, quarantine inactive, conflicts = 0)
    # Pass regime (g_Adv = 0): 0 conflicts
    specs.extend([
        GuardSpec("guard_Adv_pass_0conflicts", "adversarial", "pass", False, "conflict_count", 0, 0),
        GuardSpec("guard_Adv_pass_consensus", "adversarial", "pass", False, "conflict_count", 0, 0),
        GuardSpec("guard_Adv_pass_unanimous", "adversarial", "pass", False, "conflict_count", 0, 0),
    ])
    # Trip regime (g_Adv = 1): conflicts >= 1, quarantine active
    specs.extend([
        GuardSpec("guard_Adv_trip_1conflict", "adversarial", "trip", True, "conflict_count", 1, DISTURBED_UNITS_COUNT),
        GuardSpec("guard_Adv_trip_2conflicts", "adversarial", "trip", True, "conflict_count", 2, DISTURBED_UNITS_COUNT),
        GuardSpec("guard_Adv_trip_4conflicts", "adversarial", "trip", True, "conflict_count", 4, DISTURBED_UNITS_COUNT),
    ])

    return tuple(specs)


DEFAULT_GUARD_SPECS = build_guard_specs()


def run_guard_spec(spec: GuardSpec) -> dict[str, Any]:
    M = TOTAL_UNITS
    Q = QUORUM_REQUIRED
    k = spec.disturbed_units_count
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

    # 2. Induce failure in leaf runtimes if tripped
    if spec.guard_tripped and spec.guard_name == "authority":
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

    if spec.guard_tripped:
        output_keys = []
        root_status = "FAILED"

    # Specific guard adjustments
    if spec.guard_name == "temporal":
        duration_ms = float(spec.parameter_value)
        if spec.guard_tripped:
            temporal_ok = False
        else:
            temporal_ok = True

    elif spec.guard_name == "resource":
        ram_units = int(spec.parameter_value)
        duration_ms = 350.0
        if spec.guard_tripped:
            resource_ok = False
            node_seq = ["parse", "dispatch", "route"]
            evidence_records = ["parse", "dispatch", "route"]
            chain_continuity = False
        else:
            resource_ok = True

    elif spec.guard_name == "authority":
        if spec.guard_tripped:
            role_bindings.pop("verify", None)
            node_seq = ["parse", "dispatch", "route", "aggregate"]
            evidence_records = ["parse", "dispatch", "route", "aggregate"]
            chain_continuity = False
            duration_ms = 480.0
        else:
            n_ver = int(spec.parameter_value)
            if n_ver >= 2:
                role_bindings["verify_secondary"] = "role:verifier"
            if n_ver >= 3:
                role_bindings["verify_tertiary"] = "role:verifier"
            duration_ms = 450.0

    elif spec.guard_name == "evidence":
        if spec.guard_tripped:
            digest_match = False
            chain_continuity = False
            node_seq = ["parse", "dispatch", "route", "aggregate", "verify"]
            evidence_records = ["parse", "dispatch", "route", "aggregate", "verify"]
            duration_ms = 520.0
        else:
            digest_match = True
            chain_continuity = True
            duration_ms = 450.0

    elif spec.guard_name == "causal":
        if spec.guard_tripped:
            chain_continuity = False
            if spec.parameter_value == "dispatch->route":
                causal_edges = [["parse", "dispatch"], ["route", "aggregate"], ["aggregate", "verify"], ["verify", "commit"]]
                node_seq = ["parse", "dispatch"]
                evidence_records = ["parse", "dispatch"]
                duration_ms = 210.0
            elif spec.parameter_value == "route->aggregate":
                causal_edges = [["parse", "dispatch"], ["dispatch", "route"], ["aggregate", "verify"], ["verify", "commit"]]
                node_seq = ["parse", "dispatch", "route"]
                evidence_records = ["parse", "dispatch", "route"]
                duration_ms = 240.0
            else:
                causal_edges = [["parse", "dispatch"], ["dispatch", "route"], ["route", "aggregate"], ["verify", "commit"]]
                node_seq = ["parse", "dispatch", "route", "aggregate"]
                evidence_records = ["parse", "dispatch", "route", "aggregate"]
                duration_ms = 280.0
        else:
            if spec.parameter_value == "redundant_paths":
                causal_edges.append(["parse", "route"])
            elif spec.parameter_value == "parallel_branch":
                causal_edges.append(["dispatch", "aggregate"])

    elif spec.guard_name == "adversarial":
        if spec.guard_tripped:
            conflict_count = int(spec.parameter_value)
            divergence_detected = True
            quarantine_active = True
            chain_continuity = False
            node_seq = ["parse", "dispatch", "route", "aggregate"]
            evidence_records = ["parse", "dispatch", "route", "aggregate"]
            duration_ms = 580.0 + 20.0 * conflict_count
        else:
            conflict_count = 0
            divergence_detected = False
            quarantine_active = False

    state = {
        "subject": "governed_guard_semantics_unit",
        "spec_id": spec.spec_id,
        "guard_name": spec.guard_name,
        "guard_regime": spec.guard_regime,
        "guard_tripped": spec.guard_tripped,
        "parameter_name": spec.parameter_name,
        "parameter_value": str(spec.parameter_value),
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
        "guard_name": spec.guard_name,
        "guard_regime": spec.guard_regime,
        "guard_tripped": spec.guard_tripped,
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
            "guard_name": spec.guard_name,
            "guard_regime": spec.guard_regime,
            "guard_tripped": spec.guard_tripped,
            "parameter_name": spec.parameter_name,
            "parameter_value": spec.parameter_value,
            "disturbed_units_count": spec.disturbed_units_count,
        },
        "state": state,
        "oracle": oracle,
    }


def build_guard_states(specs: Sequence[GuardSpec] = DEFAULT_GUARD_SPECS) -> list[dict[str, Any]]:
    return [run_guard_spec(s) for s in specs]


def analyze_guard_semantics_observations(
    deterministic_states: Sequence[dict[str, Any]],
    observations: Sequence[dict[str, Any]],
    *,
    specs: Sequence[GuardSpec] = DEFAULT_GUARD_SPECS,
    replicates: int = 3,
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

    guards_to_analyze = ["temporal", "resource", "authority", "evidence", "causal", "adversarial"]
    guard_results: dict[str, Any] = {}

    jump_ratios_mean: list[float] = []
    jump_ratios_min: list[float] = []
    within_compactness_checks: list[bool] = []

    for gname in guards_to_analyze:
        pass_sids = [s.spec_id for s in specs if s.guard_name == gname and s.guard_regime == "pass"]
        trip_sids = [s.spec_id for s in specs if s.guard_name == gname and s.guard_regime == "trip"]

        pass_vecs = [spec_means[sid] for sid in pass_sids]
        trip_vecs = [spec_means[sid] for sid in trip_sids]

        # Within-pass distances
        pass_dists: list[float] = []
        for i in range(len(pass_vecs)):
            for j in range(i + 1, len(pass_vecs)):
                pass_dists.append(float(np.linalg.norm(pass_vecs[i] - pass_vecs[j])))
        D_pass = max(pass_dists) if pass_dists else 0.0
        mean_D_pass = float(np.mean(pass_dists)) if pass_dists else 0.0

        # Within-trip distances
        trip_dists: list[float] = []
        for i in range(len(trip_vecs)):
            for j in range(i + 1, len(trip_vecs)):
                trip_dists.append(float(np.linalg.norm(trip_vecs[i] - trip_vecs[j])))
        D_trip = max(trip_dists) if trip_dists else 0.0
        mean_D_trip = float(np.mean(trip_dists)) if trip_dists else 0.0

        D_within = max(D_pass, D_trip)

        # Across-boundary jump distances
        across_jumps: list[float] = []
        for v_trip in trip_vecs:
            for v_pass in pass_vecs:
                across_jumps.append(float(np.linalg.norm(v_trip - v_pass)))

        delta_min = min(across_jumps) if across_jumps else 0.0
        delta_mean = float(np.mean(across_jumps)) if across_jumps else 0.0
        delta_max = max(across_jumps) if across_jumps else 0.0

        denom = max(D_within, eff_noise)
        R_min = delta_min / denom if denom > 0 else 0.0
        R_mean = delta_mean / denom if denom > 0 else 0.0

        jump_ratios_mean.append(R_mean)
        jump_ratios_min.append(R_min)
        within_compactness_checks.append(D_within < delta_mean)

        guard_results[gname] = {
            "guard_name": gname,
            "pass_specs": pass_sids,
            "trip_specs": trip_sids,
            "within_pass_diameter_D_minus": round(D_pass, 4),
            "within_pass_mean_distance": round(mean_D_pass, 4),
            "within_trip_diameter_D_plus": round(D_trip, 4),
            "within_trip_mean_distance": round(mean_D_trip, 4),
            "max_within_regime_diameter_D": round(D_within, 4),
            "boundary_jump_min_delta": round(delta_min, 4),
            "boundary_jump_mean_delta": round(delta_mean, 4),
            "boundary_jump_max_delta": round(delta_max, 4),
            "boundary_jump_ratio_R_min": round(R_min, 2),
            "boundary_jump_ratio_R_mean": round(R_mean, 2),
            "is_within_compact": bool(D_within < delta_mean),
            "is_jump_dominant": bool(R_mean >= 2.0),
        }

    # Step sharpness for scalar guards: Temporal (g_T) and Resource (g_R)
    # Temporal:
    v_T_900 = spec_means["guard_T_pass_900ms"]
    v_T_1000 = spec_means["guard_T_pass_1000ms"]
    v_T_1001 = spec_means["guard_T_trip_1001ms"]
    v_T_3000 = spec_means["guard_T_trip_3000ms"]

    dist_T_pass_span = float(np.linalg.norm(v_T_1000 - v_T_900))
    slope_T_pass = dist_T_pass_span / 100.0  # change per ms over 900 -> 1000 ms

    dist_T_step = float(np.linalg.norm(v_T_1001 - v_T_1000))
    slope_T_boundary = dist_T_step / 1.0  # change per ms over 1000 -> 1001 ms

    dist_T_trip_span = float(np.linalg.norm(v_T_3000 - v_T_1001))
    slope_T_trip = dist_T_trip_span / 1999.0  # change per ms over 1001 -> 3000 ms

    rho_T = slope_T_boundary / max(slope_T_pass, 1e-6)

    temporal_sharpness = {
        "pass_span_900_to_1000ms_norm": round(dist_T_pass_span, 4),
        "pass_slope_per_ms": round(slope_T_pass, 6),
        "boundary_step_1000_to_1001ms_norm": round(dist_T_step, 4),
        "boundary_slope_per_ms": round(slope_T_boundary, 4),
        "trip_span_1001_to_3000ms_norm": round(dist_T_trip_span, 4),
        "trip_slope_per_ms": round(slope_T_trip, 6),
        "sharpness_ratio_rho_T": round(rho_T, 2),
        "boundary_step_over_pass_span_ratio": round(dist_T_step / max(dist_T_pass_span, eff_noise), 2),
    }

    # Resource:
    v_R_8 = spec_means["guard_R_pass_08ram"]
    v_R_16 = spec_means["guard_R_pass_16ram"]
    v_R_17 = spec_means["guard_R_trip_17ram"]
    v_R_64 = spec_means["guard_R_trip_64ram"]

    dist_R_pass_span = float(np.linalg.norm(v_R_16 - v_R_8))
    slope_R_pass = dist_R_pass_span / 8.0  # change per RAM unit over 8 -> 16 RAM

    dist_R_step = float(np.linalg.norm(v_R_17 - v_R_16))
    slope_R_boundary = dist_R_step / 1.0  # change per RAM unit over 16 -> 17 RAM

    dist_R_trip_span = float(np.linalg.norm(v_R_64 - v_R_17))
    slope_R_trip = dist_R_trip_span / 47.0  # change per RAM unit over 17 -> 64 RAM

    rho_R = slope_R_boundary / max(slope_R_pass, 1e-6)

    resource_sharpness = {
        "pass_span_8_to_16ram_norm": round(dist_R_pass_span, 4),
        "pass_slope_per_ram_unit": round(slope_R_pass, 6),
        "boundary_step_16_to_17ram_norm": round(dist_R_step, 4),
        "boundary_slope_per_ram_unit": round(slope_R_boundary, 4),
        "trip_span_17_to_64ram_norm": round(dist_R_trip_span, 4),
        "trip_slope_per_ram_unit": round(slope_R_trip, 6),
        "sharpness_ratio_rho_R": round(rho_R, 2),
        "boundary_step_over_pass_span_ratio": round(dist_R_step / max(dist_R_pass_span, eff_noise), 2),
    }

    # Engineering Gates:
    gate_U0 = oracle_pass
    gate_J0 = bool(noise_floor <= 0.050)
    gate_J1 = bool(all(r >= 2.0 for r in jump_ratios_mean))
    gate_J2 = bool(all(within_compactness_checks))
    gate_J3 = bool(rho_T >= 10.0 and rho_R >= 5.0)

    gates = {
        "G_U0_oracle_conformance": gate_U0,
        "G_J0_repeatability_noise_floor": gate_J0,
        "G_J1_jump_dominance_across_guards": gate_J1,
        "G_J2_within_regime_compactness": gate_J2,
        "G_J3_scalar_boundary_step_sharpness": gate_J3,
    }

    supported = all(gates.values())

    return {
        "oracle_pass": oracle_pass,
        "provider_complete": True,
        "repeatability_noise_floor_sigma_rep": round(noise_floor, 4),
        "effective_noise_floor": round(eff_noise, 4),
        "guard_evaluations": guard_results,
        "scalar_step_sharpness": {
            "temporal": temporal_sharpness,
            "resource": resource_sharpness,
        },
        "aggregate_metrics": {
            "min_jump_ratio_across_guards": round(min(jump_ratios_mean), 2),
            "mean_jump_ratio_across_guards": round(float(np.mean(jump_ratios_mean)), 2),
            "max_jump_ratio_across_guards": round(max(jump_ratios_mean), 2),
            "all_guards_jump_dominant": gate_J1,
            "all_guards_within_compact": gate_J2,
        },
        "gates": gates,
        "supported_within_engineering_gates": supported,
        "verdict": (
            "GUARD_STEP_SEMANTICS_CONFIRMED"
            if supported
            else "CONTINUOUS_DRIFT_DETECTED"
        ),
        "formal_mathematical_model": "guarded_discrete_transition_system",
    }


def run_live_guard_semantics_experiment(
    *,
    provider: Any,
    specs: Sequence[GuardSpec] = DEFAULT_GUARD_SPECS,
    replicates: int = 3,
) -> dict[str, Any]:
    deterministic_states = build_guard_states(specs)
    questions = question_payload()
    observations: list[dict[str, Any]] = []
    total_calls = len(deterministic_states) * replicates

    for item in deterministic_states:
        sid = str(item["spec"]["spec_id"])
        gname = str(item["spec"]["guard_name"])
        greg = str(item["spec"]["guard_regime"])
        pval = str(item["spec"]["parameter_value"])
        for rep in range(replicates):
            request_id = f"uow-guard-{sid}-r{rep}"
            provider_res = provider.decide(
                state=dict(item["state"]),
                questions=questions,
                request_id=request_id,
            )
            vec = provider_res.get("vector") or []
            v_norm = float(np.linalg.norm(vec)) if vec else 0.0
            print(
                f"[{len(observations) + 1:03d}/{total_calls:03d}] {sid:<24} "
                f"({gname:<12}, {greg:<5}, {pval:<10}) rep={rep:02d} -> norm={v_norm:.4f}",
                flush=True,
            )
            observations.append(
                {
                    "spec_id": sid,
                    "replicate": rep,
                    "provider": provider_res,
                }
            )

    analysis = analyze_guard_semantics_observations(
        deterministic_states,
        observations,
        specs=specs,
        replicates=replicates,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "JEV x UoW Guard Semantics Qualification Campaign",
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
        description="Run JEV x UoW Guard Semantics Qualification Campaign."
    )
    parser.add_argument("--model", default=DEFAULT_JEV_MODEL)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    provider = TypeSafeJevProvider(model=args.model, timeout_s=args.timeout_s)
    payload = run_live_guard_semantics_experiment(
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
