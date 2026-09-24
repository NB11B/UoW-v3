"""Typed conformance registry and normalized result envelopes."""

from .registry import (
    ConformanceDomain,
    ConformanceRegistry,
    DEFAULT_CONFORMANCE_REGISTRY,
    MatcherKind,
    build_default_registry,
)
from .types import ConformanceDecision, ConformanceResult

__all__ = [
    "ConformanceDecision",
    "ConformanceDomain",
    "ConformanceRegistry",
    "ConformanceResult",
    "DEFAULT_CONFORMANCE_REGISTRY",
    "MatcherKind",
    "build_default_registry",
]
