"""Public API runtime facade for UoW Autonomy."""
from __future__ import annotations

from typing import Optional, Tuple

from .controller import AutonomousClosureController, ClosureResult, ClosureState
from .model import (
    AutonomyBudget,
    AutonomyRequest,
    AutonomyResult,
    CapabilityRegistry,
    CapabilitySpec,
    GoalSpec,
    TerminalDisposition,
    capability_spec_to_descriptor,
    goal_spec_to_envelope,
)
from .ports import ExecutionPort, WorkItemCompiler


class AutonomousRuntime:
    """Production runtime facade for autonomous goal execution.

    Composes planning, metacognition, bounded repair, adaptation, and
    application execution ports behind a clean high-level API.
    """

    def __init__(
        self,
        execution_port: ExecutionPort,
        *,
        work_compiler: Optional[WorkItemCompiler] = None,
        capability_registry: Optional[CapabilityRegistry] = None,
        budget: Optional[AutonomyBudget] = None,
        max_planning_depth: Optional[int] = None,
        max_planning_budget: Optional[int] = None,
        max_stagnation_steps: int = 4,
    ) -> None:
        self.execution_port = execution_port
        self.work_compiler = work_compiler
        self.capability_registry = capability_registry
        self.budget = budget or AutonomyBudget()
        self.max_planning_depth = max_planning_depth
        self.max_planning_budget = max_planning_budget
        self.max_stagnation_steps = max_stagnation_steps

    def run(self, request: AutonomyRequest) -> AutonomyResult:
        """Execute an autonomy request through the governed runtime."""
        # 1. Establish capability registry
        if self.capability_registry is not None:
            registry = self.capability_registry
        else:
            descriptors = tuple(capability_spec_to_descriptor(c) for c in request.capabilities)
            registry = CapabilityRegistry(descriptors)

        from .ports import SimulatedExecutionPort
        if isinstance(self.execution_port, SimulatedExecutionPort):
            if not self.execution_port.environment.registry.all_capabilities():
                self.execution_port.environment.registry = registry

        # 2. Lower goal specification to internal envelope
        goal = goal_spec_to_envelope(request.goal, request.initial_state)

        # 3. Resolve budget
        budget = request.budget or self.budget

        # 4. Instantiate and execute controller
        controller = AutonomousClosureController(
            registry,
            budget=budget,
            max_planning_depth=self.max_planning_depth,
            max_planning_budget=self.max_planning_budget,
            max_stagnation_steps=self.max_stagnation_steps,
        )

        closure_res: ClosureResult = controller.run(goal, self.execution_port)

        # 5. Map terminal disposition
        if closure_res.terminal_state == ClosureState.COMPLETE:
            disposition = TerminalDisposition.COMPLETE
        elif closure_res.deficit_certificate is not None or "GOAL_UNREPRESENTABLE" in closure_res.rejection_reasons:
            disposition = TerminalDisposition.UNREPRESENTABLE
        elif any("STAGNATION" in r for r in closure_res.rejection_reasons):
            disposition = TerminalDisposition.STAGNATED
        elif closure_res.terminal_state == ClosureState.FAILED:
            disposition = TerminalDisposition.FAILED
        else:
            disposition = TerminalDisposition.ESCALATED

        diagnostic = closure_res.rejection_reasons[0] if closure_res.rejection_reasons else None
        evidence: Tuple[object, ...] = ()
        if closure_res.closure_certificate is not None:
            evidence = (closure_res.closure_certificate,)

        return AutonomyResult(
            success=closure_res.success,
            disposition=disposition,
            final_state=self.execution_port.state,
            evidence=evidence,
            diagnostic=diagnostic,
            transitions=closure_res.transitions,
        )


__all__ = [
    "AutonomousRuntime",
    "AutonomyBudget",
    "AutonomyRequest",
    "AutonomyResult",
    "CapabilitySpec",
    "GoalSpec",
    "TerminalDisposition",
]
