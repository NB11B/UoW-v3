"""Q6 Authority Replica Daemon: Independent OS Process with Persistent WAL, Sockets, and Ed25519."""
from __future__ import annotations

import argparse
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
        self.uncertain_groups: set[str] = set()

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

        for rec in records:
            if rec.record_type == "INIT":
                pass
            elif rec.record_type == "PREPARE":
                gid = rec.payload["group_id"]
                prepared_map[gid] = rec.payload
            elif rec.record_type == "COMMIT":
                gid = rec.payload["group_id"]
                committed_set.add(gid)
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

        self.state = curr_state
        self.ledger = curr_ledger
        self.prepared_groups = prepared_map
        self.committed_groups = committed_set
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
        with self._lock:
            if mtype == "PREPARE_REQUEST":
                return self._handle_prepare(req)
            elif mtype == "COMMIT_REQUEST":
                return self._handle_commit(req)
            elif mtype == "QUERY_STATUS":
                return self._handle_query_status(req)
            elif mtype == "CATCHUP_REQUEST":
                return self._handle_catchup(req)
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

        # Advance state and append ledger
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

        sdict = pdata["final_state"]
        self.state = WorldState(
            attributes=sdict["attributes"],
            cursor=sdict["cursor"],
            status=sdict["status"],
            sequence=sdict["sequence"],
        )

        commit_record = {
            "group_id": group_id,
            "certificate": cert,
            "final_state": self.state.to_dict(),
            "evidence_root": self.ledger.root_hash(),
        }
        self.wal.append("COMMIT", commit_record)
        self.committed_groups.add(group_id)
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
            return {"status": "COMMITTED", "node_id": self.node_id}
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

    def resolve_uncertain_groups_cooperatively(self) -> Dict[str, str]:
        """Cooperative recovery protocol: query peer nodes for any uncertain groups."""
        resolutions = {}
        with self._lock:
            uncertain = list(self.uncertain_groups)

        for gid in uncertain:
            # Query all reachable peers
            peer_statuses = {}
            for peer_id, (p_host, p_port) in self.peer_addresses.items():
                if peer_id == self.node_id:
                    continue
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(1.0)
                    s.connect((p_host, p_port))
                    send_frame(s, {"type": "QUERY_STATUS", "group_id": gid})
                    resp = recv_frame(s, timeout=1.0)
                    s.close()
                    if resp:
                        peer_statuses[peer_id] = resp.get("status")
                except Exception:
                    pass

            with self._lock:
                if any(st == "COMMITTED" for st in peer_statuses.values()):
                    # A peer committed it! Safe to commit.
                    # Find peer that committed and fetch certificate if needed
                    pdata = self.prepared_groups.get(gid)
                    if pdata:
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
                        sdict = pdata["final_state"]
                        self.state = WorldState(
                            attributes=sdict["attributes"],
                            cursor=sdict["cursor"],
                            status=sdict["status"],
                            sequence=sdict["sequence"],
                        )
                        self.wal.append("COMMIT", {"group_id": gid, "recovered_from_peers": True, "final_state": self.state.to_dict()})
                        self.committed_groups.add(gid)
                        self.prepared_groups.pop(gid, None)
                        self.uncertain_groups.discard(gid)
                        resolutions[gid] = "COMMITTED"
                elif all(st == "UNKNOWN" for st in peer_statuses.values()) and len(peer_statuses) >= 1:
                    # No peer prepared or coordinator aborted
                    self.wal.append("ABORT", {"group_id": gid, "reason": "PEERS_DID_NOT_COMMIT"})
                    self.prepared_groups.pop(gid, None)
                    self.uncertain_groups.discard(gid)
                    resolutions[gid] = "ABORTED"
        return resolutions
