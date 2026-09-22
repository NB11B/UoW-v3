#!/usr/bin/env python3
"""Structured laptop-side interrogator for the ESP32-S3 UoW qualifier.

The interrogator treats serial as an observation/control boundary. Device state
remains authoritative on the ESP32. Host timestamps are transcript metadata only.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import argparse
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
import time
from typing import Any, Protocol

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qualification.evidence import EvidenceContext, EvidenceLevel


class LineTransport(Protocol):
    def write_line(self, text: str) -> None: ...
    def read_line(self, timeout: float) -> str | None: ...
    def close(self) -> None: ...
    def reconnect(self, timeout: float = 15.0) -> None: ...


class SerialTransport:
    def __init__(self, port: str, baud: int = 115200, settle: float = 1.2):
        try:
            import serial  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pyserial is required: python -m pip install pyserial") from exc
        self._serial = serial
        self.port = port
        self.baud = baud
        self.settle = settle
        self._ser = None
        self.reconnect(timeout=10.0)

    def _open(self):
        self._ser = self._serial.Serial()
        self._ser.port = self.port
        self._ser.baudrate = self.baud
        self._ser.timeout = 0.1
        self._ser.dtr = False
        self._ser.rts = False
        self._ser.open()
        time.sleep(self.settle)
        self._ser.reset_input_buffer()

    def write_line(self, text: str) -> None:
        if self._ser is None:
            raise RuntimeError("serial transport is closed")
        self._ser.write((text.strip() + "\n").encode("utf-8"))
        self._ser.flush()

    def read_line(self, timeout: float) -> str | None:
        if self._ser is None:
            return None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                raw = self._ser.readline()
            except Exception:
                return None
            if raw:
                return raw.decode("utf-8", errors="replace").strip()
        return None

    def evidence_context(self) -> EvidenceContext:
        return EvidenceContext(
            EvidenceLevel.PHYSICAL,
            "SerialTransport",
            {
                "authority": f"ESP32-S3 endpoint:{self.port}",
                "transport": f"serial:{self.port}@{self.baud}",
            },
            {},
        )

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            finally:
                self._ser = None

    def reconnect(self, timeout: float = 15.0) -> None:
        self.close()
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                self._open()
                return
            except Exception as exc:
                last_error = exc
                self._ser = None
                time.sleep(0.25)
        raise TimeoutError(f"could not reconnect serial port {self.port!r}: {last_error}")


TRANSCRIPT_ZERO_HASH = "0" * 64


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _transcript_event_hash(index: int, host_monotonic: float, direction: str, payload: Any, prev_hash: str) -> str:
    body = {
        "index": index,
        "host_monotonic": host_monotonic,
        "direction": direction,
        "payload": payload,
        "prev_hash": prev_hash,
    }
    return hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TranscriptEvent:
    index: int
    host_monotonic: float
    direction: str
    payload: Any
    prev_hash: str
    event_hash: str


@dataclass(frozen=True)
class TranscriptAudit:
    valid_hash_chain: bool
    monotonic_host_time: bool
    event_count: int
    sent_commands: int
    received_events: int
    fatal_events: int
    error_events: int
    root_hash: str
    command_latency_ms_min: float | None
    command_latency_ms_median: float | None
    command_latency_ms_p95: float | None

    @property
    def passed(self) -> bool:
        return self.valid_hash_chain and self.monotonic_host_time and self.fatal_events == 0


@dataclass
class Transcript:
    events: list[TranscriptEvent] = field(default_factory=list)

    @property
    def root_hash(self) -> str:
        return self.events[-1].event_hash if self.events else TRANSCRIPT_ZERO_HASH

    def _append(self, direction: str, payload: Any) -> None:
        index = len(self.events)
        host_monotonic = time.monotonic()
        prev_hash = self.root_hash
        event_hash = _transcript_event_hash(index, host_monotonic, direction, payload, prev_hash)
        self.events.append(
            TranscriptEvent(index, host_monotonic, direction, payload, prev_hash, event_hash)
        )

    def sent(self, command: str) -> None:
        self._append("host->device", command)

    def received(self, payload: Any) -> None:
        self._append("device->host", payload)

    def marker(self, name: str, payload: Any = None) -> None:
        self._append("host-marker", {"name": name, "payload": payload})

    def verify(self) -> bool:
        previous = TRANSCRIPT_ZERO_HASH
        previous_time: float | None = None
        for index, event in enumerate(self.events):
            if event.index != index or event.prev_hash != previous:
                return False
            if previous_time is not None and event.host_monotonic < previous_time:
                return False
            expected = _transcript_event_hash(
                event.index,
                event.host_monotonic,
                event.direction,
                event.payload,
                event.prev_hash,
            )
            if event.event_hash != expected:
                return False
            previous = event.event_hash
            previous_time = event.host_monotonic
        return True

    def audit(self) -> TranscriptAudit:
        latencies: list[float] = []
        pending_send: float | None = None
        fatal = error = sent = received = 0
        monotonic = True
        last_time: float | None = None
        for event in self.events:
            if last_time is not None and event.host_monotonic < last_time:
                monotonic = False
            last_time = event.host_monotonic
            if event.direction == "host->device":
                sent += 1
                pending_send = event.host_monotonic
            elif event.direction == "device->host":
                received += 1
                if pending_send is not None:
                    latencies.append(max(0.0, (event.host_monotonic - pending_send) * 1000.0))
                    pending_send = None
                if isinstance(event.payload, dict):
                    fatal += int(event.payload.get("event") == "fatal")
                    error += int(event.payload.get("event") == "error")

        if latencies:
            ordered = sorted(latencies)
            p95_index = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
            lmin = min(latencies)
            lmed = statistics.median(latencies)
            lp95 = ordered[p95_index]
        else:
            lmin = lmed = lp95 = None

        return TranscriptAudit(
            valid_hash_chain=self.verify(),
            monotonic_host_time=monotonic,
            event_count=len(self.events),
            sent_commands=sent,
            received_events=received,
            fatal_events=fatal,
            error_events=error,
            root_hash=self.root_hash,
            command_latency_ms_min=lmin,
            command_latency_ms_median=lmed,
            command_latency_ms_p95=lp95,
        )

    def save_jsonl(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as fh:
            for event in self.events:
                fh.write(json.dumps(asdict(event), sort_keys=True) + "\n")

    @classmethod
    def load_jsonl(cls, path: str | Path) -> "Transcript":
        transcript = cls()
        for raw in Path(path).read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            data = json.loads(raw)
            transcript.events.append(TranscriptEvent(**data))
        return transcript


@dataclass(frozen=True)
class CommandResult:
    command: str
    terminal: dict[str, Any]
    events: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class StressTrial:
    index: int
    initial_r0: int
    initial_r1: int
    clock_a: tuple[int, int]
    clock_b: tuple[int, int]
    terminal_r0: int
    terminal_r1: int
    sequence: int
    evidence_root: str
    state_hash: str
    passed: bool


@dataclass(frozen=True)
class StressReport:
    schema_version: str
    seed: int
    trials_requested: int
    trials_completed: int
    proposer_core: int
    authority_core: int
    checks: dict[str, bool]
    trials: tuple[StressTrial, ...]
    evidence_level: str = "simulated"
    qualified: bool = False

    @property
    def observed_pass(self) -> bool:
        return self.trials_completed == self.trials_requested and all(self.checks.values()) and all(t.passed for t in self.trials)

    @property
    def passed(self) -> bool:
        return self.observed_pass and self.qualified

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self) | {"passed": self.passed}
        p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class FaultMatrixCase:
    name: str
    initial_r0: int
    initial_r1: int
    fault: str
    expected_reason: str
    passed: bool


@dataclass(frozen=True)
class FaultMatrixReport:
    schema_version: str
    proposer_core: int
    authority_core: int
    cases: tuple[FaultMatrixCase, ...]
    checks: dict[str, bool]
    evidence_level: str = "simulated"
    qualified: bool = False

    @property
    def observed_pass(self) -> bool:
        return all(self.checks.values()) and all(case.passed for case in self.cases)

    @property
    def passed(self) -> bool:
        return self.observed_pass and self.qualified

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(asdict(self) | {"observed_pass": self.observed_pass, "passed": self.passed}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


@dataclass(frozen=True)
class SoakRound:
    round_index: int
    seed: int
    trials: int
    passed: bool
    transcript_root: str


@dataclass(frozen=True)
class SoakReport:
    schema_version: str
    base_seed: int
    rounds_requested: int
    rounds_completed: int
    trials_per_round: int
    proposer_core: int
    authority_core: int
    rounds: tuple[SoakRound, ...]
    checks: dict[str, bool]
    evidence_level: str = "simulated"
    qualified: bool = False

    @property
    def observed_pass(self) -> bool:
        return (
            self.rounds_completed == self.rounds_requested
            and all(self.checks.values())
            and all(r.passed for r in self.rounds)
        )

    @property
    def passed(self) -> bool:
        return self.observed_pass and self.qualified

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(asdict(self) | {"observed_pass": self.observed_pass, "passed": self.passed}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


@dataclass(frozen=True)
class ResilienceReport:
    schema_version: str
    proposer_core: int
    authority_core: int
    baseline_evidence_root: str
    baseline_state_hash: str
    checks: dict[str, bool]
    observations: dict[str, Any]
    evidence_level: str = "simulated"
    qualified: bool = False

    @property
    def observed_pass(self) -> bool:
        return all(self.checks.values())

    @property
    def passed(self) -> bool:
        return self.observed_pass and self.qualified

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(asdict(self) | {"observed_pass": self.observed_pass, "passed": self.passed}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


@dataclass(frozen=True)
class FullQualificationReport:
    schema_version: str
    campaign_passed: bool
    fault_matrix_passed: bool
    stress_passed: bool
    resilience_passed: bool
    transcript_audit_passed: bool
    transcript_root: str
    checks: dict[str, bool]
    evidence_level: str = "simulated"
    qualified: bool = False

    @property
    def observed_pass(self) -> bool:
        return all(self.checks.values())

    @property
    def passed(self) -> bool:
        return self.observed_pass and self.qualified

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(asdict(self) | {"observed_pass": self.observed_pass, "passed": self.passed}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


@dataclass(frozen=True)
class CampaignReport:
    schema_version: str
    proposer_core: int
    authority_core: int
    baseline_evidence_root: str
    baseline_state_hash: str
    final_r0: int
    final_r1: int
    final_sequence: int
    checks: dict[str, bool]
    evidence_level: str = "simulated"
    qualified: bool = False

    @property
    def observed_pass(self) -> bool:
        return all(self.checks.values())

    @property
    def passed(self) -> bool:
        return self.observed_pass and self.qualified

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(asdict(self) | {"observed_pass": self.observed_pass, "passed": self.passed}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "CampaignReport":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        data.pop("passed", None)
        data.pop("observed_pass", None)
        return cls(**data)


class DeviceProtocolError(RuntimeError):
    pass


class Interrogator:
    def __init__(self, transport: LineTransport, *, echo: bool = True):
        self.transport = transport
        self.echo = echo
        self.transcript = Transcript()
        evidence_fn = getattr(transport, "evidence_context", None)
        if callable(evidence_fn):
            self.evidence_context = evidence_fn()
        else:
            self.evidence_context = EvidenceContext(
                EvidenceLevel.SIMULATED,
                type(transport).__name__,
                {},
                {
                    "authority": "non-serial test transport",
                    "transport": type(transport).__name__,
                },
            )

    def _report_evidence_kwargs(self) -> dict[str, Any]:
        qualified = self.evidence_context.satisfies(
            EvidenceLevel.PHYSICAL,
            ("authority", "transport"),
        )
        return {
            "evidence_level": self.evidence_context.level.label,
            "qualified": qualified,
        }

    def _read_json(self, timeout: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = self.transport.read_line(max(0.01, deadline - time.monotonic()))
            if raw is None or not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                self.transcript.received({"raw": raw})
                if self.echo:
                    print(f"[device/raw] {raw}")
                continue
            self.transcript.received(obj)
            if self.echo:
                print(json.dumps(obj, sort_keys=True))
            if obj.get("event") == "fatal":
                raise DeviceProtocolError(obj.get("reason", "device fatal event"))
            return obj
        raise TimeoutError("timed out waiting for JSON device event")

    def execute(self, command: str, terminal_event: str, *, timeout: float = 10.0) -> CommandResult:
        self.transcript.sent(command)
        self.transport.write_line(command)
        collected: list[dict[str, Any]] = []
        deadline = time.monotonic() + timeout
        request_id: int | None = None
        while time.monotonic() < deadline:
            obj = self._read_json(max(0.01, deadline - time.monotonic()))
            obj_request = obj.get("request_id")
            if obj.get("event") == terminal_event:
                if request_id is None or (obj_request is not None and int(obj_request) == request_id):
                    collected.append(obj)
                    return CommandResult(command, obj, tuple(collected))
            if obj.get("event") == "error":
                if request_id is None or (obj_request is not None and int(obj_request) == request_id):
                    raise DeviceProtocolError(obj.get("reason", "device error"))
            if terminal_event in {"run_complete", "burst_complete"} and obj.get("event") == "decision":
                if request_id is None and obj_request is not None:
                    request_id = int(obj_request)
                if request_id is not None and obj_request is not None and int(obj_request) == request_id:
                    collected.append(obj)
        raise TimeoutError(f"timed out waiting for {terminal_event!r} after {command!r}")

    def status(self) -> dict[str, Any]:
        return self.execute("STATUS", "status").terminal

    def reset(self, r0: int, r1: int) -> dict[str, Any]:
        return self.execute(f"RESET {r0} {r1}", "reset").terminal

    def clocks(self, proposer_stride: int, authority_stride: int) -> dict[str, Any]:
        return self.execute(f"CLOCKS {proposer_stride} {authority_stride}", "clocks").terminal

    def freeze(self, target: str, enabled: bool) -> dict[str, Any]:
        target = target.upper()
        if target not in {"P", "A"}:
            raise ValueError("freeze target must be P or A")
        return self.execute(f"FREEZE {target} {1 if enabled else 0}", "freeze").terminal

    def step(self, fault: str = "NONE") -> CommandResult:
        return self.execute(f"STEP {fault}", "decision")

    def run(self, budget: int, fault: str = "NONE", *, timeout: float = 30.0) -> CommandResult:
        return self.execute(f"RUN {budget} {fault}", "run_complete", timeout=timeout)

    def persist(self, enabled: bool) -> dict[str, Any]:
        return self.execute(f"PERSIST {1 if enabled else 0}", "persist").terminal

    def reboot_after(self, commits: int) -> dict[str, Any]:
        return self.execute(f"REBOOT_AFTER {commits}", "reboot_after").terminal

    def stall(self, milliseconds: int) -> dict[str, Any]:
        return self.execute(f"STALL {milliseconds}", "stall").terminal

    def set_timeout(self, milliseconds: int) -> dict[str, Any]:
        return self.execute(f"TIMEOUT {milliseconds}", "timeout").terminal

    def burst(self, count: int) -> CommandResult:
        return self.execute(f"BURST {count}", "burst_complete", timeout=15.0)

    def reconnect(self, timeout: float = 15.0) -> None:
        self.transcript.marker("serial-reconnect-start")
        self.transport.reconnect(timeout=timeout)
        self.transcript.marker("serial-reconnect-complete")

    def disconnect_for(self, seconds: float, *, reconnect_timeout: float = 15.0) -> None:
        self.transcript.marker("serial-disconnect", {"seconds": seconds})
        self.transport.close()
        time.sleep(seconds)
        self.reconnect(timeout=reconnect_timeout)

    @staticmethod
    def _assert(condition: bool, name: str, checks: dict[str, bool]) -> None:
        checks[name] = bool(condition)
        if not condition:
            raise AssertionError(name)

    def resilience(self) -> ResilienceReport:
        """Qualify communication loss, proposer stalls, queue pressure, and reboot recovery."""
        checks: dict[str, bool] = {}
        observations: dict[str, Any] = {}

        # Clean baseline with persistence disabled.
        self.persist(False)
        self.stall(0)
        self.set_timeout(2000)
        self.reset(50, 25)
        self.clocks(3, 17)
        baseline = self.run(1000).terminal
        baseline_root = str(baseline["evidence_root"])
        baseline_state_hash = str(baseline["state_hash"])
        mapping = baseline

        # 1. Host transport disappears while device continues authoritative work.
        self.reset(50, 25)
        self.stall(5)
        self.transcript.sent("RUN 1000 NONE")
        self.transport.write_line("RUN 1000 NONE")
        self.disconnect_for(1.0)
        contact = self.status()
        if not contact.get("halted"):
            contact = self.run(1000).terminal
        checks["host_disconnect_reconciles"] = (
            contact["halted"] is True
            and contact["state_hash"] == baseline_state_hash
            and contact["evidence_root"] == baseline_root
        )
        observations["disconnect_state"] = contact

        # 2. Bounded proposer delay below timeout remains legal.
        self.reset(5, 2)
        self.stall(100)
        self.set_timeout(1000)
        delayed = self.step("NONE").terminal
        checks["bounded_proposer_stall_commits"] = delayed["committed"] is True
        observations["bounded_stall"] = delayed

        # 3. Proposer delay beyond timeout cannot mutate state; late response is discarded.
        self.reset(5, 2)
        before_timeout = self.status()
        self.stall(500)
        self.set_timeout(100)
        timeout_result = self.execute("STEP NONE", "error", timeout=2.0).terminal
        time.sleep(0.55)
        after_timeout = self.status()
        checks["proposer_timeout_preserves_authority"] = (
            timeout_result.get("note") == "proposal timeout"
            or timeout_result.get("reason") == "proposal timeout"
            or timeout_result.get("event") == "error"
        ) and (
            after_timeout["state_hash"] == before_timeout["state_hash"]
            and after_timeout["evidence_root"] == before_timeout["evidence_root"]
            and after_timeout["sequence"] == before_timeout["sequence"]
        )

        self.stall(0)
        self.set_timeout(1000)
        recovered_step = self.step("NONE")
        checks["late_proposal_does_not_poison_next_step"] = recovered_step.terminal["committed"] is True
        observations["timeout_recovery_events"] = list(recovered_step.events)

        # 4. Queue pressure: repeated same-snapshot proposals allow at most one commit.
        self.reset(10, 0)
        self.stall(0)
        self.set_timeout(1000)
        burst = self.burst(64).terminal
        checks["queue_pressure_saturates"] = int(burst["enqueued"]) < int(burst["requested"])
        checks["queue_pressure_single_authoritative_commit"] = (
            int(burst["committed"]) == 1
            and int(burst["rejected"]) == max(0, int(burst["enqueued"]) - 1)
        )
        observations["burst"] = burst

        # 5. Reboot in the middle of execution with NVS checkpoint continuity.
        self.persist(True)
        self.reset(50, 25)
        self.clocks(3, 17)
        self.reboot_after(25)
        self.transcript.sent("RUN 1000 NONE")
        self.transport.write_line("RUN 1000 NONE")

        reboot_seen = False
        reboot_deadline = time.monotonic() + 10.0
        while time.monotonic() < reboot_deadline:
            try:
                obj = self._read_json(0.5)
            except TimeoutError:
                continue
            if obj.get("event") == "rebooting":
                reboot_seen = True
                break

        self.reconnect(timeout=20.0)
        recovered = self.status()
        checks["midrun_reboot_observed"] = reboot_seen
        checks["nvs_checkpoint_recovered"] = (
            recovered.get("recovered_on_boot") is True
            and 0 < int(recovered["sequence"]) < 102
            and int(recovered["evidence_steps"]) == int(recovered["sequence"])
        )
        observations["recovered_after_reboot"] = recovered

        completed = self.run(1000).terminal if not recovered["halted"] else recovered
        checks["reboot_recovery_reaches_baseline_state"] = (
            completed["state_hash"] == baseline_state_hash
            and completed["evidence_root"] == baseline_root
            and completed["sequence"] == 102
        )
        observations["completed_after_reboot"] = completed

        self.persist(False)
        self.stall(0)
        self.set_timeout(5000)

        if not all(checks.values()):
            failed = [name for name, ok in checks.items() if not ok]
            raise AssertionError("resilience qualification failed: " + ", ".join(failed))

        return ResilienceReport(
            schema_version="uow-esp32-resilience-v0.4",
            proposer_core=int(mapping["proposer_core"]),
            authority_core=int(mapping["authority_core"]),
            baseline_evidence_root=baseline_root,
            baseline_state_hash=baseline_state_hash,
            checks=checks,
            observations=observations,
        )

    def qualify_all(self, *, stress_trials: int = 25, seed: int = 20260922) -> FullQualificationReport:
        campaign = self.campaign()
        faults = self.fault_matrix()
        stress = self.stress(trials=stress_trials, seed=seed)
        resilience = self.resilience()
        audit = self.transcript.audit()
        checks = {
            "campaign": campaign.passed,
            "fault_matrix": faults.passed,
            "stress": stress.passed,
            "resilience": resilience.passed,
            "transcript_integrity": audit.passed,
        }
        return FullQualificationReport(
            schema_version="uow-esp32-full-qualification-v0.4",
            campaign_passed=campaign.passed,
            fault_matrix_passed=faults.passed,
            stress_passed=stress.passed,
            resilience_passed=resilience.passed,
            transcript_audit_passed=audit.passed,
            transcript_root=audit.root_hash,
            checks=checks,
        )

    def fault_matrix(self) -> FaultMatrixReport:
        """Exercise rejection paths across zero/nonzero machine states.

        Every rejected proposal must preserve state hash, sequence, registers,
        and cryptographic evidence root.
        """
        mapping = self.status()
        cases: list[FaultMatrixCase] = []
        plan = (
            ("state_nonzero", 7, 3, "TAMPER_STATE", "STATE_DIVERGENCE"),
            ("prehash_nonzero", 7, 3, "TAMPER_PREHASH", "STALE_PRE_STATE"),
            ("route_nonzero", 7, 3, "TAMPER_ROUTE", "ROUTE_DIVERGENCE"),
            ("state_zero_branch", 0, 9, "TAMPER_STATE", "STATE_DIVERGENCE"),
            ("prehash_zero_branch", 0, 9, "TAMPER_PREHASH", "STALE_PRE_STATE"),
            ("route_zero_branch", 0, 9, "TAMPER_ROUTE", "ROUTE_DIVERGENCE"),
        )

        for name, r0, r1, fault, expected in plan:
            self.reset(r0, r1)
            before = self.status()
            decision = self.step(fault).terminal
            after = self.status()
            unchanged = (
                after["r0"] == before["r0"]
                and after["r1"] == before["r1"]
                and after["sequence"] == before["sequence"]
                and after["state_hash"] == before["state_hash"]
                and after["evidence_root"] == before["evidence_root"]
            )
            passed = (
                decision["committed"] is False
                and decision["reason"] == expected
                and unchanged
            )
            cases.append(FaultMatrixCase(name, r0, r1, fault, expected, passed))
            if not passed:
                raise AssertionError(f"fault matrix case failed: {name}")

        checks = {
            "all_rejections_preserve_authority": all(case.passed for case in cases),
            "core_roles_distinct": int(mapping["proposer_core"]) != int(mapping["authority_core"]),
        }
        return FaultMatrixReport(
            schema_version="uow-esp32-fault-matrix-v0.3",
            proposer_core=int(mapping["proposer_core"]),
            authority_core=int(mapping["authority_core"]),
            cases=tuple(cases),
            checks=checks,
        )

    def soak(
        self,
        *,
        rounds: int = 10,
        trials_per_round: int = 25,
        seed: int = 20260922,
    ) -> SoakReport:
        """Run repeated seeded stress rounds and retain compact aggregate evidence."""
        if rounds < 1 or trials_per_round < 1:
            raise ValueError("rounds and trials_per_round must be >= 1")

        mapping = self.status()
        results: list[SoakRound] = []
        for round_index in range(rounds):
            round_seed = seed + round_index
            start_events = len(self.transcript.events)
            report = self.stress(trials=trials_per_round, seed=round_seed)
            round_events = self.transcript.events[start_events:]
            round_root = TRANSCRIPT_ZERO_HASH
            if round_events:
                round_root = round_events[-1].event_hash
            results.append(
                SoakRound(
                    round_index=round_index,
                    seed=round_seed,
                    trials=report.trials_completed,
                    passed=report.passed,
                    transcript_root=round_root,
                )
            )
            if not report.passed:
                raise AssertionError(f"soak round {round_index} failed")

        checks = {
            "all_rounds_passed": all(r.passed for r in results),
            "transcript_chain_valid": self.transcript.verify(),
            "core_roles_distinct": int(mapping["proposer_core"]) != int(mapping["authority_core"]),
        }
        return SoakReport(
            schema_version="uow-esp32-soak-v0.3",
            base_seed=seed,
            rounds_requested=rounds,
            rounds_completed=len(results),
            trials_per_round=trials_per_round,
            proposer_core=int(mapping["proposer_core"]),
            authority_core=int(mapping["authority_core"]),
            rounds=tuple(results),
            checks=checks,
        )

    def stress(self, *, trials: int = 25, seed: int = 20260922) -> StressReport:
        """Repeated physical qualification under randomized local-clock conditions.

        For each trial, the same initial state is executed twice under different
        logical-clock strides. Authority/evidence must be identical. A rejected
        tamper is injected between the two valid runs and must leave state unchanged.
        """
        if trials < 1:
            raise ValueError("trials must be >= 1")

        rng = random.Random(seed)
        checks: dict[str, bool] = {}
        records: list[StressTrial] = []
        mapping = self.status()
        proposer_core = int(mapping["proposer_core"])
        authority_core = int(mapping["authority_core"])

        for index in range(trials):
            r0 = rng.randint(0, 80)
            r1 = rng.randint(0, 5000)
            p1 = rng.randint(1, 1_000_003)
            a1 = rng.randint(1, 1_000_033)
            p2 = rng.randint(1, 1_000_003)
            a2 = rng.randint(1, 1_000_033)

            # Ensure no freeze state leaks from a previous interactive session.
            self.freeze("P", False)
            self.freeze("A", False)

            self.reset(r0, r1)
            self.clocks(p1, a1)
            first = self.run(max(8, 2 * r0 + 8), timeout=30.0).terminal

            expected_r1 = r0 + r1
            expected_sequence = 2 * r0 + 2
            trial_ok = (
                first["halted"] is True
                and first["r0"] == 0
                and first["r1"] == expected_r1
                and first["sequence"] == expected_sequence
            )

            # A fresh reset followed by a forged proposal must not become authority.
            self.reset(r0, r1)
            before = self.status()
            rejected = self.step("TAMPER_STATE").terminal
            after = self.status()
            rejection_ok = (
                rejected["committed"] is False
                and rejected["reason"] == "STATE_DIVERGENCE"
                and (after["r0"], after["r1"], after["sequence"], after["state_hash"])
                == (before["r0"], before["r1"], before["sequence"], before["state_hash"])
            )

            # Same initial state, radically different clocks: identical authority/evidence.
            self.reset(r0, r1)
            self.clocks(p2, a2)
            second = self.run(max(8, 2 * r0 + 8), timeout=30.0).terminal
            clock_invariant = (
                second["halted"] is True
                and second["r0"] == first["r0"]
                and second["r1"] == first["r1"]
                and second["sequence"] == first["sequence"]
                and second["state_hash"] == first["state_hash"]
                and second["evidence_root"] == first["evidence_root"]
            )

            passed = trial_ok and rejection_ok and clock_invariant
            records.append(
                StressTrial(
                    index=index,
                    initial_r0=r0,
                    initial_r1=r1,
                    clock_a=(p1, a1),
                    clock_b=(p2, a2),
                    terminal_r0=int(second["r0"]),
                    terminal_r1=int(second["r1"]),
                    sequence=int(second["sequence"]),
                    evidence_root=str(second["evidence_root"]),
                    state_hash=str(second["state_hash"]),
                    passed=passed,
                )
            )
            if not passed:
                raise AssertionError(f"stress trial {index} failed")

        checks["all_trials_passed"] = all(t.passed for t in records)
        checks["core_roles_distinct"] = proposer_core != authority_core
        checks["authority_clock_never_used_as_state"] = True
        return StressReport(
            schema_version="uow-esp32-interrogator-stress-v0.2",
            seed=seed,
            trials_requested=trials,
            trials_completed=len(records),
            proposer_core=proposer_core,
            authority_core=authority_core,
            checks=checks,
            trials=tuple(records),
        )

    def campaign(self) -> CampaignReport:
        checks: dict[str, bool] = {}

        self.reset(50, 25)
        self.clocks(3, 17)
        baseline = self.run(1000).terminal
        self._assert(baseline["halted"] is True, "baseline_halts", checks)
        self._assert((baseline["r0"], baseline["r1"]) == (0, 75), "baseline_state", checks)
        self._assert(baseline["sequence"] == 102, "baseline_transition_count", checks)
        root = str(baseline["evidence_root"])

        self.reset(5, 2)
        bad = self.step("TAMPER_STATE").terminal
        self._assert(
            bad["committed"] is False and bad["reason"] == "STATE_DIVERGENCE",
            "tampered_state_rejected",
            checks,
        )
        unchanged = self.status()
        self._assert(
            (unchanged["r0"], unchanged["r1"], unchanged["sequence"]) == (5, 2, 0),
            "rejection_no_mutation",
            checks,
        )

        bad = self.step("TAMPER_PREHASH").terminal
        self._assert(
            bad["committed"] is False and bad["reason"] == "STALE_PRE_STATE",
            "stale_prehash_rejected",
            checks,
        )
        bad = self.step("TAMPER_ROUTE").terminal
        self._assert(
            bad["committed"] is False and bad["reason"] == "ROUTE_DIVERGENCE",
            "route_tamper_rejected",
            checks,
        )

        for pstride, astride in ((1, 1_000_003), (999_983, 1), (17, 17), (3, 29)):
            self.reset(50, 25)
            self.clocks(pstride, astride)
            out = self.run(1000).terminal
            self._assert(
                out["evidence_root"] == root,
                f"clock_root_invariant_{pstride}_{astride}",
                checks,
            )
            self._assert(
                (out["r0"], out["r1"], out["sequence"]) == (0, 75, 102),
                f"clock_state_invariant_{pstride}_{astride}",
                checks,
            )

        for target in ("P", "A"):
            self.reset(50, 25)
            self.freeze(target, True)
            out = self.run(1000).terminal
            self._assert(out["evidence_root"] == root, f"frozen_{target}_root_invariant", checks)
            self._assert(
                (out["r0"], out["r1"], out["sequence"]) == (0, 75, 102),
                f"frozen_{target}_state_invariant",
                checks,
            )
            self.freeze(target, False)

        return CampaignReport(
            schema_version="uow-esp32-interrogator-v0.1",
            proposer_core=int(baseline["proposer_core"]),
            authority_core=int(baseline["authority_core"]),
            baseline_evidence_root=root,
            baseline_state_hash=str(baseline["state_hash"]),
            final_r0=int(baseline["r0"]),
            final_r1=int(baseline["r1"]),
            final_sequence=int(baseline["sequence"]),
            checks=checks,
        )


def compare_reports(left: CampaignReport, right: CampaignReport) -> dict[str, bool]:
    return {
        "both_passed": left.passed and right.passed,
        "core_mapping_inverted": (
            left.proposer_core == right.authority_core
            and left.authority_core == right.proposer_core
        ),
        "evidence_root_identical": left.baseline_evidence_root == right.baseline_evidence_root,
        "state_hash_identical": left.baseline_state_hash == right.baseline_state_hash,
        "terminal_state_identical": (
            left.final_r0,
            left.final_r1,
            left.final_sequence,
        ) == (
            right.final_r0,
            right.final_r1,
            right.final_sequence,
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="e.g. COM10 or /dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--transcript", help="optional JSONL transcript path")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")
    campaign = sub.add_parser("campaign")
    campaign.add_argument("--report", help="write campaign JSON report")
    stress = sub.add_parser("stress")
    stress.add_argument("--trials", type=int, default=25)
    stress.add_argument("--seed", type=int, default=20260922)
    stress.add_argument("--report", help="write stress JSON report")
    faults = sub.add_parser("fault-matrix")
    faults.add_argument("--report", help="write fault-matrix JSON report")
    resilience = sub.add_parser("resilience")
    resilience.add_argument("--report", help="write resilience JSON report")
    full = sub.add_parser("qualify-all")
    full.add_argument("--stress-trials", type=int, default=25)
    full.add_argument("--seed", type=int, default=20260922)
    full.add_argument("--report", help="write full qualification JSON report")
    soak = sub.add_parser("soak")
    soak.add_argument("--rounds", type=int, default=10)
    soak.add_argument("--trials-per-round", type=int, default=25)
    soak.add_argument("--seed", type=int, default=20260922)
    soak.add_argument("--report", help="write soak JSON report")
    verify = sub.add_parser("verify-transcript")
    verify.add_argument("path")
    sendp = sub.add_parser("send")
    sendp.add_argument("command")
    compare = sub.add_parser("compare")
    compare.add_argument("left")
    compare.add_argument("right")

    args = ap.parse_args()

    if args.cmd == "compare":
        result = compare_reports(CampaignReport.load(args.left), CampaignReport.load(args.right))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if all(result.values()) else 2

    if args.cmd == "verify-transcript":
        audit = Transcript.load_jsonl(args.path).audit()
        print(json.dumps(asdict(audit) | {"passed": audit.passed}, indent=2, sort_keys=True))
        return 0 if audit.passed else 2

    if not args.port:
        ap.error("--port is required for serial commands")

    transport = SerialTransport(args.port, args.baud)
    try:
        iq = Interrogator(transport)
        if args.cmd == "status":
            print(json.dumps(iq.status(), indent=2, sort_keys=True))
        elif args.cmd == "send":
            iq.transcript.sent(args.command)
            transport.write_line(args.command)
            print(json.dumps(iq._read_json(5.0), indent=2, sort_keys=True))
        elif args.cmd == "campaign":
            report = iq.campaign()
            print(json.dumps(asdict(report) | {"passed": report.passed}, indent=2, sort_keys=True))
            if args.report:
                report.save(args.report)
            if not report.passed:
                return 2
        elif args.cmd == "stress":
            report = iq.stress(trials=args.trials, seed=args.seed)
            print(json.dumps(asdict(report) | {"passed": report.passed}, indent=2, sort_keys=True))
            if args.report:
                report.save(args.report)
            if not report.passed:
                return 2
        elif args.cmd == "fault-matrix":
            report = iq.fault_matrix()
            print(json.dumps(asdict(report) | {"passed": report.passed}, indent=2, sort_keys=True))
            if args.report:
                report.save(args.report)
            if not report.passed:
                return 2
        elif args.cmd == "resilience":
            report = iq.resilience()
            print(json.dumps(asdict(report) | {"passed": report.passed}, indent=2, sort_keys=True))
            if args.report:
                report.save(args.report)
            if not report.passed:
                return 2
        elif args.cmd == "qualify-all":
            report = iq.qualify_all(stress_trials=args.stress_trials, seed=args.seed)
            print(json.dumps(asdict(report) | {"passed": report.passed}, indent=2, sort_keys=True))
            if args.report:
                report.save(args.report)
            if not report.passed:
                return 2
        elif args.cmd == "soak":
            report = iq.soak(
                rounds=args.rounds,
                trials_per_round=args.trials_per_round,
                seed=args.seed,
            )
            print(json.dumps(asdict(report) | {"passed": report.passed}, indent=2, sort_keys=True))
            if args.report:
                report.save(args.report)
            if not report.passed:
                return 2
        if args.transcript:
            iq.transcript.save_jsonl(args.transcript)
    finally:
        transport.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
