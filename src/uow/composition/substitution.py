"""Graph substitution protocols and runtime certification boundary for Campaign A2.

This module provides the pure authoritative certification boundary for candidate
realization graph replacements. An adaptive or external proposer may propose alternative
execution graphs, but ZERO structural changes are applied without an authoritative
GraphReplacementCertificate proving Phi(G_cand, U) == Phi(G_orig, U).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Optional, Tuple

from uow.composition.actor import ActorRegistry
from uow.composition.binding import ActorBinding, validate_binding
from uow.composition.contract import ParentContract
from uow.composition.graph import RealizationGraph
from uow.composition.projection import (
    SemanticProjection,
    are_equivalent,
    check_conformance,
    project_semantics,
)


class SubstitutionStrategy(str, Enum):
    PARALLEL_DECOMPOSITION = "parallel_decomposition"
    ACCELERATOR_OFFLOAD = "accelerator_offload"
    DISTRIBUTED_QUORUM = "distributed_quorum"
    SPECULATIVE_PIPELINE = "speculative_pipeline"
    FALLBACK_BASELINE = "fallback_baseline"


class SubstitutionDecision(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class GraphReplacementProposal:
    """Proposal from an adaptive or external engine to replace the active realization graph."""

    parent_contract_id: str
    current_graph_hash: str
    candidate_graph: RealizationGraph
    strategy: SubstitutionStrategy
    predicted_speedup: float = 1.0
    rationale: str = ""
    proposal_id: str = ""
    actor_binding: Optional[ActorBinding] = None

    def compute_hash(self) -> str:
        payload = {
            "proposal_id": self.proposal_id,
            "parent_contract_id": self.parent_contract_id,
            "current_graph_hash": self.current_graph_hash,
            "candidate_graph_hash": self.candidate_graph.compute_hash(),
            "strategy": self.strategy.value,
            "predicted_speedup": f"{self.predicted_speedup:.4f}",
            "rationale": self.rationale,
            "actor_binding_hash": self.actor_binding.compute_hash() if self.actor_binding else "",
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class GraphReplacementCertificate:
    """Cryptographic certificate issued by the CompositionCertifier upon evaluating a proposal."""

    certificate_id: str
    proposal_hash: str
    parent_contract_hash: str
    original_graph_hash: str
    candidate_graph_hash: str
    projection_hash: str
    decision: SubstitutionDecision
    violations: Tuple[str, ...] = ()
    epoch: int = 1
    actor_binding_hash: str = ""
    certifier_id: str = "authoritative_composition_certifier"
    timestamp_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def compute_hash(self) -> str:
        payload = {
            "certificate_id": self.certificate_id,
            "proposal_hash": self.proposal_hash,
            "parent_contract_hash": self.parent_contract_hash,
            "original_graph_hash": self.original_graph_hash,
            "candidate_graph_hash": self.candidate_graph_hash,
            "projection_hash": self.projection_hash,
            "decision": self.decision.value,
            "violations": sorted(self.violations),
            "epoch": self.epoch,
            "actor_binding_hash": self.actor_binding_hash,
            "certifier_id": self.certifier_id,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @property
    def is_accepted(self) -> bool:
        return self.decision == SubstitutionDecision.ACCEPTED


class CompositionCertifier:
    """Pure deterministic Judge that evaluates candidate realization graph proposals against parent contract U."""

    def __init__(self, certifier_id: str = "composition_judge_authoritative") -> None:
        self.certifier_id = certifier_id

    def certify_proposal(
        self,
        proposal: GraphReplacementProposal,
        original_graph: RealizationGraph,
        contract: ParentContract,
        current_epoch: int = 1,
        actor_registry: Optional[ActorRegistry] = None,
    ) -> GraphReplacementCertificate:
        """Evaluates a graph replacement proposal and issues an authoritative certificate."""
        violations = []

        # 1. Verify parent contract identity
        if proposal.parent_contract_id != contract.contract_id:
            violations.append(
                f"CONTRACT_ID_MISMATCH: proposal={proposal.parent_contract_id} contract={contract.contract_id}"
            )

        # 2. Verify current graph state binding (anti-stale proposal check)
        orig_hash = original_graph.compute_hash()
        if proposal.current_graph_hash != orig_hash:
            violations.append(
                f"STALE_CURRENT_GRAPH_HASH: proposal specifies {proposal.current_graph_hash} but active is {orig_hash}"
            )

        # 3. Verify acyclic topology
        cand_graph = proposal.candidate_graph
        if not cand_graph.validate_acyclic():
            violations.append("CANDIDATE_GRAPH_CYCLIC")

        # 4. Evaluate semantic projection & conformance
        cand_proj: SemanticProjection | None = None
        if "CANDIDATE_GRAPH_CYCLIC" not in violations:
            cand_proj = project_semantics(cand_graph, contract)
            if not cand_proj.conforms:
                violations.extend(cand_proj.violations)

            # 5. Evaluate semantic equivalence with original graph
            orig_proj = project_semantics(original_graph, contract)
            if not orig_proj.conforms:
                violations.append("ORIGINAL_GRAPH_NON_CONFORMING")
            elif cand_proj.conforms and cand_proj.projection_hash != orig_proj.projection_hash:
                violations.append("SEMANTIC_EQUIVALENCE_FAILED: projection hash mismatch")

        # 6. Evaluate actor binding if provided
        if proposal.actor_binding is not None:
            if actor_registry is not None:
                valid_binding, bind_violations = validate_binding(
                    cand_graph, proposal.actor_binding, actor_registry
                )
                if not valid_binding:
                    violations.extend(bind_violations)
            else:
                violations.append("NO_ACTOR_REGISTRY_FOR_BINDING_VALIDATION")

        # Decision
        if violations:
            decision = SubstitutionDecision.REJECTED
            proj_hash = cand_proj.projection_hash if cand_proj else ""
        else:
            decision = SubstitutionDecision.ACCEPTED
            assert cand_proj is not None
            proj_hash = cand_proj.projection_hash

        binding_hash = proposal.actor_binding.compute_hash() if proposal.actor_binding else ""
        cert_id = f"cert_{proposal.proposal_id or 'anon'}_e{current_epoch}"
        return GraphReplacementCertificate(
            certificate_id=cert_id,
            proposal_hash=proposal.compute_hash(),
            parent_contract_hash=contract.contract_hash,
            original_graph_hash=orig_hash,
            candidate_graph_hash=cand_graph.compute_hash(),
            projection_hash=proj_hash,
            decision=decision,
            violations=tuple(violations),
            epoch=current_epoch,
            actor_binding_hash=binding_hash,
            certifier_id=self.certifier_id,
        )
