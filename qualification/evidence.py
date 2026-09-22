"""Shared qualification evidence contract.

A capability may be *observed* in a simulator or portable fallback, but it may
only be reported as qualified when the evidence substrate required by the claim
was actually exercised.

This module intentionally separates:
- observed_pass: did the tested logic behave as expected?
- qualified: did the run exercise the required real substrate/components?
- passed: observed_pass AND qualified

Mocks and substitutions are useful tests. They are never physical evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import IntEnum
from typing import Any, Mapping


class EvidenceLevel(IntEnum):
    SIMULATED = 0
    PORTABLE = 1
    PHYSICAL = 2

    @property
    def label(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class EvidenceContext:
    level: EvidenceLevel
    source: str
    actual_components: Mapping[str, str] = field(default_factory=dict)
    substitutions: Mapping[str, str] = field(default_factory=dict)

    def has_actual(self, component: str) -> bool:
        return component in self.actual_components and component not in self.substitutions

    def satisfies(
        self,
        required_level: EvidenceLevel,
        required_components: tuple[str, ...] = (),
    ) -> bool:
        return (
            self.level >= required_level
            and all(self.has_actual(component) for component in required_components)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.label,
            "source": self.source,
            "actual_components": dict(self.actual_components),
            "substitutions": dict(self.substitutions),
        }


@dataclass(frozen=True)
class ClaimRequirement:
    required_level: EvidenceLevel
    required_components: tuple[str, ...] = ()


def evaluate_claim(
    observed_pass: bool,
    context: EvidenceContext,
    requirement: ClaimRequirement,
    **details: Any,
) -> dict[str, Any]:
    """Return a gate result that cannot confuse simulation with qualification."""
    qualified = context.satisfies(
        requirement.required_level,
        requirement.required_components,
    )
    result = {
        "observed_pass": bool(observed_pass),
        "qualified": bool(qualified),
        "passed": bool(observed_pass and qualified),
        "evidence_level": context.level.label,
        "required_evidence_level": requirement.required_level.label,
        "required_components": list(requirement.required_components),
    }
    result.update(details)
    if observed_pass and not qualified:
        result["qualification_blocked_reason"] = (
            "logic observed, but required evidence substrate/components were not exercised"
        )
    return result


def combine_contexts(*contexts: EvidenceContext, source: str) -> EvidenceContext:
    """Combine component attestations; the weakest evidence level dominates."""
    if not contexts:
        return EvidenceContext(EvidenceLevel.SIMULATED, source)
    level = min(context.level for context in contexts)
    actual: dict[str, str] = {}
    substitutions: dict[str, str] = {}
    for context in contexts:
        actual.update(context.actual_components)
        substitutions.update(context.substitutions)
    return EvidenceContext(level, source, actual, substitutions)
