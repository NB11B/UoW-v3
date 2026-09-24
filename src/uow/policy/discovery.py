"""Bounded Discovery Engine.

Generates candidate computational graphs G_c based on available capabilities and workload requirements.
ARCHITECTURAL INVARIANT: Discovery produces candidates, NEVER authority.
Only the QualificationEngine can certify and promote candidates into operational policy.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    RealizationGraph,
    RealizationStage,
    ResourceCapability,
    WorkRequirement,
    WorldConditions,
)


@dataclass(frozen=True)
class DiscoveryCandidate:
    """An uncertified candidate realization graph proposed by the discovery engine."""
    candidate_id: str
    requirement: WorkRequirement
    graph: RealizationGraph
    estimated_energy_wh: float
    estimated_latency_ms: float
    rationale: str


class DiscoveryEngine:
    """Explores alternative computational graph realizations within bounded operating parameters."""

    # Nominal capability cost heuristics (energy Wh per scale unit, latency ms per scale unit)
    CAPABILITY_HEURISTICS = {
        "preprocess": {
            ResourceCapability.LOW_POWER_ACCELERATOR: (0.00000045, 0.025),
            ResourceCapability.GENERAL_COMPUTE: (0.00000085, 0.038),
            ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR: (0.00000320, 0.080),
        },
        "dense_compute": {
            ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR: (0.00000180, 0.052),
            ResourceCapability.LOW_POWER_ACCELERATOR: (0.00000850, 0.350),
            ResourceCapability.GENERAL_COMPUTE: (0.00000720, 0.280),
        },
        "reduce": {
            ResourceCapability.GENERAL_COMPUTE: (0.00000055, 0.018),
            ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR: (0.00000240, 0.065),
            ResourceCapability.LOW_POWER_ACCELERATOR: (0.00000310, 0.120),
        },
        "verify": {
            ResourceCapability.DETERMINISTIC_AUTHORITY: (0.00000003, 0.015),
            ResourceCapability.GENERAL_COMPUTE: (0.00000040, 0.008),
            ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR: (0.00000280, 0.040),
        },
    }

    def propose_candidates(
        self,
        requirement: WorkRequirement,
        conditions: WorldConditions,
    ) -> List[DiscoveryCandidate]:
        """Propose bounded set of candidate realization graphs matching the required capabilities."""
        avail = conditions.available_capabilities
        scale = max(1, requirement.scale)
        candidates = []

        # Candidate 1: Monolithic fallback on whatever primary compute capability exists
        if ResourceCapability.GENERAL_COMPUTE in avail:
            g_mono = self._build_graph(
                graph_id=f"G_MONO_CPU_{requirement.workload_class}",
                requirement=requirement,
                prep_cap=ResourceCapability.GENERAL_COMPUTE,
                comp_cap=ResourceCapability.GENERAL_COMPUTE,
                red_cap=ResourceCapability.GENERAL_COMPUTE,
                ver_cap=ResourceCapability.GENERAL_COMPUTE,
                scale=scale,
                transfer_energy=0.0,
                transfer_latency=0.0,
            )
            candidates.append(DiscoveryCandidate(
                candidate_id="cand_monolithic_general_compute",
                requirement=requirement,
                graph=g_mono,
                estimated_energy_wh=g_mono.total_energy_wh,
                estimated_latency_ms=g_mono.total_latency_ms,
                rationale="Monolithic baseline utilizing general-purpose compute exclusively",
            ))

        # Candidate 2: High-throughput accelerator monolithic
        if ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR in avail and conditions.power_budget_w >= 100.0:
            g_accel = self._build_graph(
                graph_id=f"G_MONO_ACCEL_{requirement.workload_class}",
                requirement=requirement,
                prep_cap=ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR,
                comp_cap=ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR,
                red_cap=ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR,
                ver_cap=ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR,
                scale=scale,
                transfer_energy=0.0,
                transfer_latency=0.0,
            )
            candidates.append(DiscoveryCandidate(
                candidate_id="cand_monolithic_high_throughput",
                requirement=requirement,
                graph=g_accel,
                estimated_energy_wh=g_accel.total_energy_wh,
                estimated_latency_ms=g_accel.total_latency_ms,
                rationale="Monolithic acceleration utilizing high-throughput accelerator across all stages",
            ))

        # Candidate 3: Heterogeneous Optimal Composition (Hypothesis H4 Hybrid)
        has_npu = ResourceCapability.LOW_POWER_ACCELERATOR in avail
        has_gpu = ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR in avail and conditions.power_budget_w >= 45.0
        has_cpu = ResourceCapability.GENERAL_COMPUTE in avail
        has_mcu = ResourceCapability.DETERMINISTIC_AUTHORITY in avail

        if has_npu and has_gpu and has_cpu and has_mcu:
            # Transfer overhead for inter-device interconnect
            transfer_e = 0.000010 * (scale / 100.0)
            transfer_l = 0.5 * (scale / 100.0)
            g_opt = self._build_graph(
                graph_id=f"G_HETERO_OPTIMAL_{requirement.workload_class}",
                requirement=requirement,
                prep_cap=ResourceCapability.LOW_POWER_ACCELERATOR,
                comp_cap=ResourceCapability.HIGH_THROUGHPUT_ACCELERATOR,
                red_cap=ResourceCapability.GENERAL_COMPUTE,
                ver_cap=ResourceCapability.DETERMINISTIC_AUTHORITY,
                scale=scale,
                transfer_energy=transfer_e,
                transfer_latency=transfer_l,
            )
            candidates.append(DiscoveryCandidate(
                candidate_id="cand_heterogeneous_optimal",
                requirement=requirement,
                graph=g_opt,
                estimated_energy_wh=g_opt.total_energy_wh,
                estimated_latency_ms=g_opt.total_latency_ms,
                rationale="Heterogeneous hybrid matching each stage to its capability-optimal resource",
            ))

        return candidates

    def _build_graph(
        self,
        graph_id: str,
        requirement: WorkRequirement,
        prep_cap: ResourceCapability,
        comp_cap: ResourceCapability,
        red_cap: ResourceCapability,
        ver_cap: ResourceCapability,
        scale: int,
        transfer_energy: float,
        transfer_latency: float,
    ) -> RealizationGraph:
        prep_e, prep_l = self.CAPABILITY_HEURISTICS["preprocess"][prep_cap]
        comp_e, comp_l = self.CAPABILITY_HEURISTICS["dense_compute"][comp_cap]
        red_e, red_l = self.CAPABILITY_HEURISTICS["reduce"][red_cap]
        ver_e, ver_l = self.CAPABILITY_HEURISTICS["verify"][ver_cap]

        stages = (
            RealizationStage("preprocess", prep_cap, prep_e * scale, prep_l * scale, ()),
            RealizationStage("dense_compute", comp_cap, comp_e * scale, comp_l * scale, ("preprocess",)),
            RealizationStage("reduce", red_cap, red_e * scale, red_l * scale, ("dense_compute",)),
            RealizationStage("verify", ver_cap, ver_e * scale, ver_l * scale, ("reduce",)),
        )

        return RealizationGraph(
            graph_id=graph_id,
            stages=stages,
            inter_stage_transfer_energy_wh=transfer_energy,
            inter_stage_transfer_latency_ms=transfer_latency,
            meaning_digest=requirement.canonical_meaning_digest,
            is_valid=True,
        )
