"""Canonical timing-independence qualification.

This module does not add a clock service to UoW. It reproduces the original
Orchestrator invariant using the canonical runtime:

- local timing domains are independently owned;
- causal/dependency order, not clock order, governs legality;
- permissible local clock drift does not change certified computational state;
- the core/orchestration path does not require a wall clock;
- deliberately shared mutable clock ownership is detected by qualification.

The stronger problem of synchronizing arbitrary distributed physical clocks is
outside this claim.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import random
from typing import Dict, Mapping, Tuple
from unittest.mock import patch

from uow import (
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    OrchestrationState,
    Route,
    Timing,
    WorldState,
    create_initial_orchestration_state,
    make_domain_task,
    run_orchestration,
)


@dataclass
class SyntheticClock:
    """Qualification-only mutable local clock."""

    owner: str
    value: float
    rate: float

    def read(self, local_step: int = 0) -> float:
        return self.value + self.rate * local_step

    def advance(self, delta: float) -> None:
        self.value += delta


@dataclass(frozen=True)
class TimingQualificationResult:
    drift_trials: int
    baseline_state_hash: str
    baseline_transition_ids: Tuple[str, ...]
    state_invariant: bool
    transition_order_invariant: bool
    causal_order_dominates_clock_order: bool
    shared_clock_mutant_rejected: bool
    nested_clock_isolation: bool
    wall_clock_independent: bool


def validate_independent_clock_ownership(
    bindings: Mapping[str, SyntheticClock],
) -> None:
    """Reject aliasing of one mutable clock across independently owned roles."""

    seen_objects: Dict[int, str] = {}
    for role, clock in bindings.items():
        if clock.owner != role:
            raise ValueError(
                f"Clock owner mismatch: role {role!r} is bound to {clock.owner!r}."
            )
        object_id = id(clock)
        if object_id in seen_objects:
            raise ValueError(
                "Shared mutable clock detected between "
                f"{seen_objects[object_id]!r} and {role!r}."
            )
        seen_objects[object_id] = role


def make_clock_bindings(seed: int) -> Dict[str, SyntheticClock]:
    """Create independently drifting clocks for UoW timing roles."""

    rng = random.Random(seed)
    roles = (
        "parent:lifecycle",
        "parent:realization",
        "parent:evidence",
        "parent:port",
        "child:lifecycle",
        "child:realization",
        "child:evidence",
        "child:port",
    )
    return {
        role: SyntheticClock(
            owner=role,
            value=rng.uniform(-1_000_000.0, 1_000_000.0),
            rate=rng.uniform(0.01, 100.0),
        )
        for role in roles
    }


def _timed_diamond(seed: int):
    rng = random.Random(seed)
    dependencies = {
        "A": (),
        "B": ("A",),
        "C": ("A",),
        "D": ("B", "C"),
    }
    tasks = {
        "A": make_domain_task(
            "A",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 10),))],
        ),
        "B": make_domain_task(
            "B",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 20),))],
        ),
        "C": make_domain_task(
            "C",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r1", 30),))],
        ),
        "D": make_domain_task(
            "D",
            [
                Route(
                    Guard(GuardOp.ALWAYS),
                    (
                        Mutation(MutationOp.ADD, "r0", 5),
                        Mutation(MutationOp.ADD, "r1", 5),
                    ),
                )
            ],
        ),
    }

    # Timing metadata varies independently by UoW. It is deliberately not an
    # execution authority. Causal legality remains encoded by the DAG.
    tasks = {
        task_id: replace(
            uow,
            T=Timing(
                clock_owner=f"uow:{task_id}",
                causal_epoch=rng.randint(0, 2**31 - 1),
            ),
        )
        for task_id, uow in tasks.items()
    }

    initial = create_initial_orchestration_state(
        ["A", "B", "C", "D"],
        dependencies,
        attributes={"r0": 0, "r1": 0},
    )
    return dependencies, tasks, initial


def _run_timed_diamond(seed: int):
    _dependencies, tasks, initial = _timed_diamond(seed)
    final, sequencer = run_orchestration(tasks, initial)
    identities = tuple(record.uow_id for record in sequencer.ledger.records)
    return final, sequencer, identities


def run_clock_drift_campaign(trials: int = 1_000) -> Tuple[bool, bool, str, Tuple[str, ...]]:
    """Perturb local timing metadata over many seeds and compare certified behavior."""

    baseline, baseline_seq, baseline_ids = _run_timed_diamond(0)
    expected_domain = (
        baseline.require("r0"),
        baseline.require("r1"),
        tuple(baseline.get("__completed__")),
        baseline.status,
        baseline.sequence,
    )

    state_invariant = True
    order_invariant = True

    for seed in range(1, trials + 1):
        final, sequencer, identities = _run_timed_diamond(seed)
        observed_domain = (
            final.require("r0"),
            final.require("r1"),
            tuple(final.get("__completed__")),
            final.status,
            final.sequence,
        )
        if observed_domain != expected_domain:
            state_invariant = False
            break
        if identities != baseline_ids:
            order_invariant = False
            break
        if not sequencer.ledger.verify_integrity():
            state_invariant = False
            break

    return (
        state_invariant,
        order_invariant,
        baseline.state_hash,
        baseline_ids,
    )


def causal_order_beats_local_clock_order() -> bool:
    """A dependency must win even when the dependent task's clock reads earlier."""

    dependencies, tasks, initial = _timed_diamond(7)

    # Deliberately make B appear "earlier" and A "later" in local timing
    # metadata. The DAG still requires A before B.
    tasks = dict(tasks)
    tasks["A"] = replace(tasks["A"], T=Timing(clock_owner="uow:A", causal_epoch=999_999))
    tasks["B"] = replace(tasks["B"], T=Timing(clock_owner="uow:B", causal_epoch=1))

    final, sequencer = run_orchestration(tasks, initial)
    identities = [record.uow_id for record in sequencer.ledger.records]

    return (
        final.status == "HALTED"
        and identities.index("A") < identities.index("B")
        and tuple(final.get("__completed__")) == ("A", "B", "C", "D")
    )


def shared_clock_mutant_is_rejected() -> bool:
    """A deliberately aliased mutable clock must fail the ownership qualification."""

    shared = SyntheticClock("parent:lifecycle", 0.0, 1.0)
    bindings = {
        "parent:lifecycle": shared,
        # Mutant: same object is illegally shared and its ownership label is
        # rewritten only conceptually, not structurally.
        "child:lifecycle": shared,
    }
    try:
        validate_independent_clock_ownership(bindings)
    except ValueError:
        return True
    return False


def nested_clock_isolation_holds(seed: int = 20260922) -> bool:
    """Advancing a child-local clock must not mutate any parent-local clock."""

    bindings = make_clock_bindings(seed)
    validate_independent_clock_ownership(bindings)

    parent_before = {
        role: clock.read()
        for role, clock in bindings.items()
        if role.startswith("parent:")
    }

    bindings["child:lifecycle"].advance(10_000.0)
    bindings["child:realization"].advance(-123.5)

    parent_after = {
        role: clock.read()
        for role, clock in bindings.items()
        if role.startswith("parent:")
    }
    return parent_before == parent_after


def wall_clock_is_not_required() -> bool:
    """Run canonical orchestration while common host-clock APIs are forbidden."""

    _deps, tasks, initial = _timed_diamond(42)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Canonical orchestration attempted to consult a host wall clock.")

    with (
        patch("time.time", side_effect=forbidden),
        patch("time.monotonic", side_effect=forbidden),
        patch("time.perf_counter", side_effect=forbidden),
        patch("time.sleep", side_effect=forbidden),
    ):
        final, sequencer = run_orchestration(tasks, initial)

    return (
        final.status == "HALTED"
        and final.require("r0") == 35
        and final.require("r1") == 35
        and sequencer.ledger.verify_integrity()
    )


def run_timing_independence_campaign(trials: int = 1_000) -> TimingQualificationResult:
    """Execute the canonical timing-independence fidelity campaign."""

    state_ok, order_ok, baseline_hash, baseline_ids = run_clock_drift_campaign(trials)

    return TimingQualificationResult(
        drift_trials=trials,
        baseline_state_hash=baseline_hash,
        baseline_transition_ids=baseline_ids,
        state_invariant=state_ok,
        transition_order_invariant=order_ok,
        causal_order_dominates_clock_order=causal_order_beats_local_clock_order(),
        shared_clock_mutant_rejected=shared_clock_mutant_is_rejected(),
        nested_clock_isolation=nested_clock_isolation_holds(),
        wall_clock_independent=wall_clock_is_not_required(),
    )
