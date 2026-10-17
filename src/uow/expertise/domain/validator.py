"""Authoritative Domain Grounding Validator (WP04).

Independently validates candidate proposal actions, parameter bindings,
and entity identifiers against authoritative domain packages.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .models import DomainPackage, SafetyGuard


@dataclass
class GroundingValidationResult:
    """Result of domain grounding verification."""
    is_valid: bool
    grounding_violations: List[str] = field(default_factory=list)
    safety_violations: List[str] = field(default_factory=list)
    resolved_bindings: Dict[str, Any] = field(default_factory=dict)


class DomainGroundingValidator:
    """Validates proposals against domain knowledge without model assistance."""

    def __init__(self, domain_package: DomainPackage) -> None:
        self.domain = domain_package

    def validate(
        self,
        proposed_action: str,
        bindings: Dict[str, Any],
    ) -> GroundingValidationResult:
        """Validate candidate proposal action and bindings against domain ontology."""
        violations: List[str] = []
        safety_violations: List[str] = []
        resolved = dict(bindings)

        # 1. Action catalog verification
        action_def = self.domain.actions.get(proposed_action)
        if not action_def:
            violations.append(
                f"Proposed action '{proposed_action}' is not in authoritative action catalog for {self.domain.domain_id}."
            )
            return GroundingValidationResult(is_valid=False, grounding_violations=violations)

        # 2. Required parameter check
        for param in action_def.required_parameters:
            if param not in bindings:
                violations.append(f"Missing required parameter '{param}' for action '{proposed_action}'.")

        # 3. Entity grounding check
        # Search for entity parameters (keys ending in _id, e.g. pump_id, equipment_id, node_id, asset_id)
        for k, v in bindings.items():
            if isinstance(v, str) and (k.endswith("_id") or k in ("target", "entity", "equipment", "asset")):
                canonical_id = self.domain.resolve_entity(v)
                if not canonical_id:
                    violations.append(
                        f"Fabricated or ungrounded entity identifier '{v}' in parameter '{k}' (not registered in {self.domain.domain_id})."
                    )
                else:
                    resolved[k] = canonical_id

        # 4. Safety guards check
        for guard in action_def.safety_guards:
            val = bindings.get(guard.parameter)
            if val is not None and isinstance(val, (int, float)):
                if guard.condition.startswith("max_value:"):
                    threshold = float(guard.threshold)
                    if float(val) > threshold:
                        safety_violations.append(
                            f"Safety guard '{guard.guard_id}' violated: parameter '{guard.parameter}' value {val} exceeds ceiling {threshold}."
                        )
                elif guard.condition.startswith("min_value:"):
                    threshold = float(guard.threshold)
                    if float(val) < threshold:
                        safety_violations.append(
                            f"Safety guard '{guard.guard_id}' violated: parameter '{guard.parameter}' value {val} below floor {threshold}."
                        )

        is_valid = len(violations) == 0 and len(safety_violations) == 0
        return GroundingValidationResult(
            is_valid=is_valid,
            grounding_violations=violations,
            safety_violations=safety_violations,
            resolved_bindings=resolved,
        )
