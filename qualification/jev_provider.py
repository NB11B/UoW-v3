"""Provider adapter for the bounded JEV recursive-scale qualification experiment.

Vendor-specific TypeSafe SDK imports are intentionally isolated in this module.
The UoW experiment consumes only the normalized ``decide`` interface below.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence


DEFAULT_JEV_MODEL = "jev-1.13.0"
MOVING_MODEL_ALIASES = frozenset({"jev-latest", "jev-preview"})


@dataclass(frozen=True)
class JevQuestionSpec:
    """One fixed, bounded binary observer question."""

    question_id: str
    instructions: str


UOW_OBSERVER_QUESTIONS: tuple[JevQuestionSpec, ...] = (
    JevQuestionSpec(
        "effective_authority",
        "Does the described governed unit currently retain effective authority to complete its declared work without bypassing certification?",
    ),
    JevQuestionSpec(
        "semantic_continuity",
        "Does the described unit preserve the same externally declared work meaning despite its current internal condition?",
    ),
    JevQuestionSpec(
        "commit_path_viable",
        "Is there currently a viable end-to-end path from execution through verification to a lawful commit?",
    ),
    JevQuestionSpec(
        "recursive_control_coherent",
        "Does the described recursive system remain operationally coherent as a governed control unit?",
    ),
    JevQuestionSpec(
        "failure_handling_coherent",
        "If a disruption is present, is it being handled in a way that preserves the governing constraints rather than bypassing them?",
    ),
    JevQuestionSpec(
        "boundary_semantics_stable",
        "Do the recursive composition boundaries still preserve the parent-visible semantics of the governed work?",
    ),
    JevQuestionSpec(
        "recoverable_without_contract_change",
        "Could the described unit recover through lawful actor substitution or rebinding without changing the declared parent contract?",
    ),
    JevQuestionSpec(
        "parent_recertification_required",
        "Would the parent need to change or recertify its own contract before this unit could lawfully continue?",
    ),
)


def question_payload() -> list[dict[str, str]]:
    """Return the frozen provider-neutral question description."""

    return [
        {"question_id": spec.question_id, "instructions": spec.instructions}
        for spec in UOW_OBSERVER_QUESTIONS
    ]


def _model_dump(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return dict(value)
    return str(value)


class TypeSafeJevProvider:
    """Thin live adapter around ``typesafe_sdk.TypeSafeClient``.

    The dependency is imported lazily so the canonical UoW package and its
    ordinary test suite do not depend on the external SDK.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_JEV_MODEL,
        timeout_s: float = 30.0,
    ) -> None:
        self.model = model
        self.timeout_s = float(timeout_s)

    def decide(
        self,
        *,
        state: dict[str, Any],
        questions: Sequence[Mapping[str, str]],
        request_id: str,
    ) -> dict[str, Any]:
        try:
            from typesafe_sdk import Noul, TypeSafeClient
        except ImportError as exc:  # pragma: no cover - exercised only locally.
            raise RuntimeError(
                "Live JEV execution requires typesafe-sdk. Install with: "
                "python -m pip install 'typesafe-sdk>=0.7.1,<0.8'"
            ) from exc

        expected_ids = tuple(spec.question_id for spec in UOW_OBSERVER_QUESTIONS)
        supplied_ids = tuple(str(item.get("question_id", "")) for item in questions)
        if supplied_ids != expected_ids:
            raise ValueError(
                "JEV question battery drifted; expected the frozen UoW observer order"
            )

        api_questions = {
            str(item["question_id"]): Noul(instructions=str(item["instructions"]))
            for item in questions
        }

        with TypeSafeClient(model=self.model, timeout=self.timeout_s) as client:
            response = client.system_one(
                state=state,
                questions=api_questions,
                model=self.model,
            )

        resolved_model = str(getattr(response, "model", self.model))
        if self.model not in MOVING_MODEL_ALIASES and resolved_model != self.model:
            raise RuntimeError(
                "UNEXPECTED_PROVIDER_MODEL:"
                f"requested={self.model}:resolved={resolved_model}"
            )

        vector: list[float] = []
        answers: dict[str, dict[str, Any]] = {}
        for question_id in expected_ids:
            try:
                answer = response.nouls[question_id]
                probability_true = float(answer.noul)
            except Exception as exc:
                raise RuntimeError(
                    f"INVALID_PROVIDER_RESPONSE: missing/invalid Noul answer for {question_id}"
                ) from exc

            if not math.isfinite(probability_true) or not 0.0 <= probability_true <= 1.0:
                raise RuntimeError(
                    f"INVALID_PROVIDER_RESPONSE: non-probability for {question_id}"
                )
            vector.append(probability_true)
            answers[question_id] = {
                "primitive": "noul",
                "probability_true": probability_true,
                "validation_status": "VALID",
            }

        usage = _model_dump(getattr(response, "usage", None))
        return {
            "request_id": request_id,
            "requested_model": self.model,
            "resolved_model": resolved_model,
            "question_ids": list(expected_ids),
            "vector": vector,
            "answers": answers,
            "usage": usage,
            "validation_status": "VALID",
        }


__all__ = [
    "DEFAULT_JEV_MODEL",
    "JevQuestionSpec",
    "MOVING_MODEL_ALIASES",
    "TypeSafeJevProvider",
    "UOW_OBSERVER_QUESTIONS",
    "question_payload",
]
