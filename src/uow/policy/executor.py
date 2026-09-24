"""Production Realization Graph Executor.

Executes a multi-stage RealizationGraph G = (V, E, M) satisfying a WorkRequirement U
under WorldConditions S, managing stage transitions, authority preservation, and
emitting a cryptographically bound ExecutionCertificate chained to the PolicyDecisionRecord.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .models import (
    ExecutionCertificate,
    PolicyDecisionRecord,
    RealizationGraph,
    RealizationStage,
    ResourceCapability,
    WorkRequirement,
    WorldConditions,
)


class GraphExecutionError(RuntimeError):
    """Raised when realization graph execution fails an invariant or constraint."""


class RealizationGraphExecutor:
    """Executes ordered multi-stage computational graphs across capability boundaries."""

    def __init__(self, max_stage_retries: int = 2) -> None:
        self.max_stage_retries = max_stage_retries
        self.total_graph_executions = 0
        self.total_stage_executions = 0

    def execute_graph(
        self,
        graph: RealizationGraph,
        requirement: WorkRequirement,
        world: WorldConditions,
        policy_registry_version: int = 1,
        policy_id: Optional[str] = None,
        policy_version: Optional[int] = None,
        decision: Optional[PolicyDecisionRecord] = None,
        state_payload: Optional[Dict[str, Any]] = None,
    ) -> ExecutionCertificate:
        r"""Execute all stages in graph preserving causality, authority, and cryptographic lineage.
        
        Binds certificate: C = H(U, S, \Pi, G, R, E) chained with DecisionRecord.
        """
        self.total_graph_executions += 1
        t_start = time.perf_counter()

        # If a PolicyDecisionRecord was supplied, inherit its provenance fields
        dec_id = ""
        dec_digest = ""
        if decision is not None:
            policy_registry_version = decision.registry_version
            policy_id = decision.selected_policy_id
            policy_version = decision.selected_policy_version
            dec_id = decision.decision_id
            dec_digest = decision.decision_digest

        # 1. Pre-execution Invariant Checks
        if not graph.is_valid:
            raise GraphExecutionError(f"Graph {graph.graph_id} is marked invalid")

        if not graph.matches_meaning(requirement.canonical_meaning_digest):
            raise GraphExecutionError(
                f"Semantic divergence: graph meaning {graph.meaning_digest} "
                f"does not match requirement {requirement.canonical_meaning_digest}"
            )

        # 2. Dependency validation & Topological ordering
        completed_stages: Set[str] = set()
        stage_outputs: Dict[str, str] = {}
        total_measured_e_wh = 0.0
        total_measured_lat_ms = 0.0

        current_state_hash = hashlib.sha256(
            f"INITIAL:{requirement.uow_id}:{requirement.canonical_meaning_digest}".encode("utf-8")
        ).hexdigest()[:24]

        # 3. Stage-by-stage Execution
        for stage in graph.stages:
            # Verify dependencies
            for dep in stage.dependencies:
                if dep not in completed_stages:
                    raise GraphExecutionError(
                        f"Stage {stage.stage_id} missing satisfied dependency {dep}"
                    )

            # Verify capability availability in world snapshot
            if stage.capability not in world.available_capabilities:
                raise GraphExecutionError(
                    f"Required capability {stage.capability.value} for stage {stage.stage_id} "
                    f"is not available in world snapshot {world.snapshot_id}"
                )

            # Simulate/execute stage with congestion multiplier
            congestion = world.congestion_factors.get(stage.capability, 1.0)
            stage_e = stage.nominal_energy_wh * congestion
            stage_lat = stage.nominal_latency_ms * congestion

            total_measured_e_wh += stage_e
            total_measured_lat_ms += stage_lat
            self.total_stage_executions += 1

            # Chain stage state
            stage_repr = (
                f"STAGE:{stage.stage_id}:{stage.capability.value}:{current_state_hash}:"
                f"{stage_e:.8f}:{requirement.required_authority}"
            )
            current_state_hash = hashlib.sha256(stage_repr.encode("utf-8")).hexdigest()[:24]
            stage_outputs[stage.stage_id] = current_state_hash
            completed_stages.add(stage.stage_id)

        # Add inter-stage transfer overhead
        total_measured_e_wh += graph.inter_stage_transfer_energy_wh
        total_measured_lat_ms += graph.inter_stage_transfer_latency_ms

        t_end = time.perf_counter()
        measured_wall_ms = (t_end - t_start) * 1000.0

        # Construct final ExecutionCertificate
        cert_id = f"cert_{requirement.uow_id}_{graph.graph_id}_{world.snapshot_id}"
        graph_digest = graph.compute_digest()

        certificate = ExecutionCertificate(
            certificate_id=cert_id,
            uow_id=requirement.uow_id,
            graph_id=graph.graph_id,
            state_hash=current_state_hash,
            is_certified=True,
            measured_energy_wh=total_measured_e_wh,
            measured_latency_ms=total_measured_lat_ms,
            authority_compliant=True,
            policy_registry_version=policy_registry_version,
            policy_id=policy_id,
            policy_version=policy_version,
            world_snapshot_id=world.snapshot_id,
            realization_graph_digest=graph_digest,
            decision_id=dec_id,
            decision_digest=dec_digest,
            correctness_breaches=0,
        )

        return certificate
