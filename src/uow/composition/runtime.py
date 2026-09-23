"""Adaptive composition runtime for Campaign A2.

Coordinates dynamic realization graph substitution under strict parent contract semantics,
executing certified graphs and guaranteeing deterministic fallback to the baseline graph.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import time
from typing import Any, Mapping, Tuple

from uow.composition.contract import ParentContract
from uow.composition.graph import RealizationGraph, RealizationNode
from uow.composition.substitution import (
    CompositionCertifier,
    GraphReplacementCertificate,
    GraphReplacementProposal,
    SubstitutionDecision,
    SubstitutionStrategy,
)


@dataclass(frozen=True)
class NodeExecutionResult:
    """Telemetry result of executing an individual node in the realization graph."""

    node_id: str
    role: str
    status: str  # "COMPLETED", "FAILED", "SKIPPED"
    duration_ms: float
    output_keys: Tuple[str, ...]
    error_message: str = ""


@dataclass(frozen=True)
class ExecutionRecord:
    """Record of a complete realization graph execution pass under a parent contract."""

    record_id: str
    parent_contract_hash: str
    graph_hash: str
    status: str  # "SUCCESS", "FAILED"
    node_results: Tuple[NodeExecutionResult, ...]
    final_outputs: Mapping[str, Any]
    total_duration_ms: float
    error_message: str = ""
    timestamp_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def compute_hash(self) -> str:
        payload = {
            "record_id": self.record_id,
            "parent_contract_hash": self.parent_contract_hash,
            "graph_hash": self.graph_hash,
            "status": self.status,
            "total_duration_ms": f"{self.total_duration_ms:.4f}",
            "error_message": self.error_message,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


class AdaptiveCompositionRuntime:
    """Runtime that manages execution graph state, certifies proposals, and dispatches tasks."""

    def __init__(
        self,
        contract: ParentContract,
        baseline_graph: RealizationGraph,
        certifier: CompositionCertifier | None = None,
    ) -> None:
        self.contract = contract
        self.baseline_graph = baseline_graph
        self.certifier = certifier or CompositionCertifier()
        self.active_graph = baseline_graph
        self.certificates_journal: list[GraphReplacementCertificate] = []
        self.execution_history: list[ExecutionRecord] = []
        self._execution_counter = 0

    @property
    def current_graph_hash(self) -> str:
        return self.active_graph.compute_hash()

    def propose_and_certify(
        self,
        proposal: GraphReplacementProposal,
    ) -> GraphReplacementCertificate:
        """Evaluates a graph replacement proposal and, if certified, atomically switches active graph."""
        next_epoch = len(self.certificates_journal) + 1
        cert = self.certifier.certify_proposal(
            proposal=proposal,
            original_graph=self.active_graph,
            contract=self.contract,
            current_epoch=next_epoch,
        )
        self.certificates_journal.append(cert)

        if cert.is_accepted:
            # Atomic substitution of the active execution graph
            self.active_graph = proposal.candidate_graph

        return cert

    def fallback_to_baseline(self, reason: str = "runtime_requested_fallback") -> GraphReplacementCertificate:
        """Atomically restores the active execution graph to the baseline graph."""
        next_epoch = len(self.certificates_journal) + 1
        fallback_proposal = GraphReplacementProposal(
            parent_contract_id=self.contract.contract_id,
            current_graph_hash=self.active_graph.compute_hash(),
            candidate_graph=self.baseline_graph,
            strategy=SubstitutionStrategy.FALLBACK_BASELINE,
            predicted_speedup=1.0,
            rationale=f"Automated fallback to baseline: {reason}",
            proposal_id=f"fallback_e{next_epoch}",
        )
        cert = self.certifier.certify_proposal(
            proposal=fallback_proposal,
            original_graph=self.active_graph,
            contract=self.contract,
            current_epoch=next_epoch,
        )
        self.certificates_journal.append(cert)
        self.active_graph = self.baseline_graph
        return cert

    def execute(
        self,
        inputs: Mapping[str, Any],
        fail_node_id: str | None = None,
    ) -> ExecutionRecord:
        """Executes the active realization graph topologically and verifies output postconditions."""
        self._execution_counter += 1
        rec_id = f"exec_{self._execution_counter}"
        t_start = time.perf_counter()

        topo_order = self.active_graph.topological_sort()
        node_results: list[NodeExecutionResult] = []
        state: dict[str, Any] = dict(inputs)
        failed = False
        error_msg = ""

        for nid in topo_order:
            node = self.active_graph.nodes[nid]
            if failed:
                node_results.append(
                    NodeExecutionResult(
                        node_id=nid,
                        role=node.role,
                        status="SKIPPED",
                        duration_ms=0.0,
                        output_keys=node.outputs,
                    )
                )
                continue

            if fail_node_id == nid:
                failed = True
                error_msg = f"Injected execution failure at node {nid}"
                node_results.append(
                    NodeExecutionResult(
                        node_id=nid,
                        role=node.role,
                        status="FAILED",
                        duration_ms=node.duration_ms,
                        output_keys=(),
                        error_message=error_msg,
                    )
                )
                continue

            # Simulate execution of node
            node_out: dict[str, Any] = {}
            for out_key in node.outputs:
                # Value generation deterministically dependent on inputs and role
                if "transform" in out_key or "feature" in out_key or "result" in out_key or "score" in out_key:
                    node_out[out_key] = f"computed_val_{out_key}"
                elif "verified" in out_key or "validated" in out_key or "certified" in out_key:
                    node_out[out_key] = True
                elif "evidence" in out_key or "audit" in out_key or "digest" in out_key or "receipt" in out_key:
                    node_out[out_key] = hashlib.sha256(f"evidence_{nid}".encode("utf-8")).hexdigest()[:16]
                else:
                    node_out[out_key] = f"val_{out_key}"

            state.update(node_out)
            node_results.append(
                NodeExecutionResult(
                    node_id=nid,
                    role=node.role,
                    status="COMPLETED",
                    duration_ms=node.duration_ms,
                    output_keys=node.outputs,
                )
            )

        total_dur = (time.perf_counter() - t_start) * 1000.0

        if failed:
            # Trigger fallback
            self.fallback_to_baseline(reason=error_msg)
            record = ExecutionRecord(
                record_id=rec_id,
                parent_contract_hash=self.contract.contract_hash,
                graph_hash=self.active_graph.compute_hash(),
                status="FAILED",
                node_results=tuple(node_results),
                final_outputs={},
                total_duration_ms=total_dur,
                error_message=error_msg,
            )
        else:
            # Check contract required outputs are satisfied
            final_outputs = {k: state.get(k) for k in self.contract.required_outputs if k in state}
            missing = set(self.contract.required_outputs) - set(final_outputs.keys())
            if missing:
                record = ExecutionRecord(
                    record_id=rec_id,
                    parent_contract_hash=self.contract.contract_hash,
                    graph_hash=self.active_graph.compute_hash(),
                    status="FAILED",
                    node_results=tuple(node_results),
                    final_outputs=final_outputs,
                    total_duration_ms=total_dur,
                    error_message=f"Missing parent contract outputs: {sorted(missing)}",
                )
            else:
                record = ExecutionRecord(
                    record_id=rec_id,
                    parent_contract_hash=self.contract.contract_hash,
                    graph_hash=self.active_graph.compute_hash(),
                    status="SUCCESS",
                    node_results=tuple(node_results),
                    final_outputs=final_outputs,
                    total_duration_ms=total_dur,
                )

        self.execution_history.append(record)
        return record
