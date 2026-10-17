"""Full-Record Typed Semantic Evaluator for Milestone P4.

Evaluates proposals against complete authoritative schemas, ground truth, and context grounding:
- Schema validity (types, required fields)
- Grammar classification
- Complete semantic match across all required fields
- Grounding (no invented entities/identifiers)
- Uncertainty (proper unknowns emission)
- Numeric precision (thresholds, values)
- Temporal & recovery specifics
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from experiments.uow_magazine_p4.scoring.canonicalize import canonicalize_proposal, canonicalize_value


@dataclass
class SemanticEvaluationResult:
    schema_valid: bool
    grammar_classification: bool
    complete_semantic_match: bool
    grounding_valid: bool
    uncertainty_valid: bool
    numeric_precision: bool
    temporal_correctness: bool
    recovery_correctness: bool
    grounding_violations: list[str] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)

    @property
    def is_fully_qualified(self) -> bool:
        return (
            self.schema_valid
            and self.grammar_classification
            and self.complete_semantic_match
            and self.grounding_valid
            and self.uncertainty_valid
            and self.numeric_precision
            and self.temporal_correctness
            and self.recovery_correctness
        )


class FullRecordOracle:
    """Rigorous independent oracle for typed semantic qualification."""

    @classmethod
    def evaluate(
        cls,
        proposal_dict: Optional[dict[str, Any]],
        ground_truth: dict[str, Any],
        authoritative_context: Optional[dict[str, Any]] = None,
        grammar: str = "operational",
    ) -> SemanticEvaluationResult:
        if proposal_dict is None or not isinstance(proposal_dict, dict):
            return SemanticEvaluationResult(
                schema_valid=False,
                grammar_classification=False,
                complete_semantic_match=False,
                grounding_valid=False,
                uncertainty_valid=False,
                numeric_precision=False,
                temporal_correctness=False,
                recovery_correctness=False,
                failure_reasons=["Proposal is None or not a JSON dictionary"],
            )

        p = canonicalize_proposal(proposal_dict)
        gt = canonicalize_proposal(ground_truth)
        ctx = authoritative_context or {}
        allowed_entities: set[str] = set(ctx.get("allowed_entities", []))

        reasons: list[str] = []
        violations: list[str] = []

        # 1. Schema Validity & Grammar Classification
        schema_valid = True
        grammar_class = False

        if grammar == "operational":
            req_keys = {"domain", "action", "disposition", "parameters"}
            if not req_keys.issubset(p.keys()):
                schema_valid = False
                reasons.append(f"Missing operational schema keys: {sorted(req_keys - set(p.keys()))}")
            if p.get("disposition") not in ("COMMIT", "ROLLBACK", "HALT", "ABORT", "DELEGATE", "ESCALATE"):
                schema_valid = False
                reasons.append(f"Invalid operational disposition: {p.get('disposition')}")
            grammar_class = (p.get("action") == gt.get("action")) and (p.get("disposition") == gt.get("disposition"))

        elif grammar == "temporal":
            req_keys = {"domain", "target_action", "relation"}
            if not req_keys.issubset(p.keys()):
                schema_valid = False
                reasons.append(f"Missing temporal schema keys: {sorted(req_keys - set(p.keys()))}")
            valid_relations = {"BEFORE", "AFTER", "CONCURRENT", "WITHIN", "IMMEDIATE", "BETWEEN"}
            if p.get("relation") not in valid_relations:
                schema_valid = False
                reasons.append(f"Invalid temporal relation: {p.get('relation')}")
            grammar_class = (p.get("relation") == gt.get("relation")) and (p.get("target_action") == gt.get("target_action"))

        elif grammar == "recovery":
            req_keys = {"domain", "strategy"}
            if not req_keys.issubset(p.keys()):
                schema_valid = False
                reasons.append(f"Missing recovery schema keys: {sorted(req_keys - set(p.keys()))}")
            valid_strats = {
                "RETRY", "ROLLBACK_COMPENSATE", "FAILOVER", "ESCALATE_HUMAN",
                "IMMEDIATE_RETRY", "CIRCUIT_BREAK", "EXPONENTIAL_BACKOFF", "ESCALATE_OPERATOR"
            }
            if p.get("strategy") not in valid_strats:
                schema_valid = False
                reasons.append(f"Invalid recovery strategy: {p.get('strategy')}")
            p_f = p.get("failure_mode") or p.get("failed_action") or p.get("failure_class")
            gt_f = gt.get("failure_mode") or gt.get("failed_action") or gt.get("failure_class")
            grammar_class = (p.get("strategy") == gt.get("strategy")) and (p_f == gt_f)

        # 2. Grounding Verification
        grounding_valid = True
        if allowed_entities:
            # Check string identifiers in parameters
            p_params = p.get("parameters") or {}
            for k, val in p_params.items():
                if isinstance(val, str) and any(id_keyword in k.lower() for id_keyword in ["_id", "unit", "valve", "endpoint", "host", "device"]):
                    s_val = str(val).strip()
                    if s_val and s_val not in allowed_entities and s_val.lower() not in [x.lower() for x in allowed_entities]:
                        grounding_valid = False
                        violations.append(f"Fabricated/ungrounded entity identifier '{s_val}' in parameter '{k}'")

        if violations:
            reasons.extend(violations)

        # 3. Uncertainty Verification
        uncertainty_valid = True
        gt_unknowns = gt.get("unknowns", [])
        p_unknowns = p.get("unknowns", [])
        if gt_unknowns:
            # If ground truth specifies missing information, model must mark unknowns
            if not p_unknowns:
                uncertainty_valid = False
                reasons.append("Model failed to flag required unknowns for ungrounded/missing context")
            else:
                # Check that all required unknown concepts are acknowledged
                for u in gt_unknowns:
                    if not any(u.lower() in pu.lower() or pu.lower() in u.lower() for pu in p_unknowns):
                        uncertainty_valid = False
                        reasons.append(f"Missing required unknown flag: '{u}'")
        else:
            # If ground truth has no unknowns, model shouldn't hallucinate spurious unknowns
            if p_unknowns and len(p_unknowns) > 2:
                uncertainty_valid = False
                reasons.append(f"Model flagged spurious unknowns: {p_unknowns}")

        # 4. Numeric Precision Verification
        numeric_precision = True
        gt_params = gt.get("parameters", {})
        p_params = p.get("parameters", {})
        if isinstance(gt_params, dict) and isinstance(p_params, dict):
            for k, expected_v in gt_params.items():
                if isinstance(expected_v, (int, float)) and not isinstance(expected_v, bool):
                    if k not in p_params:
                        numeric_precision = False
                        reasons.append(f"Missing numeric parameter: '{k}'")
                    else:
                        actual_v = p_params[k]
                        if not isinstance(actual_v, (int, float)):
                            try:
                                actual_v = float(actual_v)
                            except (ValueError, TypeError):
                                numeric_precision = False
                                reasons.append(f"Parameter '{k}' is non-numeric: {actual_v}")
                                continue
                        if abs(float(actual_v) - float(expected_v)) > 0.05:
                            numeric_precision = False
                            reasons.append(f"Numeric mismatch in '{k}': expected {expected_v}, got {actual_v}")

        # 5. Temporal Correctness
        temporal_correctness = True
        if grammar == "temporal":
            for field in ["time_window", "deadline_ms", "dependencies", "reference_event"]:
                if field in gt:
                    gt_f_val = gt[field]
                    p_f_val = p.get(field)
                    if gt_f_val is not None and p_f_val != gt_f_val:
                        # Allow slight tolerance or list matching
                        if isinstance(gt_f_val, list) and isinstance(p_f_val, list):
                            if sorted(p_f_val) != sorted(gt_f_val):
                                temporal_correctness = False
                                reasons.append(f"Temporal field mismatch '{field}': expected {gt_f_val}, got {p_f_val}")
                        elif p_f_val != gt_f_val:
                            temporal_correctness = False
                            reasons.append(f"Temporal field mismatch '{field}': expected {gt_f_val}, got {p_f_val}")

        # 6. Recovery Correctness
        recovery_correctness = True
        if grammar == "recovery":
            for field in ["max_retries", "fallback_parameters", "compensation_action", "max_attempts"]:
                if field in gt:
                    gt_f_val = gt[field]
                    p_f_val = p.get(field)
                    if gt_f_val is not None and p_f_val != gt_f_val:
                        recovery_correctness = False
                        reasons.append(f"Recovery field mismatch '{field}': expected {gt_f_val}, got {p_f_val}")

        # 7. Complete Semantic Match
        complete_semantic = (
            schema_valid
            and grammar_class
            and grounding_valid
            and uncertainty_valid
            and numeric_precision
            and temporal_correctness
            and recovery_correctness
        )

        return SemanticEvaluationResult(
            schema_valid=schema_valid,
            grammar_classification=grammar_class,
            complete_semantic_match=complete_semantic,
            grounding_valid=grounding_valid,
            uncertainty_valid=uncertainty_valid,
            numeric_precision=numeric_precision,
            temporal_correctness=temporal_correctness,
            recovery_correctness=recovery_correctness,
            grounding_violations=violations,
            failure_reasons=reasons,
        )
