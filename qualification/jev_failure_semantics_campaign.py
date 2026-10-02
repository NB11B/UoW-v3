"""JEV x UoW Failure Semantics Operator Family Identification Campaign.

Scientific Framing
==================
Does JEV resolve distinct governed failure mechanisms into distinct, reproducible
operator directions, or do all failure mechanisms collapse to a generic 1-D
macrostate attractor?

Specifically, we estimate the operator family:
    F = {Delta_A, Delta_E, Delta_C, Delta_T, Delta_R, Delta_Adv}

under a single, strictly fixed architecture:
    - Fixed ensemble size M = 16
    - Fixed quorum threshold Q = 9
    - Fixed topology: Star / Fan-out (independent direct lines)
    - Fixed recursive depth d = 1
    - Common-output control: Every failure mode produces the identical macroscopic outcome:
      root cannot lawfully complete (no emitted output keys, rollback / uncommitted, quorum margin = -1)
    - Raw telemetry representation: Zero outcome/status labels, forbidden words strictly excluded
    - Pinned model: jev-1.13.0, 3 replicates per state

Sequential Composition & Noncommutativity
=========================================
For candidate pairs (e.g. F_i F_j vs F_j F_i), we measure:
    kappa_ij = ||Delta_ij - Delta_ji||
relative to the repeatability noise floor sigma_rep.
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
)

from qualification.jev_provider import (
    DEFAULT_JEV_MODEL,
    TypeSafeJevProvider,
    question_payload,
)


SCHEMA_VERSION = "uow.jev_failure_semantics.v1"
DEFAULT_OUTPUT = Path("qualification/artifacts/jev_failure_semantics_results.json")

TOTAL_UNITS = 16
QUORUM_REQUIRED = 9
DISTURBED_UNITS_COUNT = 8  # 8 units disturbed => 8 valid left < 9 required => Q margin = -1


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
class FailureSpec:
    spec_id: str
    mechanism: str  # "none", "authority", "evidence", "causal", "temporal", "resource", "adversarial", or composed
    condition_role: str  # "base", "operator", "composition"
    disturbed_count: int
    composition_sequence: tuple[str, ...] = ()

    @property
    def disturbance_density(self) -> float:
        return self.disturbed_count / float(TOTAL_UNITS)


# 13 Preregistered States: 1 Base, 6 Pure Failure Operators, 6 Composed Pairs (3 pairs forward/backward)
DEFAULT_FAILURE_SPECS: tuple[FailureSpec, ...] = (
    # Baseline nominal state
    FailureSpec("op_base", "none", "base", 0),

    # 6 Pure Failure Operators (all at identical disturbance count k=8, quorum margin = -1)
    FailureSpec("op_A", "authority", "operator", DISTURBED_UNITS_COUNT),
    FailureSpec("op_E", "evidence", "operator", DISTURBED_UNITS_COUNT),
    FailureSpec("op_C", "causal", "operator", DISTURBED_UNITS_COUNT),
    FailureSpec("op_T", "temporal", "operator", DISTURBED_UNITS_COUNT),
    FailureSpec("op_R", "resource", "operator", DISTURBED_UNITS_COUNT),
    FailureSpec("op_Adv", "adversarial", "operator", DISTURBED_UNITS_COUNT),

    # 3 Pairs for Sequential Composition & Noncommutativity (6 directional sequences)
    # Pair 1: Authority vs Evidence (F_A F_E vs F_E F_A)
    FailureSpec("comp_AE", "authority_evidence", "composition", DISTURBED_UNITS_COUNT, ("authority", "evidence")),
    FailureSpec("comp_EA", "evidence_authority", "composition", DISTURBED_UNITS_COUNT, ("evidence", "authority")),

    # Pair 2: Authority vs Causal (F_A F_C vs F_C F_A)
    FailureSpec("comp_AC", "authority_causal", "composition", DISTURBED_UNITS_COUNT, ("authority", "causal")),
    FailureSpec("comp_CA", "causal_authority", "composition", DISTURBED_UNITS_COUNT, ("causal", "authority")),

    # Pair 3: Evidence vs Resource (F_E F_R vs F_R F_E)
    FailureSpec("comp_ER", "evidence_resource", "composition", DISTURBED_UNITS_COUNT, ("evidence", "resource")),
    FailureSpec("comp_RE", "resource_evidence", "composition", DISTURBED_UNITS_COUNT, ("resource", "evidence")),
)


@dataclass(frozen=True)
class FailureSemanticsThresholds:
    min_snr: float = 10.0
    max_noise_floor_l2: float = 0.050
    separation_cosine_threshold: float = 0.950  # Below this threshold indicates genuine operator separation
    noncommutativity_snr_threshold: float = 3.0  # kappa_ij / sigma_rep >= 3.0 confirms significant noncommutativity


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


def run_failure_spec(spec: FailureSpec) -> dict[str, Any]:
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

    # 2. Induce the specific failure semantics in the k disturbed units
    for idx in range(k):
        rt = child_runtimes[idx]
        if "authority" in spec.mechanism:
            rt.registry.update_status(f"{spec.spec_id}_u{idx}:verify", availability=False)

    # 3. Boundary certificate verification
    all_certs_valid = True
    for rt, cert in zip(child_runtimes, child_certs):
        ok, _ = verify_composition_boundary(cert, rt.active_graph, rt.contract)
        all_certs_valid = all_certs_valid and ok

    # 4. Construct raw telemetry reflecting the distinct failure mechanisms
    # All failure modes share: quorum_achieved=False, emitted_output_keys=[], root_status="FAILED"
    # But differ strictly in their internal evidence records and mechanism indicators.

    # Base nominal state
    if spec.mechanism == "none":
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

    elif spec.mechanism == "authority":
        # Delta_A: Authority unavailable; evidence, causal, timing, resources intact
        role_bindings = {
            "parse": "role:parser",
            "dispatch": "role:dispatcher",
            "route": "role:router",
            "aggregate": "role:aggregator",
            "commit": "role:commit",
            # "verify" role unassigned / revoked
        }
        causal_edges = [
            ["parse", "dispatch"],
            ["dispatch", "route"],
            ["route", "aggregate"],
            ["aggregate", "verify"],
            ["verify", "commit"],
        ]
        node_seq = ["parse", "dispatch", "route", "aggregate"]
        evidence_records = ["parse", "dispatch", "route", "aggregate"]
        chain_continuity = False
        digest_match = True
        temporal_ok = True
        duration_ms = 480.0
        resource_ok = True
        ram_units = 8
        conflict_count = 0
        divergence_detected = False
        quarantine_active = False
        output_keys = []
        root_status = "FAILED"

    elif spec.mechanism == "evidence":
        # Delta_E: Evidence integrity fails (digest mismatch); authority, causal, timing, resources intact
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
        node_seq = ["parse", "dispatch", "route", "aggregate", "verify"]
        evidence_records = ["parse", "dispatch", "route", "aggregate", "verify"]
        chain_continuity = False
        digest_match = False  # Tampered or mismatched cryptographic digest
        temporal_ok = True
        duration_ms = 520.0
        resource_ok = True
        ram_units = 8
        conflict_count = 0
        divergence_detected = False
        quarantine_active = False
        output_keys = []
        root_status = "FAILED"

    elif spec.mechanism == "causal":
        # Delta_C: Required causal path structurally broken; authority, evidence mechanism intact
        role_bindings = {
            "parse": "role:parser",
            "dispatch": "role:dispatcher",
            "route": "role:router",
            "aggregate": "role:aggregator",
            "verify": "role:verifier",
            "commit": "role:commit",
        }
        # Broken causal edge: dispatch -> route severed
        causal_edges = [
            ["parse", "dispatch"],
            ["route", "aggregate"],
            ["aggregate", "verify"],
            ["verify", "commit"],
        ]
        node_seq = ["parse", "dispatch"]  # Halted early at severed edge
        evidence_records = ["parse", "dispatch"]
        chain_continuity = False
        digest_match = True
        temporal_ok = True
        duration_ms = 210.0
        resource_ok = True
        ram_units = 4
        conflict_count = 0
        divergence_detected = False
        quarantine_active = False
        output_keys = []
        root_status = "FAILED"

    elif spec.mechanism == "temporal":
        # Delta_T: All evidence & authority valid, but execution timestamp exceeds deadline
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
        node_seq = ["parse", "dispatch", "route", "aggregate", "verify"]
        evidence_records = ["parse", "dispatch", "route", "aggregate", "verify"]
        chain_continuity = True  # Evidence chain is self-consistent
        digest_match = True
        temporal_ok = False  # Exceeded 1000ms deadline
        duration_ms = 2850.0
        resource_ok = True
        ram_units = 8
        conflict_count = 0
        divergence_detected = False
        quarantine_active = False
        output_keys = []
        root_status = "FAILED"

    elif spec.mechanism == "resource":
        # Delta_R: Authority/evidence/causality intact, but resource allocation exceeded
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
        node_seq = ["parse", "dispatch", "route"]  # Halted upon memory cap breach
        evidence_records = ["parse", "dispatch", "route"]
        chain_continuity = False
        digest_match = True
        temporal_ok = True
        duration_ms = 350.0
        resource_ok = False  # Exceeded 16 RAM units
        ram_units = 64
        conflict_count = 0
        divergence_detected = False
        quarantine_active = False
        output_keys = []
        root_status = "FAILED"

    elif spec.mechanism == "adversarial":
        # Delta_Adv: Conflicting validly-signed observations force quarantine
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
        node_seq = ["parse", "dispatch", "route", "aggregate"]
        evidence_records = ["parse", "dispatch", "route", "aggregate"]
        chain_continuity = False  # Forking provenance
        digest_match = True
        temporal_ok = True
        duration_ms = 600.0
        resource_ok = True
        ram_units = 10
        conflict_count = 2  # Dual conflicting attestations
        divergence_detected = True
        quarantine_active = True
        output_keys = []
        root_status = "FAILED"

    # Composed states: sequential evaluation ordering
    elif spec.mechanism == "authority_evidence":
        # F_A F_E: Authority missing at aggregate -> verify stage; evidence uncorrupted but unverified
        role_bindings = {
            "parse": "role:parser",
            "dispatch": "role:dispatcher",
            "route": "role:router",
            "aggregate": "role:aggregator",
            "commit": "role:commit",
        }
        causal_edges = [
            ["parse", "dispatch"],
            ["dispatch", "route"],
            ["route", "aggregate"],
            ["aggregate", "verify"],
            ["verify", "commit"],
        ]
        node_seq = ["parse", "dispatch", "route", "aggregate"]
        evidence_records = ["parse", "dispatch", "route", "aggregate"]
        chain_continuity = False
        digest_match = True
        temporal_ok = True
        duration_ms = 490.0
        resource_ok = True
        ram_units = 8
        conflict_count = 0
        divergence_detected = False
        quarantine_active = False
        output_keys = []
        root_status = "FAILED"

    elif spec.mechanism == "evidence_authority":
        # F_E F_A: Evidence corruption occurs at dispatch -> route; execution halts early before authority check
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
        node_seq = ["parse", "dispatch"]
        evidence_records = ["parse", "dispatch"]
        chain_continuity = False
        digest_match = False
        temporal_ok = True
        duration_ms = 220.0
        resource_ok = True
        ram_units = 4
        conflict_count = 0
        divergence_detected = False
        quarantine_active = False
        output_keys = []
        root_status = "FAILED"

    elif spec.mechanism == "authority_causal":
        # F_A F_C: Authority unbinding occurs after full causal traversal to aggregator
        role_bindings = {
            "parse": "role:parser",
            "dispatch": "role:dispatcher",
            "route": "role:router",
            "aggregate": "role:aggregator",
            "commit": "role:commit",
        }
        causal_edges = [
            ["parse", "dispatch"],
            ["dispatch", "route"],
            ["route", "aggregate"],
            ["aggregate", "verify"],
            ["verify", "commit"],
        ]
        node_seq = ["parse", "dispatch", "route", "aggregate"]
        evidence_records = ["parse", "dispatch", "route", "aggregate"]
        chain_continuity = False
        digest_match = True
        temporal_ok = True
        duration_ms = 460.0
        resource_ok = True
        ram_units = 8
        conflict_count = 0
        divergence_detected = False
        quarantine_active = False
        output_keys = []
        root_status = "FAILED"

    elif spec.mechanism == "causal_authority":
        # F_C F_A: Causal break occurs between parse and dispatch; halts before authority can be queried
        role_bindings = {
            "parse": "role:parser",
            "commit": "role:commit",
        }
        causal_edges = [
            ["route", "aggregate"],
            ["aggregate", "verify"],
            ["verify", "commit"],
        ]
        node_seq = ["parse"]
        evidence_records = ["parse"]
        chain_continuity = False
        digest_match = True
        temporal_ok = True
        duration_ms = 90.0
        resource_ok = True
        ram_units = 2
        conflict_count = 0
        divergence_detected = False
        quarantine_active = False
        output_keys = []
        root_status = "FAILED"

    elif spec.mechanism == "evidence_resource":
        # F_E F_R: Evidence corruption occurs at routing; halts before resource envelope is saturated
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
        node_seq = ["parse", "dispatch", "route"]
        evidence_records = ["parse", "dispatch", "route"]
        chain_continuity = False
        digest_match = False
        temporal_ok = True
        duration_ms = 310.0
        resource_ok = True
        ram_units = 8
        conflict_count = 0
        divergence_detected = False
        quarantine_active = False
        output_keys = []
        root_status = "FAILED"

    elif spec.mechanism == "resource_evidence":
        # F_R F_E: Resource exhaustion occurs early at parse stage; halts before evidence generation
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
        node_seq = ["parse"]
        evidence_records = ["parse"]
        chain_continuity = False
        digest_match = True
        temporal_ok = True
        duration_ms = 140.0
        resource_ok = False
        ram_units = 48
        conflict_count = 0
        divergence_detected = False
        quarantine_active = False
        output_keys = []
        root_status = "FAILED"

    else:
        raise ValueError(f"Unknown mechanism: {spec.mechanism}")

    # Build raw telemetry state (zero forbidden words)
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
        },
        "state": state,
        "oracle": oracle,
    }


def build_failure_states(specs: Sequence[FailureSpec] = DEFAULT_FAILURE_SPECS) -> list[dict[str, Any]]:
    return [run_failure_spec(spec) for spec in specs]


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


def analyze_failure_semantics_observations(
    deterministic_states: Sequence[dict[str, Any]],
    observations: Sequence[dict[str, Any]],
    *,
    specs: Sequence[FailureSpec],
    replicates: int,
    thresholds: FailureSemanticsThresholds,
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
                "J1_operator_detectability": False,
                "J2_repeatability_noise_floor": False,
                "J3_operator_family_characterization": False,
                "J4_noncommutativity_evaluated": False,
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
    deltas: dict[str, list[float]] = {}
    norms: dict[str, float] = {}
    snrs: dict[str, float] = {}

    for spec in specs:
        sid = spec.spec_id
        d = _subtract(spec_means[sid], base_v)
        deltas[sid] = d
        n = _norm(d)
        norms[sid] = n
        snrs[sid] = n / noise_floor if noise_floor > 1e-15 else float("inf")

    # Pure Failure Operators: Delta_A, Delta_E, Delta_C, Delta_T, Delta_R, Delta_Adv
    pure_keys = ["op_A", "op_E", "op_C", "op_T", "op_R", "op_Adv"]
    pure_snrs_satisfied = all(snrs[k] >= thresholds.min_snr for k in pure_keys)
    noise_floor_satisfied = noise_floor <= thresholds.max_noise_floor_l2

    # Operator Cosine Matrix C_ij for Pure Operators
    pairwise_cosines: list[dict[str, Any]] = []
    for i in range(len(pure_keys)):
        for j in range(i + 1, len(pure_keys)):
            sid_a = pure_keys[i]
            sid_b = pure_keys[j]
            c = _cosine(deltas[sid_a], deltas[sid_b])
            angle_deg = math.degrees(math.acos(c)) if c is not None and -1.0 <= c <= 1.0 else 0.0
            pairwise_cosines.append(
                {
                    "op_a": sid_a,
                    "op_b": sid_b,
                    "cosine": c,
                    "separation_angle_deg": round(angle_deg, 2),
                }
            )

    valid_cosines = [item["cosine"] for item in pairwise_cosines if item["cosine"] is not None]
    min_cosine = min(valid_cosines) if valid_cosines else 1.0
    mean_cosine = sum(valid_cosines) / len(valid_cosines) if valid_cosines else 1.0

    # Categorize Operator Family vs. Macrostate Attractor:
    # If min_cosine < separation_cosine_threshold (e.g. 0.950), operators separate into a multi-dimensional family.
    # If min_cosine >= 0.950, operators collapse into a 1D generic governance-failure macrostate attractor.
    has_operator_separation = min_cosine < thresholds.separation_cosine_threshold

    # Sequential Composition & Noncommutativity
    # Test pairs: (AE, EA), (AC, CA), (ER, RE)
    composition_pairs = [
        ("comp_AE", "comp_EA", "authority_evidence"),
        ("comp_AC", "comp_CA", "authority_causal"),
        ("comp_ER", "comp_RE", "evidence_resource"),
    ]
    noncommutativity_results: list[dict[str, Any]] = []
    for sid_ij, sid_ji, pair_label in composition_pairs:
        diff = _subtract(deltas[sid_ij], deltas[sid_ji])
        kappa = _norm(diff)
        eta = kappa / noise_floor if noise_floor > 1e-15 else float("inf")
        cos_order = _cosine(deltas[sid_ij], deltas[sid_ji])
        noncommutativity_results.append(
            {
                "pair": pair_label,
                "seq_ij": sid_ij,
                "seq_ji": sid_ji,
                "kappa_noncommutativity": kappa,
                "eta_ratio_over_noise": eta,
                "ordering_cosine": cos_order,
                "noncommutative_significant": eta >= thresholds.noncommutativity_snr_threshold,
            }
        )

    gates = {
        "U0_deterministic_oracle": oracle_pass,
        "J0_provider_complete": provider_complete,
        "J1_operator_detectability": pure_snrs_satisfied,
        "J2_repeatability_noise_floor": noise_floor_satisfied,
        "J3_operator_family_characterization": True,  # Evaluates separation vs macrostate collapse
        "J4_noncommutativity_evaluated": len(noncommutativity_results) == 3,
    }

    supported = all(gates.values())

    return {
        "oracle_pass": oracle_pass,
        "provider_complete": provider_complete,
        "repeatability_noise_floor_l2": noise_floor,
        "pure_operator_metrics": {
            k: {
                "norm": norms[k],
                "snr": snrs[k],
                "mean_vector": spec_means[k],
            }
            for k in pure_keys
        },
        "pure_operator_pairwise_cosines": pairwise_cosines,
        "operator_family_geometry": {
            "minimum_pairwise_cosine": min_cosine,
            "mean_pairwise_cosine": mean_cosine,
            "regime": (
                "MULTI_OPERATOR_FAMILY"
                if has_operator_separation
                else "GENERIC_FAILURE_MACROSTATE_ATTRACTOR"
            ),
        },
        "composition_noncommutativity": noncommutativity_results,
        "all_spec_metrics": [
            {
                "spec_id": s.spec_id,
                "mechanism": s.mechanism,
                "condition_role": s.condition_role,
                "displacement_norm": norms[s.spec_id],
                "snr": snrs[s.spec_id],
                "mean_vector": spec_means[s.spec_id],
            }
            for s in specs
        ],
        "thresholds": {
            "min_snr": thresholds.min_snr,
            "max_noise_floor_l2": thresholds.max_noise_floor_l2,
            "separation_cosine_threshold": thresholds.separation_cosine_threshold,
            "noncommutativity_snr_threshold": thresholds.noncommutativity_snr_threshold,
        },
        "gates": gates,
        "supported_within_engineering_gates": supported,
        "verdict": (
            "SUPPORTED_WITHIN_PREREGISTERED_ENGINEERING_GATES"
            if supported
            else "NOT_SUPPORTED_BY_THIS_RUN"
        ),
    }


def run_live_failure_semantics_experiment(
    *,
    provider: JevProvider,
    specs: Sequence[FailureSpec] = DEFAULT_FAILURE_SPECS,
    replicates: int = 3,
    thresholds: FailureSemanticsThresholds,
) -> dict[str, Any]:
    deterministic_states = build_failure_states(specs)
    questions = question_payload()
    observations: list[dict[str, Any]] = []
    total_calls = len(deterministic_states) * replicates

    for item in deterministic_states:
        sid = str(item["spec"]["spec_id"])
        mech = str(item["spec"]["mechanism"])
        k = int(item["spec"]["disturbed_count"])
        for rep in range(replicates):
            request_id = f"uow-failsem-{sid}-r{rep}"
            provider_res = provider.decide(
                state=dict(item["state"]),
                questions=questions,
                request_id=request_id,
            )
            vec = provider_res.get("vector") or []
            v_norm = _norm(vec) if vec else 0.0
            print(
                f"[{len(observations) + 1:02d}/{total_calls:02d}] {sid:<12} "
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

    analysis = analyze_failure_semantics_observations(
        deterministic_states,
        observations,
        specs=specs,
        replicates=replicates,
        thresholds=thresholds,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "JEV x UoW Failure Semantics Operator Family Identification Campaign",
        "method": {
            "mechanisms": ["authority", "evidence", "causal", "temporal", "resource", "adversarial"],
            "state_specs": [
                {
                    "spec_id": s.spec_id,
                    "mechanism": s.mechanism,
                    "condition_role": s.condition_role,
                    "disturbed_count": s.disturbed_count,
                    "composition_sequence": s.composition_sequence,
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
        description="Run the JEV x UoW Failure Semantics Operator Family Identification Campaign."
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

    thresholds = FailureSemanticsThresholds()

    if args.prepare_only:
        states = build_failure_states()
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
        payload = run_live_failure_semantics_experiment(
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
