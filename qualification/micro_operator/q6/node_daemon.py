"""Q6 Authority Replica Daemon: Independent OS Process with Persistent WAL, Sockets, and Ed25519."""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from uow.compat.v2 import WorldState
from uow.engine import EvidenceLedger, EvidenceRecord, certify, commit, propose
from uow.state import canonical_json
from qualification.micro_operator.q4_grouped import MODEL, validate
from qualification.micro_operator.q2_campaign import work_for
from qualification.micro_operator.q6.crypto import AuthorityKeypair, KeyRegistry, hash_payload
from qualification.micro_operator.q6.messages import recv_frame, send_frame
from qualification.micro_operator.q6.wal import PersistentWAL, WALRecord

def clone_initial_state() -> WorldState:
    return WorldState(
        attributes={"counter": 0},
        cursor="dist.increment",
        status="RUNNING",
        sequence=0,
    )

class NodeDaemon:
    """Independent Authority Node daemon with crash-durable WAL and socket IPC."""

    def __init__(
        self,
        node_id: str,
        host: str,
        port: int,
        data_dir: Path,
        keypair: AuthorityKeypair,
        registry: KeyRegistry,
        peer_addresses: Mapping[str, Tuple[str, int]],
        ruleset_version: str = "uow-authority-v1",
    ) -> None:
        self.node_id = node_id
        self.host = host
        self.port = port
        self.data_dir = Path(data_dir)
        self.keypair = keypair
        self.registry = registry
        self.peer_addresses = peer_addresses
        self.ruleset_version = ruleset_version

        self.wal = PersistentWAL(self.data_dir / f"{node_id}.wal")
        self.state = clone_initial_state()
        self.ledger = EvidenceLedger()
        self.prepared_groups: Dict[str, Dict[str, Any]] = {}
        self.committed_groups: set[str] = set()
        self.committed_certificates: Dict[str, Dict[str, Any]] = {}
        self.uncertain_groups: set[str] = set()
        self.clock_skew_seconds: float = 0.0
        self.simulated_delay_seconds: float = 0.0

        self._server_sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        # Replay WAL to recover state
        self._recover_from_wal()

    def _recover_from_wal(self) -> None:
        records = self.wal.read_all()
        if not records:
            # First initialization
            self.wal.append("INIT", {"node_id": self.node_id, "state": self.state.to_dict()})
            return

        # Replay records
        curr_state = clone_initial_state()
        curr_ledger = EvidenceLedger()
        prepared_map = {}
        committed_set = set()
        committed_certs = {}

        for rec in records:
            if rec.record_type == "INIT":
                pass
            elif rec.record_type == "PREPARE":
                gid = rec.payload["group_id"]
                prepared_map[gid] = rec.payload
            elif rec.record_type == "COMMIT":
                gid = rec.payload["group_id"]
                committed_set.add(gid)
                if rec.payload.get("certificate"):
                    committed_certs[gid] = rec.payload["certificate"]
                if gid in prepared_map:
                    # Apply member records
                    pdata = prepared_map.pop(gid)
                    for rdict in pdata["records"]:
                        r_obj = EvidenceRecord(
                            step_number=rdict["step_number"],
                            uow_id=rdict["uow_id"],
                            source_category=rdict["source_category"],
                            target_category=rdict["target_category"],
                            pre_state_hash=rdict["pre_state_hash"],
                            selected_route_index=rdict["selected_route_index"],
                            proposed_state_hash=rdict["proposed_state_hash"],
                            certificate_hash=rdict["certificate_hash"],
                            post_state_hash=rdict["post_state_hash"],
                            next_uow_pointer=rdict["next_uow_pointer"],
                            prev_evidence_hash=rdict["prev_evidence_hash"],
                        )
                        curr_ledger.append(r_obj)
                    sdict = rec.payload["final_state"]
                    curr_state = WorldState(
                        attributes=sdict["attributes"],
                        cursor=sdict["cursor"],
                        status=sdict["status"],
                        sequence=sdict["sequence"],
                    )
            elif rec.record_type == "ABORT":
                gid = rec.payload["group_id"]
                prepared_map.pop(gid, None)
            elif rec.record_type == "CATCHUP":
                for rdict in rec.payload.get("records", []):
                    r_obj = EvidenceRecord(**rdict)
                    curr_ledger.append(r_obj)
                sdict = rec.payload["final_state"]
                curr_state = WorldState(
                    attributes=sdict["attributes"],
                    cursor=sdict["cursor"],
                    status=sdict["status"],
                    sequence=sdict["sequence"],
                )

        self.state = curr_state
        self.ledger = curr_ledger
        self.prepared_groups = prepared_map
        self.committed_groups = committed_set
        self.committed_certificates = committed_certs
        # Any remaining prepared groups without commit or abort are UNCERTAIN
        self.uncertain_groups = set(prepared_map.keys())

    def start(self) -> None:
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(128)
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True, name=f"Node-{self.node_id}")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None
        self.wal.close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _listen_loop(self) -> None:
        while self._running and self._server_sock:
            try:
                conn, _ = self._server_sock.accept()
                t = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
                t.start()
            except OSError:
                break

    def _handle_client(self, conn: socket.socket) -> None:
        with conn:
            while self._running:
                try:
                    req = recv_frame(conn)
                    if req is None:
                        break
                    if self.simulated_delay_seconds > 0:
                        time.sleep(self.simulated_delay_seconds)
                    resp = self.process_message(req)
                    send_frame(conn, resp)
                except Exception as e:
                    try:
                        send_frame(conn, {"status": "ERROR", "error": str(e)})
                    except Exception:
                        pass
                    break

    def process_message(self, req: Dict[str, Any]) -> Dict[str, Any]:
        mtype = req.get("type")
        if mtype == "RESOLVE_UNCERTAIN":
            return {"status": "OK", "resolutions": self.resolve_uncertain_groups_cooperatively()}
        with self._lock:
            if mtype == "PREPARE_REQUEST":
                return self._handle_prepare(req)
            elif mtype == "COMMIT_REQUEST":
                return self._handle_commit(req)
            elif mtype == "QUERY_STATUS":
                return self._handle_query_status(req)
            elif mtype == "CATCHUP_REQUEST":
                return self._handle_catchup(req)
            elif mtype == "APPLY_CATCHUP":
                return self._handle_apply_catchup(req)
            elif mtype == "INSPECT":
                return {
                    "status": "OK",
                    "node_id": self.node_id,
                    "sequence": self.state.sequence,
                    "state_hash": self.state.state_hash,
                    "evidence_root": self.ledger.root_hash(),
                    "state": self.state.to_dict(),
                    "committed_groups": list(self.committed_groups),
                    "uncertain_groups": list(self.uncertain_groups),
                    "prepared_groups": list(self.prepared_groups.keys()),
                    "wal_record_count": len(self.wal.read_all()),
                    "clock_skew_seconds": self.clock_skew_seconds,
                    "simulated_delay_seconds": self.simulated_delay_seconds,
                }
            elif mtype == "INJECT_STATE_DIVERGENCE":
                attr = req.get("attribute", "counter")
                val = req.get("value", 999999)
                self.state = self.state.with_attribute(attr, val)
                return {"status": "OK", "state_hash": self.state.state_hash}
            elif mtype == "SET_CLOCK_SKEW":
                self.clock_skew_seconds = float(req.get("skew_seconds", 0.0))
                return {"status": "OK", "clock_skew_seconds": self.clock_skew_seconds}
            elif mtype == "SET_NETWORK_DELAY":
                self.simulated_delay_seconds = float(req.get("delay_seconds", 0.0))
                return {"status": "OK", "simulated_delay_seconds": self.simulated_delay_seconds}
            elif mtype == "PING":
                return {"status": "PONG", "node_id": self.node_id, "sequence": self.state.sequence}
            else:
                return {"status": "UNKNOWN_TYPE"}

    def _handle_prepare(self, req: Dict[str, Any]) -> Dict[str, Any]:
        group_id = req["group_id"]
        votes = req["votes"]
        base_state_hash = req["base_state_hash"]
        base_evidence_root = req["base_evidence_root"]

        if group_id in self.committed_groups:
            return {"status": "ALREADY_COMMITTED", "node_id": self.node_id}

        if self.state.state_hash != base_state_hash:
            return {"status": "STALE_BASE", "node_id": self.node_id, "current_base": self.state.state_hash}

        if self.ledger.root_hash() != base_evidence_root:
            return {"status": "DIVERGED_EVIDENCE", "node_id": self.node_id}

        # Simulate all member proposals
        try:
            contracts = {v: work_for(MODEL, 100 * v, 100 * v) for v in (0, 1)}
            curr_state = self.state
            curr_root = self.ledger.root_hash()
            step = len(self.ledger.records)
            records = []

            for vote in votes:
                work = contracts[vote]
                prop = propose(work, curr_state)
                cert = certify(work, curr_state, prop)
                if not cert.is_valid:
                    return {"status": "CERTIFICATION_FAILED", "node_id": self.node_id}
                curr_state, rec = commit(work, curr_state, prop, cert, prev_evidence_hash=curr_root, step_number=step + 1)
                curr_root = rec.record_hash
                step += 1
                records.append(rec)

            item_hashes = [r.record_hash for r in records]
            group_digest = hash_payload({"schema": "Q6-Group", "base": base_state_hash, "root": base_evidence_root, "votes": votes})

            ballot_payload = {
                "node_id": self.node_id,
                "group_id": group_id,
                "digest": group_digest,
                "member_hashes": item_hashes,
                "state_hash": curr_state.state_hash,
                "evidence_root": curr_root,
                "base_hash": base_state_hash,
            }
            ballot_bytes = canonical_json(ballot_payload).encode("utf-8")
            signature_hex = self.keypair.sign(ballot_bytes)

            prepare_payload = {
                "group_id": group_id,
                "group_digest": group_digest,
                "votes": votes,
                "base_state_hash": base_state_hash,
                "final_state": curr_state.to_dict(),
                "records": [r.__dict__ for r in records],
                "ballot": ballot_payload,
                "signature": signature_hex,
            }

            # Durable WAL write with fsync
            self.wal.append("PREPARE", prepare_payload)
            self.prepared_groups[group_id] = prepare_payload
            self.uncertain_groups.add(group_id)

            return {
                "status": "PREPARED",
                "node_id": self.node_id,
                "ballot": ballot_payload,
                "signature": signature_hex,
            }
        except Exception as e:
            return {"status": "PREPARE_ERROR", "node_id": self.node_id, "error": str(e)}

    def _handle_commit(self, req: Dict[str, Any]) -> Dict[str, Any]:
        group_id = req["group_id"]
        cert = req["group_certificate"]

        if group_id in self.committed_groups:
            return {
                "status": "ALREADY_COMMITTED",
                "node_id": self.node_id,
                "state_hash": self.state.state_hash,
                "evidence_root": self.ledger.root_hash(),
            }

        # Verify Group Certificate
        voters = cert["voters"]
        signatures = cert["signatures"]
        ballots = cert["ballots"]

        if len(voters) < 2 or len(voters) != len(signatures):
            return {"status": "INVALID_CERTIFICATE_QUORUM"}

        # Verify Ed25519 signatures
        for voter_id, sig_hex, ballot in zip(voters, signatures, ballots):
            ballot_bytes = canonical_json(ballot).encode("utf-8")
            if not self.registry.verify(voter_id, ballot_bytes, sig_hex):
                return {"status": "INVALID_AUTHORITY_SIGNATURE", "voter": voter_id}

        pdata = self.prepared_groups.get(group_id)
        if pdata is None:
            # Committed without prior local prepare (e.g. catchup or delayed coordinator)
            # Reconstruct transitions from certificate
            return {"status": "NEED_SYNC"}

        # Write-Ahead Logging Principle: Persist and fsync COMMIT to disk WAL FIRST!
        sdict = pdata["final_state"]
        target_state = WorldState(
            attributes=sdict["attributes"],
            cursor=sdict["cursor"],
            status=sdict["status"],
            sequence=sdict["sequence"],
        )
        commit_record = {
            "group_id": group_id,
            "certificate": cert,
            "final_state": target_state.to_dict(),
            "evidence_root": pdata["ballot"]["evidence_root"],
        }
        self.wal.append("COMMIT", commit_record)

        # AFTER durable WAL persistence succeeds, advance in-memory state and ledger
        for rdict in pdata["records"]:
            r_obj = EvidenceRecord(
                step_number=rdict["step_number"],
                uow_id=rdict["uow_id"],
                source_category=rdict["source_category"],
                target_category=rdict["target_category"],
                pre_state_hash=rdict["pre_state_hash"],
                selected_route_index=rdict["selected_route_index"],
                proposed_state_hash=rdict["proposed_state_hash"],
                certificate_hash=rdict["certificate_hash"],
                post_state_hash=rdict["post_state_hash"],
                next_uow_pointer=rdict["next_uow_pointer"],
                prev_evidence_hash=rdict["prev_evidence_hash"],
            )
            self.ledger.append(r_obj)

        self.state = target_state
        self.committed_groups.add(group_id)
        if cert:
            self.committed_certificates[group_id] = cert
        self.prepared_groups.pop(group_id, None)
        self.uncertain_groups.discard(group_id)

        return {
            "status": "COMMITTED",
            "node_id": self.node_id,
            "state_hash": self.state.state_hash,
            "evidence_root": self.ledger.root_hash(),
        }

    def _handle_query_status(self, req: Dict[str, Any]) -> Dict[str, Any]:
        group_id = req["group_id"]
        if group_id in self.committed_groups:
            return {
                "status": "COMMITTED",
                "node_id": self.node_id,
                "group_certificate": self.committed_certificates.get(group_id),
            }
        elif group_id in self.prepared_groups:
            return {"status": "PREPARED", "node_id": self.node_id}
        return {"status": "UNKNOWN", "node_id": self.node_id}

    def _handle_catchup(self, req: Dict[str, Any]) -> Dict[str, Any]:
        since_seq = req.get("since_sequence", 0)
        records_to_send = [r.__dict__ for r in self.ledger.records[since_seq:]]
        return {
            "status": "CATCHUP_DATA",
            "node_id": self.node_id,
            "current_sequence": self.state.sequence,
            "state": self.state.to_dict(),
            "state_hash": self.state.state_hash,
            "evidence_root": self.ledger.root_hash(),
            "records": records_to_send,
        }

    def _handle_apply_catchup(self, req: Dict[str, Any]) -> Dict[str, Any]:
        sdict = req.get("state")
        records = req.get("records", [])
        if not sdict:
            return {"status": "INVALID_STATE"}
        target_state = WorldState(
            attributes=sdict["attributes"],
            cursor=sdict["cursor"],
            status=sdict["status"],
            sequence=sdict["sequence"],
        )
        self.wal.append("CATCHUP", {
            "final_state": target_state.to_dict(),
            "evidence_root": req.get("evidence_root", ""),
            "records": records,
        })
        for rdict in records:
            r_obj = EvidenceRecord(**rdict)
            self.ledger.append(r_obj)
        self.state = target_state
        return {
            "status": "CATCHUP_APPLIED",
            "node_id": self.node_id,
            "sequence": self.state.sequence,
            "state_hash": self.state.state_hash,
            "evidence_root": self.ledger.root_hash(),
        }

    def _verify_group_certificate_for_recovery(
        self,
        gid: str,
        pdata: Dict[str, Any],
        cert: Dict[str, Any],
    ) -> bool:
        """Cryptographically verify that a peer's presented certificate is authentic before recovery.

        Verifies:
        1. Certificate binds the exact local prepared group digest.
        2. Certificate binds the exact state hash and evidence root.
        3. Quorum count is sufficient (>= 2).
        4. Every voter's Ed25519 signature on its ballot is cryptographically valid.
        """
        try:
            # 1. Bind group digest
            if cert.get("digest") != pdata["group_digest"]:
                return False

            # 2. Bind state hash and evidence root
            expected_state = pdata["final_state"]["state_hash"]
            expected_root = pdata["ballot"]["evidence_root"]
            if cert.get("state_hash") != expected_state:
                return False
            if cert.get("evidence_root") != expected_root:
                return False

            # 3. Quorum validation (at least 2 valid voter signatures)
            voters = cert.get("voters", [])
            signatures = cert.get("signatures", [])
            ballots = cert.get("ballots", [])
            if len(voters) < 2 or len(voters) != len(signatures) or len(voters) != len(ballots):
                return False

            # 4. Verify each voter's Ed25519 signature
            for vid, sig_hex, ballot in zip(voters, signatures, ballots):
                if not self.registry.has_node(vid):
                    return False
                if ballot.get("digest") != pdata["group_digest"]:
                    return False
                if ballot.get("state_hash") != expected_state:
                    return False
                if ballot.get("evidence_root") != expected_root:
                    return False
                ballot_bytes = canonical_json(ballot).encode("utf-8")
                if not self.registry.verify(vid, ballot_bytes, sig_hex):
                    return False

            return True
        except Exception:
            return False

    def resolve_uncertain_groups_cooperatively(self) -> Dict[str, str]:
        """Cooperative recovery protocol: query peer nodes for any uncertain groups.

        CRITICAL SAFETY RULES:
        1. An uncertain transaction must never be aborted merely because currently
           reachable peers do not know its outcome.
        2. A peer's status string is NOT by itself proof of commitment. Recovery
           strictly requires a verifiable group decision certificate binding the exact
           group digest, evidence root, state hash, and verifiable Ed25519 quorum signatures.
        """
        resolutions = {}
        with self._lock:
            uncertain = list(self.uncertain_groups)

        for gid in uncertain:
            # Query all reachable peers
            peer_responses: Dict[str, Dict[str, Any]] = {}
            for peer_id, (p_host, p_port) in self.peer_addresses.items():
                if peer_id == self.node_id:
                    continue
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(2.0)
                    s.connect((p_host, p_port))
                    send_frame(s, {"type": "QUERY_STATUS", "group_id": gid})
                    resp = recv_frame(s, timeout=2.0)
                    s.close()
                    if resp:
                        peer_responses[peer_id] = resp
                except Exception:
                    pass

            with self._lock:
                pdata = self.prepared_groups.get(gid)
                if not pdata:
                    continue

                verified_cert = None
                # Must find an authentic, cryptographically verified group certificate from a peer
                for peer_id, resp in peer_responses.items():
                    if resp.get("status") == "COMMITTED":
                        cert = resp.get("group_certificate")
                        if cert and self._verify_group_certificate_for_recovery(gid, pdata, cert):
                            verified_cert = cert
                            break

                if verified_cert is not None:
                    # Verified authoritative quorum certificate! Safe to commit.
                    sdict = pdata["final_state"]
                    target_state = WorldState(
                        attributes=sdict["attributes"],
                        cursor=sdict["cursor"],
                        status=sdict["status"],
                        sequence=sdict["sequence"],
                    )
                    # Write-Ahead: Persist COMMIT record to disk WAL FIRST!
                    self.wal.append("COMMIT", {
                        "group_id": gid,
                        "recovered_from_peers": True,
                        "certificate": verified_cert,
                        "final_state": target_state.to_dict(),
                        "evidence_root": pdata["ballot"]["evidence_root"],
                    })
                    # AFTER disk persistence, advance in-memory state and ledger
                    for rdict in pdata["records"]:
                        r_obj = EvidenceRecord(**rdict)
                        self.ledger.append(r_obj)

                    self.state = target_state
                    self.committed_groups.add(gid)
                    self.committed_certificates[gid] = verified_cert
                    self.prepared_groups.pop(gid, None)
                    self.uncertain_groups.discard(gid)
                    resolutions[gid] = "COMMITTED"
                else:
                    # No peer provided a verified cryptographic commit certificate.
                    # Transaction must remain safely blocked.
                    resolutions[gid] = "UNCERTAIN_BLOCKED"

        return resolutions

def main() -> None:
    parser = argparse.ArgumentParser(description="Q6 Independent Authority Replica Daemon")
    parser.add_argument("--node-id", required=True, help="Node ID (e.g. A, B, C)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, required=True, help="Bind port")
    parser.add_argument("--data-dir", required=True, help="Persistent data directory")
    parser.add_argument("--peers", required=True, help="JSON-encoded peer address map")
    parser.add_argument("--registry", required=True, help="JSON-encoded public key registry (hex)")
    parser.add_argument("--key-seed", required=True, help="Seed hex for node private key")
    args = parser.parse_args()

    node_id = args.node_id
    host = args.host
    port = args.port
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    peer_map = json.loads(args.peers)
    peer_addresses = {nid: tuple(addr) for nid, addr in peer_map.items()}

    reg_map = json.loads(args.registry)
    pub_keys = {nid: bytes.fromhex(phex) for nid, phex in reg_map.items()}
    registry = KeyRegistry(pub_keys)

    key_seed = bytes.fromhex(args.key_seed)
    keypair = AuthorityKeypair.from_seed(node_id, key_seed)

    daemon = NodeDaemon(
        node_id=node_id,
        host=host,
        port=port,
        data_dir=data_dir,
        keypair=keypair,
        registry=registry,
        peer_addresses=peer_addresses,
    )
    daemon.start()

    # Write readiness marker
    ready_file = data_dir / f"{node_id}.ready"
    ready_file.write_text(f"READY pid={os.getpid()} port={port}\n", encoding="utf-8")

    try:
        while True:
            time.sleep(1.0)
    except (KeyboardInterrupt, SystemExit):
        daemon.stop()

if __name__ == "__main__":
    main()

