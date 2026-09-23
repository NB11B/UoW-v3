"""A2: Adaptive Composition Runtime package.

Provides formal tools to separate parent semantic intent from execution topology:
  U = ParentContract(O, D, A, E, T, R, F)
  G = RealizationGraph(V, E)
  Phi(G, U) = SemanticProjection
"""
from .contract import (
    AuthorityObligation,
    CausalConstraint,
    EvidenceObligation,
    FailureSemantics,
    ParentContract,
    ResourceConstraint,
    TemporalConstraint,
)
from .graph import RealizationGraph, RealizationNode
from .projection import (
    SemanticProjection,
    are_equivalent,
    check_conformance,
    project_semantics,
)

__all__ = [
    "AuthorityObligation",
    "CausalConstraint",
    "EvidenceObligation",
    "FailureSemantics",
    "ParentContract",
    "RealizationGraph",
    "RealizationNode",
    "ResourceConstraint",
    "SemanticProjection",
    "TemporalConstraint",
    "are_equivalent",
    "check_conformance",
    "project_semantics",
]
