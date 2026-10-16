"""Capability Resolution Engine for matching work requirements to domain specifications."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from src.uow.expertise.specification import ExpertiseSpecification


class CapabilityResolver:
    """Resolves matching domain specifications and authority constraints."""

    def __init__(self) -> None:
        self._specs: dict[str, ExpertiseSpecification] = {}

    def register_spec(self, spec: ExpertiseSpecification) -> None:
        key = f"{spec.domain.lower()}.{spec.grammar.lower()}"
        self._specs[key] = spec

    def resolve(self, domain: str, grammar: str) -> Optional[ExpertiseSpecification]:
        key = f"{domain.lower()}.{grammar.lower()}"
        return self._specs.get(key)

    def is_action_allowed(self, domain: str, grammar: str, action: str) -> bool:
        spec = self.resolve(domain, grammar)
        if not spec:
            return False
        return any(op.name.upper() == action.upper() for op in spec.operations)
