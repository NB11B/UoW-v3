"""Q6 Distributed Group Coordinator: 2PC over TCP sockets with Ed25519 Quorum Certificates."""
from __future__ import annotations

import hashlib
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from uow.state import canonical_json
from qualification.micro_operator.q4_grouped import validate
from qualification.micro_operator.q6.crypto import KeyRegistry, hash_payload
from qualification.micro_operator.q6.messages import recv_frame, send_frame
from qualification.micro_operator.q6.wal import PersistentWAL

@dataclass(frozen=True)
class Q6GroupCertificate:
    digest: str
    voters: Tuple[str, ...]
    ballots: Tuple[Dict[str, Any], ...]
    signatures: Tuple[str, ...]
    members: Tuple[str, ...]
    state_hash: str
    evidence_root: str
    certificate_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "digest": self.digest,
            "voters": list(self.voters),
            "ballots": list(self.ballots),
            "signatures": list(self.signatures),
            "members": list(self.members),
            "state_hash": self.state_hash,
            "evidence_root": self.evidence_root,
            "certificate_hash": self.certificate_hash,
        }

class Q6Coordinator:
    """Coordinator driving 2PC Group Commitment over real TCP sockets."""

    def __init__(
        self,
        node_addresses: Mapping[str, Tuple[str, int]],
        registry: KeyRegistry,
        data_dir: Path,
        threshold: int = 2,
    ) -> None:
        self.node_addresses = dict(node_addresses)
        self.registry = registry
        self.data_dir = Path(data_dir)
        self.threshold = threshold
        self.wal = PersistentWAL(self.data_dir / "coordinator.wal")
        self.applied_groups: Dict[str, Dict[str, Any]] = {}
        self._recover()

    def _recover(self) -> None:
        records = self.wal.read_all()
        for rec in records:
            if rec.record_type == "GROUP_COMMITTED":
                gid = rec.payload["group_id"]
                self.applied_groups[gid] = rec.payload

    def _send_to_node(self, node_id: str, msg: Dict[str, Any], timeout: float = 3.0) -> Optional[Dict[str, Any]]:
        addr = self.node_addresses.get(node_id)
        if not addr:
            return None
        host, port = addr
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((host, port))
            send_frame(s, msg)
            resp = recv_frame(s, timeout=timeout)
            s.close()
            return resp
        except Exception:
            return None

    def query_cluster_base(self) -> Tuple[Optional[str], Optional[str], List[str]]:
        """Queries reachable nodes for their current base state and evidence root."""
        base_states = {}
        reachable = []
        for nid in sorted(self.node_addresses.keys()):
            resp = self._send_to_node(nid, {"type": "PING"}, timeout=1.5)
            if resp and resp.get("status") == "PONG":
                reachable.append(nid)
                # Query detailed status
                st_resp = self._send_to_node(nid, {"type": "CATCHUP_REQUEST", "since_sequence": 999999}, timeout=1.5)
                if st_resp and st_resp.get("status") == "CATCHUP_DATA":
                    base_states[nid] = (st_resp["state_hash"], st_resp["evidence_root"], st_resp["current_sequence"])

        if len(reachable) < self.threshold:
            return None, None, reachable

        # Check for convergence
        state_hashes = {v[0]: (v[1], v[2]) for v in base_states.values()}
        if len(state_hashes) != 1:
            return "DIVERGED", None, reachable

        shash = list(state_hashes.keys())[0]
        eroot, _ = state_hashes[shash]
        return shash, eroot, reachable

    def commit(
        self,
        values: Sequence[int],
        *,
        group_id: Optional[str] = None,
        expected_base: Optional[str] = None,
        interrupt_prepublish: bool = False,
        interrupt_publication_replica: Optional[int] = None,
    ) -> Tuple[str, Optional[Q6GroupCertificate]]:
        votes = validate(values)

        # 1. Query cluster base state
        shash, eroot, reachable = self.query_cluster_base()
        if shash is None or len(reachable) < self.threshold:
            return "NO_QUORUM", None
        if shash == "DIVERGED":
            return "DIVERGED", None

        if expected_base is not None and expected_base != shash:
            return "STALE_BASE", None

        # Deterministic group hash
        group_digest = hash_payload({"schema": "Q6-Group", "base": shash, "root": eroot, "votes": votes})
        gid = group_id or f"q6_grp_{group_digest[:16]}"

        if gid in self.applied_groups:
            cert_dict = self.applied_groups[gid]["certificate"]
            cert = Q6GroupCertificate(
                digest=cert_dict["digest"],
                voters=tuple(cert_dict["voters"]),
                ballots=tuple(cert_dict["ballots"]),
                signatures=tuple(cert_dict["signatures"]),
                members=tuple(cert_dict["members"]),
                state_hash=cert_dict["state_hash"],
                evidence_root=cert_dict["evidence_root"],
                certificate_hash=cert_dict["certificate_hash"],
            )
            return "REPLAY", cert

        # 2. Phase 1: Prepare
        prepare_req = {
            "type": "PREPARE_REQUEST",
            "group_id": gid,
            "votes": list(votes),
            "base_state_hash": shash,
            "base_evidence_root": eroot,
        }

        ballots_collected = []
        seen_nodes = set()
        for nid in reachable:
            if nid in seen_nodes:
                continue
            resp = self._send_to_node(nid, prepare_req, timeout=3.0)
            if resp and resp.get("status") == "PREPARED":
                ballot = resp["ballot"]
                sig = resp["signature"]
                # Enforce ballot node_id matches voter identity
                if ballot.get("node_id") != nid:
                    continue
                # Verify Ed25519 signature
                ballot_bytes = canonical_json(ballot).encode("utf-8")
                if self.registry.verify(nid, ballot_bytes, sig):
                    ballots_collected.append((nid, ballot, sig))
                    seen_nodes.add(nid)

        if len(ballots_collected) < self.threshold:
            return "PREPARE_INSUFFICIENT_QUORUM", None

        # Verify ballot agreement
        first_ballot = ballots_collected[0][1]
        agreeing = [
            b for b in ballots_collected
            if b[1]["digest"] == first_ballot["digest"] and
               b[1]["member_hashes"] == first_ballot["member_hashes"] and
               b[1]["state_hash"] == first_ballot["state_hash"] and
               b[1]["evidence_root"] == first_ballot["evidence_root"]
        ]

        # Enforce distinct voter identities
        distinct_voter_ids = set(b[0] for b in agreeing)
        if len(distinct_voter_ids) < self.threshold or len(distinct_voter_ids) != len(agreeing):
            return "PREPARE_INSUFFICIENT_QUORUM", None

        # Form Group Certificate
        voter_ids = tuple(sorted(b[0] for b in agreeing))
        signatures = tuple(b[2] for b in sorted(agreeing, key=lambda x: x[0]))
        ballots_tuple = tuple(b[1] for b in sorted(agreeing, key=lambda x: x[0]))
        member_hashes = tuple(first_ballot["member_hashes"])

        cert_payload = {
            "digest": group_digest,
            "voters": list(voter_ids),
            "ballots": list(ballots_tuple),
            "signatures": list(signatures),
            "members": list(member_hashes),
            "state_hash": first_ballot["state_hash"],
            "evidence_root": first_ballot["evidence_root"],
        }
        cert_hash = hash_payload(cert_payload)

        group_cert = Q6GroupCertificate(
            digest=group_digest,
            voters=voter_ids,
            ballots=ballots_tuple,
            signatures=signatures,
            members=member_hashes,
            state_hash=first_ballot["state_hash"],
            evidence_root=first_ballot["evidence_root"],
            certificate_hash=cert_hash,
        )

        if interrupt_prepublish:
            return "INTERRUPTED_PREPUBLISH", None

        # 3. Phase 2: Commit (Publication)
        # Durable record in coordinator WAL before publication
        coord_rec = {
            "group_id": gid,
            "group_digest": group_digest,
            "certificate": group_cert.to_dict(),
        }
        self.wal.append("GROUP_PREPARED_QUORUM", coord_rec)

        commit_req = {
            "type": "COMMIT_REQUEST",
            "group_id": gid,
            "group_certificate": group_cert.to_dict(),
        }

        committed_nodes = []
        for idx, nid in enumerate(voter_ids):
            if interrupt_publication_replica is not None and idx >= interrupt_publication_replica:
                # Simulated crash of coordinator mid-publication
                return "COORDINATOR_CRASH_MID_PUBLISH", group_cert

            resp = self._send_to_node(nid, commit_req, timeout=3.0)
            if resp and resp.get("status") in ("COMMITTED", "ALREADY_COMMITTED"):
                committed_nodes.append(nid)

        if len(committed_nodes) >= self.threshold:
            self.wal.append("GROUP_COMMITTED", coord_rec)
            self.applied_groups[gid] = coord_rec
            return "COMMITTED", group_cert
        else:
            return "PUBLICATION_FAILED", None
