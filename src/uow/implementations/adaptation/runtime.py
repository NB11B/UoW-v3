"""Production proposer/adaptation orchestration implementation."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ...application import DEFAULT_APPLICATION_SPINE, CursorPolicy
from ...orchestration import (
    COMPLETION_PREFIX,
    SCHEDULER_ID,
    OrchestrationState,
    certify_materialization,
)
from ...resources.policies import BaseSchedulingPolicy
from ...resources.requirement import ResourceBoundTask, verify_requirement_binding
from ..resources.runtime import (
    ResourceAwareCompletionMaterializer,
    ResourceAwareSchedulerMaterializer,
)
from ...state import WorldState
from ...transactions import CommitSequencer, DeterministicSequencer
from ...proposer.base import BaseProposer
from ...proposer.fallback import DeterministicFallbackScheduler
from ...proposer.judge import certify_proposal
from ...proposer.observation import AdaptationObservation, create_adaptation_observation
from ...proposer.types import ModelProposal, ProposalCertificate, TelemetryRecord


class _ExplicitBatchPolicy(BaseSchedulingPolicy):
    """Adapter policy presenting an explicit certified candidate batch to the scheduler materializer."""

    def __init__(self, batch: Sequence[str]) -> None:
        self._batch = list(batch)

    def name(self) -> str:
        return "ExplicitBatchPolicy"

    def select_schedule(
        self,
        ready_candidates: Sequence[str],
        get_requirement: Any,
        resources: Any,
    ) -> List[str]:
        return list(self._batch)


class ProposerOrchestrationEngine:
    """Autonomous runtime engine connecting stochastic or learned proposers to deterministic authority.

    The model proposer suggests candidate schedules.
    The deterministic Judge strictly certifies and filters each task against:
    - State hash and sequence freshness (Gate U14.6)
    - Dependency readiness (Gate U14.3)
    - OCC conflict freedom in batch (Gate U14.4)
    - Resource capacity bounds (Gate U14.5)

    Any proposer failure, timeout, or empty accepted batch triggers deterministic fallback (Gate U14.7).
    The deterministic fallback provides a certified deterministic schedule whenever a legal ready
    task exists; correctness does not depend on proposer availability.
    All proposals and decisions are recorded in hash-bound telemetry (Gate U14.8).
    """

    def __init__(
        self,
        proposer: BaseProposer,
        fallback_scheduler: Optional[DeterministicFallbackScheduler] = None,
    ) -> None:
        self.proposer = proposer
        self.fallback_scheduler = fallback_scheduler or DeterministicFallbackScheduler()
        self.telemetry: List[TelemetryRecord] = []
        self.observations: List[AdaptationObservation] = []

    def certify_proposal(
        self,
        proposal: Optional[ModelProposal],
        ready_tasks: Sequence[str],
        graph: Mapping[str, Any],
        state: WorldState,
    ) -> ProposalCertificate:
        """Deterministic Judge evaluating candidate proposals against legality invariants."""
        return certify_proposal(proposal, ready_tasks, graph, state)

    def run_dag(
        self,
        task_registry: Mapping[str, ResourceBoundTask],
        initial_state: WorldState,
        *,
        sequencer: Optional[CommitSequencer] = None,
        max_steps: int = 10_000,
    ) -> Tuple[WorldState, CommitSequencer, List[TelemetryRecord]]:
        """Executes a resource-bound DAG driven by model proposals and certified fallback."""
        seq: CommitSequencer = sequencer or DeterministicSequencer(initial_state)

        for _ in range(max_steps):
            state = seq.current_state
            if state.status != "RUNNING" or state.cursor is None:
                return state, seq, self.telemetry

            cursor = state.cursor

            # 1. Scheduler Frontier Evaluation
            if cursor == SCHEDULER_ID:
                orch = OrchestrationState(state)
                ready_frontier = orch.ready_frontier()

                # Step 1a: Query Model Proposer (safely isolated from exceptions/crashes)
                model_prop: Optional[ModelProposal] = None
                try:
                    model_prop = self.proposer.propose(ready_frontier, task_registry, state)
                except Exception:
                    model_prop = None

                # Step 1b: Deterministic Judge Evaluation
                cert = self.certify_proposal(model_prop, ready_frontier, task_registry, state)
                self.telemetry.append(
                    TelemetryRecord(step=len(self.telemetry), proposal=model_prop, certificate=cert)
                )

                # Step 1c: Dispatch Selection (Candidate Batch vs. Deterministic Fallback)
                if cert.fallback_triggered:
                    selected_batch = self.fallback_scheduler.fallback_schedule(
                        ready_frontier, task_registry, state
                    )
                else:
                    selected_batch = cert.accepted_tasks

                # Step 1d: Certified Scheduler Materialization & Atomic OCC Commit
                scheduler_mat = ResourceAwareSchedulerMaterializer(
                    task_registry, _ExplicitBatchPolicy(selected_batch)
                )
                before = seq.current_state
                materialized = scheduler_mat.materialize(before)
                if not certify_materialization(scheduler_mat, before, materialized):
                    raise ValueError("Scheduler materialization failed certification.")

                DEFAULT_APPLICATION_SPINE.execute(
                    materialized.uow,
                    seq,
                    cursor_policy=CursorPolicy.OWNED,
                )

                after = seq.current_state
                # Emit AdaptationObservation to telemetry and adaptive proposer (Gate U15.2)
                res_state = after.get("__resources__", {})
                res_util: Dict[str, float] = {}
                if isinstance(res_state, dict):
                    res_util = {
                        str(k): float(v)
                        for k, v in res_state.get("allocated", {}).items()
                        if isinstance(v, (int, float))
                    }
                obs = create_adaptation_observation(
                    pre_state=before,
                    proposal=model_prop,
                    certificate=cert,
                    post_state=after,
                    committed=True,
                    resource_utilization=res_util,
                )
                self.observations.append(obs)
                if hasattr(self.proposer, "observe_feedback"):
                    try:
                        self.proposer.observe_feedback(obs)
                    except Exception:
                        pass
                continue

            # 2. Task Completion Evaluation
            if cursor.startswith(COMPLETION_PREFIX):
                task_id = cursor[len(COMPLETION_PREFIX):]
                comp_mat = ResourceAwareCompletionMaterializer(task_id)
                before = seq.current_state
                materialized = comp_mat.materialize(before)
                if not certify_materialization(comp_mat, before, materialized):
                    raise ValueError("Completion materialization failed certification.")

                DEFAULT_APPLICATION_SPINE.execute(
                    materialized.uow,
                    seq,
                    cursor_policy=CursorPolicy.OWNED,
                )
                continue

            # 3. Domain Task Execution
            if cursor not in task_registry:
                raise KeyError(f"Cursor references unknown domain task {cursor!r}.")

            bound_task = task_registry[cursor]
            if not verify_requirement_binding(bound_task):
                raise ValueError(f"Requirement binding violation for domain task {cursor!r}.")

            DEFAULT_APPLICATION_SPINE.execute(
                bound_task.uow,
                seq,
                cursor_policy=CursorPolicy.OWNED,
            )

        raise RuntimeError(f"Step budget {max_steps} exceeded in proposer orchestration.")


def run_proposer_orchestration(
    task_registry: Mapping[str, ResourceBoundTask],
    initial_state: WorldState,
    proposer: BaseProposer,
    *,
    fallback_scheduler: Optional[DeterministicFallbackScheduler] = None,
    sequencer: Optional[CommitSequencer] = None,
    max_steps: int = 10_000,
) -> Tuple[WorldState, CommitSequencer, List[TelemetryRecord]]:
    """Runs proposer orchestration with deterministic judge and fallback."""
    engine = ProposerOrchestrationEngine(proposer, fallback_scheduler=fallback_scheduler)
    return engine.run_dag(task_registry, initial_state, sequencer=sequencer, max_steps=max_steps)
