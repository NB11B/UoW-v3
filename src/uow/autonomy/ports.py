"""Execution port abstractions separating autonomy planning from authoritative execution."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Protocol, runtime_checkable

from uow.application import ApplicationResult, ApplicationSpine, CursorPolicy, DEFAULT_APPLICATION_SPINE
from uow.contracts import UoW
from uow.state import WorldState
from uow.transactions.sequencer import CommitSequencer
from .model import AuthorityScope, CapabilityRegistry, WorkItem


@dataclass(frozen=True)
class ExecutionOutcome:
    """Outcome of attempting to execute a single WorkItem."""
    success: bool
    new_state: WorldState
    cost_incurred: float = 0.0
    energy_incurred: float = 0.0
    error_code: Optional[str] = None
    failed_work_id: Optional[str] = None
    evidence: Optional[Any] = None


@runtime_checkable
class ExecutionPort(Protocol):
    """Execution boundary protocol governing work execution."""

    @property
    def state(self) -> WorldState:
        """Current observable world state."""
        ...

    def execute(
        self,
        item: WorkItem,
        authority: AuthorityScope,
    ) -> ExecutionOutcome:
        """Execute a single proposed work item within authority scope."""
        ...


@runtime_checkable
class WorkItemCompiler(Protocol):
    """Domain-specific translation boundary lowering WorkItem into a native UoW."""

    def compile(
        self,
        item: WorkItem,
        state: WorldState,
    ) -> UoW:
        """Compile a domain-neutral WorkItem into a typed authoritative UoW."""
        ...


class Environment:
    """Simulation environment for qualification, testing, and exploratory execution."""

    def __init__(
        self,
        initial_state: WorldState,
        capability_registry: CapabilityRegistry,
        *,
        adversarial_events: Optional[Mapping[int, Callable[[Environment], None]]] = None,
    ) -> None:
        self.state = initial_state
        self.registry = capability_registry
        self.event_stream: dict[int, Callable[[Environment], None]] = dict(adversarial_events or {})
        self.step_counter = 0
        self.failed_capabilities: set[str] = set()

    def advance_step(self) -> None:
        self.step_counter += 1
        event = self.event_stream.get(self.step_counter)
        if event is not None:
            event(self)

    def execute_work_item(
        self,
        item: WorkItem,
        authority: AuthorityScope,
    ) -> ExecutionOutcome:
        self.advance_step()

        cap = self.registry.get(item.work_kind)
        if cap is None or cap.capability_id in self.failed_capabilities:
            return ExecutionOutcome(
                success=False,
                new_state=self.state,
                cost_incurred=0.0,
                energy_incurred=0.0,
                error_code="CAPABILITY_UNAVAILABLE",
                failed_work_id=item.work_id,
            )

        for scope in cap.required_authority:
            if not authority.permits(scope):
                return ExecutionOutcome(
                    success=False,
                    new_state=self.state,
                    cost_incurred=0.0,
                    energy_incurred=0.0,
                    error_code=f"UNAUTHORIZED_WORK_AUTHORITY:{scope}",
                    failed_work_id=item.work_id,
                )

        for pre in cap.preconditions:
            if not pre.satisfied_by(self.state):
                return ExecutionOutcome(
                    success=False,
                    new_state=self.state,
                    cost_incurred=cap.cost * 0.5,
                    energy_incurred=cap.energy * 0.5,
                    error_code=f"PRECONDITION_FAILED:{pre.attribute}",
                    failed_work_id=item.work_id,
                )

        new_attributes = dict(self.state.attributes)
        for eff in cap.effects:
            new_attributes[eff.attribute] = eff.value

        self.state = WorldState(attributes=new_attributes)

        return ExecutionOutcome(
            success=True,
            new_state=self.state,
            cost_incurred=cap.cost,
            energy_incurred=cap.energy,
        )


class SimulatedExecutionPort:
    """Realizes ExecutionPort over a simulated Environment."""

    def __init__(
        self,
        environment: Optional[Environment] = None,
        *,
        initial_state: Optional[WorldState] = None,
        capability_registry: Optional[CapabilityRegistry] = None,
        adversarial_events: Optional[Mapping[int, Callable[[Environment], None]]] = None,
    ) -> None:
        if environment is not None:
            self.environment = environment
        elif initial_state is not None:
            self.environment = Environment(
                initial_state=initial_state,
                capability_registry=capability_registry or CapabilityRegistry(),
                adversarial_events=adversarial_events,
            )
        else:
            raise ValueError("Either environment or initial_state must be provided.")

    @property
    def state(self) -> WorldState:
        return self.environment.state

    def execute(
        self,
        item: WorkItem,
        authority: AuthorityScope,
    ) -> ExecutionOutcome:
        return self.environment.execute_work_item(item, authority)


class ApplicationExecutionPort:
    """Production realization of ExecutionPort routing strictly through ApplicationSpine.

    Enforces the core architecture invariant:
        Autonomy proposes work -> WorkItemCompiler compiles native UoW ->
        ApplicationSpine executes through PROPOSE -> CERTIFY -> COMMIT.
    """

    def __init__(
        self,
        sequencer: CommitSequencer,
        compiler: WorkItemCompiler,
        *,
        spine: Optional[ApplicationSpine] = None,
        cursor_policy: CursorPolicy = CursorPolicy.DETACHED,
        cost_fn: Optional[Callable[[WorkItem, UoW], float]] = None,
        energy_fn: Optional[Callable[[WorkItem, UoW], float]] = None,
    ) -> None:
        self.sequencer = sequencer
        self.compiler = compiler
        self.spine = spine or DEFAULT_APPLICATION_SPINE
        self.cursor_policy = cursor_policy
        self.cost_fn = cost_fn
        self.energy_fn = energy_fn

    @property
    def state(self) -> WorldState:
        return self.sequencer.current_state

    def execute(
        self,
        item: WorkItem,
        authority: AuthorityScope,
    ) -> ExecutionOutcome:
        for scope in item.required_capabilities:
            if not authority.permits(scope):
                return ExecutionOutcome(
                    success=False,
                    new_state=self.state,
                    cost_incurred=0.0,
                    energy_incurred=0.0,
                    error_code=f"UNAUTHORIZED_WORK_AUTHORITY:{scope}",
                    failed_work_id=item.work_id,
                )

        try:
            uow = self.compiler.compile(item, self.state)
        except Exception as compile_err:
            return ExecutionOutcome(
                success=False,
                new_state=self.state,
                cost_incurred=0.0,
                energy_incurred=0.0,
                error_code=f"COMPILATION_ERROR:{type(compile_err).__name__}:{compile_err}",
                failed_work_id=item.work_id,
            )

        try:
            result: ApplicationResult = self.spine.execute(
                uow,
                self.sequencer,
                cursor_policy=self.cursor_policy,
            )
            cost = self.cost_fn(item, uow) if self.cost_fn else 1.0
            energy = self.energy_fn(item, uow) if self.energy_fn else 1.0
            return ExecutionOutcome(
                success=True,
                new_state=result.state,
                cost_incurred=cost,
                energy_incurred=energy,
                evidence=result.evidence,
            )
        except Exception as exec_err:
            return ExecutionOutcome(
                success=False,
                new_state=self.state,
                cost_incurred=0.0,
                energy_incurred=0.0,
                error_code=f"EXECUTION_REJECTED:{type(exec_err).__name__}:{exec_err}",
                failed_work_id=item.work_id,
            )


__all__ = [
    "ApplicationExecutionPort",
    "Environment",
    "ExecutionOutcome",
    "ExecutionPort",
    "SimulatedExecutionPort",
    "WorkItemCompiler",
]
