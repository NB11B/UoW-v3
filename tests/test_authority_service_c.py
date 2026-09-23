import json
import socket
import subprocess
import sys
import time
from pathlib import Path
import pytest

from qualification.distributed_authority.authority_service_c import (
    DEFAULT_PORT,
    compute_proposal_hash,
    compute_qc_hash,
    compute_state_hash,
)

def test_authority_service_c_lifecycle(tmp_path):
    port = 9530
    storage = tmp_path / "storage_c"
    script = Path(__file__).resolve().parents[1] / "qualification" / "distributed_authority" / "authority_service_c.py"

    # Start standalone process
    proc = subprocess.Popen(
        [sys.executable, str(script), "--port", str(port), "--storage-dir", str(storage)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Wait for service to be ready
        time.sleep(0.5)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(("127.0.0.1", port))
            rfile = s.makefile("r", encoding="utf-8")
            wfile = s.makefile("w", encoding="utf-8")

            def send(cmd: str) -> dict:
                wfile.write(cmd.strip() + "\n")
                wfile.flush()
                return json.loads(rfile.readline().strip())

            # 1. Reset
            res_reset = send("AUTH_RESET 10 0")
            assert res_reset["event"] == "auth_reset"
            assert res_reset["node_id"] == "authority_c_laptop_x86"
            assert res_reset["sequence"] == 0
            assert res_reset["state_hash"] == compute_state_hash(10, 0, 0, 0, False)

            # 2. Snapshot
            snap = send("AUTH_SNAPSHOT")
            assert snap["state_hash"] == res_reset["state_hash"]

            # 3. Evaluate valid proposal (DECJZ on r0=10 -> r0=9, r1=0, pc=1, seq=1, halted=0)
            pre_hash = snap["state_hash"]
            post_hash = compute_state_hash(9, 0, 1, 1, False)
            prop_hash = compute_proposal_hash(pre_hash, post_hash, 1, False)

            vote = send(f"AUTH_EVALUATE {pre_hash} 9 0 1 1 0 1 {prop_hash}")
            assert vote["event"] == "auth_vote"
            assert vote["accepted"] is True
            assert vote["proposed_state_hash"] == post_hash

            # 4. Conflicting vote lock
            comp_post = compute_state_hash(8, 0, 2, 1, False)
            comp_prop = compute_proposal_hash(pre_hash, comp_post, 2, False)
            vote_conflict = send(f"AUTH_EVALUATE {pre_hash} 8 0 2 1 0 2 {comp_prop}")
            assert vote_conflict["accepted"] is False
            assert vote_conflict["reason"] == "CONFLICTING_VOTE_LOCK"

            # 5. Apply piecewise QC
            voters = ["authority_a_esp32", "authority_c_laptop_x86"]
            vote_hashes = ["a" * 64, vote["vote_hash"]]
            expected_ev_root = "b" * 64

            qc_hash = compute_qc_hash(
                cert_hash=vote["certificate_hash"],
                committed_state_hash=post_hash,
                evidence_step=0,
                expected_evidence_root=expected_ev_root,
                pre_evidence_root="0" * 64,
                pre_state_hash=pre_hash,
                proposal_hash=prop_hash,
                proposed_state_hash=post_hash,
                ruleset_version="uow-authority-v1",
                threshold=2,
                uow_id="test_uow",
                vote_hashes=vote_hashes,
                voters=voters,
            )

            res_begin = send(f"AUTH_QC_BEGIN test_uow 2 {expected_ev_root} {qc_hash}")
            assert res_begin["status"] == "ok"
            for v, vh in zip(voters, vote_hashes):
                res_v = send(f"AUTH_QC_VOTE {v} {vh}")
                assert res_v["status"] == "ok"

            res_apply = send(f"AUTH_QC_APPLY {prop_hash}")
            assert res_apply["applied"] is True
            assert res_apply["sequence"] == 1
            assert res_apply["state_hash"] == post_hash

            # 6. Idempotency
            res_idemp = send(f"AUTH_QC_APPLY {prop_hash}")
            assert res_idemp["applied"] is False
            assert res_idemp["idempotent"] is True

            # 7. Quarantine and Rebuild
            res_q = send("AUTH_QUARANTINE")
            assert res_q["mode"] == "QUARANTINED"
            res_blocked = send(f"AUTH_EVALUATE {post_hash} 8 0 1 2 0 1 {'c'*64}")
            assert res_blocked["reason"] == "NODE_QUARANTINED"

            res_reb = send(f"AUTH_REBUILD 9 0 1 1 {expected_ev_root} 1")
            assert res_reb["mode"] == "ACTIVE"
            assert res_reb["state_hash"] == post_hash

            # 8. Shutdown
            send("AUTH_SHUTDOWN")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
