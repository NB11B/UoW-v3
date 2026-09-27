"""Deterministic semantic admissibility validation before YES disposition."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .schema import BindingOrigin, SemanticAlternative, SemanticBinding, SemanticRequirement
from ..state import WorldState


class ValidationVerdict(str, Enum):
    """Admissibility classification for semantic candidate bindings."""

    VALID = "VALID"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"
    CONTRADICTORY = "CONTRADICTORY"


@dataclass(frozen=True)
class BindingValidationResult:
    """Result of evaluating one candidate semantic binding against authoritative state."""

    verdict: ValidationVerdict
    terminal: str
    reasons: tuple[str, ...] = ()
    admissible_alternatives: tuple[Any, ...] = ()


@runtime_checkable
class SemanticBindingValidator(Protocol):
    """Protocol for domain-specific deterministic semantic validation."""

    def validate(
        self,
        binding: SemanticBinding,
        requirement: SemanticRequirement,
        state: WorldState,
    ) -> BindingValidationResult:
        ...


class DefaultSemanticAdmissibilityValidator:
    """Production admissibility validator enforcing capability, entity, and domain invariants."""

    def __init__(
        self,
        *,
        registered_operators: Sequence[str] | None = None,
        entity_directory: dict[str, Sequence[str]] | None = None,
        max_quantity: int = 10000,
    ) -> None:
        self.registered_operators = set(
            registered_operators
            if registered_operators is not None
            else (
                "transfer",
                "dispatch",
                "convey",
                "allocate",
                "consign",
                "quarantine",
                "procure",
                "purge",
                "disgorge",
                "inspect",
                "reassign",
                "return",
                "route",
                "verify_checksum",
                "query_transfer",
                "query_delivery",
                "query_status",
                "query_dispatch",
                "query_lock_status",
            )
        )
        self.entity_directory = {k: list(v) for k, v in (entity_directory or {}).items()}
        self.max_quantity = max_quantity

    def validate(
        self,
        binding: SemanticBinding,
        requirement: SemanticRequirement,
        state: WorldState,
    ) -> BindingValidationResult:
        terminal = binding.terminal
        val = binding.value

        # 1. Operators & Capabilities check against registered capability catalog
        if terminal in ("operator", "operation", "semantic_head"):
            str_val = str(val).lower() if isinstance(val, str) else ""
            if not str_val or str_val not in self.registered_operators:
                return BindingValidationResult(
                    verdict=ValidationVerdict.UNKNOWN,
                    terminal=terminal,
                    reasons=(f"UNREGISTERED_OPERATOR:{val}",),
                )
            return BindingValidationResult(verdict=ValidationVerdict.VALID, terminal=terminal)

        # 2. Quantities & Domain Limits check
        if terminal in ("quantity", "amount", "count"):
            if isinstance(val, (int, float)):
                if val <= 0:
                    return BindingValidationResult(
                        verdict=ValidationVerdict.CONTRADICTORY,
                        terminal=terminal,
                        reasons=("NEGATIVE_OR_ZERO_QUANTITY",),
                    )
                if val > self.max_quantity:
                    return BindingValidationResult(
                        verdict=ValidationVerdict.CONTRADICTORY,
                        terminal=terminal,
                        reasons=(f"QUANTITY_EXCEEDS_MAX:{val}>{self.max_quantity}",),
                    )
                return BindingValidationResult(verdict=ValidationVerdict.VALID, terminal=terminal)
            elif isinstance(val, str) and val.upper() in ("ALL", "UNIVERSAL"):
                return BindingValidationResult(verdict=ValidationVerdict.VALID, terminal=terminal)
            else:
                return BindingValidationResult(
                    verdict=ValidationVerdict.UNKNOWN,
                    terminal=terminal,
                    reasons=(f"INVALID_QUANTITY_FORMAT:{val}",),
                )

        # 3. Entity Resolution against WorldState and Entity Directory
        if terminal in ("recipient", "actor", "destination", "item", "target"):
            str_val = str(val)
            candidates = None
            # Check state entities dict first if present
            entities_in_state = state.attributes.get("entities", {})
            if isinstance(entities_in_state, Mapping) and terminal in entities_in_state:
                candidates = entities_in_state[terminal]
            elif terminal in self.entity_directory:
                candidates = self.entity_directory[terminal]

            if candidates is not None:
                matches = [c for c in candidates if str_val.lower() == str(c).lower()]
                if not matches:
                    matches = [c for c in candidates if str_val.lower() in str(c).lower()]

                if len(matches) == 0:
                    return BindingValidationResult(
                        verdict=ValidationVerdict.UNKNOWN,
                        terminal=terminal,
                        reasons=(f"UNRESOLVED_ENTITY:{val}",),
                    )
                elif len(matches) > 1:
                    return BindingValidationResult(
                        verdict=ValidationVerdict.AMBIGUOUS,
                        terminal=terminal,
                        reasons=(f"AMBIGUOUS_ENTITY:{val}",),
                        admissible_alternatives=tuple(matches),
                    )
                return BindingValidationResult(verdict=ValidationVerdict.VALID, terminal=terminal)

        return BindingValidationResult(verdict=ValidationVerdict.VALID, terminal=terminal)
