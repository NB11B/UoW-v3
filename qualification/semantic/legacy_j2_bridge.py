"""Deterministic compatibility bridge lowering legacy J2 model proposals to UoW H3 IR.

Authority Invariant:
    probabilistic translation != authority
    bridge = representation transform, not semantic inference

Rules:
1. Zero inference authority: typed lowering function only.
2. Unknown legacy requirement ID -> rejected / fails closed.
3. is_unknown=True -> H3 unknowns.
4. Binding value passes through exactly without entity resolution or modification.
5. No deterministic field can be introduced; targets only current F_P.
6. Confidence remains diagnostic only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Mapping, Sequence

from uow.semantic.schema import (
    BindingOrigin,
    CandidateSemanticBindings,
    SemanticAlternative,
    SemanticBinding,
    SemanticRequirement,
    SemanticTranslationRequest,
)

# Standard J2 operational prompt constants
SYSTEM_PROMPT = """You are a deterministic semantic codec translating external operational signals into typed semantic bindings.
Your role is to bind ONLY the unclosed requirement terminals in the probabilistic frontier F_P.

Operational Domain Grammar:
- Performatives (req_performative, req_cmd, req_query): "COMMAND" (for imperative requests), "QUERY" (for questions/checks), "REPORT" (for status reports)
- Operations (req_op, req_head): "TRANSFER", "INSPECT", "DESTROY", "RESERVE", "ISOLATE", "ACQUIRE", "ASSEMBLE", "HOLD", "NOT_TRANSFER"
- Parties (req_recip, req_actor, req_approver, req_executor): Entity IDs like "Mike_29", "Alice_1", "Supervisor_1", "Tech_7"
- Quantities (req_qty, req_qty1, req_qty2): Integer numbers like 2, 3 or "ALL"
- Temporals (req_temporal): "BEFORE", "AFTER", "UNTIL", "IMMEDIATE"
- Conditionals (req_cond, req_policy_gate): "IF(...)" or "UNLESS(...)"
- Modalities (req_modality): "MUST", "MUST_NOT", "SHOULD", "MAY"
- Deictic Locations (req_dest): "SITE_17" (for 'here'), "SITE_01"

Rules:
1. For each requirement listed in the frontier, infer its bound value and WorkCategory from the input signal and minimal context.
2. If a word or action is unknown, nonsensical, ungrounded, or undefined (e.g. invented slang, nonce words like 'florp'), you MUST set "is_unknown": true and "binding_value": "UNKNOWN". Do NOT guess or hallucinate an operational action.
3. If a requirement is ambiguous between multiple valid entities (e.g. 'Mike' when multiple Mikes exist), set the first in "binding_value" and list the others under "alternatives".
4. For deictic references (e.g. 'here'), do not guess raw coordinates; bind the contextually referenced destination or state.
5. Output ONLY valid JSON matching the exact schema below, with no conversational filler.

Output JSON Schema:
{
  "proposals": [
    {
      "target_requirement": "<req_id>",
      "binding_value": <value>,
      "matrix_class": "<People|Processes|Data|Devices|Rules|Policies|Agents|Guidance>",
      "confidence": <float between 0.0 and 1.0>,
      "is_unknown": <boolean>,
      "alternatives": []
    }
  ]
}
"""

LEGACY_TO_H3_TERMINALS: dict[str, str] = {
    "req_op": "operation",
    "req_head": "operation",
    "req_action": "operation",
    "req_primary_op": "primary_operation",
    "req_fallback_op": "fallback_operation",
    "req_recip": "recipient",
    "req_recip1": "recipient_1",
    "req_recip2": "recipient_2",
    "req_actor": "actor",
    "req_executor": "executor",
    "req_approver": "approver",
    "req_qty": "quantity",
    "req_qty1": "quantity_1",
    "req_qty2": "quantity_2",
    "req_target": "target",
    "req_dest": "destination",
    "req_cond": "condition",
    "req_policy_gate": "policy_gate",
    "req_temporal": "temporal",
    "req_modality": "modality",
    "req_cmd": "command",
    "req_query": "query",
    "req_performative": "performative",
    "req_stage1": "stage_1",
    "req_stage2": "stage_2",
    "req_part1": "part_1",
    "req_part2": "part_2",
    "req_dep": "dependency",
}

H3_TO_LEGACY_TERMINALS: dict[str, str] = {v: k for k, v in LEGACY_TO_H3_TERMINALS.items()}


@dataclass(frozen=True)
class LegacyProposedBinding:
    value: Any
    matrix_class: str = "Data"
    is_unknown: bool = False
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LegacyCandidateProposal:
    target_requirement: str
    proposed_binding: LegacyProposedBinding
    confidence: float = 1.0
    alternatives: tuple[LegacyProposedBinding, ...] = ()


@dataclass(frozen=True)
class LegacyCandidateResponse:
    proposals: tuple[LegacyCandidateProposal, ...]
    raw_response: str
    is_syntactically_valid: bool
    notes: str = ""


class J2SemanticCodec:
    """Prompt construction and JSON parsing conforming to the legacy J2 codec."""

    def __init__(self, system_prompt: str = SYSTEM_PROMPT) -> None:
        self.system_prompt = system_prompt

    def build_prompt(self, request: SemanticTranslationRequest) -> str:
        """Format the J2 prompt matching the physical training condition."""
        lines = [
            f'Input Signal (X): "{request.signal.raw}"',
            "",
            "Minimal Context (C^min):",
        ]
        if request.minimal_context.bindings:
            for b in sorted(request.minimal_context.bindings, key=lambda x: x.terminal):
                lines.append(f"  - {b.terminal}: {b.value}")
        else:
            lines.append("  (None)")

        lines.append("")
        lines.append("Probabilistic Frontier Terminals to Close (F_P):")
        for item in request.frontier:
            legacy_id = H3_TO_LEGACY_TERMINALS.get(item.name, item.name)
            lines.append(f"  - Terminal ID: {legacy_id}")

        lines.append("")
        lines.append("Instructions:")
        legacy_ids = [H3_TO_LEGACY_TERMINALS.get(item.name, item.name) for item in request.frontier]
        ids_str = ", ".join(f'"{i}"' for i in legacy_ids)
        lines.append(
            f'Emit a proposal for each Terminal ID listed above. Set "target_requirement" strictly to the Terminal ID ({ids_str}).'
        )
        lines.append("")
        lines.append("Emit your JSON proposals:")
        body = "\n".join(lines)
        return f"{self.system_prompt}\n\n{body}\n\nJSON Output:\n"

    def parse(self, raw_output: str, request: SemanticTranslationRequest) -> LegacyCandidateResponse:
        """Parse raw model output into LegacyCandidateResponse without semantic repair."""
        cleaned = raw_output.strip()

        # Extract markdown code fence if present
        fence_match = re.search(r"```(?:json)?\s*([\{\[].*?[\}\]])\s*```", cleaned, re.DOTALL)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        else:
            # Extract outer JSON structure
            start_obj = cleaned.find("{")
            start_arr = cleaned.find("[")
            if start_obj != -1 and (start_arr == -1 or start_obj < start_arr):
                end_obj = cleaned.rfind("}")
                if end_obj > start_obj:
                    cleaned = cleaned[start_obj : end_obj + 1]
            elif start_arr != -1:
                end_arr = cleaned.rfind("]")
                if end_arr > start_arr:
                    cleaned = cleaned[start_arr : end_arr + 1]

        try:
            data = json.loads(cleaned)
        except Exception:
            return LegacyCandidateResponse(
                proposals=(),
                raw_response=raw_output,
                is_syntactically_valid=False,
                notes="JSONDecodeError",
            )

        if isinstance(data, list):
            proposals_data = data
        elif isinstance(data, dict):
            proposals_data = data.get("proposals", [])
        else:
            proposals_data = []

        if not isinstance(proposals_data, list):
            return LegacyCandidateResponse(
                proposals=(),
                raw_response=raw_output,
                is_syntactically_valid=False,
                notes="proposals root is not a list",
            )

        proposals: list[LegacyCandidateProposal] = []
        for prop in proposals_data:
            if not isinstance(prop, dict):
                continue
            req_id = str(prop.get("target_requirement", "")).strip()
            b_val = prop.get("binding_value", "")
            mc = str(prop.get("matrix_class", "Data"))
            try:
                conf = float(prop.get("confidence", 1.0))
            except (ValueError, TypeError):
                conf = 0.5

            raw_unk = prop.get("is_unknown", False)
            if isinstance(raw_unk, str):
                is_unk = raw_unk.lower() in ("true", "1", "yes", "unknown")
            else:
                is_unk = bool(raw_unk)

            alts_raw = prop.get("alternatives", [])
            alts: list[LegacyProposedBinding] = []
            if isinstance(alts_raw, list):
                for alt in alts_raw:
                    if isinstance(alt, dict):
                        alts.append(
                            LegacyProposedBinding(
                                value=alt.get("binding_value", alt.get("value", "")),
                                matrix_class=str(alt.get("matrix_class", mc)),
                                is_unknown=False,
                            )
                        )
                    else:
                        alts.append(
                            LegacyProposedBinding(
                                value=alt,
                                matrix_class=mc,
                                is_unknown=False,
                            )
                        )

            proposals.append(
                LegacyCandidateProposal(
                    target_requirement=req_id,
                    proposed_binding=LegacyProposedBinding(
                        value=b_val,
                        matrix_class=mc,
                        is_unknown=is_unk,
                    ),
                    confidence=conf,
                    alternatives=tuple(alts),
                )
            )

        return LegacyCandidateResponse(
            proposals=tuple(proposals),
            raw_response=raw_output,
            is_syntactically_valid=True,
        )


class J2ToH3Bridge:
    """Deterministic, zero-inference lowering bridge from LegacyCandidateResponse to CandidateSemanticBindings."""

    def lower(
        self,
        legacy: LegacyCandidateResponse,
        request: SemanticTranslationRequest,
        *,
        evidence_ref: str = "",
    ) -> CandidateSemanticBindings:
        """Lower legacy proposals to typed CandidateSemanticBindings.

        Strict lowering rules:
        - Malformed syntax -> fail closed with all open terminals in unknowns.
        - Unknown legacy requirement ID -> emitted as raw target or rejected to preserve frontier confinement.
        - is_unknown=True or 'UNKNOWN' value -> mapped to unknowns.
        - Binding value passes through unmodified.
        - Zero inference, entity resolution, or state modification.
        """
        evidence_tuple = (evidence_ref,) if evidence_ref else ()

        if not legacy.is_syntactically_valid:
            return CandidateSemanticBindings(
                unknowns=tuple(r.name for r in request.frontier),
                evidence_refs=evidence_tuple + ("codec_parse_failure:InvalidJSON",),
            )

        # Build bidirectional lookup of allowed terminals in request.frontier
        frontier_terminals: set[str] = {r.name for r in request.frontier}
        terminal_map: dict[str, str] = {}
        for r in request.frontier:
            terminal_map[r.name] = r.name
            legacy_id = H3_TO_LEGACY_TERMINALS.get(r.name)
            if legacy_id:
                terminal_map[legacy_id] = r.name
            # Also allow reverse lookup
            for leg, h3_name in LEGACY_TO_H3_TERMINALS.items():
                if h3_name == r.name:
                    terminal_map[leg] = r.name

        candidate_bindings: list[SemanticBinding] = []
        alternatives: list[SemanticAlternative] = []
        unknowns: list[str] = []
        confidence_map: dict[str, float] = {}

        for prop in legacy.proposals:
            target_raw = str(prop.target_requirement).strip()
            if not target_raw:
                continue

            # Resolve terminal name against F_P
            target_name = terminal_map.get(target_raw)

            if target_name is None:
                # Target is outside declared F_P.
                # Emit binding with raw target so SemanticClosureEngine detects FRONTIER_CONFINEMENT_VIOLATION.
                candidate_bindings.append(
                    SemanticBinding(
                        terminal=target_raw,
                        value=prop.proposed_binding.value,
                        origin=BindingOrigin.PROBABILISTIC,
                        evidence_refs=evidence_tuple,
                    )
                )
                continue

            val = prop.proposed_binding.value
            is_unk = (
                prop.proposed_binding.is_unknown
                or (isinstance(val, str) and val.strip().upper() == "UNKNOWN")
                or val is None
            )

            if is_unk:
                if target_name not in unknowns:
                    unknowns.append(target_name)
            else:
                candidate_bindings.append(
                    SemanticBinding(
                        terminal=target_name,
                        value=val,
                        origin=BindingOrigin.PROBABILISTIC,
                        evidence_refs=evidence_tuple,
                    )
                )

            # Map alternatives
            if prop.alternatives:
                alt_bindings: list[SemanticBinding] = []
                for alt in prop.alternatives:
                    alt_val = alt.value
                    if alt_val and str(alt_val).strip().upper() != "UNKNOWN":
                        alt_bindings.append(
                            SemanticBinding(
                                terminal=target_name,
                                value=alt_val,
                                origin=BindingOrigin.PROBABILISTIC,
                                evidence_refs=evidence_tuple,
                            )
                        )
                if alt_bindings:
                    alternatives.append(
                        SemanticAlternative(
                            bindings=tuple(alt_bindings),
                            reason="legacy_j2_alternative",
                        )
                    )

            if 0.0 <= prop.confidence <= 1.0:
                confidence_map[target_name] = prop.confidence

        return CandidateSemanticBindings(
            candidate_bindings=tuple(candidate_bindings),
            alternatives=tuple(alternatives),
            unknowns=tuple(unknowns),
            local_confidence=confidence_map,
            evidence_refs=evidence_tuple,
        )
