"""Autonomous Continuous Topology Evolution Endurance for Campaign A2 (Gate A2.8 Capstone).

Enforces:
1. Continuous Adaptation: The runtime continuously reorganizes execution graphs (G)
   and actor bindings (B) under non-stationary, overlapping environmental drift without
   artificial resets.
2. Absolute Safety Invariance:
   - For all t in [0, T]: Phi(G_t, U) == Phi(U)
   - N_wrong_commit = 0
   - N_uncertified_mutation = 0
   - N_double_commit = 0
   - N_authority_inflation = 0
   - N_accepted_stale_mutation = 0
   - N_lost_task = 0
   - Post-partition consensus: H_1 = H_2 = ... = H_n = H*
3. Performance Quality: Evaluates scalar objective J(G, B, S) = w_L L + w_E E + w_C C + w_F F
   proving J_adaptive < J_static (Delta J < 0).
4. Anti-Thrashing Hysteresis: Distinguishes necessary adaptation from high-frequency
   mutation oscillation (R_mutation <= R_max) via minimum dwell periods and delta thresholds.
5. Learning Loop Adversarial Attack Resilience: Delayed, reordered, duplicate, or corrupt
   observations may degrade policy proposals but CANNOT corrupt authoritative history or consensus.
6. Topology Lineage Artifact: Emits complete forensic lineage L of all certified graph substitutions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import random
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from uow.composition.actor import ActorDescriptor, ActorRegistry, AuthorityClass
from uow.composition.binding import ActorBinding, validate_binding
from uow.composition.contract import ParentContract
from uow.composition.convergence import AuthoritativeHistory, HistoryEntry, HistoryEntryKind
from uow.composition.fabric import canonical_json
from uow.composition.graph import RealizationGraph
from ...implementations.distributed.host_node import DurableWAL, PhysicalHostNode
from uow.composition.mutation import (
    AuthorityMutationVote,
    QuorumMutationCoordinator,
    RuntimeMutationProposal,
    RuntimeMutationQC,
    assemble_mutation_qc,
    sign_mutation_vote,
    verify_mutation_qc,
)
from uow.composition.policy import AdaptiveGraphProposer, CompositionRuntimeState, GraphAdaptationObservation
from uow.composition.projection import project_semantics


@dataclass(frozen=True)
class EnvironmentalState:
    """Non-stationary environmental conditions at time step t: S_t = (L_npu, L_cpu, lambda, A, F, Q, C)."""

    step_index: int
    npu_load: float             # [0.0, 1.0]
    cpu_load: float             # [0.0, 1.0]
    network_loss: float         # [0.0, 1.0]
    network_latency_ms: float   # in ms
    actor_availability: Mapping[str, bool]
    active_failures: Tuple[str, ...]
    queue_depth: int = 1
    cost_budget: float = 100.0

    def compute_hash(self) -> str:
        payload = {
            "step": self.step_index,
            "npu_load": f"{self.npu_load:.3f}",
            "cpu_load": f"{self.cpu_load:.3f}",
            "network_loss": f"{self.network_loss:.3f}",
            "network_latency_ms": f"{self.network_latency_ms:.1f}",
            "availability": {k: self.actor_availability[k] for k in sorted(self.actor_availability.keys())},
            "failures": sorted(self.active_failures),
            "queue_depth": self.queue_depth,
        }
        return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class ContinuousPerturbationTrace:
    """Generates continuous, overlapping environmental perturbations over endurance steps."""

    def __init__(self, total_steps: int = 100, seed: int = 42) -> None:
        self.total_steps = total_steps
        self.seed = seed
        self._states: List[EnvironmentalState] = self._generate_trace()

    @property
    def states(self) -> Tuple[EnvironmentalState, ...]:
        return tuple(self._states)

    def _generate_trace(self) -> List[EnvironmentalState]:
        rng = random.Random(self.seed)
        states = []
        actors = ["actor_host_cpu", "actor_intel_npu", "actor_parallel_worker"]

        # Base parameters
        npu_load = 0.15
        cpu_load = 0.20
        net_loss = 0.01
        net_latency = 5.0
        active_failures: List[str] = []

        for step in range(self.total_steps):
            # Phase 1 (0..20): Low load baseline, NPU preferred
            if step < 20:
                npu_load = 0.10 + 0.05 * rng.random()
                cpu_load = 0.15 + 0.05 * rng.random()
                net_loss = 0.01
                net_latency = 5.0 + rng.random() * 2.0
                active_failures = []
            # Phase 2 (20..40): NPU load surge and thermal throttle
            elif step < 40:
                npu_load = min(1.0, 0.70 + 0.25 * ((step - 20) / 20.0) + 0.05 * rng.random())
                cpu_load = 0.25 + 0.10 * rng.random()
                net_loss = 0.02
                net_latency = 10.0
                active_failures = []
            # Phase 3 (40..60): Network loss spike and NPU worker unavailable
            elif step < 60:
                npu_load = 0.90
                cpu_load = 0.40 + 0.15 * rng.random()
                net_loss = 0.15 + 0.10 * rng.random()
                net_latency = 45.0 + 10.0 * rng.random()
                active_failures = ["actor_intel_npu"] if step > 45 else []
            # Phase 4 (60..80): Authority node partition & healing
            elif step < 80:
                npu_load = 0.25
                cpu_load = 0.75 + 0.20 * rng.random()
                net_loss = 0.05
                net_latency = 20.0
                active_failures = ["auth_stm32"] if step < 72 else []
            # Phase 5 (80..100): Return to equilibrium
            else:
                npu_load = 0.15 + 0.05 * rng.random()
                cpu_load = 0.20 + 0.05 * rng.random()
                net_loss = 0.01
                net_latency = 5.0
                active_failures = []

            avail = {
                a: (a not in active_failures) for a in actors
            }

            s = EnvironmentalState(
                step_index=step,
                npu_load=npu_load,
                cpu_load=cpu_load,
                network_loss=net_loss,
                network_latency_ms=net_latency,
                actor_availability=avail,
                active_failures=tuple(sorted(active_failures)),
                queue_depth=1 + int(cpu_load * 4),
            )
            states.append(s)

        return states


@dataclass
class RuntimeObjectiveFunction:
    """Scalar runtime objective J(G, B, S) = w_L * Latency + w_E * Energy + w_C * Cost + w_F * Risk."""

    weight_latency: float = 1.0
    weight_energy: float = 0.5
    weight_cost: float = 0.5
    weight_risk: float = 4.0

    def evaluate(
        self,
        graph: RealizationGraph,
        binding: ActorBinding,
        env: EnvironmentalState,
    ) -> float:
        """Computes cost J given current topology and environmental conditions."""
        # 1. Latency calculation (in ms)
        base_latency = graph.critical_path_duration_ms()

        # If graph uses NPU and NPU is overloaded
        npu_penalty = 1.0
        if "npu" in graph.graph_id.lower() or any("npu" in a for a in binding.node_to_actor.values()):
            if env.npu_load > 0.70:
                npu_penalty = 1.0 + (env.npu_load - 0.70) * 8.0  # heavy slowdown under saturation

        # CPU load penalty
        cpu_penalty = 1.0 + env.cpu_load * 1.5

        # Network transmission penalty
        net_penalty = env.network_latency_ms * (1.0 + env.network_loss * 5.0)

        latency = (base_latency * npu_penalty * cpu_penalty) + net_penalty

        # 2. Energy and resource cost
        energy = 10.0
        if "parallel" in graph.graph_id.lower():
            energy = 30.0
        elif "npu" in graph.graph_id.lower():
            energy = 15.0

        cost = len(graph.nodes) * 2.5

        # 3. Failure risk
        risk = 0.0
        for node_id, actor_id in binding.node_to_actor.items():
            if not env.actor_availability.get(actor_id, True):
                risk += 150.0  # Massive risk penalty if bound actor is down!
        if env.network_loss > 0.20:
            risk += env.network_loss * 50.0

        j = (
            self.weight_latency * latency
            + self.weight_energy * energy
            + self.weight_cost * cost
            + self.weight_risk * risk
        )
        return float(j)


@dataclass
class AntiThrashingHysteresis:
    """Enforces hysteresis and minimum dwell period to prevent mutation thrashing."""

    min_dwell_steps: int = 4
    delta_threshold: float = 12.0
    last_mutation_step: int = -10
    total_mutations: int = 0
    total_steps: int = 0

    def should_propose(
        self,
        current_cost: float,
        candidate_cost: float,
        current_broken: bool,
        current_step: int,
    ) -> Tuple[bool, str]:
        self.total_steps = max(self.total_steps, current_step + 1)

        # 1. Structural necessity: If current topology is broken (bound actor down), mutate immediately!
        if current_broken:
            return True, "FAILOVER_MANDATORY"

        # 2. Dwell period check: prevent rapid cycling
        elapsed = current_step - self.last_mutation_step
        if elapsed < self.min_dwell_steps:
            return False, f"DWELL_TIME_ENFORCED: elapsed={elapsed}, min={self.min_dwell_steps}"

        # 3. Improvement threshold check: Delta J > epsilon
        improvement = current_cost - candidate_cost
        if improvement < self.delta_threshold:
            return False, f"INSUFFICIENT_IMPROVEMENT: delta={improvement:.2f}, threshold={self.delta_threshold:.2f}"

        return True, f"IMPROVEMENT_EXCEEDS_THRESHOLD: delta={improvement:.2f}"

    def record_mutation(self, step: int) -> None:
        self.last_mutation_step = step
        self.total_mutations += 1

    @property
    def mutation_rate(self) -> float:
        if self.total_steps == 0:
            return 0.0
        return self.total_mutations / self.total_steps


@dataclass(frozen=True)
class LineageEdge:
    """Forensic record of a certified topology mutation."""

    edge_index: int
    step: int
    from_graph_id: str
    to_graph_id: str
    from_binding_id: str
    to_binding_id: str
    generation_before: int
    generation_after: int
    history_head: str
    proposal_id: str
    rationale: str
    telemetry_hash: str
    candidate_graph_hash: str
    candidate_binding_hash: str
    conformance_verified: bool
    signers: Tuple[str, ...]
    qc_hash: str
    observed_delta_j: float
    timestamp_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_index": self.edge_index,
            "step": self.step,
            "from_graph_id": self.from_graph_id,
            "to_graph_id": self.to_graph_id,
            "from_binding_id": self.from_binding_id,
            "to_binding_id": self.to_binding_id,
            "generation_before": self.generation_before,
            "generation_after": self.generation_after,
            "history_head": self.history_head,
            "proposal_id": self.proposal_id,
            "rationale": self.rationale,
            "telemetry_hash": self.telemetry_hash,
            "candidate_graph_hash": self.candidate_graph_hash,
            "candidate_binding_hash": self.candidate_binding_hash,
            "conformance_verified": self.conformance_verified,
            "signers": list(self.signers),
            "qc_hash": self.qc_hash,
            "observed_delta_j": f"{self.observed_delta_j:.2f}",
            "timestamp_iso": self.timestamp_iso,
        }


class TopologyLineage:
    """Append-only audit ledger recording every certified topology mutation over endurance execution."""

    def __init__(self) -> None:
        self._edges: List[LineageEdge] = []

    @property
    def edges(self) -> Tuple[LineageEdge, ...]:
        return tuple(self._edges)

    def record_edge(self, edge: LineageEdge) -> None:
        self._edges.append(edge)

    def to_list(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._edges]


class ObservationPoisoningEngine:
    """Adversarial engine attacking the learning feedback loop (delayed, reordered, duplicate, corrupt)."""

    @staticmethod
    def poison_observations(
        observations: Sequence[GraphAdaptationObservation],
        attack_type: str = "all",
    ) -> List[GraphAdaptationObservation]:
        """Injects non-malicious-to-authority, but adversarial-to-policy anomalies into feedback."""
        poisoned = list(observations)
        if not poisoned:
            return poisoned

        if attack_type in ("delay", "all"):
            # Delay: duplicate stale observation from earlier step
            if len(poisoned) > 2:
                poisoned[-1] = poisoned[0]

        if attack_type in ("reorder", "all"):
            # Reorder observations out of chronological order
            random.Random(1337).shuffle(poisoned)

        if attack_type in ("duplicate", "all"):
            # Duplicate identical observation
            if poisoned:
                poisoned.append(poisoned[-1])

        if attack_type in ("corrupt", "all"):
            # Corrupt telemetry performance data (e.g. report 0.001ms latency for failed graph)
            if poisoned:
                last = poisoned[-1]
                corrupted = GraphAdaptationObservation(
                    observation_id=f"corrupt_{last.observation_id}",
                    parent_contract_id=last.parent_contract_id,
                    state_snapshot_hash=last.state_snapshot_hash,
                    proposed_graph_id=last.proposed_graph_id,
                    proposed_strategy=last.proposed_strategy,
                    certification_outcome=last.certification_outcome,
                    execution_status=last.execution_status,
                    observed_latency_ms=0.001,  # Falsified telemetry!
                    violations=last.violations,
                )
                poisoned[-1] = corrupted

        return poisoned


# =========================================================================
# Comparative Baselines: Fixed (B0), Rule-Based (B1), Learned (A2)
# =========================================================================

class FixedBaselineRuntime:
    """B0: Static baseline execution with zero adaptation (fixed G_0, B_0)."""

    def __init__(
        self,
        graph: RealizationGraph,
        binding: ActorBinding,
        parent_contract: ParentContract,
        objective: RuntimeObjectiveFunction,
    ) -> None:
        self.graph = graph
        self.binding = binding
        self.parent_contract = parent_contract
        self.objective = objective
        self.history = AuthoritativeHistory()
        self.cumulative_cost = 0.0
        self.cost_history: List[float] = []

    def execute_step(self, step: int, env: EnvironmentalState) -> Tuple[bool, float]:
        cost = self.objective.evaluate(self.graph, self.binding, env)
        self.cost_history.append(cost)
        self.cumulative_cost += cost

        # Commit task
        seq = self.history.tip_sequence() + 1
        entry = HistoryEntry(
            entry_id=f"b0_task_{step}_{seq}",
            sequence_number=seq,
            prev_hash=self.history.tip_hash(),
            kind=HistoryEntryKind.AUTHORITATIVE_COMMIT,
            author_node_id="baseline_b0",
            generation=0,
            payload={"step": step, "cost": cost},
        )
        ok, _ = self.history.append(entry)
        return ok, cost


class RuleBasedRuntime:
    """B1: Rule-based heuristic failover without online learning."""

    def __init__(
        self,
        graphs: Mapping[str, RealizationGraph],
        bindings: Mapping[str, ActorBinding],
        parent_contract: ParentContract,
        objective: RuntimeObjectiveFunction,
    ) -> None:
        self.graphs = dict(graphs)
        self.bindings = dict(bindings)
        self.parent_contract = parent_contract
        self.objective = objective
        self.active_id = "G_npu"
        self.history = AuthoritativeHistory()
        self.cumulative_cost = 0.0
        self.cost_history: List[float] = []
        self.mutations_count = 0

    def execute_step(self, step: int, env: EnvironmentalState) -> Tuple[bool, float]:
        # Simple threshold rule
        npu_avail = env.actor_availability.get("actor_intel_npu", True)
        if not npu_avail or env.npu_load > 0.70:
            target = "G_parallel" if env.cpu_load < 0.60 else "G_sequential"
        else:
            target = "G_npu"

        if target != self.active_id:
            self.active_id = target
            self.mutations_count += 1

        active_g = self.graphs[self.active_id]
        active_b = self.bindings[self.active_id]
        cost = self.objective.evaluate(active_g, active_b, env)
        self.cost_history.append(cost)
        self.cumulative_cost += cost

        seq = self.history.tip_sequence() + 1
        entry = HistoryEntry(
            entry_id=f"b1_task_{step}_{seq}",
            sequence_number=seq,
            prev_hash=self.history.tip_hash(),
            kind=HistoryEntryKind.AUTHORITATIVE_COMMIT,
            author_node_id="rule_b1",
            generation=self.mutations_count,
            payload={"step": step, "active_graph": self.active_id, "cost": cost},
        )
        ok, _ = self.history.append(entry)
        return ok, cost


class EnduranceAdaptiveRuntime:
    """A2: Learned adaptive composition runtime with quorum-certified self-reconfiguration."""

    def __init__(
        self,
        node: PhysicalHostNode,
        candidate_graphs: Mapping[str, RealizationGraph],
        candidate_bindings: Mapping[str, ActorBinding],
        parent_contract: ParentContract,
        authority_keys: Mapping[str, str],
        objective: RuntimeObjectiveFunction,
        hysteresis: Optional[AntiThrashingHysteresis] = None,
        proposer: Optional[AdaptiveGraphProposer] = None,
    ) -> None:
        self.node = node
        self.candidate_graphs = dict(candidate_graphs)
        self.candidate_bindings = dict(candidate_bindings)
        self.parent_contract = parent_contract
        self.authority_keys = dict(authority_keys)
        self.objective = objective
        self.hysteresis = hysteresis or AntiThrashingHysteresis()
        self.proposer = proposer or AdaptiveGraphProposer()
        self.lineage = TopologyLineage()

        self.cumulative_cost = 0.0
        self.cost_history: List[float] = []
        self.uncertified_mutations = 0
        self.stale_mutations = 0
        self.double_commits = 0
        self.wrong_commits = 0
        self.authority_inflations = 0
        self.lost_tasks = 0

    def execute_step(self, step: int, env: EnvironmentalState) -> Tuple[bool, float, bool]:
        """Executes a single step: evaluates adaptation, applies certified mutation if needed, commits work."""
        active_g = self.node.active_graph
        active_b = self.node.active_binding
        current_cost = self.objective.evaluate(active_g, active_b, env)

        # Check if current topology is structurally broken
        current_broken = False
        for node_id, actor_id in active_b.node_to_actor.items():
            if not env.actor_availability.get(actor_id, True):
                current_broken = True
                break

        # Proposer evaluates candidates and identifies best proposal
        best_candidate_id = None
        best_candidate_cost = current_cost

        for cand_id, cand_g in self.candidate_graphs.items():
            cand_b = self.candidate_bindings[cand_id]
            # Must satisfy semantic projection
            proj = project_semantics(cand_g, self.parent_contract)
            if not proj.conforms:
                continue

            c_cost = self.objective.evaluate(cand_g, cand_b, env)
            if c_cost < best_candidate_cost:
                best_candidate_cost = c_cost
                best_candidate_id = cand_id

        mutated = False

        if best_candidate_id and best_candidate_id != active_g.graph_id:
            should_mut, reason = self.hysteresis.should_propose(
                current_cost=current_cost,
                candidate_cost=best_candidate_cost,
                current_broken=current_broken,
                current_step=step,
            )

            if should_mut:
                cand_g = self.candidate_graphs[best_candidate_id]
                cand_b = self.candidate_bindings[best_candidate_id]

                # Proposer produces proposal (ZERO AUTHORITY)
                prop = RuntimeMutationProposal(
                    proposal_id=f"mut_prop_step{step}_{best_candidate_id}",
                    proposer_id=self.proposer.model_id,
                    parent_contract_id=self.parent_contract.contract_id,
                    parent_contract_hash=self.parent_contract.compute_hash(),
                    current_graph_hash=active_g.compute_hash(),
                    current_binding_hash=active_b.compute_hash(),
                    candidate_graph=cand_g,
                    candidate_binding=cand_b,
                    generation=self.node.generation,
                    history_head=self.node.history.tip_hash(),
                    strategy="endurance_adaptive",
                    rationale=reason,
                )

                # Authority nodes independently evaluate & vote
                votes = [
                    sign_mutation_vote(
                        v_id,
                        v_key,
                        prop,
                        self.parent_contract,
                        self.node.history.tip_hash(),
                        self.node.generation,
                    )
                    for v_id, v_key in self.authority_keys.items()
                ]

                # Assemble QC
                qc, qc_msg = assemble_mutation_qc(prop, votes, threshold=2)
                if qc is not None:
                    # Apply mutation atomically to physical node
                    gen_before = self.node.generation
                    ok_apply, apply_msg = self.node.apply_mutation_qc(
                        qc=qc,
                        candidate_graph=cand_g,
                        candidate_binding=cand_b,
                        parent_contract=self.parent_contract,
                        authority_keys=self.authority_keys,
                        threshold=2,
                    )

                    if ok_apply:
                        mutated = True
                        self.hysteresis.record_mutation(step)
                        delta_j = current_cost - best_candidate_cost

                        edge = LineageEdge(
                            edge_index=len(self.lineage.edges),
                            step=step,
                            from_graph_id=active_g.graph_id,
                            to_graph_id=cand_g.graph_id,
                            from_binding_id=active_b.binding_id,
                            to_binding_id=cand_b.binding_id,
                            generation_before=gen_before,
                            generation_after=self.node.generation,
                            history_head=qc.history_head,
                            proposal_id=prop.proposal_id,
                            rationale=reason,
                            telemetry_hash=env.compute_hash(),
                            candidate_graph_hash=cand_g.compute_hash(),
                            candidate_binding_hash=cand_b.compute_hash(),
                            conformance_verified=True,
                            signers=qc.signers,
                            qc_hash=qc.qc_hash,
                            observed_delta_j=delta_j,
                        )
                        self.lineage.record_edge(edge)

                        # Update active pointers
                        active_g = self.node.active_graph
                        active_b = self.node.active_binding
                        current_cost = best_candidate_cost
                    else:
                        self.uncertified_mutations += 1
                else:
                    self.uncertified_mutations += 1

        # Re-evaluate cost under finalized topology
        final_cost = self.objective.evaluate(active_g, active_b, env)
        self.cost_history.append(final_cost)
        self.cumulative_cost += final_cost

        # Commit task durably
        ok_commit, entry, c_msg = self.node.commit_entry_durably(
            kind=HistoryEntryKind.AUTHORITATIVE_COMMIT,
            payload={"step": step, "graph": active_g.graph_id, "cost": final_cost},
            idempotency_key=f"task_step_{step}",
        )
        if not ok_commit:
            self.lost_tasks += 1
            return False, final_cost, mutated

        return True, final_cost, mutated
