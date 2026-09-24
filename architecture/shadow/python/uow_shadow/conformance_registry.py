"""R6 prototype: typed domain conformance registry.

The registry unifies *invocation shape* and semantic metadata while preserving
the existing specialized validators as authoritative predicates.

It intentionally does not flatten resource inequalities, OCC relational
compatibility, authority qualification, freshness, evidence, or failure
semantics into generic key/value matching.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Tuple

from .adapters import (
    actor_binding_adapter,
    delegation_adapter,
    effect_receipt_adapter,
    mutation_qc_adapter,
    mutation_vote_adapter,
    occ_adapter,
    resource_binding_adapter,
    resource_capacity_adapter,
    semantic_projection_adapter,
)
from .requirements import MatcherKind
from .types import ConformanceResult


Adapter = Callable[..., ConformanceResult]


@dataclass(frozen=True)
class ConformanceDomain:
    domain_id: str
    matcher_kind: MatcherKind
    adapter: Adapter
    semantic_inputs: Tuple[str, ...]
    preserves_specialized_predicate: bool = True
    notes: str = ""


class ConformanceRegistry:
    def __init__(self) -> None:
        self._domains: Dict[str, ConformanceDomain] = {}

    def register(self, domain: ConformanceDomain) -> None:
        if domain.domain_id in self._domains:
            raise ValueError(f"Conformance domain {domain.domain_id!r} already registered.")
        self._domains[domain.domain_id] = domain

    def get(self, domain_id: str) -> ConformanceDomain:
        try:
            return self._domains[domain_id]
        except KeyError as exc:
            raise KeyError(f"Unknown conformance domain {domain_id!r}.") from exc

    def evaluate(self, domain_id: str, /, *args: Any, **kwargs: Any) -> ConformanceResult:
        domain = self.get(domain_id)
        result = domain.adapter(*args, **kwargs)
        if not isinstance(result, ConformanceResult):
            raise TypeError(
                f"Conformance adapter {domain_id!r} returned {type(result)!r}, "
                "expected ConformanceResult."
            )
        return result

    def domains(self) -> Tuple[ConformanceDomain, ...]:
        return tuple(self._domains[k] for k in sorted(self._domains))

    def manifest(self) -> Mapping[str, Mapping[str, Any]]:
        return {
            domain.domain_id: {
                "matcher_kind": domain.matcher_kind.value,
                "semantic_inputs": domain.semantic_inputs,
                "preserves_specialized_predicate": domain.preserves_specialized_predicate,
                "source_validator": domain.notes,
            }
            for domain in self.domains()
        }


def build_default_registry() -> ConformanceRegistry:
    registry = ConformanceRegistry()
    for domain in (
        ConformanceDomain(
            "resource_capacity",
            MatcherKind.QUANTITATIVE_MINIMUM,
            resource_capacity_adapter,
            ("ResourceRequirement", "ResourceState"),
            notes="ResourceState.can_accommodate",
        ),
        ConformanceDomain(
            "resource_binding",
            MatcherKind.QUALIFIED_CAPABILITY,
            resource_binding_adapter,
            ("ResourceBoundTask",),
            notes="verify_requirement_binding",
        ),
        ConformanceDomain(
            "occ_compatibility",
            MatcherKind.RELATIONAL_COMPATIBILITY,
            occ_adapter,
            ("WorldState", "TransactionDescriptor"),
            notes="validate_occ",
        ),
        ConformanceDomain(
            "actor_binding",
            MatcherKind.QUALIFIED_CAPABILITY,
            actor_binding_adapter,
            ("RealizationGraph", "ActorBinding", "ActorRegistry"),
            notes="validate_binding",
        ),
        ConformanceDomain(
            "semantic_projection",
            MatcherKind.RELATIONAL_COMPATIBILITY,
            semantic_projection_adapter,
            ("RealizationGraph", "ParentContract"),
            notes="project_semantics",
        ),
        ConformanceDomain(
            "delegation",
            MatcherKind.QUALIFIED_CAPABILITY,
            delegation_adapter,
            ("AuthorityScope", "DelegationCertificate"),
            notes="validate_delegation",
        ),
        ConformanceDomain(
            "external_receipt",
            MatcherKind.QUALIFIED_CAPABILITY,
            effect_receipt_adapter,
            ("EffectDescriptor", "EffectReceipt"),
            notes="verify_effect_receipt_binding",
        ),
        ConformanceDomain(
            "mutation_vote",
            MatcherKind.QUALIFIED_CAPABILITY,
            mutation_vote_adapter,
            ("AuthorityMutationVote", "secret_key"),
            notes="verify_mutation_vote",
        ),
        ConformanceDomain(
            "mutation_qc",
            MatcherKind.QUORUM_K_OF_N,
            mutation_qc_adapter,
            (
                "RuntimeMutationQC",
                "ParentContract",
                "history_head",
                "generation",
                "authority_keys",
            ),
            notes="verify_mutation_qc",
        ),
    ):
        registry.register(domain)
    return registry


DEFAULT_CONFORMANCE_REGISTRY = build_default_registry()
