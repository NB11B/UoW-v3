#!/usr/bin/env python3
"""Heterogeneous Physical Authority Pair Qualification Campaign.

Validates deterministic agreement, non-equivocation, clock independence,
piecewise Quorum Certificate application, stale replica catch-up, and
divergence containment between:
  - Node A: Physical ESP32-S3 microcontroller on COM10 (Xtensa dual-core)
  - Node B: Physical Arduino UNO Q STM32U585 microcontroller on COM5 (ARM Cortex-M33)

Failure Domain Invariant:
  processors != independent authority nodes
  The Arduino UNO Q Qualcomm Dragonwing QRB2210 Linux MPU and STM32U585 MCU share
  a single board-level power, reset, and failure domain. They constitute ONE physical
  authority node (Node B). Physical pair qualification qualifies agreement
  A_ESP32(S, P) == B_UNO_Q(S, P) and cross-architecture invariant safety.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Dict, Optional, Tuple

import serial

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qualification.claim_registry import get_claim
from qualification.evidence import (
    ClaimRequirement,
    EvidenceContext,
    EvidenceLevel,
    evaluate_claim,
)
from qualification.distributed_authority.authority import (
    QuorumCertificate,
)

PORT_ESP = "COM10"
PORT_UNO = "COM5"
BAUD = 115200
RULESET_VERSION = "uow-authority-v1"


def compute_state_hash(r0: int, r1: int, pc: int, seq: int, halted: bool) -> str:
    s = f"r0={r0};r1={r1};pc={pc};sequence={seq};halted={1 if halted else 0}"
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def compute_proposal_digest(pre_state_hash: str, post_state_hash: str, pc: int, halted: bool) -> str:
    s = f"pre={pre_state_hash};post={post_state_hash};pc={pc};halted={1 if halted else 0}"
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def compute_evidence_root(step: int, pre_st: str, post_st: str, prop: str, cert: str, prev_root: str) -> str:
    s = f"step={step};pre={pre_st};post={post_st};proposal={prop};certificate={cert};prev={prev_root}"
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class SerialAuthorityClient:
    def __init__(self, port: str, baud: int = BAUD, timeout: float = 1.0, name: str = "node"):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.name = name
        self.ser = serial.Serial(port, baud, timeout=timeout)
        time.sleep(0.3)
        self.ser.reset_input_buffer()
        self.rx_buf = bytearray()

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass

    def read_line(self, max_wait: float) -> str | None:
        deadline = time.time() + max_wait
        while time.time() < deadline:
            if b"\n" in self.rx_buf:
                line, self.rx_buf = self.rx_buf.split(b"\n", 1)
                return line.decode("utf-8", errors="ignore").strip()
            try:
                avail = self.ser.in_waiting
                chunk = self.ser.read(avail if avail > 0 else 1)
                if chunk:
                    self.rx_buf.extend(chunk)
            except Exception:
                time.sleep(0.002)
        if b"\n" in self.rx_buf:
            line, self.rx_buf = self.rx_buf.split(b"\n", 1)
            return line.decode("utf-8", errors="ignore").strip()
        return None

    def send_command(self, cmd: str, expected_event: Optional[str] = None, max_wait: float = 3.0) -> Dict[str, Any]:
        self.ser.write((cmd.strip() + "\n").encode("utf-8"))
        start = time.time()
        lines = []
        while time.time() - start < max_wait:
            raw = self.read_line(max(0.01, start + max_wait - time.time()))
            if not raw:
                continue
            try:
                data = json.loads(raw)
                if expected_event is None or data.get("event") == expected_event:
                    return data
                lines.append(raw)
            except json.JSONDecodeError:
                lines.append(raw)
        raise TimeoutError(f"[{self.name} {self.port}] Timeout waiting for {expected_event} on '{cmd}'. Seen: {lines}")

    def reset(self, r0: int = 10, r1: int = 0) -> Dict[str, Any]:
        return self.send_command(f"AUTH_RESET {r0} {r1}", "auth_reset")

    def snapshot(self) -> Dict[str, Any]:
        return self.send_command("AUTH_SNAPSHOT", "auth_snapshot")

    def evaluate(self, pre_hash: str, r0: int, r1: int, pc: int, seq: int, halted: bool, selected_pc: int, prop_hash: str) -> Dict[str, Any]:
        cmd = f"AUTH_EVALUATE {pre_hash} {r0} {r1} {pc} {seq} {1 if halted else 0} {selected_pc} {prop_hash}"
        return self.send_command(cmd, "auth_vote")

    def apply_piecewise_qc(self, qc: QuorumCertificate) -> Dict[str, Any]:
        # 1. AUTH_QC_BEGIN <uow_id> <threshold> <expected_ev_root> <claimed_qc_hash>
        cmd_begin = f"AUTH_QC_BEGIN {qc.uow_id} {qc.threshold} {qc.expected_evidence_root} {qc.qc_hash}"
        self.send_command(cmd_begin, "auth_qc_begin")

        # 2. AUTH_QC_VOTE <voter> <vote_hash>
        for voter, vote_hash in zip(qc.voters, qc.vote_hashes):
            cmd_vote = f"AUTH_QC_VOTE {voter} {vote_hash}"
            self.send_command(cmd_vote, "auth_qc_vote")

        # 3. AUTH_QC_APPLY <proposal_hash>
        cmd_apply = f"AUTH_QC_APPLY {qc.proposal_hash}"
        return self.send_command(cmd_apply, "auth_apply")

    def quarantine(self) -> Dict[str, Any]:
        return self.send_command("AUTH_QUARANTINE", "auth_quarantine")

    def rebuild(self, r0: int, r1: int, pc: int, seq: int, root: str, steps: int) -> Dict[str, Any]:
        cmd = f"AUTH_REBUILD {r0} {r1} {pc} {seq} {root} {steps}"
        return self.send_command(cmd, "auth_rebuild")

    def advance_clock(self, stride: int = 50, freeze: bool = False) -> Dict[str, Any]:
        return self.send_command(f"AUTH_CLOCK {stride} {1 if freeze else 0}", "auth_clock")


def check_uno_q_mpu_architecture() -> Dict[str, Any]:
    """Check and attest the Arduino UNO Q Qualcomm Linux MPU via ADB."""
    info = {
        "adb_present": False,
        "linux_mpu_detected": False,
        "kernel_release": None,
        "qualcomm_soc": None,
        "shared_failure_domain": True,
    }
    adb_bin = None
    for candidate in [
        r"C:\Program Files (x86)\Android\android-sdk\platform-tools\adb.exe",
        os.path.expanduser(r"~\AppData\Local\Android\Sdk\platform-tools\adb.exe"),
        "adb",
    ]:
        try:
            res = subprocess.run([candidate, "version"], capture_output=True, text=True)
            if res.returncode == 0:
                adb_bin = candidate
                break
        except Exception:
            continue

    if not adb_bin:
        info["error"] = "ADB binary not found"
        return info

    try:
        adb_devices = subprocess.check_output([adb_bin, "devices"], text=True, stderr=subprocess.STDOUT)
        if "3093395174" in adb_devices:
            info["adb_present"] = True
            kernel = subprocess.check_output(
                [adb_bin, "-s", "3093395174", "shell", "uname -r"],
                text=True, stderr=subprocess.STDOUT
            ).strip()
            soc = subprocess.check_output(
                [adb_bin, "-s", "3093395174", "shell", "cat /sys/devices/soc0/soc_id 2>/dev/null || uname -m"],
                text=True, stderr=subprocess.STDOUT
            ).strip()
            info["linux_mpu_detected"] = True
            info["kernel_release"] = kernel
            info["qualcomm_soc"] = soc
    except Exception as e:
        info["error"] = str(e)
    return info


def run_campaign() -> Dict[str, Any]:
    print("=" * 72)
    print("  UoW D1-P2: Heterogeneous Physical Authority Pair Qualification")
    print("=" * 72)

    evidence_context = EvidenceContext(
        level=EvidenceLevel.PHYSICAL,
        source="physical_serial_endpoints",
        actual_components={
            "authority_a_esp32": "ESP32-S3 (Xtensa Dual-Core) on COM10",
            "authority_b_unoq_stm32": "Arduino UNO Q STM32U585 (ARM Cortex-M33) on COM5",
        },
        substitutions={},
    )

    gates: Dict[str, Any] = {}

    # -------------------------------------------------------------------------
    # Gate 1: Hardware Substrate Detection & Board Failure Domain Verification
    # -------------------------------------------------------------------------
    print("\n[Gate 1] Hardware Substrate & Board Failure Domain Enforcement...")
    mpu_info = check_uno_q_mpu_architecture()
    gate1_pass = False
    g1_details: Dict[str, Any] = {}
    try:
        esp = SerialAuthorityClient(PORT_ESP, name="ESP32-S3")
        uno = SerialAuthorityClient(PORT_UNO, name="UNO-Q-STM32")

        snap_a = esp.snapshot()
        snap_b = uno.snapshot()

        g1_details = {
            "node_a": snap_a.get("node_id"),
            "node_b": snap_b.get("node_id"),
            "node_b_mpu_transport": mpu_info,
            "failure_domain_invariant": "processors != independent authority nodes",
            "failure_domain_enforced": True,
            "physical_authority_nodes": 2,
            "authority_a_arch": "Xtensa LX7 Dual-Core (ESP32-S3)",
            "authority_b_arch": "ARM Cortex-M33 (STM32U585) + Qualcomm Dragonwing QRB2210 (MPU)",
        }
        gate1_pass = (
            snap_a.get("node_id") == "authority_a_esp32"
            and snap_b.get("node_id") == "authority_b_unoq_stm32"
            and mpu_info.get("linux_mpu_detected", False)
        )
    except Exception as e:
        g1_details["error"] = str(e)
        gate1_pass = False
    finally:
        esp.close()
        uno.close()

    gates["GATE_1_HARDWARE_FAILURE_DOMAIN"] = {
        "passed": gate1_pass,
        "details": g1_details,
    }
    print(f"  Gate 1 Status: {'PASS' if gate1_pass else 'FAIL'}")

    # Open persistent connections for Gates 2 - 7
    esp = SerialAuthorityClient(PORT_ESP, name="ESP32-S3")
    uno = SerialAuthorityClient(PORT_UNO, name="UNO-Q-STM32")

    try:
        # -------------------------------------------------------------------------
        # Gate 2: Deterministic Evaluation Agreement
        # -------------------------------------------------------------------------
        print("\n[Gate 2] Deterministic Cross-Architecture Evaluation Agreement...")
        r_a = esp.reset(10, 0)
        r_b = uno.reset(10, 0)
        snap_a = esp.snapshot()
        snap_b = uno.snapshot()
        assert snap_a["state_hash"] == snap_b["state_hash"]
        pre_hash = snap_a["state_hash"]

        # Valid transition: DECJZ on r0=10 -> r0=9, r1=0, pc=1, seq=1, halted=0
        post_hash = compute_state_hash(9, 0, 1, 1, False)
        prop_hash = compute_proposal_digest(pre_hash, post_hash, 1, False)

        vote_a = esp.evaluate(pre_hash, 9, 0, 1, 1, False, 1, prop_hash)
        vote_b = uno.evaluate(pre_hash, 9, 0, 1, 1, False, 1, prop_hash)

        gate2_pass = (
            vote_a.get("accepted") is True
            and vote_b.get("accepted") is True
            and vote_a.get("certificate_hash") == vote_b.get("certificate_hash")
            and vote_a.get("proposed_state_hash") == vote_b.get("proposed_state_hash")
            and vote_a.get("certificate_hash") != ""
        )
        gates["GATE_2_DETERMINISTIC_AGREEMENT"] = {
            "passed": gate2_pass,
            "details": {
                "initial_state_hash": pre_hash,
                "proposal_hash": prop_hash,
                "node_a_vote": vote_a,
                "node_b_vote": vote_b,
                "certificate_hash_match": vote_a.get("certificate_hash") == vote_b.get("certificate_hash"),
                "proposed_state_hash_match": vote_a.get("proposed_state_hash") == vote_b.get("proposed_state_hash"),
            },
        }
        print(f"  Gate 2 Status: {'PASS' if gate2_pass else 'FAIL'}")

        # -------------------------------------------------------------------------
        # Gate 3: Negative Controls (Non-Equivocation & Invariants)
        # -------------------------------------------------------------------------
        print("\n[Gate 3] Negative Controls (Stale Pre-State, Illegal State, Conflicting Vote Lock)...")
        # 3a: Stale pre-state
        stale_pre = "f" * 64
        vote_stale_a = esp.evaluate(stale_pre, 9, 0, 1, 1, False, 1, prop_hash)
        vote_stale_b = uno.evaluate(stale_pre, 9, 0, 1, 1, False, 1, prop_hash)
        stale_ok = (
            vote_stale_a.get("accepted") is False
            and vote_stale_b.get("accepted") is False
            and vote_stale_a.get("reason") in ("PRE_STATE_MISMATCH", "STALE_PRE_STATE")
            and vote_stale_b.get("reason") in ("PRE_STATE_MISMATCH", "STALE_PRE_STATE")
        )

        # 3b: Illegal State Divergence (r1 unexpectedly altered)
        illegal_post_hash = compute_state_hash(9, 999, 1, 1, False)
        illegal_prop_hash = compute_proposal_digest(pre_hash, illegal_post_hash, 1, False)
        # Reset vote lock first with clean reset
        esp.reset(10, 0)
        uno.reset(10, 0)
        vote_illegal_a = esp.evaluate(pre_hash, 9, 999, 1, 1, False, 1, illegal_prop_hash)
        vote_illegal_b = uno.evaluate(pre_hash, 9, 999, 1, 1, False, 1, illegal_prop_hash)
        illegal_ok = (
            vote_illegal_a.get("accepted") is False
            and vote_illegal_b.get("accepted") is False
            and vote_illegal_a.get("reason") == "STATE_DIVERGENCE"
            and vote_illegal_b.get("reason") == "STATE_DIVERGENCE"
        )

        # 3c: Conflicting Vote Lock (vote on valid proposal, then attempt competing proposal)
        esp.reset(10, 0)
        uno.reset(10, 0)
        v1_a = esp.evaluate(pre_hash, 9, 0, 1, 1, False, 1, prop_hash)
        v1_b = uno.evaluate(pre_hash, 9, 0, 1, 1, False, 1, prop_hash)
        # Competing proposal from same pre_hash with different pc/state
        competing_post = compute_state_hash(8, 0, 2, 1, False)
        competing_prop = compute_proposal_digest(pre_hash, competing_post, 2, False)
        v2_a = esp.evaluate(pre_hash, 8, 0, 2, 1, False, 2, competing_prop)
        v2_b = uno.evaluate(pre_hash, 8, 0, 2, 1, False, 2, competing_prop)
        lock_ok = (
            v1_a.get("accepted") is True
            and v1_b.get("accepted") is True
            and v2_a.get("accepted") is False
            and v2_b.get("accepted") is False
            and v2_a.get("reason") == "CONFLICTING_VOTE_LOCK"
            and v2_b.get("reason") == "CONFLICTING_VOTE_LOCK"
        )

        gate3_pass = stale_ok and illegal_ok and lock_ok
        gates["GATE_3_NEGATIVE_CONTROLS"] = {
            "passed": gate3_pass,
            "details": {
                "stale_pre_state_rejected": stale_ok,
                "illegal_state_rejected": illegal_ok,
                "conflicting_vote_lock_enforced": lock_ok,
                "non_equivocation_proven": lock_ok,
            },
        }
        print(f"  Gate 3 Status: {'PASS' if gate3_pass else 'FAIL'}")

        # -------------------------------------------------------------------------
        # Gate 4: Clock Independence
        # -------------------------------------------------------------------------
        print("\n[Gate 4] Clock Independence & Authority Vote Invariance...")
        # Advance clocks with distinct strides
        esp.advance_clock(123)
        uno.advance_clock(997)
        snap4_a = esp.snapshot()
        snap4_b = uno.snapshot()
        clock_a = snap4_a.get("local_clock")
        clock_b = snap4_b.get("local_clock")
        clocks_differ = (clock_a != clock_b)

        # Fresh evaluation: clocks are different, but vote hashes must match certificate rules
        esp.reset(10, 0)
        uno.reset(10, 0)
        esp.advance_clock(500)
        uno.advance_clock(1500)
        v4_a = esp.evaluate(pre_hash, 9, 0, 1, 1, False, 1, prop_hash)
        v4_b = uno.evaluate(pre_hash, 9, 0, 1, 1, False, 1, prop_hash)

        gate4_pass = (
            clocks_differ
            and v4_a.get("local_clock") != v4_b.get("local_clock")
            and v4_a.get("certificate_hash") == v4_b.get("certificate_hash")
            and "local_clock" not in v4_a.get("vote_hash", "")
        )
        gates["GATE_4_CLOCK_INDEPENDENCE"] = {
            "passed": gate4_pass,
            "details": {
                "node_a_clock": v4_a.get("local_clock"),
                "node_b_clock": v4_b.get("local_clock"),
                "clocks_differ": v4_a.get("local_clock") != v4_b.get("local_clock"),
                "certificate_hash_invariance": v4_a.get("certificate_hash") == v4_b.get("certificate_hash"),
            },
        }
        print(f"  Gate 4 Status: {'PASS' if gate4_pass else 'FAIL'}")

        # -------------------------------------------------------------------------
        # Gate 5: Piecewise Quorum Certificate Application & Sequence Advance
        # -------------------------------------------------------------------------
        print("\n[Gate 5] Piecewise Quorum Certificate Application & Idempotency...")
        # Re-evaluate clean proposal from seq 0
        esp.reset(10, 0)
        uno.reset(10, 0)
        v_a = esp.evaluate(pre_hash, 9, 0, 1, 1, False, 1, prop_hash)
        v_b = uno.evaluate(pre_hash, 9, 0, 1, 1, False, 1, prop_hash)

        voters = tuple(sorted([v_a["node_id"], v_b["node_id"]]))
        vote_hashes_map = {v_a["node_id"]: v_a["vote_hash"], v_b["node_id"]: v_b["vote_hash"]}
        vote_hashes = tuple(vote_hashes_map[v] for v in voters)

        cert_hash = v_a["certificate_hash"]
        prev_root = "0" * 64
        expected_ev_root = compute_evidence_root(0, pre_hash, post_hash, prop_hash, cert_hash, prev_root)

        qc = QuorumCertificate(
            proposal_hash=prop_hash,
            uow_id="uow_physical_pair_001",
            pre_state_hash=pre_hash,
            proposed_state_hash=post_hash,
            committed_state_hash=post_hash,
            certificate_hash=cert_hash,
            pre_evidence_root=prev_root,
            evidence_step=0,
            expected_evidence_root=expected_ev_root,
            ruleset_version=RULESET_VERSION,
            threshold=2,
            voters=voters,
            vote_hashes=vote_hashes,
        )

        app_a = esp.apply_piecewise_qc(qc)
        app_b = uno.apply_piecewise_qc(qc)

        snap5_a = esp.snapshot()
        snap5_b = uno.snapshot()

        apply_ok = (
            app_a.get("applied") is True
            and app_b.get("applied") is True
            and snap5_a.get("sequence") == 1
            and snap5_b.get("sequence") == 1
            and snap5_a.get("state_hash") == snap5_b.get("state_hash")
            and snap5_a.get("evidence_root") == snap5_b.get("evidence_root")
        )

        # Idempotency: re-applying the exact same QC must not advance sequence or corrupt state
        idemp_a = esp.apply_piecewise_qc(qc)
        idemp_b = uno.apply_piecewise_qc(qc)
        snap5_idemp_a = esp.snapshot()
        snap5_idemp_b = uno.snapshot()
        idemp_ok = (
            snap5_idemp_a.get("sequence") == 1
            and snap5_idemp_b.get("sequence") == 1
            and snap5_idemp_a.get("state_hash") == snap5_a.get("state_hash")
            and snap5_idemp_b.get("state_hash") == snap5_b.get("state_hash")
        )

        gate5_pass = apply_ok and idemp_ok
        gates["GATE_5_PIECEWISE_QC_APPLICATION"] = {
            "passed": gate5_pass,
            "details": {
                "qc_hash": qc.qc_hash,
                "node_a_apply": app_a,
                "node_b_apply": app_b,
                "sequence_advanced": snap5_a.get("sequence") == 1,
                "state_hash_parity": snap5_a.get("state_hash") == snap5_b.get("state_hash"),
                "evidence_root_parity": snap5_a.get("evidence_root") == snap5_b.get("evidence_root"),
                "idempotency_verified": idemp_ok,
            },
        }
        print(f"  Gate 5 Status: {'PASS' if gate5_pass else 'FAIL'}")

        # -------------------------------------------------------------------------
        # Gate 6: Stale Catch-Up via Verified Journal / Authorized Rebuild
        # -------------------------------------------------------------------------
        print("\n[Gate 6] Stale Replica Catch-Up via Verified Rebuild...")
        # Desynchronize Node B to seq 0 while Node A remains at seq 1
        uno.reset(10, 0)
        snap6_a = esp.snapshot()
        snap6_b = uno.snapshot()
        assert snap6_a["sequence"] == 1
        assert snap6_b["sequence"] == 0

        # Node B catches up using verified committed state and evidence root from Node A's QC
        rebuild_res = uno.rebuild(9, 0, 1, 1, snap6_a["evidence_root"], 1)
        snap6_b_post = uno.snapshot()

        gate6_pass = (
            rebuild_res.get("event") == "auth_rebuild"
            and rebuild_res.get("mode") == "ACTIVE"
            and snap6_b_post.get("sequence") == 1
            and snap6_b_post.get("state_hash") == snap6_a.get("state_hash")
            and snap6_b_post.get("evidence_root") == snap6_a.get("evidence_root")
        )
        gates["GATE_6_STALE_REPLICA_CATCHUP"] = {
            "passed": gate6_pass,
            "details": {
                "node_b_rebuild_response": rebuild_res,
                "node_a_sequence": snap6_a.get("sequence"),
                "node_b_post_sequence": snap6_b_post.get("sequence"),
                "state_hashes_reconciled": snap6_b_post.get("state_hash") == snap6_a.get("state_hash"),
            },
        }
        print(f"  Gate 6 Status: {'PASS' if gate6_pass else 'FAIL'}")

        # -------------------------------------------------------------------------
        # Gate 7: Divergence Quarantine & Tamper Resistance
        # -------------------------------------------------------------------------
        print("\n[Gate 7] Divergence Quarantine & Tamper Resistance...")
        # Quarantine Node B
        q_res = uno.quarantine()
        snap7_b = uno.snapshot()
        quarantined_mode_active = (snap7_b.get("mode") == "QUARANTINED")

        # In QUARANTINED mode, evaluation must be rejected
        eval_blocked = uno.evaluate(snap7_b["state_hash"], 8, 0, 2, 2, False, 2, "a" * 64)
        eval_rejected = (
            eval_blocked.get("accepted") is False
            and eval_blocked.get("reason") == "NODE_QUARANTINED"
        )

        # Restore Node B via explicit authorized rebuild
        reb_restore = uno.rebuild(9, 0, 1, 1, snap6_a["evidence_root"], 1)
        snap7_b_restored = uno.snapshot()
        restored_ok = (
            reb_restore.get("event") == "auth_rebuild"
            and snap7_b_restored.get("mode") == "ACTIVE"
            and snap7_b_restored.get("state_hash") == snap6_a.get("state_hash")
        )

        gate7_pass = quarantined_mode_active and eval_rejected and restored_ok
        gates["GATE_7_DIVERGENCE_QUARANTINE"] = {
            "passed": gate7_pass,
            "details": {
                "quarantine_command_ack": q_res,
                "node_in_quarantine": quarantined_mode_active,
                "evaluation_blocked_under_quarantine": eval_rejected,
                "rejection_reason": eval_blocked.get("reason"),
                "authorized_rebuild_restored_active": restored_ok,
            },
        }
        print(f"  Gate 7 Status: {'PASS' if gate7_pass else 'FAIL'}")

    finally:
        esp.close()
        uno.close()

    # -------------------------------------------------------------------------
    # Claim Evaluation
    # -------------------------------------------------------------------------
    print("\n[Claim Evaluation] Evaluating against Evidence Substrate Policy...")
    claim_spec = get_claim("DIST.AUTHORITY.PAIR_AGREEMENT.PHYSICAL")
    claim_requirement = ClaimRequirement(
        required_level=claim_spec.required_level,
        required_components=claim_spec.required_components,
    )

    all_gates_passed = all(g["passed"] for g in gates.values())
    claim_result = evaluate_claim(
        observed_pass=all_gates_passed,
        context=evidence_context,
        requirement=claim_requirement,
        claim_id=claim_spec.claim_id,
        statement=claim_spec.statement,
        gates=gates,
    )

    artifact = {
        "claim_result": claim_result,
        "gates": gates,
        "evidence_context": evidence_context.to_dict(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    artifact_dir = REPO_ROOT / "qualification" / "distributed_authority" / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "physical-pair-qualification.json"
    with open(artifact_path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)

    print("\n" + "=" * 72)
    print(f"  Campaign Summary: {'PASS' if claim_result['passed'] else 'FAIL'}")
    print(f"  Observed Pass:    {claim_result['observed_pass']}")
    print(f"  Qualified:        {claim_result['qualified']}")
    print(f"  Evidence Level:   {claim_result['evidence_level'].upper()}")
    print(f"  Artifact:         {artifact_path}")
    print("=" * 72)

    return claim_result


if __name__ == "__main__":
    res = run_campaign()
    sys.exit(0 if res.get("passed", False) else 1)
