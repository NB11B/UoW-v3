"""Ephemeral clarification context over residual semantic frontiers."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Optional, Sequence, Tuple

from .schema import (
    BindingOrigin,
    CandidateSemanticBindings,
    ExternalSignal,
    IngressContext,
    IntentEnvelope,
    MinimalSemanticContext,
    SemanticAlternative,
    SemanticBinding,
    SemanticClosureCertificate,
    SemanticDisposition,
    SemanticFrontierResult,
    SemanticRequirement,
    SemanticResult,
)


class StaleClarificationError(ValueError):
    """Raised when authoritative state drifts between clarification turns."""


class ContradictoryContinuationError(ValueError):
    """Raised when a continuation contradicts immutable resolved bindings."""


@dataclass(frozen=True)
class ClarificationContext:
    """Ephemeral clarification state preserving partial semantic closures across turns.

    INVARIANT: ClarificationContext != WorldState.
    It carries zero execution authority and exists solely to preserve partially resolved
    frontiers and prevent re-asking the model for previously established terminals:
        resolved_t cap F_{P, t+1} = empty
    """

    clarification_id: str
    original_signal_id: str
    original_state_hash: str
    semantic_certificate_hash: str

    resolved_bindings: Tuple[SemanticBinding, ...]
    unresolved: Tuple[SemanticRequirement, ...]
    alternatives: Tuple[SemanticAlternative, ...]

    turn: int = 1
    evidence_refs: Tuple[str, ...] = ()
    signal_history: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.clarification_id:
            raise ValueError("ClarificationContext.clarification_id must be non-empty.")
        if not self.original_signal_id:
            raise ValueError("ClarificationContext.original_signal_id must be non-empty.")
        if not self.original_state_hash:
            raise ValueError("ClarificationContext.original_state_hash must be non-empty.")

    @classmethod
    def from_result(
        cls,
        result: SemanticResult,
        *,
        signal_id: str,
        state_hash: str,
        clarification_id: Optional[str] = None,
        turn: int = 1,
        source_signal: Optional[str] = None,
    ) -> ClarificationContext:
        """Construct an ephemeral ClarificationContext from a CLARIFY SemanticResult."""
        if result.disposition is not SemanticDisposition.CLARIFY:
            raise ValueError("ClarificationContext can only be created from a CLARIFY result.")

        digest = hashlib.sha256(
            f"{signal_id}:{result.certificate.certificate_hash}:{turn}".encode("utf-8")
        ).hexdigest()[:16]
        cid = clarification_id or f"clarif-{digest}"
        history = (source_signal,) if source_signal else ()

        return cls(
            clarification_id=cid,
            original_signal_id=signal_id,
            original_state_hash=state_hash,
            semantic_certificate_hash=result.certificate.certificate_hash,
            resolved_bindings=result.certificate.resolved_bindings,
            unresolved=result.unresolved,
            alternatives=result.alternatives,
            turn=turn,
            evidence_refs=result.evidence_refs,
            signal_history=history,
        )

    def resolved_map(self) -> dict[str, Any]:
        """Dictionary representation of previously resolved terminals."""
        return {b.terminal: b.value for b in self.resolved_bindings}

    def unresolved_names(self) -> tuple[str, ...]:
        """Names of remaining open terminals on the residual frontier."""
        return tuple(r.name for r in self.unresolved)
