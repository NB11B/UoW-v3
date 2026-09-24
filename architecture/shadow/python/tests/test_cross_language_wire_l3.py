from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from uow_shadow.wire_core import decode_wire, encode_wire


@pytest.fixture(scope="session")
def cpp_wire_binary(tmp_path_factory):
    repo = Path(__file__).resolve().parents[4]
    source = repo / "architecture" / "conformance" / "cpp" / "wire_core_v1.cpp"
    out = tmp_path_factory.mktemp("cpp-wire") / "uow_wire_v1"
    subprocess.run(
        ["g++", "-std=c++17", "-O2", str(source), "-o", str(out)],
        check=True,
        cwd=repo,
        capture_output=True,
        text=True,
    )
    return out


def _cpp_decode(binary: Path, wire: str):
    proc = subprocess.run(
        [str(binary), "decode", wire],
        capture_output=True,
        text=True,
    )
    return proc.returncode, json.loads(proc.stdout.strip())


def _cpp_sample(binary: Path, kind: str) -> str:
    proc = subprocess.run(
        [str(binary), "sample", kind],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


@pytest.mark.parametrize(
    ("kind", "fields"),
    [
        (
            "STATE",
            {"r0": 5, "r1": 3, "pc": 2, "sequence": 7, "halted": False},
        ),
        (
            "PROPOSAL",
            {
                "pre_state_hash": "a" * 64,
                "proposal_hash": "b" * 64,
                "r0": 4,
                "r1": 4,
                "pc": 3,
                "sequence": 7,
                "halted": False,
                "selected_pc": 3,
                "proposal_halted": False,
                "proposer_clock": 99,
            },
        ),
        (
            "CERTIFICATE",
            {
                "valid": False,
                "reason": "STATE_DIVERGENCE",
                "certificate_hash": "c" * 64,
            },
        ),
        (
            "EVIDENCE",
            {
                "step": 8,
                "pre_state_hash": "a" * 64,
                "post_state_hash": "b" * 64,
                "proposal_hash": "c" * 64,
                "certificate_hash": "d" * 64,
                "prev_record_hash": "a" * 64,
                "record_hash": "b" * 64,
            },
        ),
    ],
)
def test_r5_l3_python_wire_is_decodable_by_cpp(cpp_wire_binary, kind, fields):
    wire = encode_wire(kind, fields)
    code, decoded = _cpp_decode(cpp_wire_binary, wire)

    assert code == 0
    assert decoded["kind"] == kind
    for key, value in fields.items():
        expected = "1" if value is True else "0" if value is False else str(value)
        assert decoded[key] == expected


@pytest.mark.parametrize("kind", ["STATE", "PROPOSAL", "CERTIFICATE", "EVIDENCE"])
def test_r5_l3_cpp_wire_is_decodable_by_python(cpp_wire_binary, kind):
    wire = _cpp_sample(cpp_wire_binary, kind)
    decoded_kind, fields = decode_wire(wire)

    assert decoded_kind == kind
    assert fields


def test_r5_l3_field_order_is_not_semantic(cpp_wire_binary):
    reordered = (
        "UOW1|STATE|halted=0|sequence=7|pc=2|r1=3|r0=5"
    )
    kind, py = decode_wire(reordered)
    code, cpp = _cpp_decode(cpp_wire_binary, reordered)

    assert kind == "STATE"
    assert code == 0
    assert py == {"r0": 5, "r1": 3, "pc": 2, "sequence": 7, "halted": False}
    assert cpp["r0"] == "5"
    assert cpp["r1"] == "3"
    assert cpp["pc"] == "2"
    assert cpp["sequence"] == "7"
    assert cpp["halted"] == "0"


@pytest.mark.parametrize(
    "bad",
    [
        "WRONG|STATE|r0=1|r1=2|pc=0|sequence=0|halted=0",
        "UOW1|STATE|r0=1|r1=2|pc=0|halted=0",
        "UOW1|UNKNOWN|x=1",
        "UOW1|STATE|r0=1|r0=2|r1=2|pc=0|sequence=0|halted=0",
    ],
)
def test_r5_l3_malformed_wire_fails_closed_in_both_languages(cpp_wire_binary, bad):
    with pytest.raises(ValueError):
        decode_wire(bad)

    code, decoded = _cpp_decode(cpp_wire_binary, bad)
    assert code != 0
    assert "error" in decoded


def test_r5_l3_does_not_claim_l4_l5():
    # The L3 transport profile is deliberately independent from the existing
    # Python canonical-JSON and embedded C++ KV authority identity profiles.
    state_wire = encode_wire(
        "STATE",
        {"r0": 1, "r1": 2, "pc": 0, "sequence": 0, "halted": False},
    )
    assert state_wire.startswith("UOW1|STATE|")
    assert "{" not in state_wire
