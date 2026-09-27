"""H6.2 & H6.3: Governed Semantic Rendering and Deterministic Formatting.

Provides:
1. DeterministicEgressFormatter: Pure deterministic formatting without LLM calls.
   Guarantees: model calls = 0.
2. SemanticRenderer (Protocol): Optional natural-language renderer contract.
   Guarantees: receives only ProjectedSemanticIntent (I_B). Sees zero internal
   WorldState, authority graph, WAL, or hidden evidence.
3. DeterministicTemplateRenderer / MockNaturalLanguageRenderer: Testable renderers.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Optional, Protocol

from .projection import ProjectedSemanticIntent, RecipientClass
from .schema import SemanticDisposition


class SemanticRenderer(Protocol):
    """Protocol for optional natural-language egress rendering."""

    def render(self, projected: ProjectedSemanticIntent) -> str:
        """Render projected semantic intent I_B into natural language prose."""
        ...


class DeterministicEgressFormatter:
    """Pure deterministic egress formatter. Bypasses model entirely (model calls = 0)."""

    def format(self, projected: ProjectedSemanticIntent) -> str:
        """Format I_B into deterministic, unambiguous structured text."""
        # 1. Machine peer format (canonical JSON)
        if projected.recipient_class in (RecipientClass.MACHINE_PEER, RecipientClass.AUDITOR):
            payload: dict[str, Any] = {
                "status": projected.status,
                "disposition": projected.disposition.value,
            }
            if projected.operator:
                payload["operator"] = projected.operator
            if projected.bindings:
                payload["bindings"] = dict(projected.bindings)
            if projected.unresolved:
                payload["unresolved"] = list(projected.unresolved)
            if projected.alternatives:
                payload["alternatives"] = list(projected.alternatives)
            if projected.reason:
                payload["reason"] = projected.reason
            if projected.uow_id:
                payload["uow_id"] = projected.uow_id
            if projected.state_hash:
                payload["state_hash"] = projected.state_hash
            if projected.certificate_hash:
                payload["certificate_hash"] = projected.certificate_hash
            if projected.evidence_refs:
                payload["evidence_refs"] = list(projected.evidence_refs)
            payload["projection_hash"] = projected.projection_hash
            return json.dumps(payload, sort_keys=True)

        # 2. Human requester & Operator formatted text
        if projected.disposition is SemanticDisposition.CLARIFY:
            unresolved_str = ", ".join(projected.unresolved) if projected.unresolved else "additional information"
            msg = f"Request requires clarification: {unresolved_str}."
            if projected.alternatives:
                msg += f" Alternatives: {'; '.join(projected.alternatives)}."
            return msg

        if projected.disposition is SemanticDisposition.NO:
            reason_str = projected.reason or "request failed semantic admissibility validation"
            return f"Request rejected: {reason_str}."

        # Disposition is YES
        op = (projected.operator or "OPERATION").upper()
        status_str = projected.status.lower()

        # Material bindings formatting
        parts: list[str] = []
        for key in sorted(projected.bindings.keys()):
            if key == "operator":
                continue
            val = projected.bindings[key]
            parts.append(f"{key}={val}")

        details = f": {', '.join(parts)}" if parts else ""
        msg = f"{op} {status_str}{details}."
        return msg


class DeterministicTemplateRenderer:
    """Bounded, deterministic natural language template renderer."""

    def render(self, projected: ProjectedSemanticIntent) -> str:
        """Render projected intent into grammatically natural prose without stochasticity."""
        if projected.disposition is SemanticDisposition.CLARIFY:
            fields = " and ".join(projected.unresolved) if projected.unresolved else "unknown requirements"
            return f"Please specify the {fields} to complete the request."

        if projected.disposition is SemanticDisposition.NO:
            reason = projected.reason or "the request could not be processed"
            return f"The request was rejected because {reason}."

        # YES disposition
        b = projected.bindings
        op = b.get("operator", projected.operator or "execute")
        qty = b.get("quantity")
        unit = b.get("unit")
        recip = b.get("recipient")
        temporal = b.get("temporal")
        negation = b.get("negation")
        modality = b.get("modality", "WILL")
        condition = b.get("condition")

        # Modality prefix
        action_verb = str(op)

        # Build natural prose
        prose_parts: list[str] = []

        if negation:
            prose_parts.append(f"Do not {action_verb}")
        else:
            if modality == "MUST":
                prose_parts.append(f"Must {action_verb}")
            elif modality == "SHOULD":
                prose_parts.append(f"Should {action_verb}")
            elif modality == "MAY":
                prose_parts.append(f"May {action_verb}")
            else:
                prose_parts.append(f"Successfully executed {action_verb}")

        if qty is not None:
            qty_str = f"{qty} {unit}" if unit else str(qty)
            prose_parts.append(f"of {qty_str}")

        if recip is not None:
            prose_parts.append(f"to {recip}")

        if temporal is not None:
            prose_parts.append(str(temporal))

        if condition is not None:
            prose_parts.append(f"if {condition}")

        return " ".join(prose_parts) + "."


class ConfigurableRenderer:
    """Configurable mock renderer for exercising round-trip checks and adversarial tests."""

    def __init__(self, output: str) -> None:
        self.output = output
        self.call_count = 0
        self.last_received: Optional[ProjectedSemanticIntent] = None

    def render(self, projected: ProjectedSemanticIntent) -> str:
        self.call_count += 1
        self.last_received = projected
        return self.output
