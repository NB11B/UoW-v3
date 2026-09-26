"""Adaptive composition runtime for Campaign A2.

Coordinates dynamic realization graph substitution under strict parent contract
semantics, dispatches through qualified actor execution adapters when present,
and guarantees deterministic fallback to the baseline graph.

Actor binding remains separate from execution realization:
- ActorRegistry answers whether an actor is qualified and available.
- ActorExecutionRegistry optionally supplies how that actor executes.
- Missing execution adapters retain the historical deterministic local simulator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import time
from typing import Any, Mapping, Optional, Tuple

from uow.composition.actor import ActorRegistry
from uow.composition.binding import ActorBinding, validate_binding
from uow.composition.contract import ParentContract
from uow.composition.graph import RealizationGraph, RealizationNode
from uow.composition.policy import CompositionRuntimeState
from uow.composition.substitution import (
    CompositionCertifier,
    GraphReplacementCertificate,
    GraphReplacementProposal,
    SubstitutionStrategy,
)
from uow.implementations.composition.actor_execution import ActorExecutionRegistry


def _canonical_json(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True)
class NodeExecutionResult:
    """Telemetry result of executing an individual node in the realization graph."""

    node_id: str
    role: str
    status: str
    duration_ms: float
    output_keys: Tuple[str, ...]
    actor_id: str = "local"
    evidence_hash: str = ""
    child_record_hash: str = ""
    error_message: str = ""


@dataclass(frozen=True)
class ExecutionRecord:
    """Record of a complete realization graph execution pass under a parent contract."""

    record_id: str
    parent_contract_hash: str
    graph_hash: str
    status: str
    node_results: Tuple[NodeExecutionResult, ...]
    final_outputs: Mapping[str, Any]
    total_duration_ms: float
    error_message: str = ""
    timestamp_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evidence_root: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_root:
            payload = {
                "parent_contract_hash": self.parent_contract_hash,
                "graph_hash": self.graph_hash,
                "status": self.status,
                "nodes": [
                    {
                        "node_id": node.node_id,
                        "role": node.role,
                        "status": node.status,
                        "actor_id": node.actor_id,
                        "output_keys": list(node.output_keys),
                        "evidence_hash": node.evidence_hash,
                    }
                    for node in self.node_results
                ],
                "final_outputs": dict(self.final_outputs),
                "error_message": self.error_message,
            }
            object.__setattr__(
                self,
                "evidence_root",
                hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest(),
            )

    def compute_hash(self) -> str:
        """Historical diagnostic execution-record identity.

        Duration remains part of this record hash for compatibility.
        Recursive evidence chaining uses evidence_root because it is independent
        of wall-clock timing.
        """
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
    """Runtime that manages certified topology, actor binding and task dispatch."""

    def __init__(
        self,
        contract: ParentContract,
        baseline_graph: RealizationGraph,
        certifier: CompositionCertifier | None = None,
        registry: ActorRegistry | None = None,
        baseline_binding: ActorBinding | None = None,
        fabric: Any | None = None,
        executors: ActorExecutionRegistry | None = None,
    ) -> None:
        self.contract = contract
        self.baseline_graph = baseline_graph
        self.certifier = certifier or CompositionCertifier()
        self.registry = registry
        self.baseline_binding = baseline_binding
        self.active_binding = baseline_binding
        self.active_graph = baseline_graph
        self.fabric = fabric
        self.executors = executors or ActorExecutionRegistry()
        self.certificates_journal: list[GraphReplacementCertificate] = []
        self.execution_history: list[ExecutionRecord] = []
        self._execution_counter = 0

    @property
    def current_graph_hash(self) -> str:
        return self.active_graph.compute_hash()

    def get_runtime_state(
        self,
        queue_depth: int = 0,
        network_latency_ms: float = 0.0,
    ) -> CompositionRuntimeState:
        """Construct runtime state vector S_t from actor state and active graph."""
        if self.registry:
            avail = {a.actor_id: a.availability for a in self.registry.all_actors()}
            loads = {a.actor_id: a.load for a in self.registry.all_actors()}
            lats = {a.actor_id: a.latency_ms for a in self.registry.all_actors()}
            fails = {a.actor_id: a.recent_failures for a in self.registry.all_actors()}
        else:
            avail, loads, lats, fails = {}, {}, {}, {}

        return CompositionRuntimeState(
            actor_availability=avail,
            actor_loads=loads,
            actor_latencies=lats,
            actor_failure_counts=fails,
            active_graph_id=self.active_graph.graph_id,
            queue_depth=queue_depth,
            network_latency_ms=network_latency_ms,
        )

    def rebind_active_graph(
        self,
        new_binding: ActorBinding,
        current_ts: Optional[float] = None,
    ) -> Tuple[bool, Tuple[str, ...]]:
        """Tier 1: actor rebinding without topology mutation."""
        valid, violations = validate_binding(
            graph=self.active_graph,
            binding=new_binding,
            registry=self.registry or ActorRegistry(),
            fabric=self.fabric,
            current_ts=current_ts,
        )
        if valid:
            self.active_binding = new_binding
            return True, ()
        return False, tuple(violations)

    def propose_and_certify(
        self,
        proposal: GraphReplacementProposal,
        current_ts: Optional[float] = None,
    ) -> GraphReplacementCertificate:
        """Certify a replacement and atomically activate it only if accepted."""
        next_epoch = len(self.certificates_journal) + 1
        cert = self.certifier.certify_proposal(
            proposal=proposal,
            original_graph=self.active_graph,
            contract=self.contract,
            current_epoch=next_epoch,
            actor_registry=self.registry,
            fabric=self.fabric,
            current_ts=current_ts,
        )
        self.certificates_journal.append(cert)

        if cert.is_accepted:
            self.active_graph = proposal.candidate_graph
            if proposal.actor_binding:
                self.active_binding = proposal.actor_binding

        return cert

    def fallback_to_baseline(
        self,
        reason: str = "runtime_requested_fallback",
    ) -> GraphReplacementCertificate:
        """Atomically restore the active execution graph and binding to baseline."""
        next_epoch = len(self.certificates_journal) + 1
        fallback_proposal = GraphReplacementProposal(
            parent_contract_id=self.contract.contract_id,
            current_graph_hash=self.active_graph.compute_hash(),
            candidate_graph=self.baseline_graph,
            strategy=SubstitutionStrategy.FALLBACK_BASELINE,
            predicted_speedup=1.0,
            rationale=f"Automated fallback to baseline: {reason}",
            proposal_id=f"fallback_e{next_epoch}",
            actor_binding=self.baseline_binding,
        )
        cert = self.certifier.certify_proposal(
            proposal=fallback_proposal,
            original_graph=self.active_graph,
            contract=self.contract,
            current_epoch=next_epoch,
            actor_registry=self.registry,
            fabric=self.fabric,
        )
        self.certificates_journal.append(cert)
        self.active_graph = self.baseline_graph
        self.active_binding = self.baseline_binding
        return cert

    def _failed_preexecution_record(
        self,
        rec_id: str,
        error_message: str,
    ) -> ExecutionRecord:
        record = ExecutionRecord(
            record_id=rec_id,
            parent_contract_hash=self.contract.contract_hash,
            graph_hash=self.active_graph.compute_hash(),
            status="FAILED",
            node_results=(),
            final_outputs={},
            total_duration_ms=0.0,
            error_message=error_message,
        )
        self.execution_history.append(record)
        return record

    @staticmethod
    def _simulate_node(
        node: RealizationNode,
        actor_id: str,
    ) -> tuple[dict[str, Any], str]:
        """Historical deterministic local execution realization."""
        node_out: dict[str, Any] = {}
        for out_key in node.outputs:
            if (
                "transform" in out_key
                or "feature" in out_key
                or "result" in out_key
                or "score" in out_key
            ):
                node_out[out_key] = f"computed_val_{out_key}"
            elif (
                "verified" in out_key
                or "validated" in out_key
                or "certified" in out_key
            ):
                node_out[out_key] = True
            elif (
                "evidence" in out_key
                or "audit" in out_key
                or "digest" in out_key
                or "receipt" in out_key
            ):
                node_out[out_key] = hashlib.sha256(
                    f"evidence_{node.node_id}".encode("utf-8")
                ).hexdigest()[:16]
            else:
                node_out[out_key] = f"val_{out_key}"

        evidence_payload = {
            "node_id": node.node_id,
            "role": node.role,
            "actor_id": actor_id,
            "outputs": node_out,
        }
        evidence_hash = hashlib.sha256(
            _canonical_json(evidence_payload).encode("utf-8")
        ).hexdigest()
        return node_out, evidence_hash

    def execute(
        self,
        inputs: Mapping[str, Any],
        fail_node_id: str | None = None,
        current_ts: Optional[float] = None,
        ancestry: Tuple[str, ...] = (),
    ) -> ExecutionRecord:
        """Execute active graph, recursively dispatching registered actor adapters."""
        self._execution_counter += 1
        rec_id = f"exec_{self._execution_counter}"
        t_start = time.perf_counter()
        ts = current_ts if current_ts is not None else time.time()

        if self.fabric is not None and self.active_binding is not None:
            for nid, act_id in self.active_binding.node_to_actor.items():
                node = self.active_graph.nodes.get(nid)
                lease = self.fabric.get_valid_lease(act_id, ts)
                if (
                    lease is None
                    and node
                    and node.required_authority_class
                    in ("VERIFIER", "AUTHORITY_SUBSTRATE")
                ):
                    return self._failed_preexecution_record(
                        rec_id,
                        (
                            "AUTHORITY_ACTOR_UNAVAILABLE_FAIL_CLOSED: "
                            f"node {nid!r} authority actor {act_id!r} has no valid lease"
                        ),
                    )

        if self.registry is not None and self.active_binding is not None:
            binding_ok, binding_violations = validate_binding(
                self.active_graph,
                self.active_binding,
                self.registry,
                fabric=self.fabric,
                current_ts=ts,
            )
            if not binding_ok:
                return self._failed_preexecution_record(
                    rec_id,
                    "ACTIVE_BINDING_INVALID:" + ";".join(binding_violations),
                )

        topo_order = self.active_graph.topological_sort()
        node_results: list[NodeExecutionResult] = []
        state: dict[str, Any] = dict(inputs)
        failed = False
        error_msg = ""

        for nid in topo_order:
            node = self.active_graph.nodes[nid]
            act_id = (
                self.active_binding.node_to_actor.get(nid, "local")
                if self.active_binding
                else "local"
            )

            if failed:
                node_results.append(
                    NodeExecutionResult(
                        node_id=nid,
                        role=node.role,
                        status="SKIPPED",
                        duration_ms=0.0,
                        output_keys=node.outputs,
                        actor_id=act_id,
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
                        actor_id=act_id,
                        error_message=error_msg,
                    )
                )
                continue

            executor = self.executors.get(act_id)
            node_out: dict[str, Any]
            evidence_hash = ""
            child_record_hash = ""

            if executor is not None:
                actor_result = executor.execute_actor(
                    actor_id=act_id,
                    node=node,
                    inputs=state,
                    current_ts=ts,
                    ancestry=ancestry,
                )
                evidence_hash = actor_result.evidence_hash
                child_record_hash = actor_result.child_record_hash

                if not actor_result.ok:
                    failed = True
                    error_msg = actor_result.error_message or (
                        f"Actor {act_id!r} failed at node {nid!r}"
                    )
                    node_results.append(
                        NodeExecutionResult(
                            node_id=nid,
                            role=node.role,
                            status="FAILED",
                            duration_ms=node.duration_ms,
                            output_keys=tuple(actor_result.outputs.keys()),
                            actor_id=act_id,
                            evidence_hash=evidence_hash,
                            child_record_hash=child_record_hash,
                            error_message=error_msg,
                        )
                    )
                    continue

                node_out = dict(actor_result.outputs)
                missing_node_outputs = set(node.outputs) - set(node_out)
                if missing_node_outputs:
                    failed = True
                    error_msg = (
                        f"ACTOR_OUTPUT_DEFICIT: actor {act_id!r} at node {nid!r} "
                        f"missing {sorted(missing_node_outputs)}"
                    )
                    node_results.append(
                        NodeExecutionResult(
                            node_id=nid,
                            role=node.role,
                            status="FAILED",
                            duration_ms=node.duration_ms,
                            output_keys=tuple(node_out.keys()),
                            actor_id=act_id,
                            evidence_hash=evidence_hash,
                            child_record_hash=child_record_hash,
                            error_message=error_msg,
                        )
                    )
                    continue

                node_out = {key: node_out[key] for key in node.outputs}
            else:
                node_out, evidence_hash = self._simulate_node(node, act_id)

            state.update(node_out)
            node_results.append(
                NodeExecutionResult(
                    node_id=nid,
                    role=node.role,
                    status="COMPLETED",
                    duration_ms=node.duration_ms,
                    output_keys=tuple(node_out.keys()),
                    actor_id=act_id,
                    evidence_hash=evidence_hash,
                    child_record_hash=child_record_hash,
                )
            )

        total_dur = (time.perf_counter() - t_start) * 1000.0

        if failed:
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
            final_outputs = {
                key: state.get(key)
                for key in self.contract.required_outputs
                if key in state
            }
            missing = set(self.contract.required_outputs) - set(final_outputs)
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
