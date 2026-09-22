#!/usr/bin/env python3
"""Serial interrogation tool for the ESP32-S3 dual-core UoW qualifier."""
from __future__ import annotations

import argparse
import json
import time
from typing import Any

try:
    import serial  # type: ignore
except ImportError as exc:
    raise SystemExit("pyserial is required: python -m pip install pyserial") from exc


def open_port(name: str, baud: int):
    ser = serial.Serial(name, baudrate=baud, timeout=0.25)
    time.sleep(1.2)
    ser.reset_input_buffer()
    return ser


def read_event(ser, timeout: float = 5.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        raw = ser.readline()
        if not raw:
            continue
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            print(f"[device/raw] {text}")
            continue
        print(json.dumps(obj, sort_keys=True))
        return obj
    raise TimeoutError("timed out waiting for device event")


def send(ser, command: str) -> None:
    ser.write((command.strip() + "\n").encode("utf-8"))
    ser.flush()


def wait_for(ser, event: str, timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        obj = read_event(ser, max(0.1, deadline - time.time()))
        if obj.get("event") == event:
            return obj
    raise TimeoutError(f"timed out waiting for event={event!r}")


def command_status(ser) -> None:
    send(ser, "STATUS")
    wait_for(ser, "status")


def run_campaign(ser) -> None:
    print("== baseline deterministic transfer ==")
    send(ser, "RESET 50 25")
    wait_for(ser, "reset")
    send(ser, "CLOCKS 3 17")
    wait_for(ser, "clocks")
    send(ser, "RUN 1000")
    baseline = wait_for(ser, "run_complete", 30)
    assert baseline["halted"] is True
    assert baseline["r0"] == 0 and baseline["r1"] == 75
    assert baseline["sequence"] == 102
    root_baseline = baseline["evidence_root"]

    print("== tampered proposal must not mutate authority ==")
    send(ser, "RESET 5 2")
    wait_for(ser, "reset")
    send(ser, "STEP TAMPER_STATE")
    decision = wait_for(ser, "decision")
    assert decision["committed"] is False
    assert decision["reason"] == "STATE_DIVERGENCE"
    send(ser, "STATUS")
    unchanged = wait_for(ser, "status")
    assert unchanged["r0"] == 5 and unchanged["r1"] == 2 and unchanged["sequence"] == 0

    print("== pre-state corruption rejected ==")
    send(ser, "STEP TAMPER_PREHASH")
    decision = wait_for(ser, "decision")
    assert decision["committed"] is False
    assert decision["reason"] == "STALE_PRE_STATE"

    print("== route corruption rejected ==")
    send(ser, "STEP TAMPER_ROUTE")
    decision = wait_for(ser, "decision")
    assert decision["committed"] is False
    assert decision["reason"] == "ROUTE_DIVERGENCE"

    print("== timer independence: extreme asymmetric clocks ==")
    send(ser, "RESET 50 25")
    wait_for(ser, "reset")
    send(ser, "CLOCKS 1 1000003")
    wait_for(ser, "clocks")
    send(ser, "RUN 1000")
    skewed = wait_for(ser, "run_complete", 30)
    assert skewed["halted"] is True
    assert skewed["r0"] == 0 and skewed["r1"] == 75
    assert skewed["evidence_root"] == root_baseline

    print("== timer independence: proposer clock frozen ==")
    send(ser, "RESET 50 25")
    wait_for(ser, "reset")
    send(ser, "FREEZE P 1")
    wait_for(ser, "freeze")
    send(ser, "RUN 1000")
    frozen = wait_for(ser, "run_complete", 30)
    assert frozen["halted"] is True
    assert frozen["r0"] == 0 and frozen["r1"] == 75
    assert frozen["evidence_root"] == root_baseline
    send(ser, "FREEZE P 0")
    wait_for(ser, "freeze")

    print("PASS: device preserved authority, evidence, and timer independence")
    print(f"evidence_root={root_baseline}")
    print(f"core_map=P{baseline['proposer_core']}/A{baseline['authority_core']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="e.g. COM10 or /dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("campaign")
    sp = sub.add_parser("send")
    sp.add_argument("command")
    args = ap.parse_args()

    with open_port(args.port, args.baud) as ser:
        if args.cmd == "status":
            command_status(ser)
        elif args.cmd == "campaign":
            run_campaign(ser)
        elif args.cmd == "send":
            send(ser, args.command)
            read_event(ser, 5.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
