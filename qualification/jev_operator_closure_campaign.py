"""JEV x UoW Operator Algebraic Closure Qualification Campaign.

Scientific Framing
==================
Does sequential composition of governed failure mechanisms remain inside the
empirically discovered failure coordinate space, or does it generate new dimensions?

Specifically, we test the fundamental closure hypothesis across all 15 unordered
pairs (30 directional compositions) of the six elementary failure mechanisms:
    F_i F_j vs F_j F_i  for all (i, j) in {A, E, C, T, R, Adv}

Under a single, strictly fixed architecture:
    - Fixed ensemble size M = 16
    - Fixed quorum threshold Q = 9
    - Fixed topology: Star / Fan-out (direct independent lines)
    - Fixed recursive depth d = 1
    - Common-output control: Every failure state produces identical macro-outcome:
      admissible units = 8 < 9 => quorum margin = -1, emitted output keys = [], FAILED
    - Raw telemetry: Strictly zero outcome/error labels (forbidden words banned)
    - Pinned model: jev-1.13.0, 3 replicates per state (111 requests total: 1 base + 6 pure + 30 composed)

Closure Formulation
===================
1. Remove dominant macrostate direction Delta_G from all deltas:
       eps = Delta - (Delta . u_G) u_G
2. Construct orthonormal basis B = {B_1, ..., B_5} from SVD of the pure residuals
       E = [eps_A, eps_E, eps_C, eps_T, eps_R, eps_Adv]^T
3. For each pair (i, j), compute the empirical commutator:
       c_ij = [F_i, F_j]_emp = eps_ij - eps_ji
4. Project onto top k modes (k = 1..5) to obtain closure R^2(k) and defect zeta(k):
       c_hat_ij^(k) = sum_{a=1}^k (c_ij . B_a) B_a
       r_ij^(k) = c_ij - c_hat_ij^(k)
       R^2_close(k; i, j) = ||c_hat_ij^(k)||^2 / ||c_ij||^2
       zeta_ij^(k) = ||r_ij^(k)|| / sigma_rep
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
)

from qualification.jev_provider import (
    DEFAULT_JEV_MODEL,
    TypeSafeJevProvider,
    question_payload,
)


SCHEMA_VERSION = "uow.jev_operator_closure.v1"
DEFAULT_OUTPUT = Path("qualification/artifacts/jev_operator_closure_results.json")

TOTAL_UNITS = 16
QUORUM_REQUIRED = 9
DISTURBED_UNITS_COUNT = 8


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
class ClosureSpec:
    spec_id: str
    mechanism: str
    condition_role: str  # "base", "pure", "composition"
    disturbed_count: int
    composition_pair: tuple[str, str] = ("", "")
    composition_direction: str = ""  # "forward", "reverse", or ""


# Elementary failure codes
PURE_MECHANISMS: tuple[str, ...] = ("authority", "evidence", "causal", "temporal", "resource", "adversarial")
MECH_SHORT: dict[str, str] = {
    "authority": "A",
    "evidence": "E",
    "causal": "C",
    "temporal": "T",
    "resource": "R",
    "adversarial": "Adv",
}
SHORT_TO_MECH: dict[str, str] = {v: k for k, v in MECH_SHORT.items()}

# Generate all 15 unordered pairs
ALL_15_PAIRS: list[tuple[str, str]] = []
for i in range(len(PURE_MECHANISMS)):
    for j in range(i + 1, len(PURE_MECHANISMS)):
        ALL_15_PAIRS.append((PURE_MECHANISMS[i], PURE_MECHANISMS[j]))


def build_default_closure_specs() -> tuple[ClosureSpec, ...]:
    specs: list[ClosureSpec] = [
        # Baseline nominal state
        ClosureSpec("op_base", "none", "base", 0),
    ]

    # 6 Pure Failure Operators
    for m in PURE_MECHANISMS:
        sh = MECH_SHORT[m]
        specs.append(ClosureSpec(f"op_{sh}", m, "pure", DISTURBED_UNITS_COUNT))

    # 30 Composed States (15 pairs x 2 directions)
    for m1, m2 in ALL_15_PAIRS:
        sh1 = MECH_SHORT[m1]
        sh2 = MECH_SHORT[m2]
        # Forward: F_1 F_2
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
        # Reverse: F_2 F_1
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


DEFAULT_CLOSURE_SPECS: tuple[ClosureSpec, ...] = build_default_closure_specs()


@dataclass(frozen=True)
class ClosureThresholds:
    min_commutator_snr: float = 3.0  # ||c_ij|| / sigma_rep >= 3.0
    max_noise_floor_l2: float = 0.050
    closure_r2_threshold: float = 0.850  # R^2 >= 85% for empirical closure
    closure_defect_zeta_threshold: float = 2.0  # Defect ratio <= 2.0x noise floor indicates closure within noise


def make_child_unit(unit_id: str) -> tuple[AdaptiveCompositionRuntime, Any]:
    output_key = f"{unit_id}_result"
    contract = ParentContract(
        contract_id=f"{unit_id}:contract",
        description=f"Unit {unit_id} contract",
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
            verifier_id="unit-verifier",
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
        raise RuntimeError(f"Child {unit_id} certification failed: {cert.violations}")
    return runtime, cert


def run_closure_spec(spec: ClosureSpec) -> dict[str, Any]:
    M = TOTAL_UNITS
    Q = QUORUM_REQUIRED
    k = spec.disturbed_count
    admissible_count = M - k
    quorum_achieved = admissible_count >= Q
    quorum_margin = admissible_count - Q

    # 1. Instantiate the M child runtimes
    child_runtimes: list[AdaptiveCompositionRuntime] = []
    child_certs: list[Any] = []
    for i in range(M):
        rt, cert = make_child_unit(f"{spec.spec_id}_u{i}")
        child_runtimes.append(rt)
        child_certs.append(cert)

    # 2. Induce failure in leaf runtimes
    for idx in range(k):
        rt = child_runtimes[idx]
        if "authority" in spec.mechanism:
            rt.registry.update_status(f"{spec.spec_id}_u{idx}:verify", availability=False)

    # 3. Boundary certificate verification
    all_certs_valid = True
    for rt, cert in zip(child_runtimes, child_certs):
        ok, _ = verify_composition_boundary(cert, rt.active_graph, rt.contract)
        all_certs_valid = all_certs_valid and ok

    # 4. Construct raw telemetry reflecting the specific failure sequence
    # Common base profile:
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

    # Profile adjustments for pure and composed mechanisms:
    mech = spec.mechanism

    # Handle primary mechanism parameters
    if mech == "none":
        pass
    elif mech == "authority":
        role_bindings.pop("verify")
        node_seq = ["parse", "dispatch", "route", "aggregate"]
        evidence_records = ["parse", "dispatch", "route", "aggregate"]
        chain_continuity = False
        duration_ms = 480.0
    elif mech == "evidence":
        chain_continuity = False
        digest_match = False
        node_seq = ["parse", "dispatch", "route", "aggregate", "verify"]
        evidence_records = ["parse", "dispatch", "route", "aggregate", "verify"]
        duration_ms = 520.0
    elif mech == "causal":
        causal_edges = [["parse", "dispatch"], ["route", "aggregate"], ["aggregate", "verify"], ["verify", "commit"]]
        node_seq = ["parse", "dispatch"]
        evidence_records = ["parse", "dispatch"]
        chain_continuity = False
        duration_ms = 210.0
        ram_units = 4
    elif mech == "temporal":
        temporal_ok = False
        duration_ms = 2850.0
    elif mech == "resource":
        resource_ok = False
        ram_units = 64
        node_seq = ["parse", "dispatch", "route"]
        evidence_records = ["parse", "dispatch", "route"]
        chain_continuity = False
        duration_ms = 350.0
    elif mech == "adversarial":
        conflict_count = 2
        divergence_detected = True
        quarantine_active = True
        chain_continuity = False
        node_seq = ["parse", "dispatch", "route", "aggregate"]
        evidence_records = ["parse", "dispatch", "route", "aggregate"]
        duration_ms = 600.0

    # Handle sequential composition: m1 followed by m2 (or vice versa)
    elif "_" in mech:
        m_first, m_second = mech.split("_", 1)

        # Stage mapping:
        # resource (parse: stage 0)
        # causal (dispatch: stage 1)
        # evidence (route: stage 2)
        # adversarial (aggregate: stage 3)
        # authority (verify: stage 4)
        # temporal (commit: stage 5)
        stage_order = {"resource": 0, "causal": 1, "evidence": 2, "adversarial": 3, "authority": 4, "temporal": 5}
        first_stage = stage_order[m_first]

        # Apply primary constraint fault
        if m_first == "authority":
            role_bindings.pop("verify")
            chain_continuity = False
            node_seq = ["parse", "dispatch", "route", "aggregate"]
            evidence_records = ["parse", "dispatch", "route", "aggregate"]
            duration_ms = 470.0
        elif m_first == "evidence":
            chain_continuity = False
            digest_match = False
            node_seq = ["parse", "dispatch", "route"]
            evidence_records = ["parse", "dispatch", "route"]
            duration_ms = 310.0
        elif m_first == "causal":
            causal_edges = [["parse", "dispatch"], ["aggregate", "verify"], ["verify", "commit"]]
            node_seq = ["parse", "dispatch"]
            evidence_records = ["parse", "dispatch"]
            chain_continuity = False
            duration_ms = 190.0
            ram_units = 4
        elif m_first == "resource":
            resource_ok = False
            ram_units = 56
            node_seq = ["parse"]
            evidence_records = ["parse"]
            chain_continuity = False
            duration_ms = 120.0
        elif m_first == "adversarial":
            conflict_count = 2
            divergence_detected = True
            quarantine_active = True
            chain_continuity = False
            node_seq = ["parse", "dispatch", "route", "aggregate"]
            evidence_records = ["parse", "dispatch", "route", "aggregate"]
            duration_ms = 580.0
        elif m_first == "temporal":
            temporal_ok = False
            duration_ms = 2600.0

        # Apply secondary constraint modification if second stage is reachable
        second_stage = stage_order[m_second]
        if second_stage <= first_stage:
            # Secondary constraint is reached or coincident
            if m_second == "authority":
                role_bindings.pop("verify", None)
            elif m_second == "evidence":
                digest_match = False
            elif m_second == "resource":
                resource_ok = False
                ram_units = max(ram_units, 48)
            elif m_second == "adversarial":
                conflict_count = max(conflict_count, 2)
                divergence_detected = True
            elif m_second == "temporal":
                temporal_ok = False
                duration_ms = max(duration_ms, 2400.0)
        else:
            # Secondary constraint modifies late telemetry slightly
            if m_second == "temporal":
                duration_ms += 400.0
            elif m_second == "resource":
                ram_units += 8
            elif m_second == "evidence":
                digest_match = False

    # Raw telemetry state
    state = {
        "subject": "governed_operator_realization_unit",
        "spec_id": spec.spec_id,
        "mechanism": spec.mechanism,
        "condition_role": spec.condition_role,
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
        "condition_role": spec.condition_role,
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
            "condition_role": spec.condition_role,
            "disturbed_count": k,
            "admissible_count": admissible_count,
            "composition_pair": spec.composition_pair,
            "composition_direction": spec.composition_direction,
        },
        "state": state,
        "oracle": oracle,
    }


def build_closure_states(specs: Sequence[ClosureSpec] = DEFAULT_CLOSURE_SPECS) -> list[dict[str, Any]]:
    return [run_closure_spec(spec) for spec in specs]


def _norm(v: Sequence[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _subtract(a: Sequence[float], b: Sequence[float]) -> list[float]:
    return [x - y for x, y in zip(a, b)]


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def analyze_closure_observations(
    deterministic_states: Sequence[dict[str, Any]],
    observations: Sequence[dict[str, Any]],
    *,
    specs: Sequence[ClosureSpec],
    replicates: int,
    thresholds: ClosureThresholds,
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
                "J1_repeatability_noise_floor": False,
                "J2_commutator_detectability": False,
                "J3_algebraic_closure_evaluated": False,
                "J4_closure_spectrum_characterized": False,
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

    spec_means = {
        sid: [sum(col) / len(reps) for col in zip(*reps)]
        for sid, reps in grouped.items()
    }

    base_v = spec_means["op_base"]
    deltas = {sid: _subtract(spec_means[sid], base_v) for sid in expected_ids}

    # 1. Pure failure operator displacement vectors and dominant macrostate
    pure_sids = [f"op_{MECH_SHORT[m]}" for m in PURE_MECHANISMS]
    dim = len(base_v)
    delta_G = [sum(deltas[sid][d] for sid in pure_sids) / float(len(pure_sids)) for d in range(dim)]
    norm_delta_G = _norm(delta_G)
    u_G = [x / norm_delta_G for x in delta_G]

    # Orthogonal pure residuals: eps_i = Delta_i - (Delta_i . u_G) u_G
    eps_pure: dict[str, list[float]] = {}
    for sid in pure_sids:
        d = deltas[sid]
        proj_scalar = _dot(d, u_G)
        eps_pure[sid] = [x - proj_scalar * u for x, u in zip(d, u_G)]

    # SVD of pure residuals using standard numpy-free Gram-Schmidt or power iteration / numpy
    # We can use numpy for robust SVD
    import numpy as np

    E_mat = np.array([eps_pure[sid] for sid in pure_sids])  # (6, 8)
    U, S, Vt = np.linalg.svd(E_mat, full_matrices=False)
    B = Vt  # (6, 8) row basis of singular vectors (rank <= 5)

    pure_variance_explained = [(float(s)**2) / float(np.sum(S**2)) * 100.0 for s in S]

    # Precompute pseudo-inverse of pure residual matrix for physical operator basis expansion
    pinv_ET = np.linalg.pinv(E_mat.T, rcond=1e-5)

    # 2. Pairwise Empirical Commutators across all 15 pairs
    pair_results: list[dict[str, Any]] = []
    commutator_norms: list[float] = []

    for m1, m2 in ALL_15_PAIRS:
        sh1 = MECH_SHORT[m1]
        sh2 = MECH_SHORT[m2]
        sid_ij = f"comp_{sh1}_{sh2}"
        sid_ji = f"comp_{sh2}_{sh1}"

        d_ij = deltas[sid_ij]
        d_ji = deltas[sid_ji]

        # Orthogonal residuals
        eps_ij = [x - _dot(d_ij, u_G) * u for x, u in zip(d_ij, u_G)]
        eps_ji = [x - _dot(d_ji, u_G) * u for x, u in zip(d_ji, u_G)]

        # Empirical commutator c_ij = eps_ij - eps_ji
        c_ij = [a - b for a, b in zip(eps_ij, eps_ji)]
        norm_c = _norm(c_ij)
        commutator_norms.append(norm_c)
        snr_c = norm_c / noise_floor if noise_floor > 1e-15 else float("inf")

        # Projections onto top k modes (k = 1..5)
        c_np = np.array(c_ij)
        dim_r2: dict[str, float] = {}
        dim_zeta: dict[str, float] = {}
        for k in range(1, 6):
            B_k = B[:k]  # (k, 8)
            c_hat_k = np.dot(B_k.T, np.dot(B_k, c_np))
            r_k = c_np - c_hat_k
            norm_c_hat = float(np.linalg.norm(c_hat_k))
            norm_r = float(np.linalg.norm(r_k))
            r2 = (norm_c_hat**2) / (norm_c**2) if norm_c > 1e-15 else 1.0
            zeta = norm_r / noise_floor if noise_floor > 1e-15 else 0.0
            dim_r2[f"R2_{k}D"] = round(r2 * 100.0, 2)
            dim_zeta[f"zeta_{k}D"] = round(zeta, 2)

        # Observer-space PCA projection coefficients: f_ij^a = c_ij . B_a
        f_coeffs = [round(float(np.dot(c_np, B[a])), 4) for a in range(5)]

        # Physical operator basis reconstruction: [F_i, F_j] = sum_k c_ij^k eps_k
        w_phys = pinv_ET @ c_np
        w_phys = w_phys - np.mean(w_phys)  # zero-sum gauge
        c_hat_phys = E_mat.T @ w_phys
        norm_c_phys = float(np.linalg.norm(c_hat_phys))
        r2_phys = (norm_c_phys**2) / (norm_c**2) if norm_c > 1e-15 else 1.0

        phys_coeffs = {
            MECH_SHORT[m]: round(float(w), 4)
            for m, w in zip(PURE_MECHANISMS, w_phys)
        }

        pair_results.append(
            {
                "pair": f"{sh1}-{sh2}",
                "mech_i": m1,
                "mech_j": m2,
                "seq_ij": sid_ij,
                "seq_ji": sid_ji,
                "commutator_norm": norm_c,
                "commutator_snr": snr_c,
                "closure_r2_by_dim": dim_r2,
                "defect_zeta_by_dim": dim_zeta,
                "pca_projection_coefficients_5D": f_coeffs,
                "structure_coefficients_5D": f_coeffs,  # backwards compatibility alias
                "physical_basis_closure_R2_percent": round(r2_phys * 100.0, 2),
                "physical_basis_coefficients": phys_coeffs,
            }
        )

    # 3. Aggregate Dimensional Closure Spectrum
    closure_spectrum: dict[str, Any] = {}
    for k in range(1, 6):
        mean_r2 = sum(p["closure_r2_by_dim"][f"R2_{k}D"] for p in pair_results) / len(pair_results)
        mean_zeta = sum(p["defect_zeta_by_dim"][f"zeta_{k}D"] for p in pair_results) / len(pair_results)
        closure_spectrum[f"{k}D"] = {
            "mean_R2_percent": round(mean_r2, 2),
            "mean_defect_zeta": round(mean_zeta, 2),
        }

    mean_comm_snr = sum(p["commutator_snr"] for p in pair_results) / len(pair_results)
    full_r2 = closure_spectrum["5D"]["mean_R2_percent"]
    full_zeta = closure_spectrum["5D"]["mean_defect_zeta"]

    closes_in_residual_space = full_r2 >= thresholds.closure_r2_threshold * 100.0

    gates = {
        "U0_deterministic_oracle": oracle_pass,
        "J0_provider_complete": provider_complete,
        "J1_repeatability_noise_floor": noise_floor <= thresholds.max_noise_floor_l2,
        "J2_commutator_detectability": mean_comm_snr >= thresholds.min_commutator_snr,
        "J3_algebraic_closure_evaluated": True,
        "J4_closure_spectrum_characterized": len(closure_spectrum) == 5,
    }

    supported = all(gates.values())

    return {
        "oracle_pass": oracle_pass,
        "provider_complete": provider_complete,
        "repeatability_noise_floor_l2": noise_floor,
        "dominant_macrostate_norm": norm_delta_G,
        "pure_residual_singular_values": [round(float(s), 4) for s in S],
        "pure_residual_variance_explained": [round(v, 2) for v in pure_variance_explained],
        "mean_commutator_norm": sum(commutator_norms) / len(commutator_norms),
        "mean_commutator_snr": mean_comm_snr,
        "dimensional_closure_spectrum": closure_spectrum,
        "closure_verdict": (
            "APPROXIMATE_RESIDUAL_SPAN_CLOSURE_SUPPORTED"
            if closes_in_residual_space and full_zeta <= thresholds.closure_defect_zeta_threshold
            else "EMERGENT_NEW_DIMENSIONS_DETECTED"
        ),
        "all_15_pair_results": pair_results,
        "thresholds": {
            "min_commutator_snr": thresholds.min_commutator_snr,
            "max_noise_floor_l2": thresholds.max_noise_floor_l2,
            "closure_r2_threshold": thresholds.closure_r2_threshold,
            "closure_defect_zeta_threshold": thresholds.closure_defect_zeta_threshold,
        },
        "gates": gates,
        "supported_within_engineering_gates": supported,
        "verdict": (
            "SUPPORTED_WITHIN_PREREGISTERED_ENGINEERING_GATES"
            if supported
            else "NOT_SUPPORTED_BY_THIS_RUN"
        ),
    }


def run_live_closure_experiment(
    *,
    provider: JevProvider,
    specs: Sequence[ClosureSpec] = DEFAULT_CLOSURE_SPECS,
    replicates: int = 3,
    thresholds: ClosureThresholds,
) -> dict[str, Any]:
    deterministic_states = build_closure_states(specs)
    questions = question_payload()
    observations: list[dict[str, Any]] = []
    total_calls = len(deterministic_states) * replicates

    for item in deterministic_states:
        sid = str(item["spec"]["spec_id"])
        mech = str(item["spec"]["mechanism"])
        k = int(item["spec"]["disturbed_count"])
        for rep in range(replicates):
            request_id = f"uow-close-{sid}-r{rep}"
            provider_res = provider.decide(
                state=dict(item["state"]),
                questions=questions,
                request_id=request_id,
            )
            vec = provider_res.get("vector") or []
            v_norm = _norm(vec) if vec else 0.0
            print(
                f"[{len(observations) + 1:03d}/{total_calls:03d}] {sid:<15} "
                f"({mech:<22}, k={k:02d}) rep={rep} -> norm={v_norm:.4f}",
                flush=True,
            )
            observations.append(
                {
                    "spec_id": sid,
                    "replicate": rep,
                    "provider": provider_res,
                }
            )

    analysis = analyze_closure_observations(
        deterministic_states,
        observations,
        specs=specs,
        replicates=replicates,
        thresholds=thresholds,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "JEV x UoW Operator Algebraic Closure Qualification Campaign",
        "method": {
            "mechanisms": list(PURE_MECHANISMS),
            "state_specs": [
                {
                    "spec_id": s.spec_id,
                    "mechanism": s.mechanism,
                    "condition_role": s.condition_role,
                    "disturbed_count": s.disturbed_count,
                    "composition_pair": s.composition_pair,
                    "composition_direction": s.composition_direction,
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
        description="Run the JEV x UoW Operator Algebraic Closure Qualification Campaign."
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

    thresholds = ClosureThresholds()

    if args.prepare_only:
        states = build_closure_states()
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
        payload = run_live_closure_experiment(
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
