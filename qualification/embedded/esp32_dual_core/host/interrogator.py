#!/usr/bin/env python3
"""Structured laptop-side interrogator for the ESP32-S3 UoW qualifier.

The interrogator treats serial as an observation/control boundary. Device state
remains authoritative on the ESP32. Host timestamps are transcript metadata only.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import argparse
import json
from pathlib import Path
import time
from typing import Any, Protocol


class LineTransport(Protocol):
    def write_line(self, text: str) -> None: ...
    def read_line(self, timeout: float) -> str | None: ...
    def close(self) -> None: ...


class SerialTransport:
    def __init__(self, port: str, baud: int = 115200, settle: float = 1.2):
        try:
            import serial  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pyserial is required: python -m pip install pyserial") from exc
        self._ser = serial.Serial(port, baudrate=baud, timeout=0.1)
        time.sleep(settle)
        self._ser.reset_input_buffer()

    def write_line(self, text: str) -> None:
        self._ser.write((text.strip() + "\n").encode("utf-8"))
        self._ser.flush()

    def read_line(self, timeout: float) -> str | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = self._ser.readline()
            if raw:
                return raw.decode("utf-8", errors="replace").strip()
        return None

    def close(self) -> None:
        self._ser.close()


@dataclass(frozen=True)
class TranscriptEvent:
    host_monotonic: float
    direction: str
    payload: Any


@dataclass
class Transcript:
    events: list[TranscriptEvent] = field(default_factory=list)

    def sent(self, command: str) -> None:
        self.events.append(TranscriptEvent(time.monotonic(), "host->device", command))

    def received(self, payload: Any) -> None:
        self.events.append(TranscriptEvent(time.monotonic(), "device->host", payload))

    def save_jsonl(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as fh:
            for event in self.events:
                fh.write(json.dumps(asdict(event), sort_keys=True) + "\n")


@dataclass(frozen=True)
class CommandResult:
    command: str
    terminal: dict[str, Any]
    events: tuple[dict[str, Any], ...]


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

    @property
    def passed(self) -> bool:
        return all(self.checks.values())

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(asdict(self) | {"passed": self.passed}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "CampaignReport":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        data.pop("passed", None)
        return cls(**data)


class DeviceProtocolError(RuntimeError):
    pass


class Interrogator:
    def __init__(self, transport: LineTransport, *, echo: bool = True):
        self.transport = transport
        self.echo = echo
        self.transcript = Transcript()

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
            if request_id is None and obj_request is not None:
                request_id = int(obj_request)
            if request_id is not None and obj_request is not None and int(obj_request) != request_id:
                continue
            collected.append(obj)
            if obj.get("event") == terminal_event:
                return CommandResult(command, obj, tuple(collected))
            if obj.get("event") == "error":
                raise DeviceProtocolError(obj.get("reason", "device error"))
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

    @staticmethod
    def _assert(condition: bool, name: str, checks: dict[str, bool]) -> None:
        checks[name] = bool(condition)
        if not condition:
            raise AssertionError(name)

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
        if args.transcript:
            iq.transcript.save_jsonl(args.transcript)
    finally:
        transport.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
