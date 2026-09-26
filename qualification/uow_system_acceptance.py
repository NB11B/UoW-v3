#!/usr/bin/env python3
"""
Repo-native Canonical UoW System Acceptance Campaign
====================================================

Run from the root of NB11B/UoW after the proposer seam is present
(either merged to main or on curation/proposer-tfwr-v0).

This runner deliberately uses the repository's real APIs rather than the
standalone reference backend.

Fast qualification:
    python qualification/uow_system_acceptance.py

Stronger local stress:
    python qualification/uow_system_acceptance.py --step-programs 1000 --steps-per-program 20 --terminating-runs 500
"""
from __future__ import annotations

from dataclasses import replace
import argparse
from pathlib import Path
import sys
import tempfile
from typing import Dict, List, Mapping, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
for p in (str(REPO_ROOT), str(REPO_ROOT / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

from foundations.universal_computation.bounded_control import run_bounded_vs_extensible_experiment
from foundations.universal_computation.differential_campaign import (
    run_differential_step_campaign,
    run_terminating_run_campaign,
)
from foundations.universal_computation.reference_minsky import TRANSFER_R0_TO_R1
from foundations.universal_computation.uow_minsky_compiler import (
    compile_minsky,
    create_initial_world_state,
)

from uow import (
    ALL_MATRIX_CELLS,
    DeterministicSequencer,
    EvidenceLedger,
    Guard,
    GuardOp,
    MatrixCell,
    ModelProposal,
    Mutation,
    MutationOp,
    OrchestrationState,
    Proposal,
    ProposerOrchestrationEngine,
    RandomProposer,
    ResourceBoundTask,
    ResourceRequirement,
    ResourceState,
    Route,
    SagaCoordinator,
    SagaStep,
    Successor,
    WALSequencer,
    WorkCategory,
    WorldState,
    certify,
    certify_proposal,
    create_effect_descriptor,
    create_initial_orchestration_state,
    get_effects_map,
    get_sagas_map,
    make_resource_domain_task,
    propose,
    run,
    set_authoritative_resource_state,
)
from uow.effects import EffectRunner, EffectStatus, MockExternalClient
from qualification.timing_independence import run_timing_independence_campaign


class Acceptance:
    def __init__(self) -> None:
        self.rows: List[Tuple[str, str, str, str]] = []

    def check(self, section: str, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append((section, name, "PASS" if ok else "FAIL", detail))
        if not ok:
            raise AssertionError(f"{section}: {name}: {detail}")

    def report(self) -> str:
        out = [
            "UoW CANONICAL REPOSITORY ACCEPTANCE",
            "=" * 35,
            "EVIDENCE LEVEL: PORTABLE",
            "No physical accelerator, live external service, or distributed clock is claimed by this campaign.",
            "",
        ]
        current = None
        for section, name, status, detail in self.rows:
            if section != current:
                if current is not None:
                    out.append("")
                current = section
                out.append(section.upper())
            suffix = f" — {detail}" if detail else ""
            out.append(f"[{status}] {name}{suffix}")
        passed = sum(1 for _, _, s, _ in self.rows if s == "PASS")
        out += [
            "",
            f"RESULT: {passed}/{len(self.rows)} qualification assertions passed",
            "",
            "CANONICAL CLAIM:",
            "The extracted UoW repository behaved as specified by this portable acceptance campaign.",
            "Physical hardware/service claims require separate substrate-qualified evidence.",
        ]
        return "\n".join(out)


def build_acceptance_dag() -> Tuple[Mapping[str, ResourceBoundTask], WorldState]:
    # These are logical resource-capacity tokens used to exercise scheduling
    # semantics. They are not observations of physical CPU/GPU/NPU hardware.
    caps = {
        "cpu_cores": 8,
        "ram_units": 16,
        "gpu_slots": 1,
        "npu_slots": 2,
        "energy_budget": 2000,
        "cost": 1000,
    }
    registry: Dict[str, ResourceBoundTask] = {
        "A": make_resource_domain_task(
            "A",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "x", 10),), Successor.halt())],
            ResourceRequirement(cpu_cores=2, ram_units=4, priority=1, energy_budget=50),
        ),
        "B": make_resource_domain_task(
            "B",
            [Route(Guard(GuardOp.NE, "x", -999), (Mutation(MutationOp.ADD, "y", 20),), Successor.halt())],
            ResourceRequirement(cpu_cores=2, ram_units=4, priority=2, energy_budget=50),
        ),
        "C": make_resource_domain_task(
            "C",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "z", 30),), Successor.halt())],
            ResourceRequirement(cpu_cores=4, ram_units=8, gpu_slots=1, priority=3, energy_budget=100),
        ),
        "D": make_resource_domain_task(
            "D",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "w", 40),), Successor.halt())],
            ResourceRequirement(cpu_cores=1, ram_units=2, npu_slots=1, priority=1, deadline=10, energy_budget=30),
        ),
        "E": make_resource_domain_task(
            "E",
            [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "q", 50),), Successor.halt())],
            ResourceRequirement(cpu_cores=1, ram_units=2, priority=5, energy_budget=20),
        ),
    }
    deps = {
        "B": ["A"],
        "C": ["A"],
        "D": ["B", "C"],
        "E": ["D"],
    }
    base = create_initial_orchestration_state(
        queue=["A", "B", "C", "D", "E"],
        dependencies=deps,
        attributes={"x": 0, "y": 0, "z": 0, "w": 0, "q": 0},
    )
    return registry, set_authoritative_resource_state(base, ResourceState(capacities=caps))


def foundation_gate(a: Acceptance, args: argparse.Namespace) -> None:
    stats = run_differential_step_campaign(
        n_programs=args.step_programs,
        steps_per_program=args.steps_per_program,
        seed=20260922,
    )
    a.check(
        "foundation",
        "randomized single-step reference/native equivalence",
        stats.failed_checks == 0 and stats.matched_single_steps == stats.total_single_step_checks,
        f"{stats.total_single_step_checks:,} transitions",
    )

    term = run_terminating_run_campaign(
        n_runs=args.terminating_runs,
        seed=20260922,
        max_steps=5000,
    )
    a.check(
        "foundation",
        "terminating whole-program equivalence",
        term.failed_checks == 0 and term.matched_program_runs == term.total_program_runs,
        f"{term.total_program_runs:,} programs",
    )

    # Semantic-cell orthogonality: same computational result and depth.
    cells = [
        MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA),
        MatrixCell(WorkCategory.PEOPLE, WorkCategory.DEVICES),
    ]
    results = []
    for cell in cells:
        graph = compile_minsky(TRANSFER_R0_TO_R1, matrix_cell=cell)
        out, ledger = run(graph, create_initial_world_state(r0=16, r1=7))
        results.append((out.get("r0"), out.get("r1"), out.sequence, len(ledger.records)))
    dynamic_graph = compile_minsky(
        TRANSFER_R0_TO_R1,
        matrix_cell=lambda pc: ALL_MATRIX_CELLS[pc % len(ALL_MATRIX_CELLS)],
    )
    out, ledger = run(dynamic_graph, create_initial_world_state(r0=16, r1=7))
    results.append((out.get("r0"), out.get("r1"), out.sequence, len(ledger.records)))
    a.check("foundation", "semantic-cell computational orthogonality", len(set(results)) == 1)

    bounded = run_bounded_vs_extensible_experiment(bit_width=8)
    a.check(
        "foundation",
        "bounded-state negative control",
        bounded["period"] == 256
        and bounded["bounded_is_periodic"] is True
        and bounded["extensible_is_periodic"] is False,
    )

    huge = (1 << 1024) + 17
    graph = compile_minsky(TRANSFER_R0_TO_R1)
    out, _ = run(graph, create_initial_world_state(r0=1, r1=huge))
    a.check("foundation", "extensible memory beyond 1024 bits", out.get("r1") == huge + 1)

    # Core tamper rejection.
    graph = compile_minsky(TRANSFER_R0_TO_R1)
    state = create_initial_world_state(r0=3, r1=0)
    uow = graph[state.cursor]
    prop = propose(uow, state)
    forged = replace(prop, proposed_state=prop.proposed_state.with_attribute("r0", 999))
    a.check("foundation", "forged core proposal rejected", certify(uow, state, forged).is_valid is False)



def timing_gate(a: Acceptance, args: argparse.Namespace) -> None:
    """Reproduce the original local-clock independence invariant."""

    result = run_timing_independence_campaign(args.timing_seeds)
    a.check(
        "timing independence",
        "independent clock drift preserves certified domain state",
        result.state_invariant,
        f"{result.drift_trials:,} drift realizations",
    )
    a.check(
        "timing independence",
        "transition ordering is invariant to local clock drift",
        result.transition_order_invariant,
    )
    a.check(
        "timing independence",
        "causal dependency order dominates local clock readings",
        result.causal_order_dominates_clock_order,
    )
    a.check(
        "timing independence",
        "shared mutable clock mutant is rejected",
        result.shared_clock_mutant_rejected,
    )
    a.check(
        "timing independence",
        "nested parent/child clocks remain isolated",
        result.nested_clock_isolation,
    )
    a.check(
        "timing independence",
        "canonical orchestration requires no host wall clock",
        result.wall_clock_independent,
    )


def authority_gate(a: Acceptance) -> Tuple[Mapping[str, ResourceBoundTask], WorldState]:
    registry, state = build_acceptance_dag()
    ready = OrchestrationState(state).ready_frontier()

    proposer = RandomProposer(seed=17)
    before = state.state_hash
    _ = proposer.propose(ready, registry, state)
    a.check("authority", "proposer has zero authority", state.state_hash == before)

    stale = ModelProposal(
        model_id="acceptance",
        model_version="1",
        input_state_hash="stale",
        input_sequence=state.sequence,
        input_epoch=state.sequence,
        candidate_schedule=("A",),
    )
    before = state.state_hash
    stale_cert = certify_proposal(stale, ready, registry, state)
    a.check(
        "authority",
        "stale proposal rejected without state mutation",
        not stale_cert.is_valid and state.state_hash == before,
    )

    dependency_bad = ModelProposal(
        model_id="acceptance",
        model_version="1",
        input_state_hash=state.state_hash,
        input_sequence=state.sequence,
        input_epoch=state.sequence,
        candidate_schedule=("E",),
    )
    dep_cert = certify_proposal(dependency_bad, ready, registry, state)
    a.check(
        "authority",
        "unsatisfied dependency rejected",
        "E" in dep_cert.rejected_tasks
        and "DEPENDENCY_UNSATISFIED" in dep_cert.rejected_tasks["E"],
    )

    # Deliberate OCC pair outside the main DAG.
    conflict = dict(registry)
    conflict["X1"] = make_resource_domain_task(
        "X1",
        [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "shared", 1),), Successor.halt())],
        ResourceRequirement(cpu_cores=1, ram_units=1),
    )
    conflict["X2"] = make_resource_domain_task(
        "X2",
        [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "shared", 2),), Successor.halt())],
        ResourceRequirement(cpu_cores=1, ram_units=1),
    )
    occ_prop = ModelProposal(
        model_id="acceptance",
        model_version="1",
        input_state_hash=state.state_hash,
        input_sequence=state.sequence,
        input_epoch=state.sequence,
        candidate_schedule=("X1", "X2"),
    )
    occ_cert = certify_proposal(occ_prop, ("X1", "X2"), conflict, state)
    a.check(
        "authority",
        "intra-batch OCC collision rejected",
        "X2" in occ_cert.rejected_tasks
        and "OCC_WRITE_WRITE_CONFLICT" in occ_cert.rejected_tasks["X2"],
    )

    # Deliberate capacity overflow.
    heavy = dict(registry)
    heavy["R1"] = make_resource_domain_task(
        "R1",
        [Route(Guard(GuardOp.ALWAYS), (), Successor.halt())],
        ResourceRequirement(cpu_cores=6, ram_units=12),
    )
    heavy["R2"] = make_resource_domain_task(
        "R2",
        [Route(Guard(GuardOp.ALWAYS), (), Successor.halt())],
        ResourceRequirement(cpu_cores=6, ram_units=12),
    )
    res_prop = ModelProposal(
        model_id="acceptance",
        model_version="1",
        input_state_hash=state.state_hash,
        input_sequence=state.sequence,
        input_epoch=state.sequence,
        candidate_schedule=("R1", "R2"),
    )
    res_cert = certify_proposal(res_prop, ("R1", "R2"), heavy, state)
    a.check(
        "authority",
        "resource over-capacity proposal rejected",
        len(res_cert.accepted_tasks) == 1
        and any("RESOURCE_CAPACITY_EXCEEDED" in x for x in res_cert.rejected_tasks.values()),
    )
    return registry, state


def runtime_gate(
    a: Acceptance,
    registry: Mapping[str, ResourceBoundTask],
    initial: WorldState,
) -> None:
    with tempfile.TemporaryDirectory() as td:
        wal_path = Path(td) / "canonical_acceptance.wal"
        wal = WALSequencer(wal_path, initial)

        # A deliberately unreliable proposer is acceptable because the judge/fallback own legality.
        engine = ProposerOrchestrationEngine(RandomProposer(seed=20260922))
        final, seq, telemetry = engine.run_dag(registry, initial, sequencer=wal)

        orch = OrchestrationState(final)
        a.check("orchestration", "legal DAG completed", set(orch.completed) == set(registry))
        a.check("orchestration", "domain result is correct",
                (final.get("x"), final.get("y"), final.get("z"), final.get("w"), final.get("q"))
                == (10, 20, 30, 40, 50))
        a.check("orchestration", "evidence chain integral", seq.ledger.verify_integrity())
        a.check("orchestration", "model/judge telemetry emitted", len(telemetry) > 0)

        # Proposer crash: correctness must not depend on model availability.
        registry2, state2 = build_acceptance_dag()
        crash_engine = ProposerOrchestrationEngine(RandomProposer(inject_crash=True))
        out2, seq2, tel2 = crash_engine.run_dag(registry2, state2)
        a.check(
            "orchestration",
            "proposer crash falls back to certified legal scheduling",
            set(OrchestrationState(out2).completed) == set(registry2)
            and seq2.ledger.verify_integrity()
            and all(t.certificate.fallback_triggered for t in tel2),
        )

        # WAL recovery of actual repo execution.
        recovered, recovered_ledger = WALSequencer.recover(wal_path)
        a.check("durability", "recovered state equals continuous state",
                recovered.state_hash == seq.current_state.state_hash)
        a.check("durability", "recovered evidence root equals continuous",
                recovered_ledger.root_hash() == seq.ledger.root_hash())

        # Torn-tail qualification runs against a copy so the primary WAL remains clean.
        torn_path = Path(td) / "canonical_acceptance_torn.wal"
        torn_path.write_bytes(wal_path.read_bytes())
        with torn_path.open("ab") as fh:
            fh.write(b'{"type":"COMMIT","torn":')
        torn_state, torn_ledger = WALSequencer.recover(torn_path, ignore_torn_tail=True)
        a.check("durability", "torn WAL tail ignored",
                torn_state.state_hash == recovered.state_hash
                and torn_ledger.root_hash() == recovered_ledger.root_hash())

        # External-effect recovery is a distinct active authority context. The
        # orchestration above has correctly terminated in HALTED state, and the
        # application spine must not mutate that completed authority epoch.
        # Carry the recovered business attributes into a new RUNNING context with
        # its own WAL, then qualify crash/reconciliation there.
        client = MockExternalClient()
        effect_path = Path(td) / "canonical_acceptance_effects.wal"
        effect_state = WorldState(
            attributes=dict(recovered.attributes),
            cursor=None,
            status="RUNNING",
            sequence=recovered.sequence,
        )
        resumed = WALSequencer(effect_path, effect_state)
        runner = EffectRunner(resumed, client)

        eff = create_effect_descriptor(
            uow_id="acceptance_charge",
            pre_state_hash=resumed.current_state.state_hash,
            intent="charge",
            request={"amount": 25, "account": "demo"},
        )
        committed = runner.commit_intent(eff)
        # External service succeeds, process dies before receipt commit.
        request = dict(eff.request)
        request["effect_id"] = eff.effect_id
        client.invoke(request, eff.idempotency_key)
        calls_before = client.invocation_count

        rec2, led2 = WALSequencer.recover(effect_path, ignore_torn_tail=True)
        resumed2 = WALSequencer(effect_path, rec2, led2)
        runner2 = EffectRunner(resumed2, client)
        result = runner2.execute_effect(eff)
        a.check(
            "external-effect protocol (mock service)",
            "post-success crash reconciles without duplicate side effect",
            result.status == EffectStatus.COMMITTED_RESULT
            and client.invocation_count == calls_before
            and client.reconcile_count >= 1,
        )

        # Saga: two successful effects, third build fails => reverse compensation.
        coordinator = SagaCoordinator(runner2)

        def saga_step(name: str) -> SagaStep:
            def build(state: WorldState):
                return create_effect_descriptor(
                    uow_id=name,
                    pre_state_hash=state.state_hash,
                    intent=f"do_{name}",
                    request={"step": name},
                    compensation_intent=f"undo_{name}",
                    compensation_request={"step": name, "undo": True},
                )
            return SagaStep(name, build)

        def fail_build(state: WorldState):
            raise RuntimeError("acceptance downstream failure")

        before_log = len(client.call_log)
        try:
            coordinator.execute_saga(
                [saga_step("F1"), saga_step("F2"), SagaStep("F3", fail_build)],
                saga_id="acceptance_saga",
            )
            raise AssertionError("saga failure injection did not fire")
        except RuntimeError as exc:
            if "acceptance downstream failure" not in str(exc):
                raise

        comp_calls = [c for c in client.call_log[before_log:] if c["is_compensation"]]
        a.check(
            "external-effect protocol (mock service)",
            "saga compensation executes exact reverse order",
            len(comp_calls) == 2
            and "F2" in comp_calls[0]["effect_id"]
            and "F1" in comp_calls[1]["effect_id"],
        )
        a.check(
            "external-effect protocol (mock service)",
            "saga progress is authoritative state",
            "acceptance_saga" in get_sagas_map(resumed2.current_state),
        )

        # Final durable replay: no external endpoint execution during WAL recovery.
        calls_before_replay = client.invocation_count
        replay_state, replay_ledger = WALSequencer.recover(effect_path, ignore_torn_tail=True)
        a.check("replay", "final recovered state identical",
                replay_state.state_hash == resumed2.current_state.state_hash)
        a.check("replay", "final recovered evidence root identical",
                replay_ledger.root_hash() == resumed2.ledger.root_hash())
        a.check("replay", "recovery performs zero external re-execution",
                client.invocation_count == calls_before_replay)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--step-programs", type=int, default=25)
    p.add_argument("--steps-per-program", type=int, default=20)
    p.add_argument("--terminating-runs", type=int, default=50)
    p.add_argument("--timing-seeds", type=int, default=1000)
    p.add_argument("--output", default="qualification/uow_system_acceptance_report.txt")
    args = p.parse_args()

    a = Acceptance()
    foundation_gate(a, args)
    timing_gate(a, args)
    registry, state = authority_gate(a)
    runtime_gate(a, registry, state)

    report = a.report()
    print(report)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
