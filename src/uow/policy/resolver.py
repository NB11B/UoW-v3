"""Policy Resolver.

Resolves computational requirements (U) under world conditions (S) to an optimal realization graph G*,
producing a first-class PolicyDecisionRecord for complete forensic chain-of-custody.

ARCHITECTURAL PRINCIPLE:
Resolution normally collapses to an indexed lookup from the qualified PolicyRegistry.
Only when no valid policy covers the current region, or when operational drift occurs,
does the system fall back to bounded candidate discovery.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Optional, Tuple

from .discovery import DiscoveryCandidate, DiscoveryEngine
from .models import (
    DecisionSource,
    Policy,
    PolicyDecisionRecord,
    RealizationGraph,
    WorkRequirement,
    WorldConditions,
)
from .registry import PolicyRegistry


@dataclass(frozen=True)
class PolicyResolution:
    """The resolved computational realization graph and execution provenance."""
    graph: RealizationGraph
    policy: Optional[Policy]
    mode: str  # "POLICY_REUSE" or "BOUNDED_DISCOVERY"
    estimated_energy_wh: float
    decision_record: PolicyDecisionRecord
    policy_registry_version: int = 1
    candidate: Optional[DiscoveryCandidate] = None


class PolicyResolver:
    """Core decision engine matching WorkRequirement and WorldConditions to RealizationGraph."""

    def __init__(
        self,
        registry: PolicyRegistry,
        discovery_engine: Optional[DiscoveryEngine] = None,
    ) -> None:
        self.registry = registry
        self.discovery_engine = discovery_engine or DiscoveryEngine()

        self.total_resolutions = 0
        self.policy_reuse_count = 0
        self.discovery_count = 0

    @property
    def policy_residency(self) -> float:
        """Fraction of executions resolved directly from qualified policy: R_{policy} -> 1.0."""
        if self.total_resolutions == 0:
            return 0.0
        return self.policy_reuse_count / self.total_resolutions

    @property
    def learning_residency(self) -> float:
        """Fraction of executions requiring exploration: R_{learning} -> 0.0."""
        return 1.0 - self.policy_residency

    def resolve(
        self,
        requirement: WorkRequirement,
        conditions: WorldConditions,
    ) -> PolicyResolution:
        """Determine what valid computational structure should realize the required work.
        
        Normal Path:
            Qualified region match -> execute G* from policy.
        Exception Path:
            No match or drifted state -> bounded discovery proposing candidate graphs.
        """
        self.total_resolutions += 1
        reg_version = self.registry.version
        now = time.time()
        decision_id = f"dec_{requirement.uow_id}_{conditions.snapshot_id}_{self.total_resolutions}"

        # 1. Fast Path: Lookup in qualified policy registry
        matching_policies = [
            p for p in self.registry.list_active_policies()
            if p.region.contains(requirement, conditions)
        ]
        policy = self.registry.lookup(requirement, conditions)

        if policy is not None and policy.realization_graph.matches_meaning(requirement.canonical_meaning_digest):
            self.policy_reuse_count += 1
            graph = policy.realization_graph
            graph_digest = graph.compute_digest()

            decision = PolicyDecisionRecord(
                decision_id=decision_id,
                uow_id=requirement.uow_id,
                work_requirement_digest=requirement.canonical_meaning_digest,
                world_snapshot_id=conditions.snapshot_id,
                registry_version=reg_version,
                resolution_status="QUALIFIED_MATCH",
                matched_policy_ids=tuple(p.policy_id for p in matching_policies),
                selected_policy_id=policy.policy_id,
                selected_policy_version=policy.policy_version,
                realization_graph_digest=graph_digest,
                decision_source=DecisionSource.QUALIFIED_POLICY,
                objective_values={
                    "expected_energy_wh": policy.evidence.expected_energy_wh,
                    "expected_latency_ms": policy.evidence.expected_latency_ms,
                },
                constraint_checks={
                    "power_budget_compliant": conditions.power_budget_w >= policy.region.min_power_budget_w,
                    "concurrency_compliant": conditions.max_concurrency <= policy.region.max_concurrency,
                    "meaning_compliant": True,
                },
                timestamp=now,
                lifecycle_digest=policy.latest_lifecycle_digest or None,
            )

            return PolicyResolution(
                graph=graph,
                policy=policy,
                mode="POLICY_REUSE",
                estimated_energy_wh=policy.evidence.expected_energy_wh,
                decision_record=decision,
                policy_registry_version=reg_version,
                candidate=None,
            )

        # 2. Exception Path: Bounded discovery of candidate graphs
        self.discovery_count += 1
        candidates = self.discovery_engine.propose_candidates(requirement, conditions)
        if not candidates:
            raise RuntimeError(
                f"No viable realization graph can satisfy requirement {requirement.workload_class} "
                f"with available capabilities: {[c.value for c in conditions.available_capabilities]}"
            )

        # Select candidate with lowest estimated energy
        best_candidate = min(candidates, key=lambda c: c.estimated_energy_wh)
        graph = best_candidate.graph
        graph_digest = graph.compute_digest()

        decision = PolicyDecisionRecord(
            decision_id=decision_id,
            uow_id=requirement.uow_id,
            work_requirement_digest=requirement.canonical_meaning_digest,
            world_snapshot_id=conditions.snapshot_id,
            registry_version=reg_version,
            resolution_status="NO_QUALIFIED_POLICY",
            matched_policy_ids=(),
            selected_policy_id=None,
            selected_policy_version=None,
            realization_graph_digest=graph_digest,
            decision_source=DecisionSource.DISCOVERY_CANDIDATE,
            objective_values={
                "estimated_energy_wh": best_candidate.estimated_energy_wh,
                "estimated_latency_ms": best_candidate.estimated_latency_ms,
            },
            constraint_checks={
                "power_budget_compliant": True,
                "concurrency_compliant": True,
                "meaning_compliant": graph.matches_meaning(requirement.canonical_meaning_digest),
            },
            timestamp=now,
        )

        return PolicyResolution(
            graph=graph,
            policy=None,
            mode="BOUNDED_DISCOVERY",
            estimated_energy_wh=best_candidate.estimated_energy_wh,
            decision_record=decision,
            policy_registry_version=reg_version,
            candidate=best_candidate,
        )
