"""Certified recursive composition boundaries.

This module defines the language-neutral semantic seam that allows a governed
UoW realization to appear as one actor inside a larger governed UoW.

The boundary is a conformance attestation, not an authority grant. Authority
transfer remains the responsibility of delegation semantics.

Recursive rule:

    certify child internals -> contract them to one boundary -> project parent

Raw graph flattening is intentionally not used because child-local roles must not
be interpreted as parent-local roles.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Optional, Sequence, Tuple

from ..state import canonical_json
from .contract import ParentContract
from .graph import RealizationGraph, RealizationNode
from .projection import project_semantics


@dataclass(frozen=True)
class BoundaryProjection:
    """Parent-visible O/D/A/E/T/R/F projection of one governed boundary."""

    contract_id: str
    visible_outputs: Tuple[str, ...]
    outputs_satisfied: bool
    causal_satisfied: bool
    authority_satisfied: bool
    evidence_satisfied: bool
    temporal_satisfied: bool
    resource_satisfied: bool
    failure_satisfied: bool
    conforms: bool
    violations: Tuple[str, ...] = ()
    projection_hash: str = ""

    def __post_init__(self) -> None:
        if not self.projection_hash:
            payload = {
                "contract_id": self.contract_id,
                "visible_outputs": sorted(self.visible_outputs),
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

    def compute_hash(self) -> str:
        return self.projection_hash


@dataclass(frozen=True)
class CompositionBoundaryCertificate:
    """Conformance certificate for a recursively composable UoW surface.

    The certificate binds the subject to its contract and exported projection.
    It deliberately does not bind one internal graph hash. Equivalent internal
    realizations may therefore change without requiring parent recertification.
    """

    certificate_id: str
    subject_id: str
    contract_hash: str
    projection_hash: str
    accepted: bool
    violations: Tuple[str, ...] = ()
    certifier_id: str = "composition-boundary-certifier"
    certificate_hash: str = ""

    def __post_init__(self) -> None:
        if not self.certificate_hash:
            payload = {
                "certificate_id": self.certificate_id,
                "subject_id": self.subject_id,
                "contract_hash": self.contract_hash,
                "projection_hash": self.projection_hash,
                "accepted": self.accepted,
                "violations": sorted(self.violations),
                "certifier_id": self.certifier_id,
            }
            digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
            object.__setattr__(self, "certificate_hash", digest)

    @property
    def is_accepted(self) -> bool:
        return self.accepted

    def compute_hash(self) -> str:
        return self.certificate_hash


def project_boundary(
    graph: RealizationGraph,
    contract: ParentContract,
) -> BoundaryProjection:
    """Project a realization onto only the semantics exported by its contract."""
    projection = project_semantics(graph, contract)
    visible_outputs = tuple(
        sorted(set(projection.outputs).intersection(contract.required_outputs))
    )
    return BoundaryProjection(
        contract_id=contract.contract_id,
        visible_outputs=visible_outputs,
        outputs_satisfied=projection.outputs_satisfied,
        causal_satisfied=projection.causal_satisfied,
        authority_satisfied=projection.authority_satisfied,
        evidence_satisfied=projection.evidence_satisfied,
        temporal_satisfied=projection.temporal_satisfied,
        resource_satisfied=projection.resource_satisfied,
        failure_satisfied=projection.failure_satisfied,
        conforms=projection.conforms,
        violations=projection.violations,
    )


def certify_composition_boundary(
    subject_id: str,
    graph: RealizationGraph,
    contract: ParentContract,
    *,
    certifier_id: str = "composition-boundary-certifier",
) -> CompositionBoundaryCertificate:
    """Issue a pure conformance attestation for a recursive composition surface."""
    projection = project_boundary(graph, contract)
    return CompositionBoundaryCertificate(
        certificate_id=f"boundary::{subject_id}::{contract.contract_id}",
        subject_id=subject_id,
        contract_hash=contract.compute_hash(),
        projection_hash=projection.compute_hash(),
        accepted=projection.conforms,
        violations=projection.violations,
        certifier_id=certifier_id,
    )


def verify_composition_boundary(
    certificate: CompositionBoundaryCertificate,
    graph: RealizationGraph,
    contract: ParentContract,
) -> Tuple[bool, Tuple[str, ...]]:
    """Recompute a boundary and verify it still matches its certificate."""
    violations = []
    if not certificate.is_accepted:
        violations.append("BOUNDARY_CERTIFICATE_REJECTED")
    if certificate.contract_hash != contract.compute_hash():
        violations.append("BOUNDARY_CONTRACT_HASH_MISMATCH")

    projection = project_boundary(graph, contract)
    if not projection.conforms:
        violations.extend(projection.violations)
    if projection.compute_hash() != certificate.projection_hash:
        violations.append("BOUNDARY_PROJECTION_DRIFT")

    return len(violations) == 0, tuple(violations)


def boundary_equivalent(
    graph_a: RealizationGraph,
    graph_b: RealizationGraph,
    contract: ParentContract,
) -> bool:
    """Return whether two same-scope realizations export the same boundary."""
    a = project_boundary(graph_a, contract)
    b = project_boundary(graph_b, contract)
    return a.conforms and b.conforms and a.compute_hash() == b.compute_hash()


def contract_scope(
    graph: RealizationGraph,
    *,
    scope_node_ids: Sequence[str],
    replacement_node: RealizationNode,
    graph_id: Optional[str] = None,
) -> RealizationGraph:
    """Contract a child scope to one parent-visible logical actor node.

    Incoming parent edges terminate at the replacement node. Outgoing parent
    edges originate from it. All child-internal topology, roles and output names
    are hidden from the parent semantic projection.
    """
    scope = set(scope_node_ids)
    if not scope:
        raise ValueError("scope_node_ids must not be empty")

    missing = scope - set(graph.nodes)
    if missing:
        raise ValueError(f"Unknown scope nodes: {sorted(missing)}")

    if (
        replacement_node.node_id in graph.nodes
        and replacement_node.node_id not in scope
    ):
        raise ValueError("Replacement node id conflicts with an external node")

    nodes = {
        node_id: node
        for node_id, node in graph.nodes.items()
        if node_id not in scope
    }
    nodes[replacement_node.node_id] = replacement_node

    edges = set()
    for src, dst in graph.edges:
        src_inside = src in scope
        dst_inside = dst in scope

        if src_inside and dst_inside:
            continue
        if not src_inside and dst_inside:
            edges.add((src, replacement_node.node_id))
        elif src_inside and not dst_inside:
            edges.add((replacement_node.node_id, dst))
        else:
            edges.add((src, dst))

    edges.discard((replacement_node.node_id, replacement_node.node_id))
    return RealizationGraph(
        graph_id=graph_id or f"{graph.graph_id}:contracted",
        nodes=nodes,
        edges=tuple(sorted(edges)),
    )


__all__ = [
    "BoundaryProjection",
    "CompositionBoundaryCertificate",
    "boundary_equivalent",
    "certify_composition_boundary",
    "contract_scope",
    "project_boundary",
    "verify_composition_boundary",
]
