"""Expertise Specification Schema (uow.expertise.v1)."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import json


@dataclass(frozen=True)
class OperationSpec:
    """Specification of an operational action within a domain."""
    name: str
    description: str
    allowed_parameters: list[str]
    required_guards: list[str]
    dispositions: list[str] = field(default_factory=lambda: ["COMMIT", "ROLLBACK", "HALT"])


@dataclass(frozen=True)
class QualificationThresholds:
    """Rigorous threshold criteria for deployment eligibility."""
    min_valid_json_rate: float = 99.0
    min_semantic_exact_match_rate: float = 90.0
    max_unknown_fabrication_rate: float = 0.0
    max_switch_latency_ms: float = 5.0
    max_cross_contamination: float = 1e-6


@dataclass(frozen=True)
class ExpertiseSpecification:
    """Formal specification for compiling and qualifying a domain-grammar specialist."""
    spec_version: str = "uow.expertise.v1"
    domain: str = ""
    grammar: str = ""
    target_schema: str = ""
    allowed_vocabulary: list[str] = field(default_factory=list)
    operations: list[OperationSpec] = field(default_factory=list)
    qualification_thresholds: QualificationThresholds = field(default_factory=QualificationThresholds)
    ground_truth_validator: str = "default_validator"
    extra_rules: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExpertiseSpecification:
        ops_data = data.get("operations", [])
        ops = [OperationSpec(**op) if isinstance(op, dict) else op for op in ops_data]
        thresh_data = data.get("qualification_thresholds", {})
        thresh = QualificationThresholds(**thresh_data) if isinstance(thresh_data, dict) else thresh_data
        copied = dict(data)
        copied["operations"] = ops
        copied["qualification_thresholds"] = thresh
        return cls(**copied)
