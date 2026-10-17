"""Platform Authority Kernel, Evidence Ledger, and Recovery Manager (WP07).

Strict implementation of the deterministic UoW authority boundary:
- Zero Field Substitution
- Pre-State Hash Invariance
- Monotonic Cryptographic Hash-Chained Evidence Ledger
- Idempotent Recovery and Compensation
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Callable, Dict, List, Optional, Set

from src.uow.protocol.v1 import (
    CapabilityProposal,
    CommitDisposition,
    CommitRecord,
    RecoveryCommand,
    WorkCertificate,
    canonical_json,
    compute_digest,
)


class PlatformAuthorityKernel:
    """Independent Authority Certification Kernel."""

    def __init__(
        self,
        node_id: str,
        state_resolver: Optional[Callable[[str], Dict[str, Any]]] = None,
    ) -> None:
        self.node_id = node_id
        self.state_resolver = state_resolver

    def certify(
        self,
        proposal: CapabilityProposal,
        expected_pre_state_hash: str,
        actual_pre_state_hash: str,
        route_guard_evaluator: Optional[Callable[[CapabilityProposal], Tuple[bool, Optional[str]]]] = None,
    ) -> WorkCertificate:
        """Independently certify a capability proposal.
        
        Enforces:
        1. Pre-state hash match: actual_pre_state_hash == expected_pre_state_hash
        2. Fail-closed route guards
        3. Zero field substitution: raw proposal fields are audited exactly as emitted
        """
        cert_id = f"cert-{proposal.work_id}-{int(time.time() * 1000)}"

        # Invariant 1: Pre-state match
        if actual_pre_state_hash != expected_pre_state_hash:
            return WorkCertificate(
                certificate_id=cert_id,
                work_id=proposal.work_id,
                contract_hash=proposal.capability_id,
                pre_state_hash=actual_pre_state_hash,
                proposed_state_hash="",
                selected_route_index=-1,
                authorization_evidence={"actual_pre_state": actual_pre_state_hash, "expected_pre_state": expected_pre_state_hash},
                issuer_identity=self.node_id,
                is_valid=False,
                rejection_reason=f"Pre-state divergence: expected {expected_pre_state_hash[:8]}, got {actual_pre_state_hash[:8]}",
            )

        # Invariant 2: Proposal boundary check
        if not proposal.validate_boundary():
            return WorkCertificate(
                certificate_id=cert_id,
                work_id=proposal.work_id,
                contract_hash=proposal.capability_id,
                pre_state_hash=actual_pre_state_hash,
                proposed_state_hash="",
                selected_route_index=-1,
                authorization_evidence={"boundary_violation": True},
                issuer_identity=self.node_id,
                is_valid=False,
                rejection_reason="Proposal boundary violation: unprivileged proposal declared authority",
            )

        # Invariant 3: Route guard evaluation
        if route_guard_evaluator:
            guards_ok, guard_reason = route_guard_evaluator(proposal)
            if not guards_ok:
                return WorkCertificate(
                    certificate_id=cert_id,
                    work_id=proposal.work_id,
                    contract_hash=proposal.capability_id,
                    pre_state_hash=actual_pre_state_hash,
                    proposed_state_hash="",
                    selected_route_index=-1,
                    authorization_evidence={"guard_failure": guard_reason},
                    issuer_identity=self.node_id,
                    is_valid=False,
                    rejection_reason=f"Route guard failed: {guard_reason}",
                )

        # Compute deterministic successor state hash
        successor_payload = {
            "pre_state": actual_pre_state_hash,
            "action": proposal.proposed_action,
            "bindings": proposal.bindings,
        }
        proposed_state_hash = compute_digest(successor_payload)

        return WorkCertificate(
            certificate_id=cert_id,
            work_id=proposal.work_id,
            contract_hash=proposal.capability_id,
            pre_state_hash=actual_pre_state_hash,
            proposed_state_hash=proposed_state_hash,
            selected_route_index=0,
            authorization_evidence={
                "proposal_digest": proposal.digest(),
                "producer": proposal.producer_identity,
                "uncertainty": proposal.uncertainty_score,
            },
            issuer_identity=self.node_id,
            is_valid=True,
        )


class PlatformEvidenceLedger:
    """Monotonic cryptographic hash-chained evidence ledger."""

    def __init__(self, genesis_hash: str = "0" * 64) -> None:
        self.genesis_hash = genesis_hash
        self._current_root_hash = genesis_hash
        self._records: List[CommitRecord] = []
        self._by_work_id: Dict[str, CommitRecord] = {}

    @property
    def root_hash(self) -> str:
        return self._current_root_hash

    @property
    def step_count(self) -> int:
        return len(self._records)

    def commit(
        self,
        certificate: WorkCertificate,
        resulting_state_hash: Optional[str] = None,
        disposition: Optional[CommitDisposition] = None,
    ) -> CommitRecord:
        """Commit certified work or record a certified rejection."""
        disp = disposition or (
            CommitDisposition.COMMITTED if certificate.is_valid else CommitDisposition.REJECTED
        )
        res_hash = (
            (resulting_state_hash or certificate.proposed_state_hash)
            if certificate.is_valid
            else certificate.pre_state_hash
        )

        step_num = len(self._records) + 1
        prev_root = self._current_root_hash

        record = CommitRecord(
            commit_id=f"commit-{certificate.work_id}-{step_num}",
            work_id=certificate.work_id,
            step_number=step_num,
            prev_evidence_root=prev_root,
            resulting_state_hash=res_hash,
            disposition=disp,
            certificate_digest=certificate.digest(),
            committed_at_utc=time.time(),
            details={"issuer": certificate.issuer_identity, "rejection_reason": certificate.rejection_reason},
        )

        # Advance hash chain: H_i = SHA256(H_{i-1} || canonical_json(record))
        link_str = prev_root + record.to_canonical_json()
        self._current_root_hash = hashlib.sha256(link_str.encode("utf-8")).hexdigest()

        self._records.append(record)
        self._by_work_id[certificate.work_id] = record
        return record

    def verify_integrity(self) -> bool:
        """Verify the complete monotonic hash chain from genesis root to tip."""
        expected_root = self.genesis_hash
        for idx, rec in enumerate(self._records, 1):
            if rec.step_number != idx:
                return False
            if rec.prev_evidence_root != expected_root:
                return False
            link_str = expected_root + rec.to_canonical_json()
            expected_root = hashlib.sha256(link_str.encode("utf-8")).hexdigest()

        return expected_root == self._current_root_hash

    def get_records(self) -> List[CommitRecord]:
        return list(self._records)


class PlatformRecoveryManager:
    """Manages transactional idempotency, compensation, and restart recovery."""

    def __init__(self, ledger: PlatformEvidenceLedger) -> None:
        self.ledger = ledger
        self._idempotency_table: Dict[str, CommitRecord] = {}
        self._compensation_registry: Dict[str, Callable[[RecoveryCommand], bool]] = {}

    def register_compensation(
        self,
        action_name: str,
        compensator: Callable[[RecoveryCommand], bool],
    ) -> None:
        self._compensation_registry[action_name] = compensator

    def execute_compensation(self, cmd: RecoveryCommand) -> bool:
        """Execute a compensating transaction for interrupted or erroneous work."""
        compensator = self._compensation_registry.get(cmd.permitted_compensation)
        if not compensator:
            return False
        return compensator(cmd)

    def is_work_processed(self, idempotency_key: str) -> Optional[CommitRecord]:
        return self._idempotency_table.get(idempotency_key)

    def record_processed(self, idempotency_key: str, record: CommitRecord) -> None:
        self._idempotency_table[idempotency_key] = record
