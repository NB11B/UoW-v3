#!/usr/bin/env python3
"""Intel AI Boost NPU Proposer Adapter for ESP32 Deterministic Authority.

Executes candidate state transition inference directly on the host's physical
Intel(R) AI Boost NPU via OpenVINO runtime.

Candidate proposals are transmitted over serial to the physical ESP32-S3
microcontroller, which independently verifies and certifies each transition.
The ESP32 does NOT trust the NPU; authority and evidence generation remain
strictly on-device.

Supported usage:
1. Module mode:
   python host/external_proposer.py --port COM10 capability \\
       --backend module --target host.intel_npu_adapter:propose

2. Command / subprocess mode:
   python host/external_proposer.py --port COM10 capability \\
       --backend command --target "python host/intel_npu_adapter.py"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qualification.evidence import EvidenceContext, EvidenceLevel

_COMPILED_MODEL = None
_DEVICE_NAME = None


def get_npu_runner():
    """Lazily load and compile the Minsky surrogate network on the Intel NPU."""
    global _COMPILED_MODEL, _DEVICE_NAME
    if _COMPILED_MODEL is not None:
        return _COMPILED_MODEL, _DEVICE_NAME

    try:
        import openvino as ov
        import numpy as np
    except ImportError as e:
        raise RuntimeError("openvino and numpy are required for Intel NPU inference") from e

    core = ov.Core()
    available = core.available_devices

    if "NPU" not in available:
        raise RuntimeError(
            "Intel NPU qualification requested, but OpenVINO reports no NPU device; "
            "CPU fallback is forbidden for an NPU claim"
        )
    target_device = "NPU"
    try:
        device_full_name = core.get_property("NPU", "FULL_DEVICE_NAME")
    except Exception:
        device_full_name = "NPU"

    _DEVICE_NAME = f"NPU ({device_full_name})"

    onnx_path = Path(__file__).resolve().parent / "minsky_npu.onnx"
    if not onnx_path.exists():
        # Fallback to artifacts if not in host/
        alt_path = Path(__file__).resolve().parent.parent / "artifacts" / "minsky_npu.onnx"
        if alt_path.exists():
            onnx_path = alt_path
        else:
            raise FileNotFoundError(f"ONNX model not found at {onnx_path} or {alt_path}")

    model = core.read_model(str(onnx_path))
    _COMPILED_MODEL = core.compile_model(model, target_device)
    return _COMPILED_MODEL, _DEVICE_NAME


def evidence_context() -> EvidenceContext:
    """Attest that this adapter can only qualify when the actual NPU loads."""
    _, device_name = get_npu_runner()
    return EvidenceContext(
        EvidenceLevel.PHYSICAL,
        "intel_npu_adapter",
        {"proposer": device_name, "npu_proposer": device_name},
        {},
    )


def propose(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Compute the next candidate state using hardware NPU neural inference."""
    import numpy as np

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

    compiled_model, _ = get_npu_runner()

    # Model input shape: [1, 3] -> [float(r0), float(r1), float(pc)]
    inp = np.array([[float(r0), float(r1), float(pc)]], dtype=np.float32)
    output = compiled_model([inp])[compiled_model.output(0)][0]

    # Model output shape: [1, 4] -> [delta_r0, delta_r1, next_pc, halted]
    dr0 = int(round(float(output[0])))
    dr1 = int(round(float(output[1])))
    next_pc = int(round(float(output[2])))
    next_halt = bool(round(float(output[3])))

    next_r0 = r0 + dr0
    next_r1 = r1 + dr1

    return {
        "r0": next_r0,
        "r1": next_r1,
        "pc": next_pc,
        "sequence": sequence,
        "halted": next_halt,
    }


def main() -> int:
    raw = sys.stdin.readline()
    if not raw:
        return 2
    snapshot = json.loads(raw)
    candidate = propose(snapshot)
    print(json.dumps(candidate, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
