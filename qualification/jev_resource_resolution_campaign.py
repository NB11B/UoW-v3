"""Targeted JEV x UoW Resource Pairs Resolution Campaign.

Scientific Motivation
=====================
In the 15-pair closure campaign, 12 of 15 pairs closed at 96.2% to 99.9%
within the 5D elementary residual span. However, three Resource-involving
pairs (A-R, E-R, C-R) exhibited low commutator amplitudes (SNR ~ 2.4x - 3.3x)
and low 5D closure (R^2 ~ 35% - 43%), with defect ratios up to 2.71x sigma_rep.

This targeted experiment tests the two competing hypotheses:
    H_noise: Low closure was an artifact of measurement noise near the detection floor.
             Increasing replicates from N=3 to N=10 drops mean noise by ~1.83x;
             the defect should collapse toward the noise floor.
    H_dimension: Resource interactions genuinely introduce a missing state-space
                 dimension (e.g. along the orthogonal complement perp2).
                 The defect will remain persistently above the reduced noise floor.

We also compute the physical operator basis expansion:
    [F_i, F_j]_emp = sum_{k in {A,E,C,T,R,Adv}} c_{ij}^k eps_k
with the zero-sum gauge sum_k c_{ij}^k = 0, directly connecting physical inputs
to physical outputs in the common failure operator family.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Protocol, Sequence

import numpy as np

import sys
from pathlib import Path

# Safeguard python path when executed directly
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from qualification.jev_operator_closure_campaign import (
    ClosureSpec,
    ClosureThresholds,
    DISTURBED_UNITS_COUNT,
    MECH_SHORT,
    PURE_MECHANISMS,
    run_closure_spec,
)
from qualification.jev_provider import (
    DEFAULT_JEV_MODEL,
    TypeSafeJevProvider,
    question_payload,
)


SCHEMA_VERSION = "uow.jev_resource_resolution.v1"
DEFAULT_OUTPUT = Path("qualification/artifacts/jev_resource_resolution_results.json")

# Targeted states: baseline + 6 pure references + 3 target pairs (A-R, E-R, C-R) + 1 control pair (T-R)
TARGET_PAIRS: tuple[tuple[str, str], ...] = (
    ("authority", "resource"),
    ("evidence", "resource"),
    ("causal", "resource"),
    ("temporal", "resource"),  # High-closure control
)


def build_resource_resolution_specs() -> tuple[ClosureSpec, ...]:
    specs: list[ClosureSpec] = [
        ClosureSpec("op_base", "none", "base", 0),
    ]

    for m in PURE_MECHANISMS:
        sh = MECH_SHORT[m]
        specs.append(ClosureSpec(f"op_{sh}", m, "pure", DISTURBED_UNITS_COUNT))

    for m1, m2 in TARGET_PAIRS:
        sh1 = MECH_SHORT[m1]
        sh2 = MECH_SHORT[m2]
        # Forward
        specs.append(
            ClosureSpec(
                spec_id=f"comp_{sh1}_{sh2}",
                mechanism=f"{m1}_{m2}",
                condition_role="composition",
                disturbed_count=DISTURBED_UNITS_COUNT,
                composition_pair=(m1, m2),
                composition_direction="forward",
            )
        )
        # Reverse
        specs.append(
            ClosureSpec(
                spec_id=f"comp_{sh2}_{sh1}",
                mechanism=f"{m2}_{m1}",
                condition_role="composition",
                disturbed_count=DISTURBED_UNITS_COUNT,
                composition_pair=(m1, m2),
                composition_direction="reverse",
            )
        )

    return tuple(specs)


RESOURCE_SPECS = build_resource_resolution_specs()


class JevProvider(Protocol):
    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        ...


def analyze_resource_resolution(
    deterministic_states: Sequence[dict[str, Any]],
    observations: Sequence[dict[str, Any]],
    *,
    specs: Sequence[ClosureSpec],
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
    sem_noise_floor = noise_floor / math.sqrt(replicates) if replicates > 0 else 0.0

    spec_means = {
        sid: np.mean(grouped[sid], axis=0)
        for sid in expected_ids
    }

    base_v = spec_means["op_base"]
    deltas = {sid: spec_means[sid] - base_v for sid in expected_ids}

    # 1. Pure failure operator displacement vectors and dominant macrostate
    pure_sids = [f"op_{MECH_SHORT[m]}" for m in PURE_MECHANISMS]
    delta_G = np.mean([deltas[sid] for sid in pure_sids], axis=0)
    norm_delta_G = float(np.linalg.norm(delta_G))
    u_G = delta_G / norm_delta_G

    # Orthogonal pure residuals
    eps_pure_dict = {
        sid: deltas[sid] - np.dot(deltas[sid], u_G) * u_G
        for sid in pure_sids
    }
    E_mat = np.array([eps_pure_dict[sid] for sid in pure_sids])  # (6, 8)
    U, S, Vt = np.linalg.svd(E_mat, full_matrices=True)
    B = Vt[:5]  # (5, 8) orthonormal basis

    # Pseudo-inverse for physical operator basis with zero-sum gauge
    pinv_ET = np.linalg.pinv(E_mat.T, rcond=1e-5)

    # 2. Pairwise Analysis for Target Pairs
    pair_analyses: list[dict[str, Any]] = []
    for m1, m2 in TARGET_PAIRS:
        sh1 = MECH_SHORT[m1]
        sh2 = MECH_SHORT[m2]
        sid_ij = f"comp_{sh1}_{sh2}"
        sid_ji = f"comp_{sh2}_{sh1}"

        d_ij = deltas[sid_ij]
        d_ji = deltas[sid_ji]

        eps_ij = d_ij - np.dot(d_ij, u_G) * u_G
        eps_ji = d_ji - np.dot(d_ji, u_G) * u_G

        c_ij = eps_ij - eps_ji
        norm_c = float(np.linalg.norm(c_ij))
        snr_rep = norm_c / noise_floor if noise_floor > 1e-15 else float("inf")
        snr_sem = norm_c / sem_noise_floor if sem_noise_floor > 1e-15 else float("inf")

        # 5D PCA projection
        c_hat_5d = np.dot(B.T, np.dot(B, c_ij))
        r_5d = c_ij - c_hat_5d
        norm_c_hat = float(np.linalg.norm(c_hat_5d))
        norm_r = float(np.linalg.norm(r_5d))
        r2_5d = (norm_c_hat**2) / (norm_c**2) if norm_c > 1e-15 else 1.0
        zeta_rep = norm_r / noise_floor if noise_floor > 1e-15 else 0.0
        zeta_sem = norm_r / sem_noise_floor if sem_noise_floor > 1e-15 else 0.0

        # Physical operator basis reconstruction: [F_i, F_j] = sum_k c_ij^k eps_k
        w_phys = pinv_ET @ c_ij
        w_phys = w_phys - np.mean(w_phys)  # zero-sum gauge
        c_hat_phys = E_mat.T @ w_phys
        norm_c_phys = float(np.linalg.norm(c_hat_phys))
        r2_phys = (norm_c_phys**2) / (norm_c**2) if norm_c > 1e-15 else 1.0

        phys_coeffs = {
            MECH_SHORT[m]: round(float(w), 4)
            for m, w in zip(PURE_MECHANISMS, w_phys)
        }

        # Check orthogonal complement (perp2) projection
        V_null = Vt[5:]  # (3, 8)
        Q, _ = np.linalg.qr(np.vstack([u_G, V_null]).T)
        perp1 = Q[:, 1]
        perp2 = Q[:, 2]
        p_perp1 = float(np.dot(c_ij, perp1))
        p_perp2 = float(np.dot(c_ij, perp2))

        pair_analyses.append(
            {
                "pair": f"{sh1}-{sh2}",
                "mechanisms": (m1, m2),
                "commutator_norm": round(norm_c, 4),
                "replicate_noise_floor": round(noise_floor, 4),
                "sem_noise_floor": round(sem_noise_floor, 4),
                "snr_vs_replicate_noise": round(snr_rep, 2),
                "snr_vs_sem_noise": round(snr_sem, 2),
                "closure_R2_5D_percent": round(r2_5d * 100.0, 2),
                "defect_norm": round(norm_r, 4),
                "defect_ratio_vs_sigma_rep": round(zeta_rep, 2),
                "defect_ratio_vs_sigma_sem": round(zeta_sem, 2),
                "physical_basis_closure_R2_percent": round(r2_phys * 100.0, 2),
                "physical_basis_coefficients": phys_coeffs,
                "perp_projections": {
                    "perp1": round(p_perp1, 4),
                    "perp2": round(p_perp2, 4),
                },
            }
        )

    # Hypothesis test evaluation:
    # If mean defect ratio vs sigma_rep remains > 2.0x even with N=10 replicates,
    # then Resource interactions introduce an unresolved dimension.
    target_results = [p for p in pair_analyses if p["pair"] in ("A-R", "E-R", "C-R")]
    mean_target_zeta_rep = sum(p["defect_ratio_vs_sigma_rep"] for p in target_results) / len(target_results)
    mean_target_r2 = sum(p["closure_R2_5D_percent"] for p in target_results) / len(target_results)

    hypothesis_outcome = (
        "MISSING_DIMENSION_CONFIRMED"
        if mean_target_zeta_rep > 2.0
        else "COLLAPSED_TO_NOISE_CLOSURE_CONFIRMED"
    )

    return {
        "oracle_pass": oracle_pass,
        "provider_complete": provider_complete,
        "replicates_per_state": replicates,
        "repeatability_noise_floor_sigma_rep": round(noise_floor, 4),
        "standard_error_mean_sigma_sem": round(sem_noise_floor, 4),
        "dominant_macrostate_norm": round(norm_delta_G, 4),
        "pure_residual_singular_values": [round(float(s), 4) for s in S],
        "targeted_pair_analyses": pair_analyses,
        "resource_triplet_summary": {
            "mean_closure_R2_percent": round(mean_target_r2, 2),
            "mean_defect_ratio_vs_sigma_rep": round(mean_target_zeta_rep, 2),
            "verdict": hypothesis_outcome,
        },
    }


def run_live_resource_resolution_experiment(
    *,
    provider: JevProvider,
    replicates: int = 10,
    specs: Sequence[ClosureSpec] = RESOURCE_SPECS,
) -> dict[str, Any]:
    deterministic_states = [run_closure_spec(s) for s in specs]
    questions = question_payload()
    observations: list[dict[str, Any]] = []
    total_calls = len(deterministic_states) * replicates

    for item in deterministic_states:
        sid = str(item["spec"]["spec_id"])
        mech = str(item["spec"]["mechanism"])
        k = int(item["spec"]["disturbed_count"])
        for rep in range(replicates):
            request_id = f"uow-resres-{sid}-r{rep}"
            provider_res = provider.decide(
                state=dict(item["state"]),
                questions=questions,
                request_id=request_id,
            )
            vec = provider_res.get("vector") or []
            v_norm = float(np.linalg.norm(vec)) if vec else 0.0
            print(
                f"[{len(observations) + 1:03d}/{total_calls:03d}] {sid:<15} "
                f"({mech:<22}, k={k:02d}) rep={rep:02d} -> norm={v_norm:.4f}",
                flush=True,
            )
            observations.append(
                {
                    "spec_id": sid,
                    "replicate": rep,
                    "provider": provider_res,
                }
            )

    analysis = analyze_resource_resolution(
        deterministic_states,
        observations,
        specs=specs,
        replicates=replicates,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "Targeted JEV x UoW Resource Pairs Resolution Campaign",
        "method": {
            "replicates_per_state": replicates,
            "total_requests": total_calls,
            "target_pairs": [f"{s1}-{s2}" for s1, s2 in TARGET_PAIRS],
        },
        "deterministic_states": deterministic_states,
        "observations": observations,
        "analysis": analysis,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run targeted high-replicate Resource pairs resolution campaign."
    )
    parser.add_argument("--model", default=DEFAULT_JEV_MODEL)
    parser.add_argument("--replicates", type=int, default=10)
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    provider = TypeSafeJevProvider(model=args.model, timeout_s=args.timeout_s)
    payload = run_live_resource_resolution_experiment(
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
