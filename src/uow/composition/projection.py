"""Semantic Projection Phi(G, U) for Campaign A2: Adaptive Composition Runtime.

Projects an executable realization graph G back onto the parent contract U across
seven invariant classes:
  Phi(G, U) = (O, D, A, E, T, R, F)

Two graphs G_a and G_b are semantically equivalent under contract U iff:
  Phi(G_a, U) == Phi(G_b, U) == Phi(U)
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from ..state import canonical_json
from .contract import ParentContract
from .graph import RealizationGraph, RealizationNode


@dataclass(frozen=True)
class SemanticProjection:
    """Projection tuple Phi(G, U) = (O, D, A, E, T, R, F)."""
    contract_id: str
    graph_id: str

    # 1. Observable outputs (O)
    outputs: Tuple[str, ...]
    outputs_satisfied: bool

    # 2. Causal and dependency constraints (D)
    causal_satisfied: bool

    # 3. Authority obligations (A)
    authority_satisfied: bool

    # 4. Evidence / provenance obligations (E)
    evidence_satisfied: bool

    # 5. Temporal requirements (T)
    temporal_satisfied: bool
    measured_critical_path_ms: float

    # 6. Resource and safety constraints (R)
    resource_satisfied: bool
    measured_cost_units: float

    # 7. Failure semantics (F)
    failure_satisfied: bool

    # Overall validity and diagnostic trace
    conforms: bool
    violations: Tuple[str, ...]
    projection_hash: str = ""

    def __post_init__(self) -> None:
        if not self.projection_hash:
            payload = {
                "contract_id": self.contract_id,
                "outputs": sorted(self.outputs),
                "outputs_satisfied": self.outputs_satisfied,
                "causal_satisfied": self.causal_satisfied,
                "authority_satisfied": self.authority_satisfied,
                "evidence_satisfied": self.evidence_satisfied,
                "temporal_satisfied": self.temporal_satisfied,
                "resource_satisfied": self.resource_satisfied,
                "failure_satisfied": self.failure_satisfied,
                "conforms": self.conforms,
            }
            digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
            object.__setattr__(self, "projection_hash", digest)


def project_semantics(graph: RealizationGraph, contract: ParentContract) -> SemanticProjection:
    """Calculates the semantic projection Phi(G, U) = (O, D, A, E, T, R, F)."""
    violations: List[str] = []

    # -------------------------------------------------------------------------
    # 1. Observable outputs / postconditions (O)
    # -------------------------------------------------------------------------
    emitted_outputs: Set[str] = set()
    for node in graph.nodes.values():
        emitted_outputs.update(node.outputs)

    missing_outputs = set(contract.required_outputs) - emitted_outputs
    outputs_satisfied = len(missing_outputs) == 0
    if not outputs_satisfied:
        violations.append(f"O_MISSING_OUTPUTS: graph missing required outputs {sorted(missing_outputs)}")

    # -------------------------------------------------------------------------
    # 2. Dependency and causal constraints (D)
    # -------------------------------------------------------------------------
    causal_satisfied = True
    for rule in contract.causal_constraints:
        if not graph.roles_causally_ordered(rule.predecessor_role, rule.successor_role, rule.strict_immediate):
            causal_satisfied = False
            violations.append(
                f"D_CAUSAL_ORDER_VIOLATION: role '{rule.predecessor_role}' does not properly precede '{rule.successor_role}'"
            )

    # -------------------------------------------------------------------------
    # 3. Authority requirements (A)
    # -------------------------------------------------------------------------
    auth_role = contract.authority.required_role
    auth_nodes = graph.get_nodes_by_role(auth_role)
    authority_satisfied = True

    if not auth_nodes:
        authority_satisfied = False
        violations.append(f"A_AUTHORITY_ROLE_MISSING: graph contains no node with required authority role '{auth_role}'")
    else:
        # Authority tier check
        for an in auth_nodes:
            if an.authority_tier == "untrusted":
                authority_satisfied = False
                violations.append(f"A_AUTHORITY_TIER_DEFICIT: node '{an.node_id}' in authority role has untrusted tier")

        # Crucial Invariant: Authority must causally precede any commit or persist node!
        commit_nodes = graph.get_nodes_by_role("commit")
        for cn in commit_nodes:
            has_auth_predecessor = any(graph.is_reachable(an.node_id, cn.node_id) for an in auth_nodes)
            if not has_auth_predecessor:
                authority_satisfied = False
                violations.append(f"A_COMMIT_BYPASSES_AUTHORITY: commit node '{cn.node_id}' not preceded by authority '{auth_role}'")

    # -------------------------------------------------------------------------
    # 4. Evidence / provenance obligations (E)
    # -------------------------------------------------------------------------
    evidence_satisfied = True
    if contract.evidence.require_provenance:
        missing_prov = [n.node_id for n in graph.nodes.values() if not n.generates_provenance]
        if missing_prov:
            evidence_satisfied = False
            violations.append(f"E_PROVENANCE_MISSING: nodes {missing_prov} omit required cryptographic provenance")

    level_order = {"portable": 1, "physical": 2}
    req_level_val = level_order.get(contract.evidence.min_evidence_level, 1)
    for n in graph.nodes.values():
        node_level_val = level_order.get(n.evidence_level, 1)
        if node_level_val < req_level_val:
            evidence_satisfied = False
            violations.append(
                f"E_EVIDENCE_LEVEL_DEFICIT: node '{n.node_id}' has level '{n.evidence_level}', required '{contract.evidence.min_evidence_level}'"
            )

    # -------------------------------------------------------------------------
    # 5. Temporal requirements (T)
    # -------------------------------------------------------------------------
    critical_path_ms = graph.critical_path_duration_ms()
    temporal_satisfied = critical_path_ms <= contract.temporal.max_duration_ms
    if not temporal_satisfied:
        violations.append(
            f"T_DEADLINE_EXCEEDED: critical path duration {critical_path_ms:.1f}ms exceeds max {contract.temporal.max_duration_ms:.1f}ms"
        )

    # -------------------------------------------------------------------------
    # 6. Resource and safety constraints (R)
    # -------------------------------------------------------------------------
    total_cost = graph.total_cost_units()
    peaks = graph.peak_resource_demands()
    resource_satisfied = True

    if total_cost > contract.resources.max_cost_units:
        resource_satisfied = False
        violations.append(f"R_COST_BUDGET_EXCEEDED: total cost {total_cost:.1f} exceeds limit {contract.resources.max_cost_units:.1f}")

    if peaks["max_cpu_cores"] > contract.resources.max_cpu_cores:
        resource_satisfied = False
        violations.append(f"R_CPU_EXCEEDED: peak cpu {peaks['max_cpu_cores']} exceeds limit {contract.resources.max_cpu_cores}")

    if peaks["max_gpu_slots"] > contract.resources.max_gpu_slots:
        resource_satisfied = False
        violations.append(f"R_GPU_EXCEEDED: peak gpu {peaks['max_gpu_slots']} exceeds limit {contract.resources.max_gpu_slots}")

    if peaks["max_npu_slots"] > contract.resources.max_npu_slots:
        resource_satisfied = False
        violations.append(f"R_NPU_EXCEEDED: peak npu {peaks['max_npu_slots']} exceeds limit {contract.resources.max_npu_slots}")

    # -------------------------------------------------------------------------
    # 7. Failure semantics (F)
    # -------------------------------------------------------------------------
    failure_satisfied = True
    req_fail_mode = contract.failure_semantics.value
    for n in graph.nodes.values():
        if req_fail_mode == "ROLLBACK" and n.failure_mode == "PARTIAL_COMMIT":
            failure_satisfied = False
            violations.append(f"F_FAILURE_SEMANTICS_MISMATCH: node '{n.node_id}' implements PARTIAL_COMMIT under ROLLBACK contract")

    conforms = len(violations) == 0

    return SemanticProjection(
        contract_id=contract.contract_id,
        graph_id=graph.graph_id,
        outputs=tuple(sorted(emitted_outputs)),
        outputs_satisfied=outputs_satisfied,
        causal_satisfied=causal_satisfied,
        authority_satisfied=authority_satisfied,
        evidence_satisfied=evidence_satisfied,
        temporal_satisfied=temporal_satisfied,
        measured_critical_path_ms=critical_path_ms,
        resource_satisfied=resource_satisfied,
        measured_cost_units=total_cost,
        failure_satisfied=failure_satisfied,
        conforms=conforms,
        violations=tuple(violations),
    )


def check_conformance(graph: RealizationGraph, contract: ParentContract) -> bool:
    """Verifies that realization graph G satisfies parent contract U: G |= U."""
    projection = project_semantics(graph, contract)
    return projection.conforms


def are_equivalent(g_a: RealizationGraph, g_b: RealizationGraph, contract: ParentContract) -> bool:
    """Determines whether two structurally distinct graphs are semantically equivalent: G_a =_U G_b."""
    proj_a = project_semantics(g_a, contract)
    proj_b = project_semantics(g_b, contract)

    if not proj_a.conforms or not proj_b.conforms:
        return False

    return proj_a.projection_hash == proj_b.projection_hash
