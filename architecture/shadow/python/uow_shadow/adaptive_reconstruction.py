"""R4 U15 portable adaptive-loop reconstruction on minimal shadow authority."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from uow.orchestration import (
    COMPLETION_PREFIX,
    SCHEDULER_ID,
    OrchestrationState,
    certify_materialization,
)
from uow.proposer.base import BaseProposer
from uow.proposer.fallback import DeterministicFallbackScheduler
from uow.proposer.judge import certify_proposal
from uow.proposer.observation import AdaptationObservation, create_adaptation_observation
from uow.proposer.types import TelemetryRecord
from uow.resources.policies import BaseSchedulingPolicy
from uow.resources.requirement import ResourceBoundTask, verify_requirement_binding
from uow.resources.runtime import (
    ResourceAwareCompletionMaterializer,
    ResourceAwareSchedulerMaterializer,
)
from uow.state import WorldState

from .reconstruction import ReconstructionResult, execute_one_reconstructed


class _ExplicitBatchPolicy(BaseSchedulingPolicy):
    def __init__(self, batch: Sequence[str]) -> None:
        self._batch = list(batch)

    def name(self) -> str:
        return "R4AdaptiveExplicitBatchPolicy"

    def select_schedule(self, ready_candidates, get_requirement, resources) -> List[str]:
        return list(self._batch)


@dataclass(frozen=True)
class AdaptiveReconstructionResult:
    final_state: WorldState
    evidence: Tuple[Any, ...]
    telemetry: Tuple[TelemetryRecord, ...]
    observations: Tuple[AdaptationObservation, ...]
    steps: int

    def evidence_root(self) -> str:
        return ReconstructionResult(
            self.final_state,
            tuple(self.evidence),
            self.steps,
        ).evidence_root()


def run_adaptive_orchestration_reconstructed(
    task_registry: Mapping[str, ResourceBoundTask],
    initial_state: WorldState,
    proposer: BaseProposer,
    *,
    fallback_scheduler: Optional[DeterministicFallbackScheduler] = None,
    max_steps: int = 10_000,
) -> AdaptiveReconstructionResult:
    """Run adaptive proposer -> judge -> shadow authority -> certified feedback.

    The learner never receives commit authority. Its only feedback is a
    cryptographically bound AdaptationObservation derived from the deterministic
    judge result and the actual post-transition authoritative state.
    """
    fallback = fallback_scheduler or DeterministicFallbackScheduler()
    state = initial_state
    evidence = []
    telemetry = []
    observations = []

    for step in range(max_steps):
        if state.status != "RUNNING" or state.cursor is None:
            return AdaptiveReconstructionResult(
                state,
                tuple(evidence),
                tuple(telemetry),
                tuple(observations),
                step,
            )

        cursor = state.cursor

        if cursor == SCHEDULER_ID:
            orch = OrchestrationState(state)
            ready = orch.ready_frontier()

            model_prop = None
            try:
                model_prop = proposer.propose(ready, task_registry, state)
            except Exception:
                model_prop = None

            judge_cert = certify_proposal(model_prop, ready, task_registry, state)
            telemetry.append(
                TelemetryRecord(
                    step=len(telemetry),
                    proposal=model_prop,
                    certificate=judge_cert,
                )
            )

            selected = (
                fallback.fallback_schedule(ready, task_registry, state)
                if judge_cert.fallback_triggered
                else judge_cert.accepted_tasks
            )

            scheduler = ResourceAwareSchedulerMaterializer(
                task_registry,
                _ExplicitBatchPolicy(selected),
            )
            materialized = scheduler.materialize(state)
            if not certify_materialization(scheduler, state, materialized):
                raise ValueError("Adaptive scheduler materialization failed certification.")

            before = state
            state, entry = execute_one_reconstructed(
                {materialized.uow.H.identity: materialized.uow},
                state,
            )
            evidence.append(entry)

            res_state = state.get("__resources__", {})
            res_util = {}
            if isinstance(res_state, Mapping):
                allocated = res_state.get("allocated", {})
                if isinstance(allocated, Mapping):
                    res_util = {
                        str(k): float(v)
                        for k, v in allocated.items()
                        if isinstance(v, (int, float))
                    }

            obs = create_adaptation_observation(
                pre_state=before,
                proposal=model_prop,
                certificate=judge_cert,
                post_state=state,
                committed=True,
                model_identity=(
                    proposer.model_identity()
                    if hasattr(proposer, "model_identity")
                    else None
                ),
                resource_utilization=res_util,
            )
            observations.append(obs)
            if hasattr(proposer, "observe_feedback"):
                proposer.observe_feedback(obs)
            continue

        if cursor.startswith(COMPLETION_PREFIX):
            task_id = cursor[len(COMPLETION_PREFIX):]
            completion = ResourceAwareCompletionMaterializer(task_id)
            materialized = completion.materialize(state)
            if not certify_materialization(completion, state, materialized):
                raise ValueError("Adaptive completion materialization failed certification.")
            active_uow = materialized.uow
        else:
            if cursor not in task_registry:
                raise KeyError(f"Cursor references unknown adaptive domain task {cursor!r}.")
            bound = task_registry[cursor]
            if not verify_requirement_binding(bound):
                raise ValueError(f"Requirement binding violation for domain task {cursor!r}.")
            active_uow = bound.uow

        state, entry = execute_one_reconstructed(
            {active_uow.H.identity: active_uow},
            state,
        )
        evidence.append(entry)

    raise RuntimeError(f"Adaptive reconstruction step budget {max_steps} exceeded.")
