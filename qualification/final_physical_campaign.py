#!/usr/bin/env python3
"""One-command operator harness for the final UoW physical confirmation campaign.

This file is qualification tooling created after the software freeze. It does not
redefine the software candidate. Every artifact records both:
  - candidate_commit: the immutable software under qualification
  - harness_commit: the operator tooling used to conduct the campaign

The harness fails closed on missing named hardware or substrate substitution.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_REF = "archive/uow-reduction-software-candidate"
CANDIDATE_COMMIT = "f842d62c7d18355886e2c9fdc25e9cc5db17987b"
A3_REF = "qualification/a3-adaptive-compute-efficiency"
A3_COMMIT = "05c8094ac5c8572f7da6d00e781ce673754c5c59"
P1_P5_REF = "architecture/policy-aware-uow-orchestrator"
P1_P5_COMMIT = "aa886329298f87e8b006501d47dd89eb8f0d4a3b"
P1_P5_TAG = "policy-orchestrator-p5-qualified"
P1_P5_POLICY_SUITE_TESTS = 44
P1_P5_FULL_REPOSITORY_TESTS = 324
CANDIDATE_SHADOW_TESTS = 271

P1_P5_INVARIANTS = (
    "canonical_uow_requirement_projection",
    "deterministic_world_state_snapshot",
    "execution_realization_graph",
    "qualified_versioned_policy_registry",
    "discovery_without_authority",
    "prospective_qualification",
    "deterministic_policy_reuse",
    "live_drift_invalidation_safe_replacement",
    "transactional_registry_versioning",
    "distributed_policy_authority",
    "durable_persistence_atomic_recovery",
    "zero_duplicate_external_effects",
    "five_tier_cryptographic_provenance",
)

PHASES = ("F0", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8")


@dataclass
class CommandResult:
    name: str
    argv: list[str]
    cwd: str
    returncode: int
    started_at: str
    duration_s: float
    log_path: str
    passed: bool


@dataclass
class PhaseResult:
    phase: str
    passed: bool
    details: dict[str, Any]
    commands: list[CommandResult]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git_capture(*args: str, cwd: Path = REPO_ROOT) -> str:
    cp = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return cp.stdout.strip()


def harness_commit() -> str:
    return git_capture("rev-parse", "HEAD")


def parse_frozen_inputs(path: Path) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    current_path: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("- path:"):
            current_path = line.split(":", 1)[1].strip()
        elif current_path is not None and line.startswith("git_blob_sha:"):
            sha = line.split(":", 1)[1].strip()
            items.append((current_path, sha))
            current_path = None
    if not items:
        raise RuntimeError(f"No frozen input entries parsed from {path}")
    return items


def find_adb() -> str | None:
    candidates = [
        shutil.which("adb"),
        r"C:\Program Files (x86)\Android\android-sdk\platform-tools\adb.exe",
        os.path.expanduser(r"~\AppData\Local\Android\Sdk\platform-tools\adb.exe"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            cp = subprocess.run(
                [candidate, "version"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=10,
            )
            if cp.returncode == 0:
                return candidate
        except Exception:
            continue
    return None


def detect_hardware(esp_port: str, uno_port: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "esp_port_requested": esp_port,
        "uno_port_requested": uno_port,
        "serial_ports": [],
        "cuda_available": False,
        "cuda_device": None,
        "openvino_devices": [],
        "npu_device": None,
        "pio": shutil.which("pio"),
        "adb": find_adb(),
    }
    try:
        from serial.tools import list_ports  # type: ignore
        result["serial_ports"] = [p.device for p in list_ports.comports()]
    except Exception as exc:
        result["serial_error"] = repr(exc)

    try:
        import torch  # type: ignore
        result["cuda_available"] = bool(torch.cuda.is_available())
        if result["cuda_available"]:
            result["cuda_device"] = torch.cuda.get_device_name(0)
    except Exception as exc:
        result["cuda_error"] = repr(exc)

    try:
        import openvino as ov  # type: ignore
        core = ov.Core()
        result["openvino_devices"] = list(core.available_devices)
        if "NPU" in result["openvino_devices"]:
            try:
                result["npu_device"] = core.get_property("NPU", "FULL_DEVICE_NAME")
            except Exception:
                result["npu_device"] = "NPU"
    except Exception as exc:
        result["openvino_error"] = repr(exc)
    return result


def run_logged(
    name: str,
    argv: Sequence[str],
    *,
    cwd: Path,
    artifacts_dir: Path,
    env: dict[str, str] | None = None,
) -> CommandResult:
    log_path = artifacts_dir / f"{name}.log"
    started = time.perf_counter()
    started_at = utc_now()
    print(f"\n[{name}] cwd={cwd}")
    print("  " + " ".join(str(x) for x in argv))
    with log_path.open("w", encoding="utf-8") as log:
        cp = subprocess.run(
            [str(x) for x in argv],
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    duration = time.perf_counter() - started
    result = CommandResult(
        name=name,
        argv=[str(x) for x in argv],
        cwd=str(cwd),
        returncode=cp.returncode,
        started_at=started_at,
        duration_s=round(duration, 3),
        log_path=str(log_path),
        passed=cp.returncode == 0,
    )
    print(f"  -> {'PASS' if result.passed else 'FAIL'} ({result.duration_s:.2f}s), log={log_path}")
    return result


def require_commands_pass(commands: Iterable[CommandResult]) -> None:
    failed = [c for c in commands if not c.passed]
    if failed:
        names = ", ".join(c.name for c in failed)
        raise RuntimeError(f"Qualification command failure: {names}")


def require_pytest_pass_count(command: CommandResult, expected: int) -> int:
    text = Path(command.log_path).read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"(\d+) passed(?:, \d+ deselected)? in ", text)
    if not matches:
        raise RuntimeError(f"Could not recover pytest pass count from {command.log_path}")
    observed = int(matches[-1])
    if observed != expected:
        raise RuntimeError(
            f"{command.name} passed {observed} tests; expected exact frozen-suite count {expected}"
        )
    return observed


def f0_attestation(args: argparse.Namespace, phase_dir: Path) -> PhaseResult:
    details: dict[str, Any] = {
        "candidate_ref": CANDIDATE_REF,
        "candidate_commit": CANDIDATE_COMMIT,
        "harness_commit": harness_commit(),
        "source_attestation": [],
        "binary_attestation": {},
    }
    resolved = git_capture("rev-parse", CANDIDATE_REF)
    details["candidate_ref_resolved"] = resolved
    if resolved != CANDIDATE_COMMIT:
        raise RuntimeError(f"{CANDIDATE_REF} resolves to {resolved}, expected {CANDIDATE_COMMIT}")

    manifest = REPO_ROOT / "qualification" / "final_physical_candidate_inputs.yaml"
    frozen_inputs = parse_frozen_inputs(manifest)
    changed = git_capture(
        "diff",
        "--name-only",
        CANDIDATE_COMMIT,
        "HEAD",
        "--",
        *[path for path, _ in frozen_inputs],
    )
    if changed:
        raise RuntimeError(f"Frozen candidate input paths changed after freeze: {changed}")

    for rel, expected_blob in frozen_inputs:
        candidate_blob = git_capture("rev-parse", f"{CANDIDATE_COMMIT}:{rel}")
        worktree_blob = git_capture("hash-object", rel)
        passed = candidate_blob == expected_blob == worktree_blob
        details["source_attestation"].append(
            {
                "path": rel,
                "expected_blob": expected_blob,
                "candidate_blob": candidate_blob,
                "worktree_blob": worktree_blob,
                "passed": passed,
            }
        )
        if not passed:
            raise RuntimeError(f"Source attestation failed for {rel}")

    hardware = detect_hardware(args.esp_port, args.uno_port)
    details["hardware"] = hardware
    if args.execute:
        missing: list[str] = []
        ports = set(hardware.get("serial_ports", []))
        if args.esp_port not in ports:
            missing.append(f"ESP32 serial port {args.esp_port}")
        if args.uno_port not in ports:
            missing.append(f"UNO-Q serial port {args.uno_port}")
        if not hardware.get("cuda_available"):
            missing.append("CUDA GPU")
        if "NPU" not in hardware.get("openvino_devices", []):
            missing.append("OpenVINO NPU")
        if not hardware.get("pio"):
            missing.append("PlatformIO pio")
        if not hardware.get("adb"):
            missing.append("ADB")
        if missing:
            raise RuntimeError("F0 physical preflight missing: " + ", ".join(missing))

    commands: list[CommandResult] = []
    if args.execute and not args.skip_flash:
        esp_dir = REPO_ROOT / "qualification" / "embedded" / "esp32_dual_core"
        commands.append(
            run_logged(
                "f0_esp32_build",
                [hardware["pio"], "run", "-e", args.esp_env],
                cwd=esp_dir,
                artifacts_dir=phase_dir,
            )
        )
        require_commands_pass(commands)
        firmware = esp_dir / ".pio" / "build" / args.esp_env / "firmware.bin"
        if not firmware.exists():
            raise RuntimeError(f"Expected ESP32 firmware binary not found: {firmware}")
        pre_upload_hash = sha256_file(firmware)
        commands.append(
            run_logged(
                "f0_esp32_upload",
                [hardware["pio"], "run", "-e", args.esp_env, "-t", "upload"],
                cwd=esp_dir,
                artifacts_dir=phase_dir,
            )
        )
        require_commands_pass(commands)
        post_upload_hash = sha256_file(firmware)
        if pre_upload_hash != post_upload_hash:
            raise RuntimeError("ESP32 firmware changed during upload")
        details["binary_attestation"]["esp32"] = {
            "path": str(firmware),
            "sha256": post_upload_hash,
            "environment": args.esp_env,
        }

        adb = str(hardware["adb"])
        uno_dir = REPO_ROOT / "qualification" / "embedded" / "uno_q_authority"
        remote = "/tmp/uno_q_authority_final"
        build = f"{remote}/build"
        commands.append(
            run_logged(
                "f0_unoq_prepare",
                [adb, "-s", args.uno_device, "shell", f"rm -rf {remote}; mkdir -p {remote} {build}"],
                cwd=uno_dir,
                artifacts_dir=phase_dir,
            )
        )
        for fname in ("uno_q_authority.ino", "uow_embedded.hpp", "uow_embedded.cpp"):
            commands.append(
                run_logged(
                    f"f0_unoq_push_{fname.replace('.', '_')}",
                    [adb, "-s", args.uno_device, "push", str(uno_dir / fname), f"{remote}/{fname}"],
                    cwd=uno_dir,
                    artifacts_dir=phase_dir,
                )
            )
        commands.append(
            run_logged(
                "f0_unoq_compile",
                [
                    adb,
                    "-s",
                    args.uno_device,
                    "shell",
                    f"arduino-cli compile --output-dir {build} -b arduino:zephyr:unoq {remote}",
                ],
                cwd=uno_dir,
                artifacts_dir=phase_dir,
            )
        )
        require_commands_pass(commands)

        hash_cp = subprocess.run(
            [adb, "-s", args.uno_device, "shell", f"find {build} -type f -exec sha256sum {{}} \\;"],
            cwd=uno_dir,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        remote_hashes: list[dict[str, str]] = []
        for line in hash_cp.stdout.splitlines():
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2 and len(parts[0]) == 64:
                remote_hashes.append({"sha256": parts[0], "path": parts[1]})
        if not remote_hashes:
            raise RuntimeError("UNO-Q compile produced no hashable build outputs")
        details["binary_attestation"]["uno_q"] = {
            "device": args.uno_device,
            "remote_build_dir": build,
            "outputs": remote_hashes,
        }
        commands.append(
            run_logged(
                "f0_unoq_upload",
                [
                    adb,
                    "-s",
                    args.uno_device,
                    "shell",
                    f"arduino-cli upload --input-dir {build} -b arduino:zephyr:unoq {remote}",
                ],
                cwd=uno_dir,
                artifacts_dir=phase_dir,
            )
        )
        require_commands_pass(commands)

    if args.execute and args.skip_flash:
        details["binary_attestation"]["note"] = (
            "Flash skipped by operator. Existing firmware may be exercised only if its binary hashes "
            "are independently supplied and bound before physical claim promotion."
        )

    (phase_dir / "f0-candidate-attestation.json").write_text(
        json.dumps(details, indent=2),
        encoding="utf-8",
    )
    return PhaseResult("F0", True, details, commands)


def command_phase(
    phase: str,
    specs: Sequence[tuple[str, Sequence[str], Path]],
    phase_dir: Path,
) -> PhaseResult:
    commands = [
        run_logged(name, argv, cwd=cwd, artifacts_dir=phase_dir)
        for name, argv, cwd in specs
    ]
    require_commands_pass(commands)
    return PhaseResult(phase, True, {}, commands)


def f1(args: argparse.Namespace, phase_dir: Path) -> PhaseResult:
    py = sys.executable
    host = REPO_ROOT / "qualification" / "embedded" / "esp32_dual_core" / "host"
    specs = [
        (
            "f1_esp32_qualify_all",
            [
                py,
                "interrogator.py",
                "--port",
                args.esp_port,
                "--baud",
                str(args.baud),
                "--transcript",
                str(phase_dir / "esp32-transcript.jsonl"),
                "qualify-all",
                "--stress-trials",
                str(args.stress_trials),
                "--seed",
                str(args.seed),
                "--report",
                str(phase_dir / "esp32-qualification.json"),
            ],
            host,
        ),
        (
            "f1_physical_pair",
            [py, "qualification/distributed_authority/physical_pair_campaign.py"],
            REPO_ROOT,
        ),
        (
            "f1_physical_quorum",
            [py, "qualification/distributed_authority/physical_quorum_campaign.py"],
            REPO_ROOT,
        ),
    ]
    return command_phase("F1", specs, phase_dir)


def f2(args: argparse.Namespace, phase_dir: Path) -> PhaseResult:
    py = sys.executable
    host = REPO_ROOT / "qualification" / "embedded" / "esp32_dual_core" / "host"
    specs = [
        (
            "f2_heterogeneous_router",
            [
                py,
                "router_campaign.py",
                "--port",
                args.esp_port,
                "--baud",
                str(args.baud),
                "--physical",
                "--jobs",
                str(args.jobs),
                "--concurrency",
                str(args.concurrency),
                "--seed",
                str(args.seed),
                "--stochastic",
                "--adversarial-at",
                str(max(1, args.jobs // 2)),
                "--artifacts",
                str(phase_dir),
            ],
            host,
        )
    ]
    return command_phase("F2", specs, phase_dir)


def f3(args: argparse.Namespace, phase_dir: Path) -> PhaseResult:
    return command_phase(
        "F3",
        [("f3_npu_adaptive", [sys.executable, "qualification/npu_adaptive_campaign.py"], REPO_ROOT)],
        phase_dir,
    )


def f4(args: argparse.Namespace, phase_dir: Path) -> PhaseResult:
    return command_phase(
        "F4",
        [("f4_npu_hot_swap", [sys.executable, "qualification/npu_hot_swap_campaign.py"], REPO_ROOT)],
        phase_dir,
    )


def f5(args: argparse.Namespace, phase_dir: Path) -> PhaseResult:
    return command_phase(
        "F5",
        [
            (
                "f5_continuous_adaptation",
                [sys.executable, "qualification/npu_continuous_drift_campaign.py", "--device", "NPU"],
                REPO_ROOT,
            )
        ],
        phase_dir,
    )


def f6(args: argparse.Namespace, phase_dir: Path) -> PhaseResult:
    return command_phase(
        "F6",
        [
            (
                "f6_adaptive_physical_quorum",
                [sys.executable, "qualification/npu_quorum_campaign.py", "--device", "NPU"],
                REPO_ROOT,
            )
        ],
        phase_dir,
    )


def run_frozen_oracle(
    *,
    name: str,
    commit: str,
    pytest_paths: Sequence[str],
    phase_dir: Path,
) -> CommandResult:
    with tempfile.TemporaryDirectory(prefix=f"uow-{name}-") as tmp:
        wt = Path(tmp) / "worktree"
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(wt), commit],
            cwd=REPO_ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            env = os.environ.copy()
            py_path = os.pathsep.join([str(wt / "src"), str(wt), env.get("PYTHONPATH", "")])
            env["PYTHONPATH"] = py_path
            return run_logged(
                name,
                [sys.executable, "-m", "pytest", "-q", *pytest_paths],
                cwd=wt,
                artifacts_dir=phase_dir,
                env=env,
            )
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(wt)],
                cwd=REPO_ROOT,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )


def f7(args: argparse.Namespace, phase_dir: Path) -> PhaseResult:
    cmd = run_frozen_oracle(
        name="f7_a3_frozen_oracle",
        commit=A3_COMMIT,
        pytest_paths=["tests/a3"],
        phase_dir=phase_dir,
    )
    require_commands_pass([cmd])
    details = {
        "reference_ref": A3_REF,
        "reference_commit": A3_COMMIT,
        "physical_continuum_dependency": "F2",
        "historical_long_soak_reused_only_for_original_head": True,
        "new_long_soak_required_if_changed_mechanism_claimed": True,
    }
    return PhaseResult("F7", True, details, [cmd])


def f8(args: argparse.Namespace, phase_dir: Path) -> PhaseResult:
    # Re-run the exact frozen reduced candidate rather than the later operator-harness branch.
    candidate = run_frozen_oracle(
        name="f8_candidate_exact_seal_shadow",
        commit=CANDIDATE_COMMIT,
        pytest_paths=["architecture/shadow/python/tests"],
        phase_dir=phase_dir,
    )
    oracle = run_frozen_oracle(
        name="f8_post_a3_p1_p5_frozen_oracle",
        commit=P1_P5_COMMIT,
        pytest_paths=[
            "tests/test_policy_orchestrator.py",
            "tests/test_p1_end_to_end_orchestration.py",
            "tests/test_p2_live_policy_promotion.py",
            "tests/test_p3_live_drift_and_requalification.py",
            "tests/test_p4_distributed_policy_authority.py",
            "tests/test_p5_durable_recovery.py",
        ],
        phase_dir=phase_dir,
    )
    require_commands_pass([candidate, oracle])
    candidate_count = require_pytest_pass_count(candidate, CANDIDATE_SHADOW_TESTS)
    policy_count = require_pytest_pass_count(oracle, P1_P5_POLICY_SUITE_TESTS)

    gate_map = REPO_ROOT / "experiments" / "reference-oracles" / "gate_map.yaml"
    gate_text = gate_map.read_text(encoding="utf-8")
    missing = [gate for gate in P1_P5_INVARIANTS if gate not in gate_text]
    if missing:
        raise RuntimeError("P1-P5 invariant gate map missing: " + ", ".join(missing))
    details = {
        "layer": "POST_A3_POLICY_ORCHESTRATOR_P1_P5",
        "candidate_exact_seal_commit": CANDIDATE_COMMIT,
        "candidate_shadow_tests_passed": candidate_count,
        "reference_ref": P1_P5_REF,
        "reference_tag": P1_P5_TAG,
        "reference_commit": P1_P5_COMMIT,
        "policy_suite_tests_passed": policy_count,
        "historical_full_repository_tests_passed": P1_P5_FULL_REPOSITORY_TESTS,
        "mandatory_invariants": list(P1_P5_INVARIANTS),
        "mandatory_invariant_count": len(P1_P5_INVARIANTS),
        "gate_map_sha256": sha256_file(gate_map),
        "physical_phase_dependencies": ["F1", "F2", "F3", "F4", "F5", "F6"],
        "a3_evidence_inherited_not_double_counted": True,
        "p1_p5_specific_evidence_required": True,
        "p6_required": False,
    }
    return PhaseResult("F8", True, details, [candidate, oracle])


PHASE_RUNNERS = {
    "F0": f0_attestation,
    "F1": f1,
    "F2": f2,
    "F3": f3,
    "F4": f4,
    "F5": f5,
    "F6": f6,
    "F7": f7,
    "F8": f8,
}


def selected_phases(start: str, end: str) -> tuple[str, ...]:
    i = PHASES.index(start)
    j = PHASES.index(end)
    if i > j:
        raise ValueError("--from-phase must not come after --through-phase")
    return PHASES[i : j + 1]


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "candidate_ref": CANDIDATE_REF,
        "candidate_commit": CANDIDATE_COMMIT,
        "harness_commit": harness_commit(),
        "phases": list(selected_phases(args.from_phase, args.through_phase)),
        "hardware": {
            "esp32": args.esp_port,
            "uno_q": args.uno_port,
            "authority_c": "127.0.0.1:9527",
            "cuda_gpu_required": True,
            "openvino_npu_required": True,
        },
        "fail_closed": True,
        "cpu_fallback_allowed_for_npu_claims": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the final UoW F0-F8 physical qualification campaign.")
    ap.add_argument("--execute", action="store_true", help="Actually execute hardware/qualification phases. Without this flag, print the plan only.")
    ap.add_argument("--from-phase", choices=PHASES, default="F0")
    ap.add_argument("--through-phase", choices=PHASES, default="F8")
    ap.add_argument("--artifacts", type=Path, default=REPO_ROOT / "qualification" / "artifacts" / "final-physical")
    ap.add_argument("--esp-port", default="COM10")
    ap.add_argument("--uno-port", default="COM5")
    ap.add_argument("--uno-device", default="3093395174")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--esp-env", default="esp32s3_p0_a1")
    ap.add_argument("--stress-trials", type=int, default=100)
    ap.add_argument("--jobs", type=int, default=1200)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20260924)
    ap.add_argument("--skip-flash", action="store_true", help="Do not build/flash in F0. Existing binary attestation must be supplied separately before claim promotion.")
    args = ap.parse_args()

    plan = build_plan(args)
    print(json.dumps(plan, indent=2))
    if not args.execute:
        return 0

    if args.esp_port != "COM10" or args.uno_port != "COM5":
        raise RuntimeError(
            "Current physical pair/quorum campaigns are frozen with COM10/COM5 endpoints. "
            "Do not relabel alternate ports without explicitly updating and requalifying the operator harness."
        )

    run_root = args.artifacts / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_root.mkdir(parents=True, exist_ok=False)
    (run_root / "campaign-plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")

    results: list[PhaseResult] = []
    overall_passed = False
    try:
        for phase in selected_phases(args.from_phase, args.through_phase):
            phase_dir = run_root / phase
            phase_dir.mkdir(parents=True, exist_ok=True)
            print("\n" + "=" * 80)
            print(f"{phase}: FINAL PHYSICAL CONFIRMATION")
            print("=" * 80)
            result = PHASE_RUNNERS[phase](args, phase_dir)
            results.append(result)
            (phase_dir / "phase-result.json").write_text(
                json.dumps(asdict(result), indent=2),
                encoding="utf-8",
            )
            if not result.passed:
                raise RuntimeError(f"{phase} failed")

        overall_passed = all(r.passed for r in results)
        return 0 if overall_passed else 2
    finally:
        summary = {
            "schema_version": "uow-final-physical-campaign-v1.0",
            "candidate_ref": CANDIDATE_REF,
            "candidate_commit": CANDIDATE_COMMIT,
            "harness_commit": harness_commit(),
            "started_plan": plan,
            "completed_at": utc_now(),
            "phases": [asdict(r) for r in results],
            "passed": overall_passed,
            "physical_claims_promotable": overall_passed and args.from_phase == "F0" and args.through_phase == "F8" and not args.skip_flash,
        }
        (run_root / "final-physical-campaign-summary.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    raise SystemExit(main())
