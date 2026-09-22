#!/usr/bin/env python3
"""Laptop/NPU proposer -> ESP32 deterministic authority qualification.

The laptop owns proposal computation only. The ESP32 owns authoritative state,
independent certification, evidence, and commit/reject.

Backends:
- reference: deterministic control used to prove cross-machine parity.
- command: arbitrary local process, suitable for NPU/model runtimes.
- module: Python module:function adapter for an existing local NPU wrapper.

Command/module backends receive a JSON snapshot and return a JSON candidate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import shlex
import subprocess
from typing import Any, Callable, Protocol

from interrogator import Interrogator, SerialTransport


def canonical_state(r0: int, r1: int, pc: int, sequence: int, halted: bool) -> str:
    return (
        f"r0={r0};r1={r1};pc={pc};sequence={sequence};"
        f"halted={1 if halted else 0}"
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def state_hash_fields(r0: int, r1: int, pc: int, sequence: int, halted: bool) -> str:
    return sha256_text(canonical_state(r0, r1, pc, sequence, halted))


@dataclass(frozen=True)
class Snapshot:
    r0: int
    r1: int
    pc: int
    sequence: int
    halted: bool
    state_hash: str
    evidence_root: str

    @classmethod
    def from_event(cls, event: dict[str, Any]) -> "Snapshot":
        return cls(
            r0=int(event["r0"]),
            r1=int(event["r1"]),
            pc=int(event["pc"]),
            sequence=int(event["sequence"]),
            halted=bool(event["halted"]),
            state_hash=str(event["state_hash"]),
            evidence_root=str(event["evidence_root"]),
        )


@dataclass(frozen=True)
class Candidate:
    pre_state_hash: str
    r0: int
    r1: int
    pc: int
    sequence: int
    halted: bool
    selected_pc: int
    proposal_hash: str

    @classmethod
    def build(
        cls,
        *,
        pre_state_hash: str,
        r0: int,
        r1: int,
        pc: int,
        sequence: int,
        halted: bool,
        selected_pc: int,
    ) -> "Candidate":
        post_hash = state_hash_fields(r0, r1, pc, sequence, halted)
        body = (
            f"pre={pre_state_hash};post={post_hash};"
            f"pc={selected_pc};halted={1 if halted else 0}"
        )
        return cls(
            pre_state_hash=pre_state_hash,
            r0=r0,
            r1=r1,
            pc=pc,
            sequence=sequence,
            halted=halted,
            selected_pc=selected_pc,
            proposal_hash=sha256_text(body),
        )

    @classmethod
    def from_mapping(cls, data: dict[str, Any], snapshot: Snapshot) -> "Candidate":
        pre = str(data.get("pre_state_hash", snapshot.state_hash))
        r0 = int(data["r0"])
        r1 = int(data["r1"])
        pc = int(data["pc"])
        sequence = int(data["sequence"])
        halted = bool(data["halted"])
        selected_pc = int(data.get("selected_pc", pc))
        proposal_hash = data.get("proposal_hash")
        if proposal_hash is None:
            return cls.build(
                pre_state_hash=pre,
                r0=r0,
                r1=r1,
                pc=pc,
                sequence=sequence,
                halted=halted,
                selected_pc=selected_pc,
            )
        return cls(pre, r0, r1, pc, sequence, halted, selected_pc, str(proposal_hash))

    def serial_command(self) -> str:
        return (
            "EXT_PROPOSE "
            f"{self.pre_state_hash} {self.r0} {self.r1} {self.pc} "
            f"{self.sequence} {1 if self.halted else 0} "
            f"{self.selected_pc} {self.proposal_hash}"
        )


class ProposerBackend(Protocol):
    name: str
    def propose(self, snapshot: Snapshot) -> Candidate: ...


class ReferenceBackend:
    name = "reference"

    def propose(self, snapshot: Snapshot) -> Candidate:
        if snapshot.halted:
            return Candidate.build(
                pre_state_hash=snapshot.state_hash,
                r0=snapshot.r0,
                r1=snapshot.r1,
                pc=snapshot.pc,
                sequence=snapshot.sequence,
                halted=True,
                selected_pc=snapshot.pc,
            )

        r0, r1, pc = snapshot.r0, snapshot.r1, snapshot.pc
        sequence = snapshot.sequence + 1
        halted = False

        if pc == 0:
            if r0 == 0:
                pc = 2
            else:
                r0 -= 1
                pc = 1
        elif pc == 1:
            r1 += 1
            pc = 0
        elif pc == 2:
            halted = True
        else:
            # Deliberately produce an invalid candidate; authority must reject it.
            pc = snapshot.pc

        return Candidate.build(
            pre_state_hash=snapshot.state_hash,
            r0=r0,
            r1=r1,
            pc=pc,
            sequence=sequence,
            halted=halted,
            selected_pc=pc,
        )


class CommandBackend:
    """Run an arbitrary local proposer process.

    JSON snapshot is written to stdin; one JSON candidate is read from stdout.
    This is the preferred seam for local NPU SDKs that already have a CLI/wrapper.
    """

    def __init__(self, command: str):
        self.argv = shlex.split(command)
        if not self.argv:
            raise ValueError("command backend requires a command")
        self.name = "command:" + self.argv[0]

    def propose(self, snapshot: Snapshot) -> Candidate:
        payload = json.dumps(asdict(snapshot), sort_keys=True)
        proc = subprocess.run(
            self.argv,
            input=payload + "\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"external proposer exited {proc.returncode}: {proc.stderr.strip()}"
            )
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("external proposer produced no JSON")
        data = json.loads(lines[-1])
        return Candidate.from_mapping(data, snapshot)


class ModuleBackend:
    """Load module:function and call it with a snapshot mapping."""

    def __init__(self, target: str):
        if ":" not in target:
            raise ValueError("module backend target must be module:function")
        module_name, func_name = target.split(":", 1)
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
        if not callable(func):
            raise TypeError(f"{target!r} is not callable")
        self.func: Callable[[dict[str, Any]], dict[str, Any]] = func
        self.name = "module:" + target

    def propose(self, snapshot: Snapshot) -> Candidate:
        data = self.func(asdict(snapshot))
        if not isinstance(data, dict):
            raise TypeError("module proposer must return a dict")
        return Candidate.from_mapping(data, snapshot)


class CorruptingBackend:
    """Deterministically corrupt a valid candidate for authority-safety tests."""

    def __init__(self, base: ProposerBackend, mode: str):
        self.base = base
        self.mode = mode
        self.name = f"{base.name}+{mode}"

    def propose(self, snapshot: Snapshot) -> Candidate:
        c = self.base.propose(snapshot)
        data = asdict(c)
        if self.mode == "state":
            data["r1"] = int(data["r1"]) + 1
            # Preserve original hash so both semantic and hash checks are stressed.
        elif self.mode == "prehash":
            data["pre_state_hash"] = ("00" if not c.pre_state_hash.startswith("00") else "ff") + c.pre_state_hash[2:]
        elif self.mode == "route":
            data["selected_pc"] = int(data["selected_pc"]) + 1
        elif self.mode == "proposal_hash":
            data["proposal_hash"] = ("00" if not c.proposal_hash.startswith("00") else "ff") + c.proposal_hash[2:]
        else:
            raise ValueError(f"unknown corruption mode: {self.mode}")
        return Candidate(**data)


@dataclass(frozen=True)
class ExternalRunReport:
    backend: str
    initial_r0: int
    initial_r1: int
    steps: int
    commits: int
    rejections: int
    final_state_hash: str
    final_evidence_root: str
    halted: bool


@dataclass(frozen=True)
class ExternalQualificationReport:
    schema_version: str
    backend: str
    reference_parity: bool
    authority_rejects_corruption: bool
    stale_snapshot_rejected: bool
    no_mutation_on_rejection: bool
    backend_trials: int
    backend_accepts: int
    backend_rejects: int
    wrong_authoritative_commits: int
    baseline_state_hash: str
    baseline_evidence_root: str
    external_state_hash: str
    external_evidence_root: str

    @property
    def passed(self) -> bool:
        return (
            self.reference_parity
            and self.authority_rejects_corruption
            and self.stale_snapshot_rejected
            and self.no_mutation_on_rejection
            and self.wrong_authoritative_commits == 0
        )

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(asdict(self) | {"passed": self.passed}, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )


class ExternalAuthorityClient:
    def __init__(self, iq: Interrogator):
        self.iq = iq

    def snapshot(self) -> Snapshot:
        event = self.iq.execute("SNAPSHOT", "snapshot").terminal
        return Snapshot.from_event(event)

    def submit(self, candidate: Candidate):
        result = self.iq.execute(candidate.serial_command(), "decision", timeout=10.0)
        if result.terminal.get("origin") != "external":
            raise RuntimeError("device decision was not marked as external")
        return result

    def external_step(self, backend: ProposerBackend):
        snap = self.snapshot()
        candidate = backend.propose(snap)
        return snap, candidate, self.submit(candidate)

    def run_external(
        self,
        backend: ProposerBackend,
        *,
        initial_r0: int,
        initial_r1: int,
        max_steps: int = 10000,
    ) -> ExternalRunReport:
        self.iq.reset(initial_r0, initial_r1)
        commits = rejections = 0
        for step_index in range(max_steps):
            snap = self.snapshot()
            if snap.halted:
                return ExternalRunReport(
                    backend=backend.name,
                    initial_r0=initial_r0,
                    initial_r1=initial_r1,
                    steps=step_index,
                    commits=commits,
                    rejections=rejections,
                    final_state_hash=snap.state_hash,
                    final_evidence_root=snap.evidence_root,
                    halted=True,
                )
            candidate = backend.propose(snap)
            decision = self.submit(candidate).terminal
            if decision["committed"]:
                commits += 1
            else:
                rejections += 1
                return ExternalRunReport(
                    backend=backend.name,
                    initial_r0=initial_r0,
                    initial_r1=initial_r1,
                    steps=step_index + 1,
                    commits=commits,
                    rejections=rejections,
                    final_state_hash=self.snapshot().state_hash,
                    final_evidence_root=self.snapshot().evidence_root,
                    halted=False,
                )
        snap = self.snapshot()
        return ExternalRunReport(
            backend=backend.name,
            initial_r0=initial_r0,
            initial_r1=initial_r1,
            steps=max_steps,
            commits=commits,
            rejections=rejections,
            final_state_hash=snap.state_hash,
            final_evidence_root=snap.evidence_root,
            halted=snap.halted,
        )

    def qualify(
        self,
        backend: ProposerBackend,
        *,
        backend_trials: int = 50,
    ) -> ExternalQualificationReport:
        # Internal proposer establishes the device-local canonical baseline.
        self.iq.persist(False)
        self.iq.reset(50, 25)
        baseline = self.iq.run(1000).terminal

        # Cross-machine reference parity.
        reference = ReferenceBackend()
        external = self.run_external(reference, initial_r0=50, initial_r1=25)
        parity = (
            external.halted
            and external.final_state_hash == baseline["state_hash"]
            and external.final_evidence_root == baseline["evidence_root"]
        )

        # Corruption matrix: external machine must never acquire state authority.
        corruption_ok = True
        no_mutation = True
        for mode in ("state", "prehash", "route", "proposal_hash"):
            self.iq.reset(7, 3)
            before = self.snapshot()
            candidate = CorruptingBackend(reference, mode).propose(before)
            decision = self.submit(candidate).terminal
            after = self.snapshot()
            corruption_ok &= decision["committed"] is False
            no_mutation &= (
                before.state_hash == after.state_hash
                and before.evidence_root == after.evidence_root
                and before.sequence == after.sequence
            )

        # Stale proposal: snapshot on laptop, authoritative state advances elsewhere.
        self.iq.reset(5, 0)
        stale_snapshot = self.snapshot()
        stale_candidate = reference.propose(stale_snapshot)
        internal_decision = self.iq.step("NONE").terminal
        if not internal_decision["committed"]:
            raise AssertionError("internal control step failed during stale-snapshot test")
        before_stale_submit = self.snapshot()
        stale_decision = self.submit(stale_candidate).terminal
        after_stale_submit = self.snapshot()
        stale_ok = (
            stale_decision["committed"] is False
            and stale_decision["reason"] == "STALE_PRE_STATE"
            and before_stale_submit.state_hash == after_stale_submit.state_hash
            and before_stale_submit.evidence_root == after_stale_submit.evidence_root
        )

        # Backend quality/safety trials. Backend may be stochastic or imperfect.
        accepts = rejects = wrong_commits = 0
        for i in range(backend_trials):
            r0 = (i * 17 + 3) % 61
            r1 = (i * 97 + 11) % 1000
            self.iq.reset(r0, r1)
            before = self.snapshot()
            candidate = backend.propose(before)
            decision = self.submit(candidate).terminal
            after = self.snapshot()

            expected = reference.propose(before)
            candidate_is_correct = candidate == expected

            if decision["committed"]:
                accepts += 1
                # A committed external proposal must equal the independent reference.
                if not candidate_is_correct:
                    wrong_commits += 1
            else:
                rejects += 1
                if (
                    before.state_hash != after.state_hash
                    or before.evidence_root != after.evidence_root
                    or before.sequence != after.sequence
                ):
                    no_mutation = False

        return ExternalQualificationReport(
            schema_version="uow-esp32-external-proposer-v0.1",
            backend=backend.name,
            reference_parity=parity,
            authority_rejects_corruption=corruption_ok,
            stale_snapshot_rejected=stale_ok,
            no_mutation_on_rejection=no_mutation,
            backend_trials=backend_trials,
            backend_accepts=accepts,
            backend_rejects=rejects,
            wrong_authoritative_commits=wrong_commits,
            baseline_state_hash=str(baseline["state_hash"]),
            baseline_evidence_root=str(baseline["evidence_root"]),
            external_state_hash=external.final_state_hash,
            external_evidence_root=external.final_evidence_root,
        )


def make_backend(args) -> ProposerBackend:
    if args.backend == "reference":
        return ReferenceBackend()
    if args.backend == "command":
        if not args.command:
            raise SystemExit("--command is required for command backend")
        return CommandBackend(args.command)
    if args.backend == "module":
        if not args.target:
            raise SystemExit("--target module:function is required for module backend")
        return ModuleBackend(args.target)
    raise SystemExit(f"unknown backend: {args.backend}")


def add_backend_args(parser):
    parser.add_argument("--backend", choices=("reference", "command", "module"), default="reference")
    parser.add_argument("--command", help="local proposer command for command backend")
    parser.add_argument("--target", help="module:function for module backend")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    sub = ap.add_subparsers(dest="cmd", required=True)

    runp = sub.add_parser("run")
    add_backend_args(runp)
    runp.add_argument("--r0", type=int, default=50)
    runp.add_argument("--r1", type=int, default=25)
    runp.add_argument("--max-steps", type=int, default=10000)

    qual = sub.add_parser("qualify")
    add_backend_args(qual)
    qual.add_argument("--backend-trials", type=int, default=50)
    qual.add_argument("--report")

    args = ap.parse_args()
    transport = SerialTransport(args.port, args.baud)
    try:
        iq = Interrogator(transport)
        client = ExternalAuthorityClient(iq)
        backend = make_backend(args)

        if args.cmd == "run":
            report = client.run_external(
                backend,
                initial_r0=args.r0,
                initial_r1=args.r1,
                max_steps=args.max_steps,
            )
            print(json.dumps(asdict(report), indent=2, sort_keys=True))
            return 0 if report.halted else 2

        report = client.qualify(backend, backend_trials=args.backend_trials)
        print(json.dumps(asdict(report) | {"passed": report.passed}, indent=2, sort_keys=True))
        if args.report:
            report.save(args.report)
        return 0 if report.passed else 2
    finally:
        transport.close()


if __name__ == "__main__":
    raise SystemExit(main())
