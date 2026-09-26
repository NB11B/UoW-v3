"""JEV x UoW Operator Bracket Bilinearity Qualification Campaign.

Scientific Framing
==================
Following the confirmation of approximate residual span closure and the physical
failure operator basis [F_i, F_j]_emp = sum_k c_ij^k eps_k, the bracket must satisfy
bilinearity to constitute a valid Lie-algebraic bracket:
    [alpha F_i + beta F_j, F_k] = alpha [F_i, F_k] + beta [F_j, F_k]

We empirically evaluate the two fundamental axioms of bilinearity using
physically controlled fractional and combined failure perturbations:

1. Scalar Homogeneity:
       [alpha F_i, F_j]_emp ?= alpha [F_i, F_j]_emp  for alpha in {0.25, 0.50, 0.75, 1.00}
   Evaluated on high-SNR pairs:
       - (F_T(alpha), F_Adv): Continuous latency excess duration(alpha) = 450 + alpha * 2400 ms.
       - (F_A(alpha), F_Adv): Controlled fractional authority revocation (floor(8 * alpha) units revoked).
       - (F_E(alpha), F_Adv): Controlled fractional evidence corruption.

2. Additivity:
       [F_i + F_j, F_k]_emp ?= [F_i, F_k]_emp + [F_j, F_k]_emp
   Evaluated on high-SNR triples:
       - ([F_A + F_T, F_Adv]): Simultaneous authority revocation and temporal deadline excess.
       - ([F_A + F_E, F_Adv]): Simultaneous authority revocation and evidence corruption.

Error metrics are strictly normalized against the empirical repeatability floor:
    eta_hom = || [alpha F_i, F_j] - alpha [F_i, F_j] || / sigma_rep
    eta_add = || [F_i + F_j, F_k] - [F_i, F_k] - [F_j, F_k] || / sigma_rep
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


SCHEMA_VERSION = "uow.jev_operator_bilinearity.v1"
DEFAULT_OUTPUT = Path("qualification/artifacts/jev_operator_bilinearity_results.json")


@dataclass(frozen=True)
class BilinearitySpec:
    spec_id: str
    condition_role: str  # "base", "pure", "homogeneity", "additivity", "reference_pair"
    primary_mech: str
    secondary_mech: str = "none"
    alpha: float = 1.0  # Fraction for primary mechanism
    beta: float = 1.0   # Fraction for secondary mechanism
    composition_direction: str = ""  # "forward", "reverse", or ""


def build_bilinearity_specs() -> tuple[BilinearitySpec, ...]:
    specs: list[BilinearitySpec] = [
        # Baseline nominal
        BilinearitySpec("op_base", "base", "none"),
        # Pure reference states at full strength
        BilinearitySpec("op_A", "pure", "authority"),
        BilinearitySpec("op_T", "pure", "temporal"),
        BilinearitySpec("op_E", "pure", "evidence"),
        BilinearitySpec("op_Adv", "pure", "adversarial"),
        # Standard unscaled reference pairs (alpha = 1.0)
        BilinearitySpec("comp_A_Adv", "reference_pair", "authority", "adversarial", composition_direction="forward"),
        BilinearitySpec("comp_Adv_A", "reference_pair", "adversarial", "authority", composition_direction="reverse"),
        BilinearitySpec("comp_T_Adv", "reference_pair", "temporal", "adversarial", composition_direction="forward"),
        BilinearitySpec("comp_Adv_T", "reference_pair", "adversarial", "temporal", composition_direction="reverse"),
        BilinearitySpec("comp_E_Adv", "reference_pair", "evidence", "adversarial", composition_direction="forward"),
        BilinearitySpec("comp_Adv_E", "reference_pair", "adversarial", "evidence", composition_direction="reverse"),
    ]

    # Scalar Homogeneity series: [alpha T, Adv] for alpha in {0.25, 0.50, 0.75}
    for a in (0.25, 0.50, 0.75):
        tag = f"{int(a * 100):03d}"
        specs.append(BilinearitySpec(f"comp_T{tag}_Adv", "homogeneity", "temporal", "adversarial", alpha=a, composition_direction="forward"))
        specs.append(BilinearitySpec(f"comp_Adv_T{tag}", "homogeneity", "adversarial", "temporal", alpha=a, composition_direction="reverse"))

    # Scalar Homogeneity series: [alpha A, Adv] for alpha in {0.25, 0.50, 0.75}
    for a in (0.25, 0.50, 0.75):
        tag = f"{int(a * 100):03d}"
        specs.append(BilinearitySpec(f"comp_A{tag}_Adv", "homogeneity", "authority", "adversarial", alpha=a, composition_direction="forward"))
        specs.append(BilinearitySpec(f"comp_Adv_A{tag}", "homogeneity", "adversarial", "authority", alpha=a, composition_direction="reverse"))

    # Scalar Homogeneity point: [alpha E, Adv] for alpha = 0.50
    specs.append(BilinearitySpec("comp_E050_Adv", "homogeneity", "evidence", "adversarial", alpha=0.50, composition_direction="forward"))
    specs.append(BilinearitySpec("comp_Adv_E050", "homogeneity", "adversarial", "evidence", alpha=0.50, composition_direction="reverse"))

    # Additivity: [A + T, Adv] forward and reverse
    specs.append(BilinearitySpec("comp_AT_Adv", "additivity", "authority+temporal", "adversarial", composition_direction="forward"))
    specs.append(BilinearitySpec("comp_Adv_AT", "additivity", "adversarial", "authority+temporal", composition_direction="reverse"))

    # Additivity: [A + E, Adv] forward and reverse
    specs.append(BilinearitySpec("comp_AE_Adv", "additivity", "authority+evidence", "adversarial", composition_direction="forward"))
    specs.append(BilinearitySpec("comp_Adv_AE", "additivity", "adversarial", "authority+evidence", composition_direction="reverse"))

    return tuple(specs)


DEFAULT_BILINEARITY_SPECS = build_bilinearity_specs()


def run_bilinearity_spec(spec: BilinearitySpec) -> dict[str, Any]:
    M = TOTAL_UNITS
    Q = QUORUM_REQUIRED
    k = DISTURBED_UNITS_COUNT if spec.primary_mech != "none" else 0
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

    # 2. Induce failure in leaf runtimes based on physical scaling alpha
    for idx in range(k):
        rt = child_runtimes[idx]
        # Authority revocation fraction
        if "authority" in spec.primary_mech or "authority" in spec.secondary_mech:
            alpha_A = spec.alpha if "authority" in spec.primary_mech else spec.beta
            # revoke proportional to alpha_A
            units_to_revoke = max(1, int(round(k * alpha_A)))
            if idx < units_to_revoke:
                rt.registry.update_status(f"{spec.spec_id}_u{idx}:verify", availability=False)

    # 3. Boundary certificate verification
    all_certs_valid = True
    for rt, cert in zip(child_runtimes, child_certs):
        ok, _ = verify_composition_boundary(cert, rt.active_graph, rt.contract)
        all_certs_valid = all_certs_valid and ok

    # 4. Construct telemetry parameters with physically continuous parameters
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

    if spec.primary_mech != "none":
        output_keys = []
        root_status = "FAILED"

    # Apply physical perturbation logic
    # Baseline
    if spec.primary_mech == "none":
        pass

    # Pure states
    elif spec.condition_role == "pure":
        m = spec.primary_mech
        if m == "authority":
            role_bindings.pop("verify")
            node_seq = ["parse", "dispatch", "route", "aggregate"]
            evidence_records = ["parse", "dispatch", "route", "aggregate"]
            chain_continuity = False
            duration_ms = 480.0
        elif m == "temporal":
            temporal_ok = False
            duration_ms = 2850.0
        elif m == "evidence":
            chain_continuity = False
            digest_match = False
            node_seq = ["parse", "dispatch", "route", "aggregate", "verify"]
            evidence_records = ["parse", "dispatch", "route", "aggregate", "verify"]
            duration_ms = 520.0
        elif m == "adversarial":
            conflict_count = 2
            divergence_detected = True
            quarantine_active = True
            chain_continuity = False
            node_seq = ["parse", "dispatch", "route", "aggregate"]
            evidence_records = ["parse", "dispatch", "route", "aggregate"]
            duration_ms = 600.0

    # Composed states: reference pairs, scalar homogeneity, or additivity
    else:
        # Determine sequence of stages
        # stage 3: adversarial (aggregate)
        # stage 4: authority (verify)
        # stage 5: temporal (commit)
        # stage 2: evidence (route)
        first_mech = spec.primary_mech if spec.composition_direction == "forward" else spec.secondary_mech
        second_mech = spec.secondary_mech if spec.composition_direction == "forward" else spec.primary_mech
        alpha_val = spec.alpha

        # Check if first mechanism has temporal component
        has_temporal_1 = "temporal" in first_mech
        has_authority_1 = "authority" in first_mech
        has_evidence_1 = "evidence" in first_mech
        has_adv_1 = "adversarial" in first_mech

        has_temporal_2 = "temporal" in second_mech
        has_authority_2 = "authority" in second_mech
        has_evidence_2 = "evidence" in second_mech
        has_adv_2 = "adversarial" in second_mech

        # If forward: first_mech runs first
        if spec.composition_direction == "forward":
            # Primary stage executed first
            if has_authority_1:
                # Fractional authority revocation
                if alpha_val >= 0.5:
                    role_bindings.pop("verify", None)
                chain_continuity = False
                node_seq = ["parse", "dispatch", "route", "aggregate"]
                evidence_records = ["parse", "dispatch", "route", "aggregate"]
                duration_ms = 450.0 + 30.0 * alpha_val

            if has_temporal_1:
                # Fractional temporal duration: 450 + alpha * 2400 ms
                temporal_ok = False
                duration_ms = 450.0 + 2400.0 * alpha_val

            if has_evidence_1:
                chain_continuity = False
                digest_match = False
                node_seq = ["parse", "dispatch", "route"]
                evidence_records = ["parse", "dispatch", "route"]
                duration_ms = 310.0 + 50.0 * alpha_val

            # Secondary stage modification (adversarial)
            if has_adv_2:
                conflict_count = 2
                divergence_detected = True
                quarantine_active = True
                duration_ms += 100.0

        elif spec.composition_direction == "reverse":
            # Adversarial runs first at aggregate (stage 3)
            if has_adv_1:
                conflict_count = 2
                divergence_detected = True
                quarantine_active = True
                chain_continuity = False
                node_seq = ["parse", "dispatch", "route", "aggregate"]
                evidence_records = ["parse", "dispatch", "route", "aggregate"]
                duration_ms = 580.0

            # Secondary stage modifications
            if has_authority_2:
                if alpha_val >= 0.5:
                    role_bindings.pop("verify", None)
                duration_ms += 20.0 * alpha_val

            if has_temporal_2:
                temporal_ok = False
                # Temporal adds latency on top of adversarial execution
                duration_ms = 580.0 + 2000.0 * alpha_val

            if has_evidence_2:
                digest_match = False
                duration_ms += 40.0 * alpha_val

    state = {
        "subject": "governed_bilinear_realization_unit",
        "spec_id": spec.spec_id,
        "primary_mechanism": spec.primary_mech,
        "secondary_mechanism": spec.secondary_mech,
        "condition_role": spec.condition_role,
        "alpha": spec.alpha,
        "beta": spec.beta,
        "composition_direction": spec.composition_direction,
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
        "primary_mechanism": spec.primary_mech,
        "secondary_mechanism": spec.secondary_mech,
        "alpha": spec.alpha,
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
            "condition_role": spec.condition_role,
            "primary_mech": spec.primary_mech,
            "secondary_mech": spec.secondary_mech,
            "alpha": spec.alpha,
            "beta": spec.beta,
            "composition_direction": spec.composition_direction,
        },
        "state": state,
        "oracle": oracle,
    }


def build_bilinearity_states(specs: Sequence[BilinearitySpec] = DEFAULT_BILINEARITY_SPECS) -> list[dict[str, Any]]:
    return [run_bilinearity_spec(s) for s in specs]


def analyze_bilinearity_observations(
    deterministic_states: Sequence[dict[str, Any]],
    observations: Sequence[dict[str, Any]],
    *,
    specs: Sequence[BilinearitySpec],
    replicates: int,
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

    base_v = spec_means["op_base"]
    deltas = {sid: spec_means[sid] - base_v for sid in expected_ids}

    # Dominant macrostate direction from pure reference states
    pure_sids = ["op_A", "op_T", "op_E", "op_Adv"]
    delta_G = np.mean([deltas[sid] for sid in pure_sids], axis=0)
    norm_delta_G = float(np.linalg.norm(delta_G))
    u_G = delta_G / norm_delta_G

    def get_c(fwd_id: str, rev_id: str) -> np.ndarray:
        d_fwd = deltas[fwd_id]
        d_rev = deltas[rev_id]
        eps_fwd = d_fwd - np.dot(d_fwd, u_G) * u_G
        eps_rev = d_rev - np.dot(d_rev, u_G) * u_G
        return eps_fwd - eps_rev

    # Reference full commutators (alpha = 1.0)
    c_T_Adv_1 = get_c("comp_T_Adv", "comp_Adv_T")
    c_A_Adv_1 = get_c("comp_A_Adv", "comp_Adv_A")
    c_E_Adv_1 = get_c("comp_E_Adv", "comp_Adv_E")

    norm_c_T_Adv_1 = float(np.linalg.norm(c_T_Adv_1))
    norm_c_A_Adv_1 = float(np.linalg.norm(c_A_Adv_1))

    # 1. SCALAR HOMOGENEITY: [alpha T, Adv]
    t_homogeneity_results = []
    alphas_T = [0.25, 0.50, 0.75, 1.00]
    c_norms_T = []
    for a in alphas_T:
        if a == 1.00:
            c_a = c_T_Adv_1
        else:
            tag = f"{int(a * 100):03d}"
            c_a = get_c(f"comp_T{tag}_Adv", f"comp_Adv_T{tag}")
        
        c_expected = a * c_T_Adv_1
        error_vec = c_a - c_expected
        norm_e = float(np.linalg.norm(error_vec))
        norm_c = float(np.linalg.norm(c_a))
        c_norms_T.append(norm_c)
        eta_hom = norm_e / eff_noise

        t_homogeneity_results.append({
            "alpha": a,
            "measured_norm": round(norm_c, 4),
            "expected_norm": round(float(np.linalg.norm(c_expected)), 4),
            "error_norm": round(norm_e, 4),
            "defect_ratio_eta_hom": round(eta_hom, 2),
        })

    # Fit linear regression R^2 of measured norm vs alpha
    slope_T, intercept_T = np.polyfit(alphas_T, c_norms_T, 1)
    fitted_vals_T = [slope_T * a + intercept_T for a in alphas_T]
    ss_tot_T = sum((y - np.mean(c_norms_T))**2 for y in c_norms_T)
    ss_res_T = sum((y - y_hat)**2 for y, y_hat in zip(c_norms_T, fitted_vals_T))
    r2_hom_T = 1.0 - (ss_res_T / ss_tot_T) if ss_tot_T > 1e-15 else 1.0

    # 2. SCALAR HOMOGENEITY: [alpha A, Adv]
    a_homogeneity_results = []
    alphas_A = [0.25, 0.50, 0.75, 1.00]
    c_norms_A = []
    for a in alphas_A:
        if a == 1.00:
            c_a = c_A_Adv_1
        else:
            tag = f"{int(a * 100):03d}"
            c_a = get_c(f"comp_A{tag}_Adv", f"comp_Adv_A{tag}")
        
        c_expected = a * c_A_Adv_1
        error_vec = c_a - c_expected
        norm_e = float(np.linalg.norm(error_vec))
        norm_c = float(np.linalg.norm(c_a))
        c_norms_A.append(norm_c)
        eta_hom = norm_e / eff_noise

        a_homogeneity_results.append({
            "alpha": a,
            "measured_norm": round(norm_c, 4),
            "expected_norm": round(float(np.linalg.norm(c_expected)), 4),
            "error_norm": round(norm_e, 4),
            "defect_ratio_eta_hom": round(eta_hom, 2),
        })

    slope_A, intercept_A = np.polyfit(alphas_A, c_norms_A, 1)
    fitted_vals_A = [slope_A * a + intercept_A for a in alphas_A]
    ss_tot_A = sum((y - np.mean(c_norms_A))**2 for y in c_norms_A)
    ss_res_A = sum((y - y_hat)**2 for y, y_hat in zip(c_norms_A, fitted_vals_A))
    r2_hom_A = 1.0 - (ss_res_A / ss_tot_A) if ss_tot_A > 1e-15 else 1.0

    # 3. ADDITIVITY: [A + T, Adv] ?= [A, Adv] + [T, Adv]
    c_AT_Adv = get_c("comp_AT_Adv", "comp_Adv_AT")
    c_sum_expected_AT = c_A_Adv_1 + c_T_Adv_1
    error_add_AT = c_AT_Adv - c_sum_expected_AT
    norm_e_add_AT = float(np.linalg.norm(error_add_AT))
    norm_c_AT = float(np.linalg.norm(c_AT_Adv))
    norm_c_sum_AT = float(np.linalg.norm(c_sum_expected_AT))
    eta_add_AT = norm_e_add_AT / eff_noise

    # 4. ADDITIVITY: [A + E, Adv] ?= [A, Adv] + [E, Adv]
    c_AE_Adv = get_c("comp_AE_Adv", "comp_Adv_AE")
    c_sum_expected_AE = c_A_Adv_1 + c_E_Adv_1
    error_add_AE = c_AE_Adv - c_sum_expected_AE
    norm_e_add_AE = float(np.linalg.norm(error_add_AE))
    norm_c_AE = float(np.linalg.norm(c_AE_Adv))
    norm_c_sum_AE = float(np.linalg.norm(c_sum_expected_AE))
    eta_add_AE = norm_e_add_AE / eff_noise

    mean_eta_hom = (
        sum(r["defect_ratio_eta_hom"] for r in t_homogeneity_results)
        + sum(r["defect_ratio_eta_hom"] for r in a_homogeneity_results)
    ) / (len(t_homogeneity_results) + len(a_homogeneity_results))

    mean_eta_add = (eta_add_AT + eta_add_AE) / 2.0

    gates = {
        "B0_deterministic_oracle": oracle_pass,
        "B1_provider_complete": provider_complete,
        "B2_repeatability_noise_floor": noise_floor <= 0.050,
        "B3_scalar_homogeneity": mean_eta_hom <= 2.5 and r2_hom_T >= 0.85,
        "B4_bracket_additivity": mean_eta_add <= 3.0,
    }

    supported = all(gates.values())

    return {
        "oracle_pass": oracle_pass,
        "provider_complete": provider_complete,
        "repeatability_noise_floor_sigma_rep": round(noise_floor, 4),
        "scalar_homogeneity": {
            "temporal_series": {
                "results": t_homogeneity_results,
                "linear_scaling_R2_percent": round(r2_hom_T * 100.0, 2),
                "regression_slope": round(float(slope_T), 4),
                "regression_intercept": round(float(intercept_T), 4),
            },
            "authority_series": {
                "results": a_homogeneity_results,
                "linear_scaling_R2_percent": round(r2_hom_A * 100.0, 2),
                "regression_slope": round(float(slope_A), 4),
                "regression_intercept": round(float(intercept_A), 4),
            },
            "mean_homogeneity_defect_eta": round(mean_eta_hom, 2),
        },
        "bracket_additivity": {
            "authority_temporal_adv_triple": {
                "measured_sum_commutator_norm": round(norm_c_AT, 4),
                "predicted_sum_norm": round(norm_c_sum_AT, 4),
                "additivity_error_norm": round(norm_e_add_AT, 4),
                "defect_ratio_eta_add": round(eta_add_AT, 2),
            },
            "authority_evidence_adv_triple": {
                "measured_sum_commutator_norm": round(norm_c_AE, 4),
                "predicted_sum_norm": round(norm_c_sum_AE, 4),
                "additivity_error_norm": round(norm_e_add_AE, 4),
                "defect_ratio_eta_add": round(eta_add_AE, 2),
            },
            "mean_additivity_defect_eta": round(mean_eta_add, 2),
        },
        "gates": gates,
        "supported_within_engineering_gates": supported,
        "verdict": (
            "OPERATOR_BILINEARITY_SUPPORTED"
            if supported
            else "NONLINEAR_BRACKET_DETECTED"
        ),
    }


def run_live_bilinearity_experiment(
    *,
    provider: Any,
    specs: Sequence[BilinearitySpec] = DEFAULT_BILINEARITY_SPECS,
    replicates: int = 5,
) -> dict[str, Any]:
    deterministic_states = build_bilinearity_states(specs)
    questions = question_payload()
    observations: list[dict[str, Any]] = []
    total_calls = len(deterministic_states) * replicates

    for item in deterministic_states:
        sid = str(item["spec"]["spec_id"])
        p_mech = str(item["spec"]["primary_mech"])
        alpha_v = float(item["spec"]["alpha"])
        for rep in range(replicates):
            request_id = f"uow-bilin-{sid}-r{rep}"
            provider_res = provider.decide(
                state=dict(item["state"]),
                questions=questions,
                request_id=request_id,
            )
            vec = provider_res.get("vector") or []
            v_norm = float(np.linalg.norm(vec)) if vec else 0.0
            print(
                f"[{len(observations) + 1:03d}/{total_calls:03d}] {sid:<18} "
                f"({p_mech:<20}, a={alpha_v:0.2f}) rep={rep:02d} -> norm={v_norm:.4f}",
                flush=True,
            )
            observations.append(
                {
                    "spec_id": sid,
                    "replicate": rep,
                    "provider": provider_res,
                }
            )

    analysis = analyze_bilinearity_observations(
        deterministic_states,
        observations,
        specs=specs,
        replicates=replicates,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "JEV x UoW Operator Bracket Bilinearity Qualification Campaign",
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
        description="Run JEV x UoW Operator Bracket Bilinearity Qualification Campaign."
    )
    parser.add_argument("--model", default=DEFAULT_JEV_MODEL)
    parser.add_argument("--replicates", type=int, default=5)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    provider = TypeSafeJevProvider(model=args.model, timeout_s=args.timeout_s)
    payload = run_live_bilinearity_experiment(
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
