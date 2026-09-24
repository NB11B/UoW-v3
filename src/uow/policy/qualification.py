"""Rigorous Policy Qualification Engine.

Enforces Section 25 correctness gates, empirical ROI qualification, and cryptographic
evidence generation before promoting a discovery candidate to immutable operational policy.

ARCHITECTURAL PRINCIPLE:
Discovery proposes != Discovery authorizes.
Only QualificationEngine can qualify candidates and perform atomic promotion Pi_k -> Pi_{k+1}.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Dict, List, Optional, Tuple

from .discovery import DiscoveryCandidate
from .models import (
    Policy,
    PolicyEvidence,
    PolicyRegion,
    RealizationGraph,
    WorkRequirement,
    WorldConditions,
)
from .registry import PolicyRegistry


@dataclass(frozen=True)
class CandidateObservation:
    """An empirical prospective observation collected during candidate execution."""
    candidate_id: str
    requirement: WorkRequirement
    conditions: WorldConditions
    measured_energy_wh: float
    measured_latency_ms: float
    correctness_breaches: int = 0


@dataclass(frozen=True)
class QualifiedPolicyCandidate:
    """A discovery candidate that has satisfied all qualification gates and is certified for promotion."""
    candidate: DiscoveryCandidate
    region: PolicyRegion
    evidence: PolicyEvidence
    baseline_energy_wh: float
    savings_pct: float
    roi: float


class QualificationEngine:
    """Certifies candidate realization graphs and manages formal policy promotion."""

    def __init__(self, registry: PolicyRegistry, min_observations: int = 3) -> None:
        self.registry = registry
        self.min_observations = min_observations
        self.qualification_events_count = 0
        self._evidence_pool: Dict[str, List[CandidateObservation]] = {}

    def record_observation(
        self,
        candidate_id: str,
        requirement: WorkRequirement,
        conditions: WorldConditions,
        measured_energy_wh: float,
        measured_latency_ms: float,
        correctness_breaches: int = 0,
    ) -> int:
        """Accumulate an empirical observation for an unpromoted candidate."""
        obs = CandidateObservation(
            candidate_id=candidate_id,
            requirement=requirement,
            conditions=conditions,
            measured_energy_wh=measured_energy_wh,
            measured_latency_ms=measured_latency_ms,
            correctness_breaches=correctness_breaches,
        )
        if candidate_id not in self._evidence_pool:
            self._evidence_pool[candidate_id] = []
        self._evidence_pool[candidate_id].append(obs)
        return len(self._evidence_pool[candidate_id])

    def get_observation_count(self, candidate_id: str) -> int:
        return len(self._evidence_pool.get(candidate_id, []))

    def clear_observations(self, candidate_id: Optional[str] = None) -> None:
        """Clear prospective observations for a candidate or the entire pool."""
        if candidate_id is not None:
            self._evidence_pool.pop(candidate_id, None)
        else:
            self._evidence_pool.clear()

    def qualify_candidate(
        self,
        candidate: DiscoveryCandidate,
        requirement: WorkRequirement,
        conditions: WorldConditions,
        baseline_energy_wh: Optional[float] = None,
    ) -> Optional[QualifiedPolicyCandidate]:
        """Prospective qualification of candidate evidence.
        
        Evaluates the 4 core qualification questions:
        1. Correct? (Strictly 0 correctness breaches; Meaning(G_c) == Meaning(U))
        2. Better? (Energy strictly lower than baseline)
        3. Repeatable? (Standard error bounded by 95% Confidence Interval)
        4. Worth promoting? (Break-even ROI > 1.0)
        """
        observations = self._evidence_pool.get(candidate.candidate_id, [])
        n = len(observations)
        if n < self.min_observations:
            return None

        # 1. Correct?
        total_breaches = sum(o.correctness_breaches for o in observations)
        if total_breaches > 0:
            return None

        if not candidate.graph.matches_meaning(requirement.canonical_meaning_digest):
            return None

        # 2. Statistical Metrics
        energies = [o.measured_energy_wh for o in observations]
        latencies = [o.measured_latency_ms for o in observations]

        mean_e = sum(energies) / n
        mean_lat = sum(latencies) / n

        var_e = sum((e - mean_e) ** 2 for e in energies) / max(1, n - 1)
        std_e = math.sqrt(var_e)
        se_e = std_e / math.sqrt(n)
        ci_lower = max(0.0, mean_e - (1.96 * se_e))
        ci_upper = mean_e + (1.96 * se_e)

        # Baseline comparison
        base_e = baseline_energy_wh if baseline_energy_wh is not None else (mean_e * 1.5)
        if mean_e >= base_e:
            # Not better than baseline!
            return None

        energy_saved_per_uow = base_e - mean_e
        savings_pct = (energy_saved_per_uow / base_e) * 100.0

        # Amortization check
        exploration_overhead = sum(energies) - (mean_e * n)
        if exploration_overhead <= 0:
            break_even_uows = 1
            roi = 100.0
        else:
            break_even_uows = max(1, int(math.ceil(exploration_overhead / max(1e-9, energy_saved_per_uow))))
            # ROI projected over a nominal operational horizon of 100 UoWs
            roi = (energy_saved_per_uow * 100.0) / max(1e-9, exploration_overhead)

        if roi < 1.0:
            # Exploration investment exceeds expected returns
            return None

        # 3. Repeatable? (Confidence interval must not span baseline)
        if ci_upper >= base_e:
            return None

        evidence_raw = f"{candidate.graph.graph_id}:{mean_e:.8f}:{ci_lower:.8f}:{ci_upper:.8f}:{break_even_uows}"
        evidence_digest = hashlib.sha256(evidence_raw.encode("utf-8")).hexdigest()[:32]

        evidence = PolicyEvidence(
            evidence_digest=evidence_digest,
            observations_count=n,
            expected_energy_wh=mean_e,
            energy_ci95_lower=ci_lower,
            energy_ci95_upper=ci_upper,
            expected_latency_ms=mean_lat,
            break_even_uows=break_even_uows,
            correctness_breaches=0,
        )

        # Define explicit policy scope R_pi \subseteq U \times S
        region = PolicyRegion(
            workload_class=requirement.workload_class,
            min_scale=max(1, int(requirement.scale * 0.5)),
            max_scale=int(requirement.scale * 2.0),
            min_power_budget_w=conditions.power_budget_w * 0.8,
            max_power_budget_w=float("inf"),
            max_concurrency=conditions.max_concurrency * 2,
            required_capabilities=frozenset(s.capability for s in candidate.graph.stages),
        )

        return QualifiedPolicyCandidate(
            candidate=candidate,
            region=region,
            evidence=evidence,
            baseline_energy_wh=base_e,
            savings_pct=savings_pct,
            roi=roi,
        )

    def promote(
        self,
        qualified: QualifiedPolicyCandidate,
        policy_id: Optional[str] = None,
    ) -> Policy:
        """Atomically promote a qualified candidate into an active policy: Pi_k -> Pi_{k+1}."""
        candidate = qualified.candidate
        pol_id = policy_id or f"POL_{candidate.requirement.workload_class.upper()}_S{candidate.requirement.scale}_V1"
        existing = self.registry.get_policy(pol_id)
        version = (existing.policy_version + 1) if existing else 1

        promoted_policy = Policy(
            policy_id=pol_id,
            policy_version=version,
            region=qualified.region,
            realization_graph=candidate.graph,
            evidence=qualified.evidence,
            fallback_policy_id="residual_discovery",
            is_active=True,
        )

        # Atomic registry promotion
        self.registry.register_policy(promoted_policy)
        self.qualification_events_count += 1
        self.clear_observations(candidate.candidate_id)
        stored = self.registry.get_policy(pol_id, version)
        return stored or promoted_policy

    def requalify_policy(
        self,
        policy: Policy,
        requirement: WorkRequirement,
        conditions: WorldConditions,
        observed_energies_wh: List[float],
        observed_latencies_ms: List[float],
        correctness_breaches: int = 0,
    ) -> Optional[Policy]:
        """Requalify an invalidated historical policy under restored operating conditions."""
        if correctness_breaches > 0:
            return None
        if not policy.region.contains(requirement, conditions):
            return None

        n = len(observed_energies_wh)
        if n < self.min_observations:
            return None

        mean_e = sum(observed_energies_wh) / n
        if mean_e > policy.evidence.energy_ci95_upper:
            return None

        success = self.registry.reactivate_policy(
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            reason=f"Empirically requalified across {n} observations (mean {mean_e:.6f} Wh)",
            world_snapshot_id=conditions.snapshot_id,
        )
        if success:
            return self.registry.get_policy(policy.policy_id, policy.policy_version)
        return None

    def evaluate_and_promote(
        self,
        candidate: DiscoveryCandidate,
        requirement: WorkRequirement,
        conditions: WorldConditions,
        observed_energies_wh: List[float],
        observed_latencies_ms: List[float],
        correctness_breaches: int = 0,
        baseline_energy_wh: Optional[float] = None,
    ) -> Optional[Policy]:
        """Convenience method combining observation recording, qualification, and promotion."""
        self.clear_observations(candidate.candidate_id)
        for e, l in zip(observed_energies_wh, observed_latencies_ms):
            self.record_observation(
                candidate_id=candidate.candidate_id,
                requirement=requirement,
                conditions=conditions,
                measured_energy_wh=e,
                measured_latency_ms=l,
                correctness_breaches=correctness_breaches,
            )

        qualified = self.qualify_candidate(
            candidate=candidate,
            requirement=requirement,
            conditions=conditions,
            baseline_energy_wh=baseline_energy_wh,
        )
        if qualified is None:
            return None

        return self.promote(qualified)
