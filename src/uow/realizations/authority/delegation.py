"""Distributed delegation-node realization over canonical delegation semantics."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from ...composition.contract import ParentContract
from ...composition.delegation import (
    AuthorityScope,
    ChildUoWSpec,
    DelegationCertificate,
    DelegationResult,
    validate_delegation,
)
from ...implementations.distributed.fabric import DistributedActorFabric


class DistributedDelegationNode:
    """Autonomous network node capable of decomposing, delegating, and executing hierarchical UoWs."""

    def __init__(
        self,
        node_id: str,
        authority_scope: AuthorityScope,
        fabric: Optional[DistributedActorFabric] = None,
        generation: int = 1,
        delegation_ttl_sec: float = 30.0,
    ) -> None:
        self.node_id = node_id
        self.authority_scope = authority_scope
        self.fabric = fabric
        self.generation = generation
        self.delegation_ttl_sec = delegation_ttl_sec
        self.inflight_delegations: Dict[str, Tuple[ChildUoWSpec, DelegationCertificate]] = {}
        self.child_results: Dict[str, DelegationResult] = {}
        self.nonce_counter = 0

    def issue_certificate(
        self,
        parent_contract: ParentContract,
        child_spec: ChildUoWSpec,
        current_ts: Optional[float] = None,
    ) -> DelegationCertificate:
        """Issues a time-bounded, attenuated DelegationCertificate for a child UoW."""
        ts = current_ts if current_ts is not None else time.time()
        self.nonce_counter += 1
        nonce = f"non_{self.node_id}_{self.nonce_counter}_{int(ts * 1000)}"
        return DelegationCertificate(
            cert_id=f"cert_{child_spec.child_uow_id}_{self.generation}",
            parent_contract_id=parent_contract.contract_id,
            parent_contract_hash=parent_contract.contract_hash,
            child_uow_id=child_spec.child_uow_id,
            projection_hash=child_spec.sub_contract.contract_hash,
            issuer_actor_id=self.node_id,
            delegate_actor_id=child_spec.assigned_actor_id,
            authority_scope=child_spec.authority_scope,
            generation=self.generation,
            granted_at_ts=ts,
            expires_at_ts=ts + self.delegation_ttl_sec,
            nonce=nonce,
        )

    def dispatch_delegation(
        self,
        parent_contract: ParentContract,
        child_specs: Sequence[ChildUoWSpec],
        input_payload: Mapping[str, Any],
        current_ts: Optional[float] = None,
    ) -> Tuple[bool, Tuple[str, ...]]:
        """Decomposes parent work and issues validated delegation certificates."""
        ts = current_ts if current_ts is not None else time.time()
        violations: List[str] = []

        # 1. Semantic Conservation Pre-Check: union of child expected outputs must satisfy required parent outputs
        all_child_outputs: Set[str] = set()
        for c in child_specs:
            all_child_outputs.update(c.expected_outputs)

        missing_outputs = set(parent_contract.required_outputs) - all_child_outputs
        if missing_outputs:
            violations.append(
                f"SEMANTIC_CONSERVATION_DEFICIT: child specifications omit required parent outputs {sorted(missing_outputs)}"
            )

        # 2. Validate certificates for each child
        for c in child_specs:
            cert = self.issue_certificate(parent_contract, c, ts)
            valid, cert_violations = validate_delegation(
                self.authority_scope, cert, self.fabric, ts
            )
            if not valid:
                violations.extend(cert_violations)
            else:
                self.inflight_delegations[c.child_uow_id] = (c, cert)

        return len(violations) == 0, tuple(violations)

    def receive_child_result(
        self,
        result: DelegationResult,
        current_ts: Optional[float] = None,
    ) -> Tuple[bool, str]:
        """Validates and collects a result from a delegated child actor.
        
        Strictly enforces generation ordering: result.generation >= self.generation.
        """
        ts = current_ts if current_ts is not None else time.time()

        # 1. Generation Check: Stale results from obsolete generations are rejected
        if result.generation < self.generation:
            return (
                False,
                f"STALE_CHILD_RESULT_REJECTED: result generation {result.generation} < active generation {self.generation}",
            )

        if result.child_uow_id not in self.inflight_delegations:
            return False, f"UNKNOWN_CHILD_UOW: result for undelegated child {result.child_uow_id!r}"

        spec, cert = self.inflight_delegations[result.child_uow_id]

        # 2. Identity Check: Result must originate from assigned delegate
        if result.delegate_actor_id != cert.delegate_actor_id:
            return (
                False,
                f"DELEGATE_MISMATCH: expected {cert.delegate_actor_id!r}, received {result.delegate_actor_id!r}",
            )

        if result.status != "SUCCESS":
            return False, f"CHILD_EXECUTION_FAILED: {result.error_message}"

        # 3. Output Conformance Check
        missing_keys = set(spec.expected_outputs) - set(result.outputs.keys())
        if missing_keys:
            return (
                False,
                f"OUTPUT_DEFICIT: child result missing expected outputs {sorted(missing_keys)}",
            )

        self.child_results[result.child_uow_id] = result
        return True, "ACCEPTED"

    def handle_delegate_failure(
        self,
        child_uow_id: str,
        parent_contract: ParentContract,
        fallback_actor_id: str,
        current_ts: Optional[float] = None,
    ) -> Tuple[bool, Optional[DelegationCertificate], str]:
        """Safely failovers a dropped delegate if child work is idempotent."""
        ts = current_ts if current_ts is not None else time.time()

        if child_uow_id not in self.inflight_delegations:
            return False, None, f"UNKNOWN_CHILD_UOW: {child_uow_id!r}"

        spec, old_cert = self.inflight_delegations[child_uow_id]

        if not spec.is_idempotent:
            return (
                False,
                None,
                f"NON_IDEMPOTENT_DELEGATION_ABORT: child {child_uow_id!r} cannot be safely retried",
            )

        # Create new spec with fallback actor
        new_spec = ChildUoWSpec(
            child_uow_id=spec.child_uow_id,
            sub_contract=spec.sub_contract,
            input_keys=spec.input_keys,
            expected_outputs=spec.expected_outputs,
            assigned_actor_id=fallback_actor_id,
            authority_scope=spec.authority_scope,
            is_idempotent=spec.is_idempotent,
        )

        new_cert = self.issue_certificate(parent_contract, new_spec, ts)
        valid, violations = validate_delegation(
            self.authority_scope, new_cert, self.fabric, ts
        )
        if not valid:
            return False, None, f"FAILOVER_DELEGATION_INVALID: {'; '.join(violations)}"

        self.inflight_delegations[child_uow_id] = (new_spec, new_cert)
        return True, new_cert, "FAILOVER_DISPATCHED"

    def assemble_results(self, parent_contract: ParentContract) -> Tuple[bool, Mapping[str, Any], str]:
        """Aggregates all child results, ensuring complete satisfaction of parent contract outputs."""
        aggregated: Dict[str, Any] = {}
        for child_id, res in self.child_results.items():
            aggregated.update(res.outputs)

        missing = set(parent_contract.required_outputs) - set(aggregated.keys())
        if missing:
            return False, aggregated, f"INCOMPLETE_ASSEMBLY: missing {sorted(missing)}"

        return True, aggregated, "ASSEMBLED"


__all__ = ["DistributedDelegationNode"]
