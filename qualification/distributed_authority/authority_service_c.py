#!/usr/bin/env python3
"""Standalone Authority Node C Service (Laptop x86-64 CPU).

Runs as an independent OS service process, listening on a localhost TCP socket.
Maintains completely isolated persistent state, keys, vote locks, and evidence
ledger on the host filesystem.

Provides the third physical authority domain:
  - Node A: ESP32-S3 (Xtensa LX7 dual-core) on COM10
  - Node B: Arduino UNO Q (ARM Cortex-M33) on COM5
  - Node C: Laptop x86-64 CPU on 127.0.0.1:9527
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

NODE_ID_C = "authority_c_laptop_x86"
RULESET_VERSION = "uow-authority-v1"
DEFAULT_PORT = 9527


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def compute_state_hash(r0: int, r1: int, pc: int, seq: int, halted: bool) -> str:
    return sha256_hex(f"r0={r0};r1={r1};pc={pc};sequence={seq};halted={1 if halted else 0}")


def compute_proposal_hash(pre_state_hash: str, post_state_hash: str, pc: int, halted: bool) -> str:
    return sha256_hex(f"pre={pre_state_hash};post={post_state_hash};pc={pc};halted={1 if halted else 0}")


def compute_cert_hash(proposal_hash: str, valid: bool, reason_code: int = 0) -> str:
    return sha256_hex(f"proposal={proposal_hash};valid={1 if valid else 0};reason={reason_code}")


def compute_evidence_record_hash(step: int, pre_st: str, post_st: str, prop: str, cert: str, prev_root: str) -> str:
    return sha256_hex(f"step={step};pre={pre_st};post={post_st};proposal={prop};certificate={cert};prev={prev_root}")


def compute_vote_hash(
    accepted: bool,
    cert_hash: str,
    evidence_step: int,
    node_id: str,
    pre_evidence_root: str,
    pre_state_hash: str,
    proposal_hash: str,
    proposed_state_hash: str,
    rejection_reason: Optional[str],
    ruleset_version: str,
) -> str:
    payload = {
        "accepted": accepted,
        "certificate_hash": cert_hash,
        "evidence_step": evidence_step,
        "node_id": node_id,
        "pre_evidence_root": pre_evidence_root,
        "pre_state_hash": pre_state_hash,
        "proposal_hash": proposal_hash,
        "proposed_state_hash": proposed_state_hash,
        "rejection_reason": rejection_reason if rejection_reason else None,
        "ruleset_version": ruleset_version,
    }
    return sha256_hex(canonical_json(payload))


def compute_qc_hash(
    cert_hash: str,
    committed_state_hash: str,
    evidence_step: int,
    expected_evidence_root: str,
    pre_evidence_root: str,
    pre_state_hash: str,
    proposal_hash: str,
    proposed_state_hash: str,
    ruleset_version: str,
    threshold: int,
    uow_id: str,
    vote_hashes: List[str],
    voters: List[str],
) -> str:
    payload = {
        "certificate_hash": cert_hash,
        "committed_state_hash": committed_state_hash,
        "evidence_step": evidence_step,
        "expected_evidence_root": expected_evidence_root,
        "pre_evidence_root": pre_evidence_root,
        "pre_state_hash": pre_state_hash,
        "proposal_hash": proposal_hash,
        "proposed_state_hash": proposed_state_hash,
        "ruleset_version": ruleset_version,
        "threshold": threshold,
        "uow_id": uow_id,
        "vote_hashes": list(vote_hashes),
        "voters": list(voters),
    }
    return sha256_hex(canonical_json(payload))


class AuthorityServiceC:
    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

        # State fields
        self.r0 = 10
        self.r1 = 0
        self.pc = 0
        self.sequence = 0
        self.halted = False
        self.mode = "ACTIVE"
        self.local_clock = 3000
        self.clock_stride = 1
        self.clock_frozen = False

        # Ledger & Verification
        self.ledger_root = "0" * 64
        self.ledger_steps = 0
        self.vote_locks: Dict[str, str] = {}
        self.applied_qcs: Set[str] = set()
        self.applied_proposals: Set[str] = set()

        # Pending evaluation & piecewise QC buffer
        self.last_eval: Optional[Dict[str, Any]] = None
        self.pending_qc: Optional[Dict[str, Any]] = None

        self._load_storage()

    def _state_file(self) -> Path:
        return self.storage_dir / "state.json"

    def _load_storage(self):
        sf = self._state_file()
        if sf.exists():
            try:
                with open(sf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.r0 = data.get("r0", 10)
                self.r1 = data.get("r1", 0)
                self.pc = data.get("pc", 0)
                self.sequence = data.get("sequence", 0)
                self.halted = data.get("halted", False)
                self.mode = data.get("mode", "ACTIVE")
                self.ledger_root = data.get("ledger_root", "0" * 64)
                self.ledger_steps = data.get("ledger_steps", 0)
                self.local_clock = data.get("local_clock", 3000)
                self.applied_qcs = set(data.get("applied_qcs", []))
                self.vote_locks = data.get("vote_locks", {})
            except Exception as e:
                print(f"[AuthorityC] Error loading state: {e}", file=sys.stderr)

    def _save_storage(self):
        data = {
            "r0": self.r0,
            "r1": self.r1,
            "pc": self.pc,
            "sequence": self.sequence,
            "halted": self.halted,
            "mode": self.mode,
            "ledger_root": self.ledger_root,
            "ledger_steps": self.ledger_steps,
            "local_clock": self.local_clock,
            "applied_qcs": list(self.applied_qcs),
            "vote_locks": self.vote_locks,
        }
        with open(self._state_file(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def state_hash(self) -> str:
        return compute_state_hash(self.r0, self.r1, self.pc, self.sequence, self.halted)

    def advance_clock(self, stride: Optional[int] = None, freeze: Optional[bool] = None) -> int:
        if freeze is not None:
            self.clock_frozen = freeze
        if stride is not None:
            self.clock_stride = stride
        if not self.clock_frozen:
            self.local_clock += self.clock_stride
        return self.local_clock

    def handle_command(self, line: str) -> str:
        with self.lock:
            parts = line.strip().split()
            if not parts:
                return json.dumps({"event": "error", "reason": "empty command"})

            cmd = parts[0]

            if cmd == "AUTH_RESET":
                r0 = int(parts[1]) if len(parts) > 1 else 10
                r1 = int(parts[2]) if len(parts) > 2 else 0
                self.r0 = r0
                self.r1 = r1
                self.pc = 0
                self.sequence = 0
                self.halted = False
                self.mode = "ACTIVE"
                self.ledger_root = "0" * 64
                self.ledger_steps = 0
                self.vote_locks.clear()
                self.applied_qcs.clear()
                self.applied_proposals.clear()
                self.last_eval = None
                self.pending_qc = None
                self._save_storage()
                return json.dumps({
                    "event": "auth_reset",
                    "node_id": NODE_ID_C,
                    "mode": self.mode,
                    "r0": self.r0,
                    "r1": self.r1,
                    "pc": self.pc,
                    "sequence": self.sequence,
                    "halted": self.halted,
                    "state_hash": self.state_hash(),
                    "evidence_root": self.ledger_root,
                    "evidence_steps": self.ledger_steps,
                    "ruleset_version": RULESET_VERSION,
                    "local_clock": self.local_clock,
                })

            elif cmd in ("AUTH_SNAPSHOT", "STATUS", "SNAPSHOT"):
                return json.dumps({
                    "event": "auth_snapshot",
                    "node_id": NODE_ID_C,
                    "mode": self.mode,
                    "r0": self.r0,
                    "r1": self.r1,
                    "pc": self.pc,
                    "sequence": self.sequence,
                    "halted": self.halted,
                    "state_hash": self.state_hash(),
                    "evidence_root": self.ledger_root,
                    "evidence_steps": self.ledger_steps,
                    "ruleset_version": RULESET_VERSION,
                    "local_clock": self.local_clock,
                })

            elif cmd == "AUTH_CLOCK":
                stride = int(parts[1]) if len(parts) > 1 else 1
                freeze = (parts[2] == "1") if len(parts) > 2 else False
                self.advance_clock(stride, freeze)
                self._save_storage()
                return json.dumps({
                    "event": "auth_clock",
                    "node_id": NODE_ID_C,
                    "local_clock": self.local_clock,
                    "stride": self.clock_stride,
                    "frozen": self.clock_frozen,
                })

            elif cmd == "AUTH_EVALUATE":
                # AUTH_EVALUATE <pre_state_hash> <r0> <r1> <pc> <seq> <halted> <selected_pc> <proposal_hash>
                if len(parts) < 9:
                    return json.dumps({"event": "error", "reason": "bad AUTH_EVALUATE envelope"})

                p_pre_hash = parts[1]
                p_r0 = int(parts[2])
                p_r1 = int(parts[3])
                p_pc = int(parts[4])
                p_seq = int(parts[5])
                p_halted = (parts[6] == "1")
                p_sel_pc = int(parts[7])
                p_prop_hash = parts[8]

                cur_state_hash = self.state_hash()
                pre_ev_root = self.ledger_root
                ev_step = self.ledger_steps

                accepted = False
                reason: Optional[str] = None
                cert_hash = ""

                # Program::transfer_r0_to_r1 logic:
                # pc 0: DECJZ r0 (jump 2 if 0, else r0-1, pc 1)
                # pc 1: INC r1 (pc 0)
                # pc 2: HALT
                if self.mode == "QUARANTINED":
                    reason = "NODE_QUARANTINED"
                elif p_pre_hash != cur_state_hash:
                    reason = "PRE_STATE_MISMATCH"
                elif cur_state_hash in self.vote_locks and self.vote_locks[cur_state_hash] != p_prop_hash:
                    reason = "CONFLICTING_VOTE_LOCK"
                else:
                    # Expected successor calculation
                    exp_r0 = self.r0
                    exp_r1 = self.r1
                    exp_pc = self.pc
                    exp_seq = self.sequence + 1
                    exp_halted = self.halted

                    if self.pc == 0:
                        if self.r0 == 0:
                            exp_pc = 2
                        else:
                            exp_r0 -= 1
                            exp_pc = 1
                    elif self.pc == 1:
                        exp_r1 += 1
                        exp_pc = 0
                    elif self.pc == 2:
                        exp_halted = True

                    expected_post_hash = compute_state_hash(exp_r0, exp_r1, exp_pc, exp_seq, exp_halted)
                    expected_prop_hash = compute_proposal_hash(cur_state_hash, expected_post_hash, exp_pc, exp_halted)

                    proposed_post_hash = compute_state_hash(p_r0, p_r1, p_pc, p_seq, p_halted)
                    calc_prop_hash = compute_proposal_hash(p_pre_hash, proposed_post_hash, p_pc, p_halted)

                    if p_prop_hash != calc_prop_hash:
                        reason = "PROPOSAL_HASH_DIVERGENCE"
                    elif (p_r0, p_r1, p_pc, p_seq, p_halted) != (exp_r0, exp_r1, exp_pc, exp_seq, exp_halted):
                        reason = "STATE_DIVERGENCE"
                    elif p_sel_pc != exp_pc:
                        reason = "ROUTE_DIVERGENCE"
                    else:
                        accepted = True
                        cert_hash = compute_cert_hash(p_prop_hash, True, 0)
                        self.vote_locks[cur_state_hash] = p_prop_hash
                        self.last_eval = {
                            "pre_state_hash": cur_state_hash,
                            "post_state_hash": proposed_post_hash,
                            "proposal_hash": p_prop_hash,
                            "cert_hash": cert_hash,
                            "pre_ev_root": pre_ev_root,
                            "ev_step": ev_step,
                            "r0": p_r0,
                            "r1": p_r1,
                            "pc": p_pc,
                            "sequence": p_seq,
                            "halted": p_halted,
                        }
                        self._save_storage()

                self.advance_clock(1)
                proposed_hash_field = compute_state_hash(p_r0, p_r1, p_pc, p_seq, p_halted)
                vote_hash = compute_vote_hash(
                    accepted=accepted,
                    cert_hash=cert_hash,
                    evidence_step=ev_step,
                    node_id=NODE_ID_C,
                    pre_evidence_root=pre_ev_root,
                    pre_state_hash=cur_state_hash,
                    proposal_hash=p_prop_hash,
                    proposed_state_hash=proposed_hash_field,
                    rejection_reason=reason,
                    ruleset_version=RULESET_VERSION,
                )

                return json.dumps({
                    "event": "auth_vote",
                    "node_id": NODE_ID_C,
                    "accepted": accepted,
                    "reason": reason,
                    "proposal_hash": p_prop_hash,
                    "pre_state_hash": cur_state_hash,
                    "proposed_state_hash": proposed_hash_field,
                    "certificate_hash": cert_hash,
                    "pre_evidence_root": pre_ev_root,
                    "evidence_step": ev_step,
                    "ruleset_version": RULESET_VERSION,
                    "vote_hash": vote_hash,
                    "local_clock": self.local_clock,
                })

            elif cmd == "AUTH_QC_BEGIN":
                # AUTH_QC_BEGIN <uow_id> <threshold> <expected_ev_root> <claimed_qc_hash>
                if len(parts) < 5:
                    return json.dumps({"event": "error", "reason": "bad AUTH_QC_BEGIN arguments"})
                self.pending_qc = {
                    "uow_id": parts[1],
                    "threshold": int(parts[2]),
                    "expected_ev_root": parts[3],
                    "claimed_qc_hash": parts[4],
                    "voters": [],
                    "vote_hashes": [],
                }
                return json.dumps({"event": "auth_qc_begin", "status": "ok"})

            elif cmd == "AUTH_QC_VOTE":
                # AUTH_QC_VOTE <voter> <vote_hash>
                if len(parts) < 3 or not self.pending_qc:
                    return json.dumps({"event": "error", "reason": "bad AUTH_QC_VOTE arguments or no pending QC"})
                self.pending_qc["voters"].append(parts[1])
                self.pending_qc["vote_hashes"].append(parts[2])
                return json.dumps({"event": "auth_qc_vote", "status": "ok", "count": len(self.pending_qc["voters"])})

            elif cmd == "AUTH_QC_APPLY":
                # AUTH_QC_APPLY <proposal_hash>
                if len(parts) < 2:
                    return json.dumps({"event": "error", "reason": "bad AUTH_QC_APPLY arguments"})
                claimed_prop_hash = parts[1]

                if self.pending_qc and self.pending_qc.get("claimed_qc_hash") in self.applied_qcs:
                    return json.dumps({
                        "event": "auth_apply",
                        "node_id": NODE_ID_C,
                        "applied": False,
                        "idempotent": True,
                        "reason": "ALREADY_APPLIED",
                        "state_hash": self.state_hash(),
                        "evidence_root": self.ledger_root,
                        "sequence": self.sequence,
                    })

                if claimed_prop_hash in self.applied_proposals:
                    return json.dumps({
                        "event": "auth_apply",
                        "node_id": NODE_ID_C,
                        "applied": False,
                        "idempotent": True,
                        "reason": "ALREADY_APPLIED",
                        "state_hash": self.state_hash(),
                        "evidence_root": self.ledger_root,
                        "sequence": self.sequence,
                    })

                if not self.pending_qc or not self.last_eval:
                    return json.dumps({
                        "event": "auth_apply",
                        "node_id": NODE_ID_C,
                        "applied": False,
                        "idempotent": False,
                        "reason": "NO_PENDING_PROPOSAL",
                    })

                claimed_qc_hash = self.pending_qc["claimed_qc_hash"]

                if self.mode == "QUARANTINED":
                    return json.dumps({
                        "event": "auth_apply",
                        "node_id": NODE_ID_C,
                        "applied": False,
                        "idempotent": False,
                        "reason": "NODE_QUARANTINED",
                    })

                if claimed_prop_hash != self.last_eval["proposal_hash"]:
                    return json.dumps({
                        "event": "auth_apply",
                        "node_id": NODE_ID_C,
                        "applied": False,
                        "idempotent": False,
                        "reason": "PROPOSAL_MISMATCH",
                    })

                voters = self.pending_qc["voters"]
                vote_hashes = self.pending_qc["vote_hashes"]
                threshold = self.pending_qc["threshold"]

                if len(voters) < threshold:
                    return json.dumps({
                        "event": "auth_apply",
                        "node_id": NODE_ID_C,
                        "applied": False,
                        "idempotent": False,
                        "reason": "INSUFFICIENT_QUORUM",
                    })

                if len(set(voters)) != len(voters):
                    return json.dumps({
                        "event": "auth_apply",
                        "node_id": NODE_ID_C,
                        "applied": False,
                        "idempotent": False,
                        "reason": "DUPLICATE_VOTER",
                    })

                # Compute expected QC hash
                expected_qc = compute_qc_hash(
                    cert_hash=self.last_eval["cert_hash"],
                    committed_state_hash=self.last_eval["post_state_hash"],
                    evidence_step=self.last_eval["ev_step"],
                    expected_evidence_root=self.pending_qc["expected_ev_root"],
                    pre_evidence_root=self.last_eval["pre_ev_root"],
                    pre_state_hash=self.last_eval["pre_state_hash"],
                    proposal_hash=self.last_eval["proposal_hash"],
                    proposed_state_hash=self.last_eval["post_state_hash"],
                    ruleset_version=RULESET_VERSION,
                    threshold=threshold,
                    uow_id=self.pending_qc["uow_id"],
                    vote_hashes=vote_hashes,
                    voters=voters,
                )

                if expected_qc != claimed_qc_hash:
                    return json.dumps({
                        "event": "auth_apply",
                        "node_id": NODE_ID_C,
                        "applied": False,
                        "idempotent": False,
                        "reason": "QC_HASH_MISMATCH",
                    })

                # Commit transition
                self.r0 = self.last_eval["r0"]
                self.r1 = self.last_eval["r1"]
                self.pc = self.last_eval["pc"]
                self.sequence = self.last_eval["sequence"]
                self.halted = self.last_eval["halted"]

                # Update evidence ledger
                rec_hash = compute_evidence_record_hash(
                    step=self.ledger_steps + 1,
                    pre_st=self.last_eval["pre_state_hash"],
                    post_st=self.last_eval["post_state_hash"],
                    prop=self.last_eval["proposal_hash"],
                    cert=self.last_eval["cert_hash"],
                    prev_root=self.ledger_root,
                )
                self.ledger_root = rec_hash
                self.ledger_steps += 1

                self.applied_qcs.add(claimed_qc_hash)
                self.applied_proposals.add(self.last_eval["proposal_hash"])
                self.mode = "ACTIVE"
                self.last_eval = None
                self.pending_qc = None
                self._save_storage()

                return json.dumps({
                    "event": "auth_apply",
                    "node_id": NODE_ID_C,
                    "applied": True,
                    "idempotent": False,
                    "reason": "APPLIED",
                    "state_hash": self.state_hash(),
                    "evidence_root": self.ledger_root,
                    "sequence": self.sequence,
                })

            elif cmd == "AUTH_REBUILD":
                # AUTH_REBUILD <r0> <r1> [pc] <seq> <root> <steps>
                if len(parts) >= 7:
                    r0 = int(parts[1])
                    r1 = int(parts[2])
                    pc = int(parts[3])
                    seq = int(parts[4])
                    root = parts[5]
                    steps = int(parts[6])
                elif len(parts) >= 6:
                    r0 = int(parts[1])
                    r1 = int(parts[2])
                    pc = 0
                    seq = int(parts[3])
                    root = parts[4]
                    steps = int(parts[5])
                else:
                    return json.dumps({"event": "error", "reason": "bad AUTH_REBUILD arguments"})

                self.r0 = r0
                self.r1 = r1
                self.pc = pc
                self.sequence = seq
                self.halted = False
                self.ledger_root = root
                self.ledger_steps = steps
                self.vote_locks.clear()
                self.mode = "ACTIVE"
                self.last_eval = None
                self.pending_qc = None
                self._save_storage()

                return json.dumps({
                    "event": "auth_rebuild",
                    "node_id": NODE_ID_C,
                    "mode": self.mode,
                    "r0": self.r0,
                    "r1": self.r1,
                    "pc": self.pc,
                    "sequence": self.sequence,
                    "halted": self.halted,
                    "state_hash": self.state_hash(),
                    "evidence_root": self.ledger_root,
                    "evidence_steps": self.ledger_steps,
                    "ruleset_version": RULESET_VERSION,
                    "local_clock": self.local_clock,
                })

            elif cmd == "AUTH_QUARANTINE":
                self.mode = "QUARANTINED"
                self._save_storage()
                return json.dumps({
                    "event": "auth_quarantine",
                    "node_id": NODE_ID_C,
                    "mode": self.mode,
                })

            elif cmd == "AUTH_SHUTDOWN":
                return json.dumps({"event": "auth_shutdown", "node_id": NODE_ID_C, "status": "terminating"})

            else:
                return json.dumps({"event": "error", "reason": f"unknown command: {cmd}"})


def run_server(port: int = DEFAULT_PORT, storage_dir: Optional[Path] = None):
    if storage_dir is None:
        storage_dir = Path(__file__).resolve().parent / "storage_authority_c"

    svc = AuthorityServiceC(storage_dir)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(5)
    print(f"[AuthorityC] Service listening on 127.0.0.1:{port} (storage: {storage_dir})", flush=True)

    running = True
    while running:
        try:
            client, addr = server.accept()
        except Exception:
            break

        def client_handler(conn):
            nonlocal running
            with conn:
                rfile = conn.makefile("r", encoding="utf-8")
                wfile = conn.makefile("w", encoding="utf-8")
                for line in rfile:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        resp = svc.handle_command(line)
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        resp = json.dumps({"event": "error", "reason": f"EXCEPTION: {e}"})
                    wfile.write(resp + "\n")
                    wfile.flush()
                    if "auth_shutdown" in resp:
                        running = False
                        break

        t = threading.Thread(target=client_handler, args=(client,), daemon=True)
        t.start()

    server.close()
    print("[AuthorityC] Server shutdown complete.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Authority Node C Service (Laptop x86-64 CPU)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on")
    parser.add_argument("--storage-dir", type=str, default=None, help="Directory for persistent state")
    args = parser.parse_args()

    s_dir = Path(args.storage_dir) if args.storage_dir else None
    run_server(args.port, s_dir)
