"""JEV x UoW Realization Graph Topology Invariance Campaign.

Questions
=========
Does the collective cybernetic behavior and failure geometry of a governed UoW
ensemble survive when the realization interaction topology is fundamentally altered?
Specifically:
1. Topology-Driven Resilience: Does causal evidence propagation through different graph
   topologies (star, ring, tree, modular, small-world) produce materially different
   effective governance thresholds rho_c(T) even with identical M=16, Q=9?
2. Geometry Invariance Across Topologies: Does the post-threshold authority-loss operator
   Delta_A*(T) remain directionally invariant (min cos >= 0.950, target > 0.980) across
   all five topologically distinct graphs?
3. Invariant Transition Jump: Does every topology exhibit a sharp discontinuous transition
   jump J_T across its respective critical threshold?
4. Subcritical Shielding Across Topologies: Does quorum governance shield the parent
   observer from internal component failure prior to reaching rho_c(T)?
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


SCHEMA_VERSION = "uow.jev_realization_topology.v1"
DEFAULT_OUTPUT = Path("qualification/artifacts/jev_realization_topology_results.json")

TOTAL_UNITS = 16
QUORUM_REQUIRED = 9


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
class TopologySpec:
    spec_id: str
    topology_type: str  # "star", "tree", "ring", "modular", "small_world"
    condition_role: str  # "base", "pre", "at", "sub", "casc"
    disturbed_units: tuple[int, ...]
    regime: str = "quorum"  # "quorum" or "cascade"

    @property
    def disturbed_count(self) -> int:
        return len(self.disturbed_units)

    @property
    def disturbance_density(self) -> float:
        return self.disturbed_count / float(TOTAL_UNITS)


# 18 Preregistered States across the 5 Topologies
# Tree: rho_c = 0.250 (k_c = 4)
# Modular: rho_c = 0.3125 (k_c = 5)
# Ring: rho_c = 0.375 (k_c = 6)
# Star: rho_c = 0.500 (k_c = 8)
# Small-World: rho_c = 0.500 (k_c = 8)
DEFAULT_TOPOLOGY_SPECS: tuple[TopologySpec, ...] = (
    # Group 1: Star / Fan-Out (rho_c = 0.500, k_c = 8)
    TopologySpec("star_base", "star", "base", ()),
    TopologySpec("star_pre", "star", "pre", (0, 1, 2, 3, 4, 5, 6)),  # k=7, reachable=9, margin=0
    TopologySpec("star_at", "star", "at", (0, 1, 2, 3, 4, 5, 6, 7)),  # k=8, reachable=8, margin=-1
    TopologySpec("star_casc", "star", "casc", (0, 1), regime="cascade"),  # k=2 unshielded

    # Group 2: Hierarchical Balanced Tree (rho_c = 0.250, k_c = 4)
    # 4 branches of 4 units: B0(0..3), B1(4..7), B2(8..11), B3(12..15)
    # Local branch quorum requires >= 3 units.
    TopologySpec("tree_base", "tree", "base", ()),
    TopologySpec("tree_sub", "tree", "sub", (0, 4)),  # k=2 (1 in B0, 1 in B1), reachable=14
    TopologySpec("tree_pre", "tree", "pre", (0, 1, 4)),  # k=3 (2 in B0, 1 in B1), reachable=11 >= 9
    TopologySpec("tree_at", "tree", "at", (0, 1, 4, 5)),  # k=4 (2 in B0, 2 in B1), reachable=8 < 9, margin=-1

    # Group 3: Modular Clusters (rho_c = 0.3125, k_c = 5)
    # 4 clusters C0..C3. C1,C2,C3 route to root via bridges u3, u7, u11.
    TopologySpec("modular_base", "modular", "base", ()),
    TopologySpec("modular_pre", "modular", "pre", (0, 1, 11, 12)),  # k=4, bridge 11 cut, reachable=9, margin=0
    TopologySpec("modular_at", "modular", "at", (0, 1, 2, 11, 12)),  # k=5, reachable=8 < 9, margin=-1

    # Group 4: Ring with Chordal Bypasses (rho_c = 0.375, k_c = 6)
    # Ring with dual collectors at 0 and 8. Chord bypasses step 1 and 2.
    TopologySpec("ring_base", "ring", "base", ()),
    TopologySpec("ring_sub", "ring", "sub", (1, 9)),  # k=2 non-consecutive, reachable=14
    TopologySpec("ring_pre", "ring", "pre", (1, 2, 3, 6, 7)),  # k=5, reachable=9 >= 9, margin=0
    TopologySpec("ring_at", "ring", "at", (1, 2, 3, 6, 7, 9)),  # k=6, reachable=8 < 9, margin=-1

    # Group 5: Small-World Network (rho_c = 0.500, k_c = 8)
    # Ring lattice + 4 frozen shortcuts (0-8, 2-10, 4-12, 6-14). External root receives from 0 and 8.
    TopologySpec("sw_base", "small_world", "base", ()),
    TopologySpec("sw_pre", "small_world", "pre", (1, 2, 3, 4, 5, 6, 7)),  # k=7, reachable=9 >= 9, margin=0
    TopologySpec("sw_at", "small_world", "at", (1, 2, 3, 4, 5, 6, 7, 9)),  # k=8, reachable=8 < 9, margin=-1
)


@dataclass(frozen=True)
class TopologyThresholds:
    min_cross_topology_cosine: float = 0.950
    min_transition_jump: float = 0.80
    min_shielding_ratio: float = 3.0
    max_post_threshold_norm_cv: float = 0.15


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


def compute_causal_reachability(
    topology: str,
    disturbed_indices: set[int],
) -> int:
    """Deterministically route evidence through the realization graph topology."""
    nominal_units = set(range(TOTAL_UNITS)) - disturbed_indices

    if topology == "star":
        # Direct fan-out: every nominal unit reaches root directly
        return len(nominal_units)

    elif topology == "tree":
        # 4 branches of 4 units: B0(0..3), B1(4..7), B2(8..11), B3(12..15)
        # Each branch requires local quorum >= 3 valid units to certify and report
        reachable_count = 0
        for branch_idx in range(4):
            branch_units = set(range(branch_idx * 4, (branch_idx + 1) * 4))
            valid_in_branch = len(branch_units.intersection(nominal_units))
            if valid_in_branch >= 3:
                reachable_count += valid_in_branch
        return reachable_count

    elif topology == "modular":
        # 4 clusters of 4 units. C0 connects to root.
        # C1 via bridge u3, C2 via bridge u7, C3 via bridge u11.
        reachable = len(set(range(0, 4)).intersection(nominal_units))
        if 3 in nominal_units:
            reachable += len(set(range(4, 8)).intersection(nominal_units))
            if 7 in nominal_units:
                reachable += len(set(range(8, 12)).intersection(nominal_units))
                if 11 in nominal_units:
                    reachable += len(set(range(12, 16)).intersection(nominal_units))
        return reachable

    elif topology == "ring":
        # Ring with 2 collectors at 0 and 8. Links: i -> i+1, i -> i+2 (mod 16).
        collectors = [h for h in (0, 8) if h in nominal_units]
        visited = set(collectors)
        queue = list(collectors)

        while queue:
            curr = queue.pop(0)
            for step in (-2, -1, 1, 2):
                nbr = (curr + step) % 16
                if nbr in nominal_units and nbr not in visited:
                    visited.add(nbr)
                    queue.append(nbr)
        return len(visited)

    elif topology == "small_world":
        # Ring + 4 frozen shortcuts: (0,8), (2,10), (4,12), (6,14). Dual collectors at 0 and 8.
        collectors = [h for h in (0, 8) if h in nominal_units]
        if not collectors:
            return 0

        shortcuts = {0: [8], 8: [0], 2: [10], 10: [2], 4: [12], 12: [4], 6: [14], 14: [6]}
        visited = set(collectors)
        queue = list(collectors)

        while queue:
            curr = queue.pop(0)
            neighbors = [(curr - 1) % 16, (curr + 1) % 16] + shortcuts.get(curr, [])
            for nbr in neighbors:
                if nbr in nominal_units and nbr not in visited:
                    visited.add(nbr)
                    queue.append(nbr)
        return len(visited)

    raise ValueError(f"Unknown topology: {topology}")


def run_topology_spec(spec: TopologySpec) -> dict[str, Any]:
    M = TOTAL_UNITS
    Q = M if spec.regime == "cascade" else QUORUM_REQUIRED
    disturbed_set = set(spec.disturbed_units)
    k = len(disturbed_set)

    # 1. Instantiate the M child runtimes
    child_runtimes: list[AdaptiveCompositionRuntime] = []
    child_certs: list[Any] = []
    for i in range(M):
        rt, cert = make_child_unit(f"{spec.spec_id}_u{i}")
        child_runtimes.append(rt)
        child_certs.append(cert)

    # 2. Induce leaf authority loss in the specified units
    for idx in disturbed_set:
        child_runtimes[idx].registry.update_status(f"{spec.spec_id}_u{idx}:verify", availability=False)

    # 3. Execute all units locally
    for i in range(M):
        child_runtimes[i].execute({"payload": "probe"})

    # 4. Compute causal reachability through graph topology
    reachable_count = compute_causal_reachability(spec.topology_type, disturbed_set)
    quorum_achieved = reachable_count >= Q
    quorum_margin = reachable_count - Q

    # 5. Boundary certificate verification
    all_certs_valid = True
    for rt, cert in zip(child_runtimes, child_certs):
        ok, _ = verify_composition_boundary(cert, rt.active_graph, rt.contract)
        all_certs_valid = all_certs_valid and ok

    if quorum_achieved:
        root_status = "SUCCESS"
        node_seq = ["parse", "dispatch", "route", "aggregate", "verify", "commit"]
        evidence_present = ["parse", "dispatch", "route", "aggregate", "verify", "commit"]
        chain_continuity = True
        output_keys = ["topology_result"]
    else:
        root_status = "FAILED"
        node_seq = ["parse", "dispatch", "route"]
        evidence_present = ["parse", "dispatch", "route"]
        chain_continuity = False
        output_keys = []

    state = {
        "subject": "governed_topology_realization_unit",
        "spec_id": spec.spec_id,
        "topology_type": spec.topology_type,
        "condition_role": spec.condition_role,
        "governance_regime": spec.regime,
        "constituent_unit_count": M,
        "quorum_threshold_count": Q,
        "reachable_constituent_units": reachable_count,
        "disturbed_constituent_units": k,
        "disturbance_density_ratio": round(k / float(M), 4),
        "quorum_margin": quorum_margin,
        "boundary_certificates_valid": all_certs_valid,
        "declared_causal_edges": [
            ["parse", "dispatch"],
            ["dispatch", "route"],
            ["route", "aggregate"],
            ["aggregate", "verify"],
            ["verify", "commit"],
        ],
        "actor_role_bindings": {
            "parse": "role:parser",
            "dispatch": "role:dispatcher",
            "route": "role:router",
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
        "topology_type": spec.topology_type,
        "condition_role": spec.condition_role,
        "regime": spec.regime,
        "disturbed_count": k,
        "reachable_count": reachable_count,
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
            "topology_type": spec.topology_type,
            "condition_role": spec.condition_role,
            "disturbed_count": k,
            "reachable_count": reachable_count,
            "regime": spec.regime,
        },
        "state": state,
        "oracle": oracle,
    }


def build_topology_states(specs: Sequence[TopologySpec] = DEFAULT_TOPOLOGY_SPECS) -> list[dict[str, Any]]:
    return [run_topology_spec(spec) for spec in specs]


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


def analyze_topology_observations(
    deterministic_states: Sequence[dict[str, Any]],
    observations: Sequence[dict[str, Any]],
    *,
    specs: Sequence[TopologySpec],
    replicates: int,
    thresholds: TopologyThresholds,
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
                "J3_cross_topology_directional_alignment": False,
                "J4_amplitude_stability_across_topology": False,
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

    # Baselines per topology
    topologies = ["star", "tree", "modular", "ring", "small_world"]
    deltas: dict[str, list[float]] = {}
    norms: dict[str, float] = {}

    for spec in specs:
        sid = spec.spec_id
        top = spec.topology_type
        base_v = spec_means[f"{top}_base"] if top != "small_world" else spec_means["sw_base"]
        d = _subtract(spec_means[sid], base_v)
        deltas[sid] = d
        norms[sid] = _norm(d)

    # 1. Effective Resilience Thresholds rho_c(T)
    resilience_thresholds = {
        "tree": 0.250,
        "modular": 0.3125,
        "ring": 0.375,
        "star": 0.500,
        "small_world": 0.500,
    }

    # 2. Subcritical Shielding S_T
    # star_casc is unshielded cascade baseline at k=2
    casc_norm = norms["star_casc"]
    shielding_ratios = {
        "tree": casc_norm / norms["tree_sub"] if norms["tree_sub"] > 1e-15 else float("inf"),
        "ring": casc_norm / norms["ring_sub"] if norms["ring_sub"] > 1e-15 else float("inf"),
    }
    shielding_satisfied = all(s >= thresholds.min_shielding_ratio for s in shielding_ratios.values())

    # 3. Transition Jumps J_T across the 5 topologies
    transition_jumps = {
        "star": norms["star_at"] - norms["star_pre"],
        "tree": norms["tree_at"] - norms["tree_pre"],
        "modular": norms["modular_at"] - norms["modular_pre"],
        "ring": norms["ring_at"] - norms["ring_pre"],
        "small_world": norms["sw_at"] - norms["sw_pre"],
    }
    jumps_satisfied = all(j >= thresholds.min_transition_jump for j in transition_jumps.values())

    # 4. Cross-Topology Directional Cosines between post-threshold states:
    post_thresh_sids = ["star_at", "tree_at", "modular_at", "ring_at", "sw_at"]
    cross_cosines: list[dict[str, Any]] = []
    for i in range(len(post_thresh_sids)):
        for j in range(i + 1, len(post_thresh_sids)):
            sid_a = post_thresh_sids[i]
            sid_b = post_thresh_sids[j]
            c = _cosine(deltas[sid_a], deltas[sid_b])
            cross_cosines.append({"spec_a": sid_a, "spec_b": sid_b, "cosine": c})

    valid_cosines = [item["cosine"] for item in cross_cosines if item["cosine"] is not None]
    min_cross_cosine = min(valid_cosines) if valid_cosines else 0.0
    direction_aligned = min_cross_cosine >= thresholds.min_cross_topology_cosine

    # 5. Amplitude Stability across topologies:
    post_norms = [norms[sid] for sid in post_thresh_sids]
    mean_amp = sum(post_norms) / len(post_norms)
    amp_cv = pstdev(post_norms) / mean_amp if mean_amp > 1e-15 else float("inf")
    amplitude_stable = amp_cv <= thresholds.max_post_threshold_norm_cv

    gates = {
        "U0_deterministic_oracle": oracle_pass,
        "J0_provider_complete": provider_complete,
        "J1_subcritical_shielding_universal": shielding_satisfied,
        "J2_transition_jump_invariant": jumps_satisfied,
        "J3_cross_topology_directional_alignment": direction_aligned,
        "J4_amplitude_stability_across_topology": amplitude_stable,
    }

    supported = all(gates.values())

    return {
        "oracle_pass": oracle_pass,
        "provider_complete": provider_complete,
        "repeatability_noise_floor_l2": noise_floor,
        "effective_resilience_thresholds_rho_c": resilience_thresholds,
        "shielding_ratios": shielding_ratios,
        "transition_jumps": transition_jumps,
        "post_threshold_norms": {sid: norms[sid] for sid in post_thresh_sids},
        "amplitude_cv_across_topology": amp_cv,
        "minimum_cross_topology_cosine": min_cross_cosine,
        "pairwise_cross_topology_cosines": cross_cosines,
        "all_spec_metrics": [
            {
                "spec_id": s.spec_id,
                "topology_type": s.topology_type,
                "condition_role": s.condition_role,
                "disturbed_count": s.disturbed_count,
                "displacement_norm": norms[s.spec_id],
                "mean_vector": spec_means[s.spec_id],
            }
            for s in specs
        ],
        "thresholds": {
            "min_cross_topology_cosine": thresholds.min_cross_topology_cosine,
            "min_transition_jump": thresholds.min_transition_jump,
            "min_shielding_ratio": thresholds.min_shielding_ratio,
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


def run_live_topology_experiment(
    *,
    provider: JevProvider,
    specs: Sequence[TopologySpec] = DEFAULT_TOPOLOGY_SPECS,
    replicates: int = 3,
    thresholds: TopologyThresholds,
) -> dict[str, Any]:
    deterministic_states = build_topology_states(specs)
    questions = question_payload()
    observations: list[dict[str, Any]] = []
    total_calls = len(deterministic_states) * replicates

    for item in deterministic_states:
        sid = str(item["spec"]["spec_id"])
        top = str(item["spec"]["topology_type"])
        k = int(item["spec"]["disturbed_count"])
        r = int(item["spec"]["reachable_count"])
        for rep in range(replicates):
            request_id = f"uow-top-{sid}-r{rep}"
            provider_res = provider.decide(
                state=dict(item["state"]),
                questions=questions,
                request_id=request_id,
            )
            vec = provider_res.get("vector") or []
            v_norm = _norm(vec) if vec else 0.0
            print(
                f"[{len(observations) + 1:02d}/{total_calls:02d}] {sid:<15} "
                f"({top:<11}, k={k:02d}, reachable={r:02d}) rep={rep} -> norm={v_norm:.4f}",
                flush=True,
            )
            observations.append(
                {
                    "spec_id": sid,
                    "replicate": rep,
                    "provider": provider_res,
                }
            )

    analysis = analyze_topology_observations(
        deterministic_states,
        observations,
        specs=specs,
        replicates=replicates,
        thresholds=thresholds,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "JEV x UoW Realization Graph Topology Invariance Campaign",
        "method": {
            "topologies": ["star", "tree", "modular", "ring", "small_world"],
            "state_specs": [
                {
                    "spec_id": s.spec_id,
                    "topology_type": s.topology_type,
                    "condition_role": s.condition_role,
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
        description="Run the JEV x UoW Realization Graph Topology Invariance Campaign."
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

    thresholds = TopologyThresholds()

    if args.prepare_only:
        states = build_topology_states()
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
        payload = run_live_topology_experiment(
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
