"""Bounded prompt construction and deterministic output parsing for semantic model codecs."""
from __future__ import annotations

from enum import Enum
import json
import math
from typing import Any, Mapping

from ..schema import (
    BindingOrigin,
    CandidateSemanticBindings,
    SemanticAlternative,
    SemanticBinding,
    SemanticTranslationRequest,
)
from ...state import canonical_json


SYSTEM_PROMPT = """You are a bounded semantic translator.

Translate the external signal only into bindings for the declared unresolved terminals.

Do not make policy decisions.
Do not authorize actions.
Do not plan execution.
Do not invent missing information.
Do not modify deterministic context.
Use UNKNOWN when a terminal cannot be uniquely resolved.
Return only the required structured output."""

ALLOWED_TOP_LEVEL_KEYS = frozenset({"bindings", "alternatives", "unknowns", "local_confidence"})


class AdapterFailureCategory(str, Enum):
    """Categorized model adapter failure taxonomy."""

    LOAD_FAILURE = "LOAD_FAILURE"
    MANIFEST_FAILURE = "MANIFEST_FAILURE"
    INFERENCE_FAILURE = "INFERENCE_FAILURE"
    OUTPUT_VALIDATION_FAILURE = "OUTPUT_VALIDATION_FAILURE"


class SemanticOutputValidationError(ValueError):
    """Raised when model generation violates the output grammar or frontier confinement."""


class SemanticPromptBuilder:
    """Construct minimal prompt payloads containing only (X, C_min, F_P)."""

    def __init__(self, system_prompt: str = SYSTEM_PROMPT) -> None:
        self.system_prompt = system_prompt

    def build_user_payload(self, request: SemanticTranslationRequest) -> dict[str, Any]:
        """Construct the canonical conceptual (X, C_min, F_P) object."""
        return {
            "signal": request.signal.raw,
            "context": {b.terminal: b.value for b in request.minimal_context.bindings},
            "frontier": [{"name": r.name} for r in request.frontier],
        }

    def build_user_prompt(self, request: SemanticTranslationRequest) -> str:
        """Format the conceptual payload with explicit schema instructions."""
        payload = self.build_user_payload(request)
        canonical_str = canonical_json(payload)
        return (
            f"INPUT:\n{canonical_str}\n\n"
            "INSTRUCTION:\n"
            "Return a strictly valid JSON object matching this exact schema:\n"
            "{\n"
            '  "bindings": [{"terminal": "<name>", "value": <value>}],\n'
            '  "alternatives": [{"bindings": [{"terminal": "<name>", "value": <value>}], "reason": "<optional_reason>"}],\n'
            '  "unknowns": ["<name>"]\n'
            "}\n"
            "Do not output markdown fences or explanatory text. Emit only raw JSON."
        )

    def build_chat_messages(
        self,
        request: SemanticTranslationRequest,
    ) -> list[dict[str, str]]:
        """Return standardized OpenAI/HuggingFace chat-template message dictionaries."""
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self.build_user_prompt(request)},
        ]


class SemanticOutputParser:
    """Strict, deterministic parser for model candidate bindings IR."""

    @staticmethod
    def _reject_constants(token: str) -> None:
        raise SemanticOutputValidationError(f"Invalid non-standard JSON literal: {token!r}")

    @classmethod
    def extract_json_text(cls, raw: str) -> str:
        """Strip enclosing code fences or outer whitespace if present."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return cleaned

    def parse(
        self,
        raw_text: str,
        request: SemanticTranslationRequest,
        *,
        evidence_ref: str = "",
        fail_closed: bool = True,
    ) -> CandidateSemanticBindings:
        """Parse raw model output into CandidateSemanticBindings.

        If fail_closed is True, any syntax or schema violation safely returns
        CandidateSemanticBindings with all open frontier terminals marked UNKNOWN.
        """
        try:
            return self._parse_strict(raw_text, request, evidence_ref=evidence_ref)
        except (json.JSONDecodeError, SemanticOutputValidationError) as exc:
            if not fail_closed:
                raise
            evidence = (evidence_ref,) if evidence_ref else ()
            if evidence_ref:
                evidence = (evidence_ref, f"codec_parse_failure:{type(exc).__name__}")
            else:
                evidence = (f"codec_parse_failure:{type(exc).__name__}",)
            return CandidateSemanticBindings(
                unknowns=tuple(r.name for r in request.frontier),
                evidence_refs=evidence,
            )

    def _parse_strict(
        self,
        raw_text: str,
        request: SemanticTranslationRequest,
        *,
        evidence_ref: str = "",
    ) -> CandidateSemanticBindings:
        cleaned = self.extract_json_text(raw_text)
        try:
            parsed = json.loads(cleaned, parse_constant=self._reject_constants)
        except json.JSONDecodeError as exc:
            raise SemanticOutputValidationError(f"Malformed JSON from model: {exc}") from exc

        if not isinstance(parsed, dict):
            raise SemanticOutputValidationError(
                f"Model output root must be a JSON object, got {type(parsed).__name__}"
            )

        # Enforce required top-level keys
        for required_key in ("bindings", "alternatives", "unknowns"):
            if required_key not in parsed:
                raise SemanticOutputValidationError(
                    f"Model output missing required key: {required_key!r}"
                )

        # Reject arbitrary top-level keys
        unknown_keys = set(parsed.keys()) - ALLOWED_TOP_LEVEL_KEYS
        if unknown_keys:
            raise SemanticOutputValidationError(
                f"Model output contains disallowed top-level keys: {sorted(unknown_keys)}"
            )

        allowed_terminals = {r.name for r in request.frontier}
        evidence_tuple = (evidence_ref,) if evidence_ref else ()

        # Parse unknowns
        raw_unknowns = parsed.get("unknowns", [])
        if not isinstance(raw_unknowns, list):
            raise SemanticOutputValidationError("unknowns must be a JSON list.")
        unknowns: list[str] = []
        for item in raw_unknowns:
            if not isinstance(item, str):
                raise SemanticOutputValidationError("unknown terminal name must be a string.")
            if item not in allowed_terminals:
                raise SemanticOutputValidationError(
                    f"Model emitted unknown for undeclared terminal {item!r}."
                )
            if item not in unknowns:
                unknowns.append(item)

        # Parse primary bindings
        raw_bindings = parsed.get("bindings", [])
        if not isinstance(raw_bindings, list):
            raise SemanticOutputValidationError("bindings must be a JSON list.")

        candidate_bindings: list[SemanticBinding] = []
        seen_pairs: set[tuple[str, str]] = set()

        for item in raw_bindings:
            if not isinstance(item, dict):
                raise SemanticOutputValidationError("binding item must be an object.")
            if "terminal" not in item or "value" not in item:
                raise SemanticOutputValidationError(
                    "binding item must contain 'terminal' and 'value'."
                )
            terminal = item["terminal"]
            val = item["value"]

            if not isinstance(terminal, str):
                raise SemanticOutputValidationError("terminal must be a string.")
            if terminal not in allowed_terminals:
                raise SemanticOutputValidationError(
                    f"Model emitted binding for undeclared terminal {terminal!r} outside frontier."
                )
            self._validate_value(val)

            val_canonical = canonical_json(val)
            pair_key = (terminal, val_canonical)
            if pair_key in seen_pairs:
                # Duplicate equal binding normalized
                continue

            seen_pairs.add(pair_key)
            candidate_bindings.append(
                SemanticBinding(
                    terminal=terminal,
                    value=val,
                    origin=BindingOrigin.PROBABILISTIC,
                    evidence_refs=evidence_tuple,
                )
            )

        # Parse alternatives
        raw_alternatives = parsed.get("alternatives", [])
        if not isinstance(raw_alternatives, list):
            raise SemanticOutputValidationError("alternatives must be a JSON list.")

        alternatives: list[SemanticAlternative] = []
        for alt_item in raw_alternatives:
            if not isinstance(alt_item, dict):
                raise SemanticOutputValidationError("alternative item must be an object.")
            if "bindings" not in alt_item or not isinstance(alt_item["bindings"], list):
                raise SemanticOutputValidationError(
                    "alternative must contain a 'bindings' list."
                )
            alt_bindings: list[SemanticBinding] = []
            for b in alt_item["bindings"]:
                if not isinstance(b, dict) or "terminal" not in b or "value" not in b:
                    raise SemanticOutputValidationError(
                        "alternative binding must contain 'terminal' and 'value'."
                    )
                alt_term = b["terminal"]
                alt_val = b["value"]
                if alt_term not in allowed_terminals:
                    raise SemanticOutputValidationError(
                        f"Alternative target {alt_term!r} outside frontier."
                    )
                self._validate_value(alt_val)
                alt_bindings.append(
                    SemanticBinding(
                        terminal=alt_term,
                        value=alt_val,
                        origin=BindingOrigin.PROBABILISTIC,
                        evidence_refs=evidence_tuple,
                    )
                )
            alternatives.append(
                SemanticAlternative(
                    bindings=tuple(alt_bindings),
                    reason=str(alt_item.get("reason", "")),
                )
            )

        # Parse optional local confidence
        confidence_map: dict[str, float] = {}
        raw_confidence = parsed.get("local_confidence")
        if isinstance(raw_confidence, dict):
            for k, v in raw_confidence.items():
                if isinstance(k, str) and k in allowed_terminals and isinstance(v, (int, float)):
                    if not math.isnan(v) and not math.isinf(v) and 0.0 <= v <= 1.0:
                        confidence_map[k] = float(v)

        return CandidateSemanticBindings(
            candidate_bindings=tuple(candidate_bindings),
            alternatives=tuple(alternatives),
            unknowns=tuple(unknowns),
            local_confidence=confidence_map,
            evidence_refs=evidence_tuple,
        )

    def _validate_value(self, val: Any) -> None:
        """Ensure values are serializable and free of NaN/Infinity."""
        if val is None or isinstance(val, (str, bool, int)):
            return
        if isinstance(val, float):
            if math.isnan(val) or math.isinf(val):
                raise SemanticOutputValidationError("Float value cannot be NaN or Infinity.")
            return
        if isinstance(val, list):
            for v in val:
                self._validate_value(v)
            return
        if isinstance(val, dict):
            for k, v in val.items():
                if not isinstance(k, str):
                    raise SemanticOutputValidationError("Dictionary keys must be strings.")
                self._validate_value(v)
            return
        raise SemanticOutputValidationError(f"Unsupported value type: {type(val).__name__}")
