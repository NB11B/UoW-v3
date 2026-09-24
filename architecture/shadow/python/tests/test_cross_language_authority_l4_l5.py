from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess

import pytest

from qualification.distributed_authority.authority_service_c import (
    compute_cert_hash,
    compute_evidence_record_hash,
    compute_proposal_hash,
    compute_qc_hash,
    compute_state_hash,
    compute_vote_hash,
)


def _load_profile():
    repo = Path(__file__).resolve().parents[4]
    path = repo / "architecture" / "conformance" / "authority" / "profile_v1.py"
    spec = importlib.util.spec_from_file_location("authority_profile_v1", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def profile():
    return _load_profile()


@pytest.fixture(scope="session")
def cpp_authority_hash_binary(tmp_path_factory):
    repo = Path(__file__).resolve().parents[4]
    out = tmp_path_factory.mktemp("cpp-authority-hash") / "authority_hash_v1"
    source = repo / "architecture" / "conformance" / "cpp" / "authority_hash_profile_v1.cpp"
    embedded = repo / "qualification" / "embedded" / "esp32_dual_core"
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-O2",
            "-I",
            str(embedded / "include"),
            str(source),
            str(embedded / "src" / "uow_embedded.cpp"),
            "-o",
            str(out),
        ],
        check=True,
        cwd=repo,
        capture_output=True,
        text=True,
    )
    return out


def _cpp_vector(binary: Path, mode: str):
    proc = subprocess.run(
        [str(binary), mode],
        check=True,
        capture_output=True,
        text=True,
    )
    lines = proc.stdout.splitlines()
    assert len(lines) == 2
    return lines[0], lines[1]


def _vectors(profile):
    a, b, c, d, e, f = ("a"*64, "b"*64, "c"*64, "d"*64, "e"*64, "f"*64)
    g, h = "1"*64, "2"*64
    return {
        "state": profile.canonical_state(10, 2, 3, 4, False),
        "proposal": profile.canonical_proposal(a, b, 3, False),
        "certificate": profile.canonical_certificate(c, True, 0),
        "evidence": profile.canonical_evidence(5, a, b, c, d, e),
        "vote": profile.canonical_vote(
            accepted=True,
            certificate_hash=d,
            evidence_step=5,
            node_id="authority_a_esp32",
            pre_evidence_root=e,
            pre_state_hash=a,
            proposal_hash=c,
            proposed_state_hash=b,
            rejection_reason=None,
            ruleset_version="uow-authority-v1",
        ),
        "qc": profile.canonical_qc(
            certificate_hash=d,
            committed_state_hash=b,
            evidence_step=5,
            expected_evidence_root=f,
            pre_evidence_root=e,
            pre_state_hash=a,
            proposal_hash=c,
            proposed_state_hash=b,
            ruleset_version="uow-authority-v1",
            threshold=2,
            uow_id="test_uow",
            vote_hashes=(g, h),
            voters=("authority_a_esp32", "authority_b_unoq_stm32"),
        ),
    }


@pytest.mark.parametrize("mode", ["state", "proposal", "certificate", "evidence", "vote", "qc"])
def test_r5_l4_l5_cpp_and_python_profile_match_exactly(
    profile,
    cpp_authority_hash_binary,
    mode,
):
    canonical = _vectors(profile)[mode]
    cpp_canonical, cpp_hash = _cpp_vector(cpp_authority_hash_binary, mode)

    assert cpp_canonical == canonical
    assert cpp_hash == profile.sha256_hex(canonical)


def test_r5_l5_profile_matches_existing_x86_authority_service(profile):
    a, b, c, d, e, f = ("a"*64, "b"*64, "c"*64, "d"*64, "e"*64, "f"*64)
    g, h = "1"*64, "2"*64

    assert profile.sha256_hex(profile.canonical_state(10, 2, 3, 4, False)) == compute_state_hash(
        10, 2, 3, 4, False
    )
    assert profile.sha256_hex(profile.canonical_proposal(a, b, 3, False)) == compute_proposal_hash(
        a, b, 3, False
    )
    assert profile.sha256_hex(profile.canonical_certificate(c, True, 0)) == compute_cert_hash(
        c, True, 0
    )
    assert profile.sha256_hex(profile.canonical_evidence(5, a, b, c, d, e)) == compute_evidence_record_hash(
        5, a, b, c, d, e
    )
    assert profile.sha256_hex(
        profile.canonical_vote(
            accepted=True,
            certificate_hash=d,
            evidence_step=5,
            node_id="authority_a_esp32",
            pre_evidence_root=e,
            pre_state_hash=a,
            proposal_hash=c,
            proposed_state_hash=b,
            rejection_reason=None,
            ruleset_version="uow-authority-v1",
        )
    ) == compute_vote_hash(
        True, d, 5, "authority_a_esp32", e, a, c, b, None, "uow-authority-v1"
    )
    assert profile.sha256_hex(
        profile.canonical_qc(
            certificate_hash=d,
            committed_state_hash=b,
            evidence_step=5,
            expected_evidence_root=f,
            pre_evidence_root=e,
            pre_state_hash=a,
            proposal_hash=c,
            proposed_state_hash=b,
            ruleset_version="uow-authority-v1",
            threshold=2,
            uow_id="test_uow",
            vote_hashes=(g, h),
            voters=("authority_a_esp32", "authority_b_unoq_stm32"),
        )
    ) == compute_qc_hash(
        d, b, 5, f, e, a, c, b, "uow-authority-v1", 2, "test_uow",
        [g, h], ["authority_a_esp32", "authority_b_unoq_stm32"]
    )


def test_r5_l4_l5_profile_is_boundary_specific(profile):
    # This profile deliberately does not claim equivalence with generic Python
    # WorldState canonical JSON identity.
    from uow import WorldState

    state = WorldState(
        attributes={"r0": 10, "r1": 2},
        cursor="uow_3",
        sequence=4,
    )
    authority_hash = profile.sha256_hex(profile.canonical_state(10, 2, 3, 4, False))
    assert state.state_hash != authority_hash
