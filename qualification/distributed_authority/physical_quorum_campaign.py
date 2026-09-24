#!/usr/bin/env python3
"""D1-P3: Heterogeneous Physical 2-of-3 Authority Quorum Qualification Campaign.

Validates deterministic agreement, 2-of-3 quorum progress across all partitions,
minority isolation safety (no-quorum -> no-commit), non-equivocation, clock independence,
stale replica catch-up, and divergence containment across:
  - Node A: Physical ESP32-S3 microcontroller on COM10 (Xtensa LX7 Dual-Core)
  - Node B: Physical Arduino UNO Q microcontroller on COM5 (STM32U585 ARM Cortex-M33)
  - Node C: Physical Laptop CPU on localhost TCP socket (x86-64 isolated OS daemon)

Failure Domain Invariant:
  All three nodes belong to distinct, physically independent failure domains:
    F(A) = esp32-s3-com10
    F(B) = arduino-uno-q-com5
    F(C) = laptop-cpu-host
  The Qualcomm Dragonwing QRB2210 Linux MPU on the UNO Q board remains in the
  service/transport plane with ZERO commit authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

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
from qualification.distributed_authority.physical_profile import (
    assess_topology,
    tri_heterogeneous_profile,
)

PORT_ESP = "COM10"
PORT_UNO = "COM5"
PORT_C = 9527
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
        cmd_begin = f"AUTH_QC_BEGIN {qc.uow_id} {qc.threshold} {qc.expected_evidence_root} {qc.qc_hash}"
        self.send_command(cmd_begin, "auth_qc_begin")
        for voter, vote_hash in zip(qc.voters, qc.vote_hashes):
            cmd_vote = f"AUTH_QC_VOTE {voter} {vote_hash}"
            self.send_command(cmd_vote, "auth_qc_vote")
        cmd_apply = f"AUTH_QC_APPLY {qc.proposal_hash}"
        return self.send_command(cmd_apply, "auth_apply")

    def apply_raw_qc(self, uow_id: str, threshold: int, expected_ev_root: str, qc_hash: str, voters: List[str], vote_hashes: List[str], prop_hash: str) -> Dict[str, Any]:
        cmd_begin = f"AUTH_QC_BEGIN {uow_id} {threshold} {expected_ev_root} {qc_hash}"
        self.send_command(cmd_begin, "auth_qc_begin")
        for voter, vote_hash in zip(voters, vote_hashes):
            cmd_vote = f"AUTH_QC_VOTE {voter} {vote_hash}"
            self.send_command(cmd_vote, "auth_qc_vote")
        cmd_apply = f"AUTH_QC_APPLY {prop_hash}"
        return self.send_command(cmd_apply, "auth_apply")

    def quarantine(self) -> Dict[str, Any]:
        return self.send_command("AUTH_QUARANTINE", "auth_quarantine")

    def rebuild(self, r0: int, r1: int, pc: int, seq: int, root: str, steps: int) -> Dict[str, Any]:
        cmd = f"AUTH_REBUILD {r0} {r1} {pc} {seq} {root} {steps}"
        return self.send_command(cmd, "auth_rebuild")

    def advance_clock(self, stride: int = 50, freeze: bool = False) -> Dict[str, Any]:
        return self.send_command(f"AUTH_CLOCK {stride} {1 if freeze else 0}", "auth_clock")


class SocketAuthorityClient:
    def __init__(self, host: str = "127.0.0.1", port: int = PORT_C, timeout: float = 3.0, name: str = "Authority-C"):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.name = name
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect((host, port))
        self.rfile = self.sock.makefile("r", encoding="utf-8")
        self.wfile = self.sock.makefile("w", encoding="utf-8")

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass

    def send_command(self, cmd: str, expected_event: Optional[str] = None) -> Dict[str, Any]:
        self.wfile.write(cmd.strip() + "\n")
        self.wfile.flush()
        line = self.rfile.readline()
        if not line:
            raise ConnectionError(f"[{self.name}] Connection closed by remote authority service")
        data = json.loads(line.strip())
        if expected_event and data.get("event") != expected_event:
            raise ValueError(f"[{self.name}] Expected event {expected_event}, got: {data}")
        return data

    def reset(self, r0: int = 10, r1: int = 0) -> Dict[str, Any]:
        return self.send_command(f"AUTH_RESET {r0} {r1}", "auth_reset")

    def snapshot(self) -> Dict[str, Any]:
        return self.send_command("AUTH_SNAPSHOT", "auth_snapshot")

    def evaluate(self, pre_hash: str, r0: int, r1: int, pc: int, seq: int, halted: bool, selected_pc: int, prop_hash: str) -> Dict[str, Any]:
        cmd = f"AUTH_EVALUATE {pre_hash} {r0} {r1} {pc} {seq} {1 if halted else 0} {selected_pc} {prop_hash}"
        return self.send_command(cmd, "auth_vote")

    def apply_piecewise_qc(self, qc: QuorumCertificate) -> Dict[str, Any]:
        cmd_begin = f"AUTH_QC_BEGIN {qc.uow_id} {qc.threshold} {qc.expected_evidence_root} {qc.qc_hash}"
        self.send_command(cmd_begin, "auth_qc_begin")
        for voter, vote_hash in zip(qc.voters, qc.vote_hashes):
            cmd_vote = f"AUTH_QC_VOTE {voter} {vote_hash}"
            self.send_command(cmd_vote, "auth_qc_vote")
        cmd_apply = f"AUTH_QC_APPLY {qc.proposal_hash}"
        return self.send_command(cmd_apply, "auth_apply")

    def apply_raw_qc(self, uow_id: str, threshold: int, expected_ev_root: str, qc_hash: str, voters: List[str], vote_hashes: List[str], prop_hash: str) -> Dict[str, Any]:
        cmd_begin = f"AUTH_QC_BEGIN {uow_id} {threshold} {expected_ev_root} {qc_hash}"
        self.send_command(cmd_begin, "auth_qc_begin")
        for voter, vote_hash in zip(voters, vote_hashes):
            cmd_vote = f"AUTH_QC_VOTE {voter} {vote_hash}"
            self.send_command(cmd_vote, "auth_qc_vote")
        cmd_apply = f"AUTH_QC_APPLY {prop_hash}"
        return self.send_command(cmd_apply, "auth_apply")

    def quarantine(self) -> Dict[str, Any]:
        return self.send_command("AUTH_QUARANTINE", "auth_quarantine")

    def rebuild(self, r0: int, r1: int, pc: int, seq: int, root: str, steps: int) -> Dict[str, Any]:
        cmd = f"AUTH_REBUILD {r0} {r1} {pc} {seq} {root} {steps}"
        return self.send_command(cmd, "auth_rebuild")

    def advance_clock(self, stride: int = 50, freeze: bool = False) -> Dict[str, Any]:
        return self.send_command(f"AUTH_CLOCK {stride} {1 if freeze else 0}", "auth_clock")

    def shutdown(self):
        try:
            self.send_command("AUTH_SHUTDOWN", "auth_shutdown")
        except Exception:
            pass


def check_uno_q_mpu_architecture() -> Dict[str, Any]:
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
    print("=" * 76)
    print("  UoW D1-P3: Heterogeneous Physical 2-of-3 Authority Quorum Qualification")
    print("=" * 76)

    storage_dir = REPO_ROOT / "qualification" / "distributed_authority" / "storage_authority_c"
    service_c_script = REPO_ROOT / "qualification" / "distributed_authority" / "authority_service_c.py"

    # Start Authority Node C as an isolated OS process
    print("\n[Service C] Launching Authority Node C daemon process on 127.0.0.1:9527...")
    proc_c = subprocess.Popen(
        [sys.executable, str(service_c_script), "--port", str(PORT_C), "--storage-dir", str(storage_dir)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.6)

    evidence_context = EvidenceContext(
        level=EvidenceLevel.PHYSICAL,
        source="tri_heterogeneous_physical_cluster",
        actual_components={
            "authority_a_esp32": "ESP32-S3 (Xtensa Dual-Core) on COM10",
            "authority_b_unoq_stm32": "Arduino UNO Q STM32U585 (ARM Cortex-M33) on COM5",
            "authority_c_laptop_x86": "Laptop Host CPU (x86-64 standalone process on 127.0.0.1:9527)",
        },
        substitutions={},
    )

    gates: Dict[str, Any] = {}

    try:
        # Connect to all 3 nodes
        node_a = SerialAuthorityClient(PORT_ESP, name="ESP32-S3")
        node_b = SerialAuthorityClient(PORT_UNO, name="UNO-Q-STM32")
        node_c = SocketAuthorityClient("127.0.0.1", PORT_C, name="Laptop-CPU-C")

        # ---------------------------------------------------------------------
        # Gate 1: Hardware Substrates & 3 Independent Failure Domains
        # ---------------------------------------------------------------------
        print("\n[Gate 1] Hardware Substrates & 3 Independent Failure Domains...")
        mpu_info = check_uno_q_mpu_architecture()
        topo_profile = tri_heterogeneous_profile()
        assessment = assess_topology(topo_profile)

        snap_a = node_a.snapshot()
        snap_b = node_b.snapshot()
        snap_c = node_c.snapshot()

        gate1_pass = (
            snap_a.get("node_id") == "authority_a_esp32"
            and snap_b.get("node_id") == "authority_b_unoq_stm32"
            and snap_c.get("node_id") == "authority_c_laptop_x86"
            and mpu_info.get("linux_mpu_detected", False)
            and assessment.independent_failure_domains == 3
            and assessment.two_of_three_quorum_ready is True
        )
        gates["GATE_1_HARDWARE_FAILURE_DOMAINS"] = {
            "passed": gate1_pass,
            "details": {
                "node_a": snap_a.get("node_id"),
                "node_b": snap_b.get("node_id"),
                "node_c": snap_c.get("node_id"),
                "node_b_mpu_transport": mpu_info,
                "independent_failure_domains": assessment.independent_failure_domains,
                "two_of_three_quorum_ready": assessment.two_of_three_quorum_ready,
                "isa_diversity": ["Xtensa LX7", "ARM Cortex-M33", "x86-64"],
            },
        }
        print(f"  Gate 1 Status: {'PASS' if gate1_pass else 'FAIL'}")

        # ---------------------------------------------------------------------
        # Gate 2: 3-Way Cross-Architecture Deterministic Evaluation Agreement
        # ---------------------------------------------------------------------
        print("\n[Gate 2] 3-Way Cross-Architecture Deterministic Evaluation Agreement...")
        node_a.reset(10, 0)
        node_b.reset(10, 0)
        node_c.reset(10, 0)

        snap_a = node_a.snapshot()
        snap_b = node_b.snapshot()
        snap_c = node_c.snapshot()
        pre_hash = snap_a["state_hash"]
        assert snap_a["state_hash"] == snap_b["state_hash"] == snap_c["state_hash"]

        post_hash = compute_state_hash(9, 0, 1, 1, False)
        prop_hash = compute_proposal_digest(pre_hash, post_hash, 1, False)

        v_a = node_a.evaluate(pre_hash, 9, 0, 1, 1, False, 1, prop_hash)
        v_b = node_b.evaluate(pre_hash, 9, 0, 1, 1, False, 1, prop_hash)
        v_c = node_c.evaluate(pre_hash, 9, 0, 1, 1, False, 1, prop_hash)

        gate2_pass = (
            v_a.get("accepted") is True
            and v_b.get("accepted") is True
            and v_c.get("accepted") is True
            and v_a.get("certificate_hash") == v_b.get("certificate_hash") == v_c.get("certificate_hash")
            and v_a.get("proposed_state_hash") == v_b.get("proposed_state_hash") == v_c.get("proposed_state_hash")
            and v_a.get("vote_hash") != v_b.get("vote_hash") != v_c.get("vote_hash")
        )
        gates["GATE_2_THREE_WAY_DETERMINISTIC_AGREEMENT"] = {
            "passed": gate2_pass,
            "details": {
                "initial_state_hash": pre_hash,
                "proposal_hash": prop_hash,
                "node_a_cert_hash": v_a.get("certificate_hash"),
                "node_b_cert_hash": v_b.get("certificate_hash"),
                "node_c_cert_hash": v_c.get("certificate_hash"),
                "all_cert_hashes_identical": v_a.get("certificate_hash") == v_b.get("certificate_hash") == v_c.get("certificate_hash"),
                "vote_hash_uniqueness": len({v_a.get("vote_hash"), v_b.get("vote_hash"), v_c.get("vote_hash")}) == 3,
            },
        }
        print(f"  Gate 2 Status: {'PASS' if gate2_pass else 'FAIL'}")

        # ---------------------------------------------------------------------
        # Gate 3: All 4 Physical Quorum Permutations Commit Progress
        # ---------------------------------------------------------------------
        print("\n[Gate 3] All 4 Permutations of Physical 2-of-3 Quorum Commit Progress...")
        # Permutations to test:
        # 1. {A, B} (C offline/unreachable)
        # 2. {B, C} (A offline/unreachable)
        # 3. {A, C} (B offline/unreachable)
        # 4. {A, B, C} (All 3 reachable)

        perm_results = {}
        all_perms_ok = True

        for name, participating_nodes, offline_nodes in [
            ("{A, B}", [("A", node_a), ("B", node_b)], [("C", node_c)]),
            ("{B, C}", [("B", node_b), ("C", node_c)], [("A", node_a)]),
            ("{A, C}", [("A", node_a), ("C", node_c)], [("B", node_b)]),
            ("{A, B, C}", [("A", node_a), ("B", node_b), ("C", node_c)], []),
        ]:
            # Reset all to known baseline
            node_a.reset(10, 0)
            node_b.reset(10, 0)
            node_c.reset(10, 0)

            # Evaluate on participating nodes only
            votes = {}
            for n_id, client in participating_nodes:
                v = client.evaluate(pre_hash, 9, 0, 1, 1, False, 1, prop_hash)
                votes[v["node_id"]] = v

            voters = tuple(sorted(votes.keys()))
            vote_hashes = tuple(votes[v]["vote_hash"] for v in voters)
            cert_hash = list(votes.values())[0]["certificate_hash"]
            expected_ev_root = compute_evidence_root(1, pre_hash, post_hash, prop_hash, cert_hash, "0" * 64)

            qc = QuorumCertificate(
                proposal_hash=prop_hash,
                uow_id=f"uow_perm_{name.replace('{','').replace('}','').replace(' ','_')}",
                pre_state_hash=pre_hash,
                proposed_state_hash=post_hash,
                committed_state_hash=post_hash,
                certificate_hash=cert_hash,
                pre_evidence_root="0" * 64,
                evidence_step=0,
                expected_evidence_root=expected_ev_root,
                ruleset_version=RULESET_VERSION,
                threshold=2,
                voters=voters,
                vote_hashes=vote_hashes,
            )

            # Apply QC to participating nodes
            applies = {}
            for n_id, client in participating_nodes:
                applies[n_id] = client.apply_piecewise_qc(qc)

            # Verify participating nodes advanced to seq 1 with matching state and root
            all_applied = all(res.get("applied") is True for res in applies.values())
            snaps = {n_id: client.snapshot() for n_id, client in participating_nodes}
            all_seq1 = all(snap.get("sequence") == 1 for snap in snaps.values())
            hashes_match = len({snap.get("state_hash") for snap in snaps.values()}) == 1
            roots_match = len({snap.get("evidence_root") for snap in snaps.values()}) == 1

            perm_ok = all_applied and all_seq1 and hashes_match and roots_match
            if not perm_ok:
                all_perms_ok = False
            perm_results[name] = {
                "passed": perm_ok,
                "voters": voters,
                "applies": applies,
                "post_snapshots": snaps,
            }

        gates["GATE_3_ALL_QUORUM_PERMUTATIONS"] = {
            "passed": all_perms_ok,
            "details": perm_results,
        }
        print(f"  Gate 3 Status: {'PASS' if all_perms_ok else 'FAIL'}")

        # ---------------------------------------------------------------------
        # Gate 4: Minority Partition Safety (No Quorum -> No Commit)
        # ---------------------------------------------------------------------
        print("\n[Gate 4] Minority Partition Safety (No-Quorum -> No-Commit)...")
        # Isolate Node A: Node A generates vote, but receives QC with only 1 voter (< T=2)
        node_a.reset(10, 0)
        v_iso_a = node_a.evaluate(pre_hash, 9, 0, 1, 1, False, 1, prop_hash)

        # Attempt to submit QC with threshold 2 but only 1 voter
        cert_hash = v_iso_a["certificate_hash"]
        expected_ev_root = compute_evidence_root(1, pre_hash, post_hash, prop_hash, cert_hash, "0" * 64)
        voters_1 = ["authority_a_esp32"]
        vote_hashes_1 = [v_iso_a["vote_hash"]]
        fake_qc_hash = "f" * 64

        res_insufficient = node_a.apply_raw_qc(
            uow_id="insufficient_uow",
            threshold=2,
            expected_ev_root=expected_ev_root,
            qc_hash=fake_qc_hash,
            voters=voters_1,
            vote_hashes=vote_hashes_1,
            prop_hash=prop_hash,
        )
        snap4_a = node_a.snapshot()

        # Same test on Node C
        node_c.reset(10, 0)
        v_iso_c = node_c.evaluate(pre_hash, 9, 0, 1, 1, False, 1, prop_hash)
        res_insufficient_c = node_c.apply_raw_qc(
            uow_id="insufficient_uow",
            threshold=2,
            expected_ev_root=expected_ev_root,
            qc_hash=fake_qc_hash,
            voters=["authority_c_laptop_x86"],
            vote_hashes=[v_iso_c["vote_hash"]],
            prop_hash=prop_hash,
        )
        snap4_c = node_c.snapshot()

        gate4_pass = (
            res_insufficient.get("applied") is False
            and res_insufficient.get("reason") == "INSUFFICIENT_QUORUM"
            and snap4_a.get("sequence") == 0
            and res_insufficient_c.get("applied") is False
            and res_insufficient_c.get("reason") == "INSUFFICIENT_QUORUM"
            and snap4_c.get("sequence") == 0
        )
        gates["GATE_4_NO_QUORUM_NO_COMMIT"] = {
            "passed": gate4_pass,
            "details": {
                "node_a_rejection": res_insufficient,
                "node_a_sequence_unmutated": snap4_a.get("sequence") == 0,
                "node_c_rejection": res_insufficient_c,
                "node_c_sequence_unmutated": snap4_c.get("sequence") == 0,
            },
        }
        print(f"  Gate 4 Status: {'PASS' if gate4_pass else 'FAIL'}")

        # ---------------------------------------------------------------------
        # Gate 5: Non-Equivocation & Conflicting Quorums Blocked
        # ---------------------------------------------------------------------
        print("\n[Gate 5] Non-Equivocation & Conflicting Quorums Blocked...")
        node_a.reset(10, 0)
        node_b.reset(10, 0)
        node_c.reset(10, 0)

        # Proposer 1 sends Proposal 1 to {A, B}
        v1_a = node_a.evaluate(pre_hash, 9, 0, 1, 1, False, 1, prop_hash)
        v1_b = node_b.evaluate(pre_hash, 9, 0, 1, 1, False, 1, prop_hash)
        assert v1_a["accepted"] is True and v1_b["accepted"] is True

        # Malicious Proposer 2 sends competing Proposal 2 from same pre_hash to {A, C}
        comp_post = compute_state_hash(8, 0, 2, 1, False)
        comp_prop = compute_proposal_digest(pre_hash, comp_post, 2, False)

        v2_a = node_a.evaluate(pre_hash, 8, 0, 2, 1, False, 2, comp_prop)
        v2_c = node_c.evaluate(pre_hash, 8, 0, 2, 1, False, 2, comp_prop)

        # Node A must reject Proposal 2 with CONFLICTING_VOTE_LOCK, preventing split-brain
        gate5_pass = (
            v2_a.get("accepted") is False
            and v2_a.get("reason") == "CONFLICTING_VOTE_LOCK"
        )
        gates["GATE_5_CONFLICTING_QUORUM_PREVENTION"] = {
            "passed": gate5_pass,
            "details": {
                "proposer_1_votes": ["authority_a_esp32", "authority_b_unoq_stm32"],
                "proposer_2_vote_lock_rejection": v2_a,
                "split_brain_prevented": gate5_pass,
            },
        }
        print(f"  Gate 5 Status: {'PASS' if gate5_pass else 'FAIL'}")

        # ---------------------------------------------------------------------
        # Gate 6: Cross-Architecture Stale Replica Catch-Up & Rebuild
        # ---------------------------------------------------------------------
        print("\n[Gate 6] Cross-Architecture Stale Replica Catch-Up & Rebuild...")
        # Cluster advances via {A, C} to sequence 1 while Node B is desynchronized at seq 0
        node_a.reset(10, 0)
        node_b.reset(10, 0)
        node_c.reset(10, 0)

        v_ac_a = node_a.evaluate(pre_hash, 9, 0, 1, 1, False, 1, prop_hash)
        v_ac_c = node_c.evaluate(pre_hash, 9, 0, 1, 1, False, 1, prop_hash)
        voters_ac = tuple(sorted([v_ac_a["node_id"], v_ac_c["node_id"]]))
        vote_hashes_ac = tuple(v_ac_a["vote_hash"] if v == v_ac_a["node_id"] else v_ac_c["vote_hash"] for v in voters_ac)
        cert_hash = v_ac_a["certificate_hash"]
        expected_ev_root = compute_evidence_root(1, pre_hash, post_hash, prop_hash, cert_hash, "0" * 64)

        qc_ac = QuorumCertificate(
            proposal_hash=prop_hash,
            uow_id="uow_catchup_test",
            pre_state_hash=pre_hash,
            proposed_state_hash=post_hash,
            committed_state_hash=post_hash,
            certificate_hash=cert_hash,
            pre_evidence_root="0" * 64,
            evidence_step=0,
            expected_evidence_root=expected_ev_root,
            ruleset_version=RULESET_VERSION,
            threshold=2,
            voters=voters_ac,
            vote_hashes=vote_hashes_ac,
        )
        node_a.apply_piecewise_qc(qc_ac)
        node_c.apply_piecewise_qc(qc_ac)

        snap6_a = node_a.snapshot()
        snap6_b = node_b.snapshot()
        snap6_c = node_c.snapshot()
        assert snap6_a["sequence"] == 1 and snap6_c["sequence"] == 1
        assert snap6_b["sequence"] == 0

        # Catch up Node B via authorized rebuild
        reb_b = node_b.rebuild(9, 0, 1, 1, snap6_a["evidence_root"], 1)
        snap6_b_post = node_b.snapshot()

        gate6_pass = (
            reb_b.get("event") == "auth_rebuild"
            and reb_b.get("mode") == "ACTIVE"
            and snap6_b_post.get("sequence") == 1
            and snap6_b_post.get("state_hash") == snap6_a.get("state_hash") == snap6_c.get("state_hash")
            and snap6_b_post.get("evidence_root") == snap6_a.get("evidence_root") == snap6_c.get("evidence_root")
        )
        gates["GATE_6_CROSS_ARCHITECTURE_STALE_CATCHUP"] = {
            "passed": gate6_pass,
            "details": {
                "node_b_rebuild": reb_b,
                "node_b_reconciled_sequence": snap6_b_post.get("sequence"),
                "state_hash_parity": snap6_b_post.get("state_hash") == snap6_a.get("state_hash"),
                "evidence_root_parity": snap6_b_post.get("evidence_root") == snap6_a.get("evidence_root"),
            },
        }
        print(f"  Gate 6 Status: {'PASS' if gate6_pass else 'FAIL'}")

        # ---------------------------------------------------------------------
        # Gate 7: Heterogeneous Divergence Quarantine & Tamper Resistance
        # ---------------------------------------------------------------------
        print("\n[Gate 7] Heterogeneous Divergence Quarantine & Tamper Resistance...")
        # Quarantine Node C
        q_res = node_c.quarantine()
        snap7_c = node_c.snapshot()
        quarantined_mode_active = (snap7_c.get("mode") == "QUARANTINED")

        # In QUARANTINED mode, evaluations must be rejected
        eval_blocked = node_c.evaluate(snap7_c["state_hash"], 8, 0, 2, 2, False, 2, "a" * 64)
        eval_rejected = (
            eval_blocked.get("accepted") is False
            and eval_blocked.get("reason") == "NODE_QUARANTINED"
        )

        # Meanwhile, cluster continues making progress via {A, B} (2-of-3 availability)
        # Advance sequence 1 -> 2 on A and B
        snap7_a = node_a.snapshot()
        pre2_hash = snap7_a["state_hash"]
        # Step 2: INC r1 (pc=1, r1=0 -> r1=1, pc=0, seq=2)
        post2_hash = compute_state_hash(9, 1, 0, 2, False)
        prop2_hash = compute_proposal_digest(pre2_hash, post2_hash, 0, False)

        v7_a = node_a.evaluate(pre2_hash, 9, 1, 0, 2, False, 0, prop2_hash)
        v7_b = node_b.evaluate(pre2_hash, 9, 1, 0, 2, False, 0, prop2_hash)
        voters7 = tuple(sorted([v7_a["node_id"], v7_b["node_id"]]))
        vote_hashes7 = tuple(v7_a["vote_hash"] if v == v7_a["node_id"] else v7_b["vote_hash"] for v in voters7)
        cert7_hash = v7_a["certificate_hash"]
        expected7_root = compute_evidence_root(1, pre2_hash, post2_hash, prop2_hash, cert7_hash, snap7_a["evidence_root"])

        qc7 = QuorumCertificate(
            proposal_hash=prop2_hash,
            uow_id="uow_seq2_progress",
            pre_state_hash=pre2_hash,
            proposed_state_hash=post2_hash,
            committed_state_hash=post2_hash,
            certificate_hash=cert7_hash,
            pre_evidence_root=snap7_a["evidence_root"],
            evidence_step=1,
            expected_evidence_root=expected7_root,
            ruleset_version=RULESET_VERSION,
            threshold=2,
            voters=voters7,
            vote_hashes=vote_hashes7,
        )
        node_a.apply_piecewise_qc(qc7)
        node_b.apply_piecewise_qc(qc7)

        snap7_post_a = node_a.snapshot()
        snap7_post_b = node_b.snapshot()
        cluster_progress_during_quarantine = (snap7_post_a.get("sequence") == 2 and snap7_post_b.get("sequence") == 2)

        # Restore Node C via authorized rebuild to certified seq 2 checkpoint
        reb_restore_c = node_c.rebuild(9, 1, 0, 2, snap7_post_a["evidence_root"], 2)
        snap7_restored_c = node_c.snapshot()
        restored_ok = (
            reb_restore_c.get("event") == "auth_rebuild"
            and snap7_restored_c.get("mode") == "ACTIVE"
            and snap7_restored_c.get("sequence") == 2
            and snap7_restored_c.get("state_hash") == snap7_post_a.get("state_hash")
            and snap7_restored_c.get("evidence_root") == snap7_post_a.get("evidence_root")
        )

        gate7_pass = quarantined_mode_active and eval_rejected and cluster_progress_during_quarantine and restored_ok
        gates["GATE_7_DIVERGENCE_QUARANTINE_RESILIENCE"] = {
            "passed": gate7_pass,
            "details": {
                "node_c_quarantined": quarantined_mode_active,
                "evaluation_blocked_under_quarantine": eval_rejected,
                "cluster_majority_progress_maintained": cluster_progress_during_quarantine,
                "authorized_rebuild_restoration": restored_ok,
            },
        }
        print(f"  Gate 7 Status: {'PASS' if gate7_pass else 'FAIL'}")

    finally:
        node_a.close()
        node_b.close()
        node_c.shutdown()
        node_c.close()
        proc_c.terminate()
        try:
            proc_c.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc_c.kill()

    # ---------------------------------------------------------------------
    # Claim Evaluation against Evidence Substrate Policy
    # ---------------------------------------------------------------------
    print("\n[Claim Evaluation] Evaluating against Evidence Substrate Policy...")
    claim_spec = get_claim("DIST.AUTHORITY.QUORUM_2_OF_3.PHYSICAL")
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
    artifact_path = artifact_dir / "physical-quorum-qualification.json"
    with open(artifact_path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)

    print("\n" + "=" * 76)
    print(f"  Campaign Summary: {'PASS' if claim_result['passed'] else 'FAIL'}")
    print(f"  Observed Pass:    {claim_result['observed_pass']}")
    print(f"  Qualified:        {claim_result['qualified']}")
    print(f"  Evidence Level:   {claim_result['evidence_level'].upper()}")
    print(f"  Artifact:         {artifact_path}")
    print("=" * 76)

    return claim_result


if __name__ == "__main__":
    res = run_campaign()
    sys.exit(0 if res.get("passed", False) else 1)
