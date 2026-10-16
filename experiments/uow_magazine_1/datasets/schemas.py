"""Typed Schemas and Codecs for UoW-MAGAZINE-1 (Operational, Temporal, Recovery)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from typing import Any, Dict, List, Optional, Tuple


# --- 1. Operational Grammar (uow.operational.v1) ---
@dataclass(frozen=True)
class OperationalProposal:
    domain: str
    action: str
    disposition: str  # COMMIT, ROLLBACK, HALT
    parameters: dict[str, Any] = field(default_factory=dict)
    guard_conditions: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "action": self.action,
            "disposition": self.disposition,
            "parameters": self.parameters,
            "guard_conditions": self.guard_conditions,
            "unknowns": self.unknowns,
        }


# --- 2. Temporal Grammar (uow.temporal.v1) ---
@dataclass(frozen=True)
class TemporalConstraint:
    domain: str
    target_action: str
    relation: str  # IMMEDIATE, AFTER, BEFORE, BETWEEN, CONCURRENT
    reference_event: Optional[str] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    deadline: Optional[str] = None
    duration_seconds: Optional[int] = None
    unknowns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "domain": self.domain,
            "target_action": self.target_action,
            "relation": self.relation,
        }
        if self.reference_event is not None:
            d["reference_event"] = self.reference_event
        if self.window_start is not None or self.window_end is not None:
            d["window"] = {"start": self.window_start, "end": self.window_end}
        if self.deadline is not None:
            d["deadline"] = self.deadline
        if self.duration_seconds is not None:
            d["duration_seconds"] = self.duration_seconds
        if self.unknowns:
            d["unknowns"] = self.unknowns
        return d


# --- 3. Recovery Grammar (uow.recovery.v1) ---
@dataclass(frozen=True)
class RecoveryStrategy:
    domain: str
    failure_mode: str
    strategy: str  # IMMEDIATE_RETRY, CIRCUIT_BREAK, ROLLBACK_COMPENSATE, EXPONENTIAL_BACKOFF, ESCALATE_OPERATOR
    max_attempts: int = 1
    backoff_seconds: Optional[int] = None
    compensation_action: Optional[str] = None
    idempotency_required: bool = True
    unknowns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "domain": self.domain,
            "failure_mode": self.failure_mode,
            "strategy": self.strategy,
            "max_attempts": self.max_attempts,
            "idempotency_required": self.idempotency_required,
        }
        if self.backoff_seconds is not None:
            d["backoff_seconds"] = self.backoff_seconds
        if self.compensation_action is not None:
            d["compensation_action"] = self.compensation_action
        if self.unknowns:
            d["unknowns"] = self.unknowns
        return d


class JsonCodec:
    """Robust extractor and validator for LLM structured output."""

    @classmethod
    def extract_json(cls, raw: str) -> Optional[dict[str, Any]]:
        cleaned = raw.strip()
        if "```json" in cleaned:
            parts = cleaned.split("```json")
            if len(parts) > 1:
                cleaned = parts[1].split("```")[0].strip()
        elif "```" in cleaned:
            parts = cleaned.split("```")
            if len(parts) > 1:
                cleaned = parts[1].strip()

        # Direct parse attempt
        try:
            val = json.loads(cleaned)
            if isinstance(val, dict):
                return val
        except Exception:
            pass

        # Regex scan for curly braced object
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                val = json.loads(match.group(0))
                if isinstance(val, dict):
                    return val
            except Exception:
                pass

        # Partial repair: if starts with '{', attempt to balance open braces/brackets
        if "{" in cleaned:
            start_idx = cleaned.find("{")
            candidate = cleaned[start_idx:]
            # Strip trailing incomplete quote or key
            candidate = candidate.rstrip(", \t\n")
            if candidate.count('"') % 2 != 0:
                candidate += '"'
            open_braces = candidate.count("{") - candidate.count("}")
            open_brackets = candidate.count("[") - candidate.count("]")
            if open_brackets > 0:
                candidate += "]" * open_brackets
            if open_braces > 0:
                candidate += "}" * open_braces
            try:
                val = json.loads(candidate)
                if isinstance(val, dict):
                    return val
            except Exception:
                pass

        return None
