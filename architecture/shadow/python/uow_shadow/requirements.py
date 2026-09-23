"""Typed requirement/capability shadow matcher for R3."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Optional, Sequence

from .types import ConformanceDecision, ConformanceResult
from .identity import shadow_identity


class MatcherKind(str, Enum):
    SET_INCLUSION = "SET_INCLUSION"
    ORDERED_LATTICE = "ORDERED_LATTICE"
    QUANTITATIVE_MINIMUM = "QUANTITATIVE_MINIMUM"
    QUANTITATIVE_MAXIMUM = "QUANTITATIVE_MAXIMUM"
    RELATIONAL_COMPATIBILITY = "RELATIONAL_COMPATIBILITY"
    QUALIFIED_CAPABILITY = "QUALIFIED_CAPABILITY"
    FRESH_CAPABILITY = "FRESH_CAPABILITY"
    QUORUM_K_OF_N = "QUORUM_K_OF_N"
    ONE_OF = "ONE_OF"
    CONDITIONAL = "CONDITIONAL"


@dataclass(frozen=True)
class Requirement:
    requirement_id: str
    kind: str
    matcher: MatcherKind
    expected: Any
    evidence_requirement: Optional[str] = None
    freshness_requirement: Optional[Any] = None
    failure_requirement: Optional[str] = None
    predicate: Optional[Callable[[Any, "Capability", "MatchContext"], bool]] = None


@dataclass(frozen=True)
class Capability:
    capability_id: str
    kind: str
    offered_value: Any
    source_id: str
    qualification: Optional[Any] = None
    freshness: Optional[Any] = None
    evidence: Optional[Any] = None


@dataclass(frozen=True)
class MatchContext:
    context_id: str
    now: Optional[float] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


def _rank(order: Sequence[Any], value: Any) -> int:
    try:
        return list(order).index(value)
    except ValueError:
        return -1


def match_requirement(
    requirement: Requirement,
    capability: Capability,
    context: MatchContext,
) -> ConformanceResult:
    violations = []

    if requirement.kind != capability.kind:
        violations.append(
            f"KIND_MISMATCH: required {requirement.kind!r}, offered {capability.kind!r}"
        )
    else:
        m = requirement.matcher
        expected = requirement.expected
        offered = capability.offered_value

        if m is MatcherKind.SET_INCLUSION:
            if not set(expected).issubset(set(offered)):
                violations.append("SET_INCLUSION_FAILED")

        elif m is MatcherKind.ORDERED_LATTICE:
            order = context.metadata.get("order", ())
            if _rank(order, offered) < _rank(order, expected):
                violations.append("ORDERED_LATTICE_FAILED")

        elif m is MatcherKind.QUANTITATIVE_MINIMUM:
            if offered < expected:
                violations.append("QUANTITATIVE_MINIMUM_FAILED")

        elif m is MatcherKind.QUANTITATIVE_MAXIMUM:
            if offered > expected:
                violations.append("QUANTITATIVE_MAXIMUM_FAILED")

        elif m is MatcherKind.QUALIFIED_CAPABILITY:
            if capability.qualification != expected:
                violations.append("QUALIFICATION_FAILED")

        elif m is MatcherKind.FRESH_CAPABILITY:
            if context.now is None:
                violations.append("FRESHNESS_CONTEXT_MISSING")
            elif capability.freshness is None or float(capability.freshness) < float(context.now):
                violations.append("FRESHNESS_FAILED")

        elif m is MatcherKind.QUORUM_K_OF_N:
            threshold = int(expected)
            voters = tuple(offered)
            if len(set(voters)) < threshold:
                violations.append("QUORUM_K_OF_N_FAILED")

        elif m is MatcherKind.ONE_OF:
            if offered not in set(expected):
                violations.append("ONE_OF_FAILED")

        elif m in (MatcherKind.RELATIONAL_COMPATIBILITY, MatcherKind.CONDITIONAL):
            if requirement.predicate is None:
                violations.append("RELATIONAL_PREDICATE_MISSING")
            elif not bool(requirement.predicate(offered, capability, context)):
                violations.append("RELATIONAL_PREDICATE_FAILED")

        else:
            violations.append(f"UNSUPPORTED_MATCHER:{m.value}")

    decision = ConformanceDecision.ACCEPT if not violations else ConformanceDecision.REJECT
    cid = shadow_identity(
        "requirement-match",
        {
            "requirement_id": requirement.requirement_id,
            "capability_id": capability.capability_id,
            "context_id": context.context_id,
            "decision": decision.value,
            "violations": violations,
        },
    )
    return ConformanceResult(
        conformance_id=cid,
        subject_id=capability.capability_id,
        contract_id=requirement.requirement_id,
        context_id=context.context_id,
        decision=decision,
        violations=tuple(violations),
        evidence={
            "matcher": requirement.matcher.value,
            "source_id": capability.source_id,
        },
        source_validator="uow_shadow.requirements.match_requirement",
    )
