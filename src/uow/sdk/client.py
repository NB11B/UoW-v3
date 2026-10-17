"""UoW Python SDK Client (WP09).

Provides a high-level typed interface for submitting work, inspecting evidence,
and managing capabilities.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from uow.capabilities import CapabilityRecord, UniversalCapabilityRegistry
from uow.orchestration.planner import ExecutionPlanner
from uow.authority.platform_authority import PlatformEvidenceLedger
from uow.protocol.v1 import (
    CommitRecord,
    WorkRequest,
)
from .models import ClientWorkRequest, ClientWorkResponse, NodeStatus


class UoWClient:
    """Developer-facing typed SDK client for the UoW Capability Platform."""

    def __init__(
        self,
        node_id: str = "uow-node-local",
        planner: Optional[ExecutionPlanner] = None,
        registry: Optional[UniversalCapabilityRegistry] = None,
        ledger: Optional[PlatformEvidenceLedger] = None,
        endpoint_url: Optional[str] = None,
    ) -> None:
        self.node_id = node_id
        self.planner = planner
        self.registry = registry
        self.ledger = ledger
        self.endpoint_url = endpoint_url

    def submit_work(self, request: ClientWorkRequest) -> ClientWorkResponse:
        """Submit work request for deterministic planning, execution, and certification."""
        work_id = request.work_id or f"work-{uuid.uuid4().hex[:12]}"
        t0 = time.time()

        if self.planner:
            # In-process execution path
            state_ref = (
                self.ledger.root_hash
                if self.ledger and request.state_reference == "current"
                else request.state_reference
            )

            envelope = WorkRequest(
                work_id=work_id,
                origin_node=self.node_id,
                state_reference=state_ref,
                requested_capability=request.capability_id,
                payload=request.payload,
                deadline_policy=request.deadline_policy,
                created_at_utc=time.time(),
            )

            result = self.planner.execute_work(envelope, pre_state_hash=state_ref)

            # If certified and ledger present, commit to ledger
            cert_id = None
            if result.certificate and self.ledger:
                commit_rec = self.ledger.commit(result.certificate)
                cert_id = result.certificate.certificate_id

            action = result.proposal.proposed_action if result.proposal else None
            bindings = result.proposal.bindings if result.proposal else {}

            return ClientWorkResponse(
                work_id=work_id,
                success=result.success,
                disposition=result.final_disposition.value,
                action=action,
                bindings=bindings,
                certificate_id=cert_id,
                audit_explanation=result.explain(),
                rejection_reason=result.rejection_reason,
                total_latency_ms=(time.time() - t0) * 1000,
            )

        raise RuntimeError("No planner or remote endpoint configured for UoWClient")

    def list_capabilities(self) -> List[Dict[str, Any]]:
        """List registered capabilities."""
        if self.registry:
            recs = self.registry.list_capabilities()
            return [
                {
                    "capability_id": r.capability_id,
                    "version": r.version,
                    "kind": r.kind.value,
                    "state": r.state.value,
                    "status": r.descriptor.qualification_status.value,
                }
                for r in recs
            ]
        return []

    def get_node_status(self) -> NodeStatus:
        """Retrieve current node health, capabilities count, and ledger height."""
        cap_count = len(self.registry.list_capabilities()) if self.registry else 0
        ledger_height = self.ledger.step_count if self.ledger else 0
        ledger_root = self.ledger.root_hash if self.ledger else "0" * 64

        return NodeStatus(
            node_id=self.node_id,
            node_type="host_complete",
            is_online=True,
            registered_capabilities_count=cap_count,
            ledger_height=ledger_height,
            ledger_root_hash=ledger_root,
        )

    def get_evidence_records(self) -> List[CommitRecord]:
        """Fetch all monotonic evidence ledger records."""
        if self.ledger:
            return self.ledger.get_records()
        return []
