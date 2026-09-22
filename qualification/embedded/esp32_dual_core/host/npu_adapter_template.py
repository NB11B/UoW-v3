#!/usr/bin/env python3
"""Template subprocess adapter for a local NPU/model runtime.

Protocol:
- read one JSON snapshot from stdin
- run any local NPU/model inference you want
- print one JSON candidate to stdout

The ESP32 does NOT trust this output. It independently certifies it.

Replace propose_with_your_npu() with your existing local runtime call.
"""
from __future__ import annotations

import json
import sys


def propose_with_your_npu(snapshot: dict) -> dict:
    # REPLACE THIS BODY with the local NPU/model call.
    #
    # The candidate may omit pre_state_hash, selected_pc, and proposal_hash;
    # external_proposer.py will bind/hash them. The minimum fields are:
    # r0, r1, pc, sequence, halted.
    #
    # This reference body simply computes the known two-counter transition so
    # the adapter can be smoke-tested before inserting a model.
    r0 = int(snapshot["r0"])
    r1 = int(snapshot["r1"])
    pc = int(snapshot["pc"])
    sequence = int(snapshot["sequence"]) + 1
    halted = bool(snapshot["halted"])

    if halted:
        return {
            "r0": r0,
            "r1": r1,
            "pc": pc,
            "sequence": int(snapshot["sequence"]),
            "halted": True,
        }

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

    return {
        "r0": r0,
        "r1": r1,
        "pc": pc,
        "sequence": sequence,
        "halted": halted,
    }


def main() -> int:
    raw = sys.stdin.readline()
    if not raw:
        return 2
    snapshot = json.loads(raw)
    candidate = propose_with_your_npu(snapshot)
    print(json.dumps(candidate, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
