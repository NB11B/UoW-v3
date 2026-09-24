"""Typed conformance result envelope."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Tuple


class ConformanceDecision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


@dataclass(frozen=True)
class ConformanceResult:
    conformance_id: str
    subject_id: str
    contract_id: str
    context_id: str
    decision: ConformanceDecision
    violations: Tuple[str, ...] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)
    source_validator: str = ""

    @property
    def accepted(self) -> bool:
        return self.decision is ConformanceDecision.ACCEPT
