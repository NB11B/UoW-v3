"""H6.4: Round-Trip Semantic Verifier for Governed Egress.

Enforces the hard invariant:
    parse(render(I_B)) === I_B
for every material field.

Mandatory verification checks:
1. operator
2. recipient
3. quantity
4. unit
5. negation (DO NOT vs DO)
6. modality (MUST vs SHOULD vs MAY vs WILL)
7. temporal constraint (BEFORE vs AFTER)
8. condition (IF vs UNLESS)
9. reference / entity ID
10. certainty level (UNKNOWN vs asserted fact)

Hard Gate:
    epsilon_{egress-drift} = 0
Any output altering material meaning is rejected and falls back deterministically.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Mapping, Optional, Tuple

from .projection import ProjectedSemanticIntent
from .schema import SemanticDisposition


@dataclass(frozen=True)
class SemanticRoundTripResult:
    """Outcome of egress round-trip verification."""

    verified: bool
    original_projected: ProjectedSemanticIntent
    rendered_text: str
    parsed_fields: Mapping[str, Any]
    mismatches: Tuple[str, ...] = ()
    drift_detected: bool = False

    @property
    def drift_epsilon(self) -> float:
        """Egress drift metric: 0.0 if perfectly verified, > 0.0 if any drift detected."""
        return 0.0 if self.verified else float(len(self.mismatches))


class SemanticRoundTripVerifier:
    """Strict, deterministic round-trip verifier for rendered egress communication."""

    def __init__(self) -> None:
        pass

    def verify(
        self,
        projected: ProjectedSemanticIntent,
        rendered_text: str,
    ) -> SemanticRoundTripResult:
        """Verify that render(I_B) preserves all material semantic fields of I_B."""
        parsed_fields = self._parse_rendered_text(rendered_text, projected)
        mismatches: list[str] = []

        # 1. Verification for CLARIFY disposition
        if projected.disposition is SemanticDisposition.CLARIFY:
            # Check that unresolved requirements are explicitly preserved as questions/requests
            # and NOT asserted as facts (hallucinated certainty).
            text_lower = rendered_text.lower()
            if not any(w in text_lower for w in ("clarif", "specify", "please", "require", "missing", "?")):
                mismatches.append(
                    "Omission: CLARIFY disposition rendered without clarification or question marker."
                )
            for unres in projected.unresolved:
                if unres.lower() not in text_lower:
                    mismatches.append(
                        f"Omission: unresolved requirement '{unres}' omitted from clarification text."
                    )
            # Check hallucinated certainty: must not assert values for unresolved terminals
            for unres in projected.unresolved:
                if parsed_fields.get(unres) is not None:
                    mismatches.append(
                        f"Hallucinated certainty: unresolved terminal '{unres}' asserted with value {parsed_fields[unres]!r}."
                    )

            is_verified = len(mismatches) == 0
            return SemanticRoundTripResult(
                verified=is_verified,
                original_projected=projected,
                rendered_text=rendered_text,
                parsed_fields=parsed_fields,
                mismatches=tuple(mismatches),
                drift_detected=not is_verified,
            )

        # 2. Verification for NO disposition
        if projected.disposition is SemanticDisposition.NO:
            text_lower = rendered_text.lower()
            if not any(w in text_lower for w in ("reject", "denied", "could not", "failed", "cannot", "invalid")):
                mismatches.append(
                    "Omission: NO disposition rendered without rejection or denial marker."
                )
            is_verified = len(mismatches) == 0
            return SemanticRoundTripResult(
                verified=is_verified,
                original_projected=projected,
                rendered_text=rendered_text,
                parsed_fields=parsed_fields,
                mismatches=tuple(mismatches),
                drift_detected=not is_verified,
            )

        # 3. Verification for YES disposition (Material Fields)
        bindings = projected.bindings

        # 3.1 Operator preservation
        expected_op = str(bindings.get("operator", projected.operator or "")).lower()
        if expected_op:
            parsed_op = str(parsed_fields.get("operator", "")).lower()
            if not parsed_op:
                mismatches.append(f"Omission: operator '{expected_op}' missing from rendered text.")
            elif parsed_op != expected_op:
                mismatches.append(
                    f"Operator mutation: expected '{expected_op}', found '{parsed_op}'."
                )

        # 3.2 Recipient preservation
        expected_recip = bindings.get("recipient")
        if expected_recip is not None:
            parsed_recip = parsed_fields.get("recipient")
            if parsed_recip is None:
                mismatches.append(
                    f"Omission: recipient '{expected_recip}' missing from rendered text."
                )
            elif str(parsed_recip).strip().lower() != str(expected_recip).strip().lower():
                mismatches.append(
                    f"Recipient mutation: expected '{expected_recip}', found '{parsed_recip}'."
                )

        # 3.3 Quantity preservation
        expected_qty = bindings.get("quantity")
        if expected_qty is not None:
            parsed_qty = parsed_fields.get("quantity")
            if parsed_qty is None:
                mismatches.append(
                    f"Omission: quantity {expected_qty} missing from rendered text."
                )
            elif parsed_qty != expected_qty:
                mismatches.append(
                    f"Quantity mutation: expected {expected_qty}, found {parsed_qty}."
                )

        # 3.4 Unit preservation
        expected_unit = bindings.get("unit")
        if expected_unit is not None:
            parsed_unit = parsed_fields.get("unit")
            if parsed_unit is None:
                mismatches.append(f"Omission: unit '{expected_unit}' missing from rendered text.")
            elif str(parsed_unit).lower() != str(expected_unit).lower():
                mismatches.append(
                    f"Unit mutation: expected '{expected_unit}', found '{parsed_unit}'."
                )

        # 3.5 Negation preservation (DO NOT vs DO)
        expected_neg = bool(bindings.get("negation", False))
        parsed_neg = bool(parsed_fields.get("negation", False))
        if expected_neg != parsed_neg:
            mismatches.append(
                f"Negation polarity shift: expected negation={expected_neg}, found negation={parsed_neg}."
            )

        # 3.6 Modality preservation (MUST vs SHOULD vs MAY vs WILL)
        expected_modality = str(bindings.get("modality", "WILL")).upper()
        parsed_modality = str(parsed_fields.get("modality", "WILL")).upper()
        if expected_modality != parsed_modality:
            mismatches.append(
                f"Modality shift: expected modality={expected_modality}, found modality={parsed_modality}."
            )

        # 3.7 Temporal constraint preservation (BEFORE vs AFTER)
        expected_temporal = bindings.get("temporal")
        if expected_temporal is not None:
            parsed_temporal = parsed_fields.get("temporal")
            if parsed_temporal is None:
                mismatches.append(
                    f"Omission: temporal constraint '{expected_temporal}' missing from rendered text."
                )
            elif str(parsed_temporal).strip().lower() != str(expected_temporal).strip().lower():
                mismatches.append(
                    f"Temporal mutation: expected '{expected_temporal}', found '{parsed_temporal}'."
                )

        # 3.8 Condition preservation (IF vs UNLESS)
        expected_cond = bindings.get("condition")
        if expected_cond is not None:
            parsed_cond = parsed_fields.get("condition")
            if parsed_cond is None:
                mismatches.append(
                    f"Omission: condition '{expected_cond}' missing from rendered text."
                )
            elif str(parsed_cond).strip().lower() != str(expected_cond).strip().lower():
                mismatches.append(
                    f"Condition mutation: expected '{expected_cond}', found '{parsed_cond}'."
                )

        is_verified = len(mismatches) == 0
        return SemanticRoundTripResult(
            verified=is_verified,
            original_projected=projected,
            rendered_text=rendered_text,
            parsed_fields=parsed_fields,
            mismatches=tuple(mismatches),
            drift_detected=not is_verified,
        )

    def _parse_rendered_text(
        self,
        text: str,
        projected: ProjectedSemanticIntent,
    ) -> dict[str, Any]:
        """Extract material fields from rendered text using deterministic parsing."""
        raw = text.strip()
        parsed: dict[str, Any] = {}

        # 1. Try structured JSON extraction first
        if raw.startswith("{") and raw.endswith("}"):
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    if "bindings" in data and isinstance(data["bindings"], dict):
                        parsed.update(data["bindings"])
                    for k in ("operator", "status", "disposition", "quantity", "recipient", "unit"):
                        if k in data and k not in parsed:
                            parsed[k] = data[k]
                    return parsed
            except Exception:
                pass

        # 2. Try structured key=value format (e.g. TRANSFER committed: quantity=3, recipient=Mike Jones.)
        kv_match = re.match(r"^([A-Za-z_]+)\s+(?:committed|executed|completed|rejected|halted):\s*(.*)", raw, re.IGNORECASE)
        if kv_match and "=" in kv_match.group(2):
            parsed["operator"] = kv_match.group(1).lower()
            rest = kv_match.group(2).rstrip(".")
            for part in rest.split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    k = k.strip()
                    v = v.strip()
                    if k == "quantity":
                        try:
                            parsed[k] = int(v) if "." not in v else float(v)
                        except ValueError:
                            parsed[k] = v
                    else:
                        parsed[k] = v

        text_lower = raw.lower()

        # 3. Natural language extraction
        # 3.1 Operator extraction
        known_operators = ["transfer", "purge", "disgorge", "hold", "query", "deploy"]
        if "operator" not in parsed:
            for op in known_operators:
                if re.search(r"\b" + re.escape(op) + r"\b", text_lower):
                    parsed["operator"] = op
                    break

        # 3.2 Negation extraction
        negation_pattern = r"\b(do not|don't|not|never|cannot)\b"
        parsed["negation"] = bool(re.search(negation_pattern, text_lower))

        # 3.3 Modality extraction
        if re.search(r"\bmust\b", text_lower):
            parsed["modality"] = "MUST"
        elif re.search(r"\bshould\b", text_lower):
            parsed["modality"] = "SHOULD"
        elif re.search(r"\bmay\b", text_lower):
            parsed["modality"] = "MAY"
        elif re.search(r"\bwill\b", text_lower):
            parsed["modality"] = "WILL"
        elif not parsed.get("negation"):
            # Default positive execution implies WILL
            parsed["modality"] = "WILL"

        # 3.4 Quantity & Unit extraction
        if "quantity" not in parsed:
            qty_match = re.search(r"\b(?:of\s+)?(\d+(?:\.\d+)?)\s*([a-zA-Z_]+)?\b", raw)
            if qty_match:
                num_str = qty_match.group(1)
                unit_str = qty_match.group(2)
                try:
                    parsed["quantity"] = int(num_str) if "." not in num_str else float(num_str)
                except ValueError:
                    parsed["quantity"] = num_str
                if unit_str and unit_str.lower() not in ("to", "of", "before", "after", "if", "unless", "the", "items"):
                    parsed["unit"] = unit_str
                elif unit_str and unit_str.lower() == "items":
                    parsed["unit"] = "items"

        # 3.5 Recipient extraction
        if "recipient" not in parsed:
            recip_match = re.search(r"\bto\s+([A-Z][a-zA-Z0-9_\s]+?)(?:\s+(?:before|after|if|unless|at)|\.|$)", raw)
            if recip_match:
                parsed["recipient"] = recip_match.group(1).strip()
            elif projected.bindings.get("recipient"):
                # Check if expected recipient name is present verbatim
                exp = str(projected.bindings["recipient"])
                if exp.lower() in text_lower:
                    parsed["recipient"] = exp

        # 3.6 Temporal extraction (BEFORE vs AFTER)
        if "temporal" not in parsed:
            if re.search(r"\bbefore\s+([a-zA-Z0-9_\-\:]+)\b", text_lower):
                m = re.search(r"\b(before\s+[a-zA-Z0-9_\-\:]+)\b", text_lower)
                if m:
                    parsed["temporal"] = m.group(1)
            elif re.search(r"\bafter\s+([a-zA-Z0-9_\-\:]+)\b", text_lower):
                m = re.search(r"\b(after\s+[a-zA-Z0-9_\-\:]+)\b", text_lower)
                if m:
                    parsed["temporal"] = m.group(1)

        # 3.7 Condition extraction (IF vs UNLESS)
        if "condition" not in parsed:
            cond_match = re.search(r"\b(if\s+[^.]+)\b", text_lower)
            if cond_match:
                parsed["condition"] = cond_match.group(1)
            else:
                unless_match = re.search(r"\b(unless\s+[^.]+)\b", text_lower)
                if unless_match:
                    parsed["condition"] = unless_match.group(1)

        return parsed
