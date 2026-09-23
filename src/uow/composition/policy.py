"""Adaptive Graph Proposer policy and online learning for Campaign A2.

Learns optimal execution graph selection and actor bindings based on dynamic runtime
state vectors S_t, while remaining subject to authoritative Judge certification.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from uow.composition.actor import ActorDescriptor, ActorRegistry, AuthorityClass
from uow.composition.binding import ActorBinding, validate_binding
from uow.composition.contract import ParentContract
from uow.composition.graph import RealizationGraph
from uow.composition.substitution import GraphReplacementProposal, SubstitutionStrategy


def canonical_json(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class CompositionRuntimeState:
    """Runtime state vector S_t representing current environmental conditions."""

    actor_availability: Mapping[str, bool]
    actor_loads: Mapping[str, float]
    actor_latencies: Mapping[str, float]
    actor_failure_counts: Mapping[str, int]
    active_graph_id: str
    queue_depth: int = 0
    network_latency_ms: float = 0.0
    state_hash: str = ""

    def __post_init__(self) -> None:
        if not self.state_hash:
            payload = {
                "availability": {k: self.actor_availability[k] for k in sorted(self.actor_availability.keys())},
                "loads": {k: f"{self.actor_loads[k]:.3f}" for k in sorted(self.actor_loads.keys())},
                "latencies": {k: f"{self.actor_latencies[k]:.1f}" for k in sorted(self.actor_latencies.keys())},
                "failures": {k: self.actor_failure_counts[k] for k in sorted(self.actor_failure_counts.keys())},
                "active_graph_id": self.active_graph_id,
                "queue_depth": self.queue_depth,
                "network_latency_ms": f"{self.network_latency_ms:.1f}",
            }
            digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
            object.__setattr__(self, "state_hash", digest)


@dataclass(frozen=True)
class GraphAdaptationObservation:
    """Certified observation from authority certifier and runtime execution."""

    observation_id: str
    parent_contract_id: str
    state_snapshot_hash: str
    proposed_graph_id: str
    proposed_strategy: str
    certification_outcome: str  # "ACCEPTED", "REJECTED"
    execution_status: str       # "SUCCESS", "FAILED", "NOT_EXECUTED"
    observed_latency_ms: float = 0.0
    violations: Tuple[str, ...] = ()
    timestamp_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AdaptiveGraphProposer:
    """Policy engine P_theta(S_t, G_t, U) -> (G_cand, B_cand) that proposes graph substitutions."""

    def __init__(
        self,
        model_id: str = "AdaptiveGraphProposer",
        model_version: str = "1.0.0",
        initial_weights: Optional[Mapping[str, float]] = None,
        learning_rate: float = 0.15,
    ) -> None:
        self.model_id = model_id
        self.model_version = model_version
        self.learning_rate = learning_rate
        self.generation = 0

        # Policy weights theta
        self.weights: Dict[str, float] = {
            "w_npu_affinity": 2.0,
            "w_parallel_affinity": 1.5,
            "w_distributed_affinity": 1.0,
            "w_sequential_affinity": 0.8,
            "w_load_penalty": 3.0,
            "w_latency_penalty": 1.5,
            "w_failure_penalty": 5.0,
        }
        if initial_weights:
            self.weights.update(initial_weights)

        self.model_artifact_hash = self._compute_artifact_hash()

    def _compute_artifact_hash(self) -> str:
        payload = {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "generation": self.generation,
            "weights": {k: f"{v:.4f}" for k, v in sorted(self.weights.items())},
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()

    def find_feasible_binding(
        self,
        graph: RealizationGraph,
        registry: ActorRegistry,
    ) -> Optional[ActorBinding]:
        """Finds the optimal physical actor binding for a candidate graph topology."""
        mapping: Dict[str, str] = {}
        for node_id, node in graph.nodes.items():
            req_caps = node.required_capabilities
            req_auth = AuthorityClass(node.required_authority_class)
            capable = registry.find_capable_actors(
                required_capabilities=req_caps,
                min_authority=req_auth,
                require_available=True,
                max_load=0.95,
            )
            if not capable:
                return None
            # Select actor with lowest load and latency
            mapping[node_id] = capable[0].actor_id

        binding = ActorBinding(
            binding_id=f"bind_{graph.graph_id}_g{self.generation}",
            graph_id=graph.graph_id,
            node_to_actor=mapping,
        )
        valid, _ = validate_binding(graph, binding, registry)
        return binding if valid else None

    def evaluate_score(
        self,
        graph: RealizationGraph,
        binding: ActorBinding,
        state: CompositionRuntimeState,
    ) -> float:
        """Computes utility score Q_theta(S_t, G_i, B_i)."""
        score = 100.0 - (graph.critical_path_duration_ms() / 10.0)

        # Affinity bonus by topology category
        if "accelerator" in graph.graph_id.lower() or "npu" in graph.graph_id.lower():
            score += self.weights["w_npu_affinity"] * 10.0
        elif "parallel" in graph.graph_id.lower():
            score += self.weights["w_parallel_affinity"] * 10.0
        elif "distributed" in graph.graph_id.lower() or "quorum" in graph.graph_id.lower():
            score += self.weights["w_distributed_affinity"] * 10.0
        else:
            score += self.weights["w_sequential_affinity"] * 5.0

        # Penalties based on bound actors
        for node_id, actor_id in binding.node_to_actor.items():
            load = state.actor_loads.get(actor_id, 0.0)
            latency = state.actor_latencies.get(actor_id, 1.0)
            failures = state.actor_failure_counts.get(actor_id, 0)

            score -= self.weights["w_load_penalty"] * (load * 10.0)
            score -= self.weights["w_latency_penalty"] * (latency / 10.0)
            score -= self.weights["w_failure_penalty"] * (failures * 10.0)

        return score

    def propose_realization(
        self,
        state: CompositionRuntimeState,
        contract: ParentContract,
        candidate_graphs: Sequence[RealizationGraph],
        registry: ActorRegistry,
        current_graph_hash: str,
        proposal_id: str = "",
    ) -> Optional[GraphReplacementProposal]:
        """Proposes the highest-scoring candidate graph and actor binding given state S_t."""
        best_graph: Optional[RealizationGraph] = None
        best_binding: Optional[ActorBinding] = None
        best_score = float("-inf")
        best_strategy = SubstitutionStrategy.FALLBACK_BASELINE

        for graph in candidate_graphs:
            binding = self.find_feasible_binding(graph, registry)
            if not binding:
                continue

            score = self.evaluate_score(graph, binding, state)
            if score > best_score:
                best_score = score
                best_graph = graph
                best_binding = binding

                if "accelerator" in graph.graph_id.lower() or "npu" in graph.graph_id.lower():
                    best_strategy = SubstitutionStrategy.ACCELERATOR_OFFLOAD
                elif "parallel" in graph.graph_id.lower():
                    best_strategy = SubstitutionStrategy.PARALLEL_DECOMPOSITION
                elif "distributed" in graph.graph_id.lower() or "quorum" in graph.graph_id.lower():
                    best_strategy = SubstitutionStrategy.DISTRIBUTED_QUORUM
                else:
                    best_strategy = SubstitutionStrategy.FALLBACK_BASELINE

        if best_graph is None or best_binding is None:
            return None

        # Estimate speedup relative to 140ms sequential baseline
        base_dur = 140.0
        cand_dur = max(1.0, best_graph.critical_path_duration_ms())
        speedup = round(base_dur / cand_dur, 2)

        return GraphReplacementProposal(
            parent_contract_id=contract.contract_id,
            current_graph_hash=current_graph_hash,
            candidate_graph=best_graph,
            strategy=best_strategy,
            predicted_speedup=speedup,
            rationale=f"Selected {best_graph.graph_id} with score {best_score:.2f} under generation {self.generation}",
            proposal_id=proposal_id or f"prop_g{self.generation}_{best_graph.graph_id}",
            actor_binding=best_binding,
        )

    def adapt(self, observation: GraphAdaptationObservation) -> None:
        """Online policy adaptation driven by certified Judge outcomes and execution records."""
        self.generation += 1

        if observation.certification_outcome == "REJECTED":
            # Rejection penalty: reduce affinity of the failed strategy
            if observation.proposed_strategy == SubstitutionStrategy.ACCELERATOR_OFFLOAD.value:
                self.weights["w_npu_affinity"] = max(0.1, self.weights["w_npu_affinity"] - self.learning_rate)
            elif observation.proposed_strategy == SubstitutionStrategy.PARALLEL_DECOMPOSITION.value:
                self.weights["w_parallel_affinity"] = max(0.1, self.weights["w_parallel_affinity"] - self.learning_rate)
            self.weights["w_failure_penalty"] += self.learning_rate
        elif observation.execution_status == "FAILED":
            # Execution failure: penalize load and failure weights
            self.weights["w_load_penalty"] += self.learning_rate
            self.weights["w_failure_penalty"] += self.learning_rate * 2.0
        elif observation.execution_status == "SUCCESS":
            # Positive reinforcement: reinforce strategy that succeeded
            if observation.proposed_strategy == SubstitutionStrategy.ACCELERATOR_OFFLOAD.value:
                self.weights["w_npu_affinity"] += self.learning_rate
            elif observation.proposed_strategy == SubstitutionStrategy.PARALLEL_DECOMPOSITION.value:
                self.weights["w_parallel_affinity"] += self.learning_rate

        self.model_artifact_hash = self._compute_artifact_hash()
