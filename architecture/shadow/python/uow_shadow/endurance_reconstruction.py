"""R4 A2.8 endurance reconstruction.

This runtime reproduces the A2.8 composition loop without using the canonical
EnduranceAdaptiveRuntime or PhysicalHostNode.apply_mutation_qc.

Retained realizations:
- RuntimeObjectiveFunction / perturbation trace / hysteresis semantics
- RuntimeMutationProposal + signed vote + QC formation
- AuthoritativeHistory representation
- optional DurableWAL persistence

Reconstructed authority:
verified QC -> minimal shadow distributed-quorum authorization
-> AuthorizedTransition -> evidence -> topology/history update.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Mapping, Optional, Tuple

from uow.composition.binding import ActorBinding
from uow.composition.contract import ParentContract
from uow.composition.convergence import AuthoritativeHistory, HistoryEntry, HistoryEntryKind
from uow.composition.endurance import (
    AntiThrashingHysteresis,
    EnvironmentalState,
    LineageEdge,
    RuntimeObjectiveFunction,
    TopologyLineage,
)
from uow.composition.graph import RealizationGraph
from uow.composition.host_node import DurableWAL
from uow.composition.mutation import (
    RuntimeMutationProposal,
    assemble_mutation_qc,
    sign_mutation_vote,
)
from uow.composition.policy import AdaptiveGraphProposer
from uow.composition.projection import project_semantics
from uow.state import WorldState

from .composition_reconstruction import apply_verified_runtime_mutation_reconstructed
from .types import EvidenceEntryRef


@dataclass(frozen=True)
class EnduranceStepResult:
    step: int
    ok: bool
    cost: float
    mutated: bool
    graph_id: str
    generation: int


class ShadowEnduranceAdaptiveRuntime:
    """A2.8 adaptive runtime on the reconstructed authority boundary."""

    def __init__(
        self,
        *,
        initial_graph: RealizationGraph,
        initial_binding: ActorBinding,
        candidate_graphs: Mapping[str, RealizationGraph],
        candidate_bindings: Mapping[str, ActorBinding],
        parent_contract: ParentContract,
        authority_keys: Mapping[str, str],
        objective: RuntimeObjectiveFunction,
        hysteresis: Optional[AntiThrashingHysteresis] = None,
        proposer: Optional[AdaptiveGraphProposer] = None,
        wal: Optional[DurableWAL] = None,
    ) -> None:
        self.active_graph = initial_graph
        self.active_binding = initial_binding
        self.candidate_graphs = dict(candidate_graphs)
        self.candidate_bindings = dict(candidate_bindings)
        self.parent_contract = parent_contract
        self.authority_keys = dict(authority_keys)
        self.objective = objective
        self.hysteresis = hysteresis or AntiThrashingHysteresis()
        self.proposer = proposer or AdaptiveGraphProposer()
        self.wal = wal

        self.generation = 0
        self.history = AuthoritativeHistory()
        self.lineage = TopologyLineage()
        self.shadow_evidence: List[EvidenceEntryRef] = []
        self.cost_history: List[float] = []
        self.cumulative_cost = 0.0
        self.completed_steps: set[int] = set()

        self.uncertified_mutations = 0
        self.stale_mutations = 0
        self.double_commits = 0
        self.wrong_commits = 0
        self.authority_inflations = 0
        self.lost_tasks = 0

        self.meta_state = WorldState(
            attributes={
                "__runtime_active_graph_hash__": initial_graph.compute_hash(),
                "__runtime_active_binding_hash__": initial_binding.compute_hash(),
                "__runtime_generation__": 0,
            },
            cursor="runtime-controller",
            status="RUNNING",
        )

    def _append_history(self, entry: HistoryEntry) -> bool:
        if self.wal is not None:
            self.wal.append(entry)
        ok, _reason = self.history.append(entry)
        return ok

    def _record_mutation_history(self, qc, generation_before: int) -> bool:
        entry = HistoryEntry(
            entry_id=f"shadow_mutation_{qc.qc_id}_{self.history.tip_sequence() + 1}",
            sequence_number=self.history.tip_sequence() + 1,
            prev_hash=self.history.tip_hash(),
            kind=HistoryEntryKind.GRAPH_SUBSTITUTION,
            author_node_id=qc.qc_id,
            generation=generation_before,
            payload={
                "candidate_graph_hash": qc.candidate_graph_hash,
                "candidate_binding_hash": qc.candidate_binding_hash,
                "signers": list(qc.signers),
                "qc_hash": qc.compute_hash(),
            },
            quorum_signatures=tuple(qc.signers),
        )
        return self._append_history(entry)

    def _record_task(self, step: int, cost: float) -> bool:
        if step in self.completed_steps:
            self.double_commits += 1
            return True
        entry = HistoryEntry(
            entry_id=f"shadow_task_{step}_{self.history.tip_sequence() + 1}",
            sequence_number=self.history.tip_sequence() + 1,
            prev_hash=self.history.tip_hash(),
            kind=HistoryEntryKind.AUTHORITATIVE_COMMIT,
            author_node_id="shadow_a2_endurance",
            generation=self.generation,
            payload={
                "step": step,
                "graph": self.active_graph.graph_id,
                "cost": cost,
            },
        )
        ok = self._append_history(entry)
        if ok:
            self.completed_steps.add(step)
        return ok

    def execute_step(self, step: int, env: EnvironmentalState) -> EnduranceStepResult:
        current_cost = self.objective.evaluate(self.active_graph, self.active_binding, env)
        current_broken = any(
            not env.actor_availability.get(actor_id, True)
            for actor_id in self.active_binding.node_to_actor.values()
        )

        best_id = None
        best_cost = current_cost
        for graph_id, graph in self.candidate_graphs.items():
            binding = self.candidate_bindings[graph_id]
            projection = project_semantics(graph, self.parent_contract)
            if not projection.conforms:
                continue
            cost = self.objective.evaluate(graph, binding, env)
            if cost < best_cost:
                best_cost = cost
                best_id = graph_id

        mutated = False
        if best_id is not None and best_id != self.active_graph.graph_id:
            should_mutate, reason = self.hysteresis.should_propose(
                current_cost=current_cost,
                candidate_cost=best_cost,
                current_broken=current_broken,
                current_step=step,
            )
            if should_mutate:
                candidate_graph = self.candidate_graphs[best_id]
                candidate_binding = self.candidate_bindings[best_id]
                generation_before = self.generation
                history_head = self.history.tip_hash()
                from_graph_id = self.active_graph.graph_id
                from_binding_id = self.active_binding.binding_id

                proposal = RuntimeMutationProposal(
                    proposal_id=f"shadow_mut_step{step}_{best_id}",
                    proposer_id=self.proposer.model_id,
                    parent_contract_id=self.parent_contract.contract_id,
                    parent_contract_hash=self.parent_contract.compute_hash(),
                    current_graph_hash=self.active_graph.compute_hash(),
                    current_binding_hash=self.active_binding.compute_hash(),
                    candidate_graph=candidate_graph,
                    candidate_binding=candidate_binding,
                    generation=self.generation,
                    history_head=history_head,
                    strategy="endurance_adaptive",
                    rationale=reason,
                )
                votes = [
                    sign_mutation_vote(
                        voter_id,
                        key,
                        proposal,
                        self.parent_contract,
                        history_head,
                        self.generation,
                    )
                    for voter_id, key in self.authority_keys.items()
                ]
                qc, _qc_reason = assemble_mutation_qc(proposal, votes, threshold=2)
                if qc is None:
                    self.uncertified_mutations += 1
                else:
                    # Refresh causal projection of the external authoritative history.
                    state_for_mutation = self.meta_state.with_attribute(
                        "__runtime_history_parent__", history_head
                    )
                    try:
                        new_meta, shadow_evidence = apply_verified_runtime_mutation_reconstructed(
                            state_for_mutation,
                            qc,
                            parent_contract=self.parent_contract,
                            candidate_graph=candidate_graph,
                            candidate_binding=candidate_binding,
                            authority_keys=self.authority_keys,
                            current_history_head=history_head,
                            current_generation=self.generation,
                            threshold=2,
                        )
                    except ValueError as exc:
                        if "STALE" in str(exc) or "GENERATION" in str(exc):
                            self.stale_mutations += 1
                        else:
                            self.uncertified_mutations += 1
                    else:
                        if not self._record_mutation_history(qc, generation_before):
                            self.lost_tasks += 1
                        else:
                            self.meta_state = new_meta
                            self.shadow_evidence.append(shadow_evidence)
                            self.active_graph = candidate_graph
                            self.active_binding = candidate_binding
                            self.generation += 1
                            self.hysteresis.record_mutation(step)
                            mutated = True

                            self.lineage.record_edge(
                                LineageEdge(
                                    edge_index=len(self.lineage.edges),
                                    step=step,
                                    from_graph_id=from_graph_id,
                                    to_graph_id=candidate_graph.graph_id,
                                    from_binding_id=from_binding_id,
                                    to_binding_id=candidate_binding.binding_id,
                                    generation_before=generation_before,
                                    generation_after=self.generation,
                                    history_head=history_head,
                                    proposal_id=proposal.proposal_id,
                                    rationale=reason,
                                    telemetry_hash=env.compute_hash(),
                                    candidate_graph_hash=candidate_graph.compute_hash(),
                                    candidate_binding_hash=candidate_binding.compute_hash(),
                                    conformance_verified=True,
                                    signers=qc.signers,
                                    qc_hash=qc.compute_hash(),
                                    observed_delta_j=current_cost - best_cost,
                                )
                            )

        final_cost = self.objective.evaluate(self.active_graph, self.active_binding, env)
        self.cost_history.append(final_cost)
        self.cumulative_cost += final_cost

        ok = self._record_task(step, final_cost)
        if not ok:
            self.lost_tasks += 1

        # Semantic invariant after every possible mutation.
        if not project_semantics(self.active_graph, self.parent_contract).conforms:
            self.wrong_commits += 1

        return EnduranceStepResult(
            step=step,
            ok=ok,
            cost=final_cost,
            mutated=mutated,
            graph_id=self.active_graph.graph_id,
            generation=self.generation,
        )

    def recover_history_from_wal(self) -> AuthoritativeHistory:
        if self.wal is None:
            raise ValueError("No WAL configured.")
        rebuilt = AuthoritativeHistory()
        for entry in self.wal.replay():
            ok, reason = rebuilt.append(entry)
            if not ok:
                raise ValueError(f"WAL replay failed: {reason}")
        return rebuilt
