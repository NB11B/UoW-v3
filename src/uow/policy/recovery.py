r"""Node Recovery and Distributed State Reconciliation Engine (Milestone P5).

Implements crash recovery, in-flight transaction idempotency, and certificate-chain reconciliation:
- P5.3: Authority node reboot with certificate chain validation (\Pi_k -> \Pi_{k+1} -> ... -> \Pi_n).
- P5.4: Whole-host restart during active UoWs (zero duplicate effects: N_{duplicate_effects} = 0).
- P5.5: Corrupted persistence fail-closed containment (never guessing).
- P5.6: Conflicting recovery peers resolved strictly by valid certificate history, not node freshness.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from .authority import AuthorityRule
from .models import (
    DistributedPolicyCertificate,
    InFlightTransaction,
    Policy,
    PolicyLifecycleEvent,
    PolicyState,
    PolicyTransitionType,
    RecoveryRecord,
    RecoveryResultStatus,
    TransactionExecutionStatus,
)
from .persistence import CorruptedStorageError, DurablePolicyStore
from .registry import PolicyRegistry


class SplitBrainRecoveryError(Exception):
    """Raised when conflicting non-reconcilable certificate forks are discovered across recovery peers."""
    pass


class NodeRecoveryCoordinator:
    """Manages crash recovery, transaction resolution, and cryptographic peer reconciliation."""

    def __init__(
        self,
        node_id: str,
        authority_id: str,
        store: DurablePolicyStore,
        authority_rule: Optional[AuthorityRule] = None,
    ) -> None:
        self.node_id = node_id
        self.authority_id = authority_id
        self.store = store
        self.authority_rule = authority_rule

        self._recovery_records: List[RecoveryRecord] = []

    @property
    def latest_recovery_record(self) -> Optional[RecoveryRecord]:
        return self._recovery_records[-1] if self._recovery_records else None

    def recover_local_state(
        self,
        policies_catalog: Optional[Mapping[str, Policy]] = None,
    ) -> Tuple[PolicyRegistry, RecoveryRecord]:
        r"""Perform crash recovery of local node state from durable storage.
        
        Guarantees:
        - Exact registry restoration (\Pi_k' == \Pi_k)
        - In-flight transaction idempotency and zero duplicate effects (N_{duplicate} = 0)
        - Fail-closed containment on corrupted disk state
        """
        now = time.time()
        recovery_id = f"rec_{self.node_id}_{int(now * 1000)}"
        p_map = policies_catalog or {}

        # 1. Load Registry Snapshot from Durable Store (Fails Closed on Corruption)
        try:
            registry, stored_rule, file_hash = self.store.load_registry()
            if stored_rule is not None:
                self.authority_rule = stored_rule
        except CorruptedStorageError as e:
            # Emit fail-closed recovery record
            fail_record = RecoveryRecord(
                recovery_id=recovery_id,
                node_id=self.node_id,
                startup_time=now,
                local_registry_version=0,
                local_registry_digest="CORRUPTED",
                committed_registry_version=0,
                committed_registry_digest="CORRUPTED",
                replayed_certificates=(),
                rejected_certificates=(),
                inflight_transactions_found=0,
                transactions_resumed=0,
                transactions_aborted=0,
                transactions_already_committed=0,
                duplicate_effects_prevented=0,
                recovery_result=RecoveryResultStatus.FAIL_CLOSED_CORRUPTION,
                details={"error": str(e)},
            )
            self._recovery_records.append(fail_record)
            raise

        v_initial = registry.version
        digest_initial = registry.compute_digest()

        # 2. Check Write-Ahead Journal for Uncommitted Transitions
        replayed_certs: List[str] = []
        journal_certs = self.store.get_journal_certificates()
        for cert in journal_certs:
            if cert.registry_version_before == registry.version and cert.quorum_satisfied:
                policy = p_map.get(cert.policy_id)
                registry.register_certified_transition(cert, policy=policy)
                replayed_certs.append(cert.transition_id)

        # 3. Classify and Resolve In-Flight Transactions (P5.4)
        inflight_txs = self.store.load_inflight_transactions()
        inflight_count = len(inflight_txs)
        tx_resumed = 0
        tx_aborted = 0
        tx_already_committed = 0
        duplicate_effects_prevented = 0

        for tx in inflight_txs:
            if tx.status == TransactionExecutionStatus.NOT_STARTED:
                # Work never started before crash: safe to abort cleanly
                tx_aborted += 1
                self.store.remove_inflight(tx.uow_id)
            elif tx.status == TransactionExecutionStatus.IN_FLIGHT:
                if not tx.external_effect_applied:
                    # In-flight computation aborted before any side effect occurred
                    tx_aborted += 1
                    self.store.remove_inflight(tx.uow_id)
                else:
                    # External effect was already applied! DO NOT execute again!
                    tx_resumed += 1
                    duplicate_effects_prevented += 1
                    committed_tx = tx.with_status(TransactionExecutionStatus.COMMITTED)
                    self.store.record_inflight(committed_tx)
            elif tx.status == TransactionExecutionStatus.EXECUTED_UNCOMMITTED:
                # Execution completed with side-effects prior to ledger commit
                tx_already_committed += 1
                duplicate_effects_prevented += 1
                committed_tx = tx.with_status(TransactionExecutionStatus.COMMITTED)
                self.store.record_inflight(committed_tx)
            elif tx.status == TransactionExecutionStatus.COMMITTED:
                tx_already_committed += 1

        v_final = registry.version
        digest_final = registry.compute_digest()

        # Update persistent snapshot if replay advanced version
        if v_final > v_initial:
            self.store.persist_registry(registry, authority_rule=self.authority_rule)

        record = RecoveryRecord(
            recovery_id=recovery_id,
            node_id=self.node_id,
            startup_time=now,
            local_registry_version=v_initial,
            local_registry_digest=digest_initial,
            committed_registry_version=v_final,
            committed_registry_digest=digest_final,
            replayed_certificates=tuple(replayed_certs),
            rejected_certificates=(),
            inflight_transactions_found=inflight_count,
            transactions_resumed=tx_resumed,
            transactions_aborted=tx_aborted,
            transactions_already_committed=tx_already_committed,
            duplicate_effects_prevented=duplicate_effects_prevented,
            recovery_result=RecoveryResultStatus.CLEAN_RECOVERY,
            details={"file_hash": file_hash},
        )
        self._recovery_records.append(record)
        return registry, record

    def reconcile_with_peer_chain(
        self,
        registry: PolicyRegistry,
        peer_certificate_chain: Sequence[DistributedPolicyCertificate],
        policies_catalog: Optional[Mapping[str, Policy]] = None,
    ) -> RecoveryRecord:
        r"""Reconcile lagging local registry state against verified peer certificate history (P5.3, P5.6).
        
        Hard Invariant:
        Certificate chain determines state (\Pi_k -> \Pi_{k+1} -> ... -> \Pi_n).
        State is never determined by peer freshness, node timestamps, or highest version integer.
        """
        now = time.time()
        recovery_id = f"rec_recon_{self.node_id}_{int(now * 1000)}"
        p_map = policies_catalog or {}

        v_initial = registry.version
        digest_initial = registry.compute_digest()

        replayed_certs: List[str] = []
        rejected_certs: List[str] = []

        # Sort candidate certificates by registry version before
        sorted_candidates = sorted(peer_certificate_chain, key=lambda c: c.registry_version_before)

        # Track parent versions to detect split-brain forks
        seen_parent_versions: Dict[int, str] = {}

        for cert in sorted_candidates:
            # Detect split-brain conflicting fork
            if cert.registry_version_before in seen_parent_versions:
                if seen_parent_versions[cert.registry_version_before] != cert.transition_id:
                    # Fork detected claiming same parent version
                    rejected_certs.append(cert.transition_id)
                    split_record = RecoveryRecord(
                        recovery_id=recovery_id,
                        node_id=self.node_id,
                        startup_time=now,
                        local_registry_version=v_initial,
                        local_registry_digest=digest_initial,
                        committed_registry_version=registry.version,
                        committed_registry_digest=registry.compute_digest(),
                        replayed_certificates=tuple(replayed_certs),
                        rejected_certificates=tuple(rejected_certs),
                        inflight_transactions_found=0,
                        transactions_resumed=0,
                        transactions_aborted=0,
                        transactions_already_committed=0,
                        duplicate_effects_prevented=0,
                        recovery_result=RecoveryResultStatus.FAIL_CLOSED_SPLIT_BRAIN,
                        details={"conflict_parent_version": cert.registry_version_before},
                    )
                    self._recovery_records.append(split_record)
                    raise SplitBrainRecoveryError(
                        f"Split-brain detected: conflicting certificates for parent version {cert.registry_version_before}"
                    )

            # Skip certificates already committed locally
            if cert.registry_version_after <= registry.version:
                continue

            # Verify causal chaining
            if cert.registry_version_before != registry.version:
                rejected_certs.append(cert.transition_id)
                continue

            if cert.previous_registry_digest != registry.compute_digest():
                rejected_certs.append(cert.transition_id)
                continue

            # Verify quorum compliance
            rule = self.authority_rule
            min_threshold = rule.threshold if rule else 2
            if not cert.quorum_satisfied or len(cert.authority_votes) < min_threshold:
                rejected_certs.append(cert.transition_id)
                continue

            # Apply certified transition
            policy = p_map.get(cert.policy_id)
            registry.register_certified_transition(cert, policy=policy)
            self.store.log_certificate(cert)
            replayed_certs.append(cert.transition_id)
            seen_parent_versions[cert.registry_version_before] = cert.transition_id

        v_final = registry.version
        digest_final = registry.compute_digest()

        if v_final > v_initial:
            self.store.persist_registry(registry, authority_rule=self.authority_rule)

        result_status = RecoveryResultStatus.RECONCILED_FROM_PEERS if replayed_certs else RecoveryResultStatus.CLEAN_RECOVERY
        record = RecoveryRecord(
            recovery_id=recovery_id,
            node_id=self.node_id,
            startup_time=now,
            local_registry_version=v_initial,
            local_registry_digest=digest_initial,
            committed_registry_version=v_final,
            committed_registry_digest=digest_final,
            replayed_certificates=tuple(replayed_certs),
            rejected_certificates=tuple(rejected_certs),
            inflight_transactions_found=0,
            transactions_resumed=0,
            transactions_aborted=0,
            transactions_already_committed=0,
            duplicate_effects_prevented=0,
            recovery_result=result_status,
            details={"peer_candidates_count": len(peer_certificate_chain)},
        )
        self._recovery_records.append(record)
        return record
