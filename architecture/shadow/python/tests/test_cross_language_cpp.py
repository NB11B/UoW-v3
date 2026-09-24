from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import subprocess

import pytest

from foundations.universal_computation.reference_minsky import (
    MachineState,
    TRANSFER_R0_TO_R1,
    run as run_reference,
)
from foundations.universal_computation.uow_minsky_compiler import (
    compile_minsky,
    create_initial_world_state,
)
from uow.engine import Proposal, certify, propose

from uow_shadow.reconstruction import run_reconstructed


@pytest.fixture(scope="session")
def cpp_core_binary(tmp_path_factory):
    repo = Path(__file__).resolve().parents[4]
    out = tmp_path_factory.mktemp("cpp-uow") / "uow_core_conformance"
    source = repo / "architecture" / "conformance" / "cpp" / "core_semantics.cpp"
    embedded = repo / "qualification" / "embedded" / "esp32_dual_core"
    cmd = [
        "g++",
        "-std=c++17",
        "-O2",
        "-I",
        str(embedded / "include"),
        str(source),
        str(embedded / "src" / "uow_embedded.cpp"),
        "-o",
        str(out),
    ]
    subprocess.run(cmd, check=True, cwd=repo, capture_output=True, text=True)
    return out


def _run_cpp(binary: Path, mode: str):
    proc = subprocess.run(
        [str(binary), mode],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout.strip())


def test_r5_l0_python_cpp_transfer_behavior_matches(cpp_core_binary):
    cpp = _run_cpp(cpp_core_binary, "transfer")

    graph = compile_minsky(TRANSFER_R0_TO_R1)
    py = run_reconstructed(
        graph,
        create_initial_world_state(pc=0, r0=5, r1=3),
    )
    ref = run_reference(
        TRANSFER_R0_TO_R1,
        MachineState(pc=0, r0=5, r1=3),
    )

    assert cpp["r0"] == py.final_state.get("r0") == ref.r0 == 0
    assert cpp["r1"] == py.final_state.get("r1") == ref.r1 == 8
    assert cpp["sequence"] == py.final_state.sequence == ref.steps
    assert cpp["halted"] is True
    assert py.final_state.status == "HALTED"
    assert cpp["evidence_steps"] == len(py.evidence) == ref.steps
    assert cpp["evidence_valid"] is True


def _python_reject_reason(mode: str) -> str:
    graph = compile_minsky(TRANSFER_R0_TO_R1)
    uow = graph["uow_0"]
    state = create_initial_world_state(pc=0, r0=2, r1=1)
    proposal = propose(uow, state)

    if mode == "tamper_state":
        proposal = replace(
            proposal,
            proposed_state=proposal.proposed_state.with_attribute(
                "r1", proposal.proposed_state.get("r1", 0) + 1
            ),
        )
    elif mode == "tamper_prehash":
        proposal = replace(proposal, pre_state_hash="0" * 64)
    elif mode == "tamper_route":
        proposal = replace(
            proposal,
            selected_route_index=0 if proposal.selected_route_index != 0 else 1,
        )
    else:
        raise ValueError(mode)

    return certify(uow, state, proposal).rejection_reason


@pytest.mark.parametrize(
    ("mode", "cpp_reason", "python_reason"),
    [
        ("tamper_state", "STATE_DIVERGENCE", "STATE_DIVERGENCE"),
        ("tamper_prehash", "STALE_PRE_STATE", "PRE_STATE_HASH_MISMATCH"),
        ("tamper_route", "ROUTE_DIVERGENCE", "ROUTE_DIVERGENCE"),
    ],
)
def test_r5_l1_python_cpp_rejection_invariant_classes_match(
    cpp_core_binary,
    mode,
    cpp_reason,
    python_reason,
):
    cpp = _run_cpp(cpp_core_binary, mode)
    py_reason = _python_reject_reason(mode)

    assert cpp["committed"] is False
    assert cpp["reason"] == cpp_reason
    assert py_reason == python_reason
    # Naming differs for stale pre-state, but the semantic rejection class is the same.
    semantic_class = {
        "STALE_PRE_STATE": "STALE_PRE_STATE",
        "PRE_STATE_HASH_MISMATCH": "STALE_PRE_STATE",
        "STATE_DIVERGENCE": "STATE_DIVERGENCE",
        "ROUTE_DIVERGENCE": "ROUTE_DIVERGENCE",
    }
    assert semantic_class[cpp["reason"]] == semantic_class[py_reason]
    assert cpp["sequence"] == 0
    assert cpp["evidence_steps"] == 0


def test_r5_l2_evidence_semantics_match_without_claiming_hash_equality(cpp_core_binary):
    cpp_a = _run_cpp(cpp_core_binary, "transfer")
    cpp_b = _run_cpp(cpp_core_binary, "transfer")

    graph = compile_minsky(TRANSFER_R0_TO_R1)
    py_a = run_reconstructed(graph, create_initial_world_state(pc=0, r0=5, r1=3))
    py_b = run_reconstructed(graph, create_initial_world_state(pc=0, r0=5, r1=3))

    assert cpp_a["evidence_steps"] == cpp_b["evidence_steps"] == len(py_a.evidence)
    assert cpp_a["evidence_valid"] and cpp_b["evidence_valid"]
    assert py_a.evidence_root() == py_b.evidence_root()

    # Intentionally no cross-language record-hash equality assertion:
    # C++ currently canonicalizes authority objects with deterministic KV strings,
    # while Python uses canonical JSON.
