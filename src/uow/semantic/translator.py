"""Model-independent probabilistic translator protocol."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .schema import CandidateSemanticBindings, SemanticTranslationRequest


@runtime_checkable
class SemanticTranslator(Protocol):
    """Bounded semantic codec with zero authority over UoW state."""

    def propose(self, request: SemanticTranslationRequest) -> CandidateSemanticBindings:
        ...


class NullSemanticTranslator:
    """Fail-closed translator used when no probabilistic runtime is installed."""

    def propose(self, request: SemanticTranslationRequest) -> CandidateSemanticBindings:
        return CandidateSemanticBindings(
            unknowns=tuple(requirement.name for requirement in request.frontier)
        )
