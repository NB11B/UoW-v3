"""Autonomous execution engine connecting external proposers to deterministic authority (Gate U14)."""
from __future__ import annotations

from typing import Any, List, Mapping, Optional, Sequence, Tuple

from ..contracts import UoW
from ..engine import CertificateResult, Proposal, certify, propose
from ..orchestration import (
    COMPLETION_PREFIX,
    SCHEDULER_ID,
    OrchestrationState,
    certify_materialization,
)
from ..resources.policies import BaseSchedulingPolicy
from ..resources.requirement import ResourceBoundTask, verify_requirement_binding
from ..resources.runtime import (
    ResourceAwareCompletionMaterializer,
    ResourceAwareSchedulerMaterializer,
)
from ..state import WorldState
from ..transactions import (
    CommitSequencer,
    DeterministicSequencer,
    create_transaction_descriptor,
)
from .base import BaseProposer
from .fallback import DeterministicFallbackScheduler
from .judge import certify_proposal
from .types import ModelProposal, ProposalCertificate, TelemetryRecord


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

                proposal = propose(materialized.uow, before)
                core_cert = certify(materialized.uow, before, proposal)
                if not core_cert.is_valid:
                    raise ValueError(f"Core certifier rejected scheduler UoW: {core_cert.rejection_reason}")

                tx = create_transaction_descriptor(materialized.uow, before)
                seq.commit(materialized.uow, proposal, tx, core_cert)
                continue

            # 2. Task Completion Evaluation
            if cursor.startswith(COMPLETION_PREFIX):
                task_id = cursor[len(COMPLETION_PREFIX):]
                comp_mat = ResourceAwareCompletionMaterializer(task_id)
                before = seq.current_state
                materialized = comp_mat.materialize(before)
                if not certify_materialization(comp_mat, before, materialized):
                    raise ValueError("Completion materialization failed certification.")

                proposal = propose(materialized.uow, before)
                core_cert = certify(materialized.uow, before, proposal)
                if not core_cert.is_valid:
                    raise ValueError(f"Core certifier rejected completion UoW: {core_cert.rejection_reason}")

                tx = create_transaction_descriptor(materialized.uow, before)
                seq.commit(materialized.uow, proposal, tx, core_cert)
                continue

            # 3. Domain Task Execution
            if cursor not in task_registry:
                raise KeyError(f"Cursor references unknown domain task {cursor!r}.")

            bound_task = task_registry[cursor]
            if not verify_requirement_binding(bound_task):
                raise ValueError(f"Requirement binding violation for domain task {cursor!r}.")

            before = seq.current_state
            proposal = propose(bound_task.uow, before)
            core_cert = certify(bound_task.uow, before, proposal)
            if not core_cert.is_valid:
                raise ValueError(f"Core certifier rejected domain task {cursor!r}: {core_cert.rejection_reason}")

            tx = create_transaction_descriptor(bound_task.uow, before)
            seq.commit(bound_task.uow, proposal, tx, core_cert)

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
