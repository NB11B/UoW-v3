"""Typed semantic mediation contracts for the UoW semantic harness.

These objects are deliberately non-authoritative. They describe candidate
semantic material and deterministic closure evidence; authoritative mutation
continues to belong to the native UoW PROPOSE -> CERTIFY -> COMMIT lifecycle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
from typing import Any, Mapping, Optional, Tuple

from ..state import canonical_json


class SemanticDisposition(str, Enum):
    YES = "YES"
    NO = "NO"
    CLARIFY = "CLARIFY"


class BindingOrigin(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    PROBABILISTIC = "PROBABILISTIC"
    DERIVED = "DERIVED"


class SemanticInvariantError(ValueError):
    """Raised when semantic mediation attempts to violate a structural invariant."""


@dataclass(frozen=True)
class ExternalSignal:
    raw: str
    signal_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.raw, str) or not self.raw:
            raise ValueError("ExternalSignal.raw must be a non-empty string.")
        if not self.signal_id:
            digest = hashlib.sha256(self.raw.encode("utf-8")).hexdigest()
            object.__setattr__(self, "signal_id", digest)


@dataclass(frozen=True)
class IngressContext:
    principal_id: str
    session_id: str
    channel: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    evidence_refs: Tuple[str, ...] = ()

    def lookup(self, key: str) -> tuple[bool, Any]:
        if key == "principal_id":
            return True, self.principal_id
        if key == "session_id":
            return True, self.session_id
        if key == "channel":
            return True, self.channel
        if key in self.metadata:
            return True, self.metadata[key]
        return False, None


@dataclass(frozen=True)
class SemanticRequirement:
    """One semantic terminal required for safe proposal formation.

    A requirement may optionally bind directly to one authoritative WorldState
    key or one ingress-context key. Leaving both unset deliberately places the
    terminal on the probabilistic frontier unless a deterministic resolver can
    derive it from other bindings.
    """

    name: str
    state_key: Optional[str] = None
    ingress_key: Optional[str] = None
    required: bool = True

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("SemanticRequirement.name must be non-empty.")
        if self.state_key and self.ingress_key:
            raise ValueError(
                "SemanticRequirement may declare at most one direct deterministic source."
            )


@dataclass(frozen=True)
class SemanticBinding:
    terminal: str
    value: Any
    origin: BindingOrigin
    evidence_refs: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.terminal:
            raise ValueError("SemanticBinding.terminal must be non-empty.")
        canonical_json(self.value)


@dataclass(frozen=True)
class SemanticAlternative:
    bindings: Tuple[SemanticBinding, ...]
    reason: str = ""


@dataclass(frozen=True)
class MinimalSemanticContext:
    state_hash: str
    state_sequence: int
    bindings: Tuple[SemanticBinding, ...] = ()
    evidence_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticFrontierResult:
    resolved: Tuple[SemanticBinding, ...]
    frontier: Tuple[SemanticRequirement, ...]
    deterministic_evidence: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticTranslationRequest:
    signal: ExternalSignal
    minimal_context: MinimalSemanticContext
    frontier: Tuple[SemanticRequirement, ...]


@dataclass(frozen=True)
class CandidateSemanticBindings:
    candidate_bindings: Tuple[SemanticBinding, ...] = ()
    alternatives: Tuple[SemanticAlternative, ...] = ()
    unknowns: Tuple[str, ...] = ()
    local_confidence: Mapping[str, float] = field(default_factory=dict)
    evidence_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticClosureCertificate:
    disposition: SemanticDisposition
    state_hash: str
    signal_id: str
    resolved_bindings: Tuple[SemanticBinding, ...]
    probabilistic_bindings: Tuple[SemanticBinding, ...]
    unresolved: Tuple[str, ...]
    reason_codes: Tuple[str, ...] = ()
    evidence_refs: Tuple[str, ...] = ()
    certificate_hash: str = ""

    def __post_init__(self) -> None:
        payload = {
            "disposition": self.disposition.value,
            "state_hash": self.state_hash,
            "signal_id": self.signal_id,
            "resolved_bindings": [
                {
                    "terminal": binding.terminal,
                    "value": binding.value,
                    "origin": binding.origin.value,
                    "evidence_refs": list(binding.evidence_refs),
                }
                for binding in self.resolved_bindings
            ],
            "probabilistic_bindings": [
                {
                    "terminal": binding.terminal,
                    "value": binding.value,
                    "origin": binding.origin.value,
                    "evidence_refs": list(binding.evidence_refs),
                }
                for binding in self.probabilistic_bindings
            ],
            "unresolved": list(self.unresolved),
            "reason_codes": list(self.reason_codes),
            "evidence_refs": list(self.evidence_refs),
        }
        expected = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        if self.certificate_hash and self.certificate_hash != expected:
            raise ValueError("Semantic closure certificate hash does not match contents.")
        object.__setattr__(self, "certificate_hash", expected)


@dataclass(frozen=True)
class IntentEnvelope:
    signal_id: str
    source_signal: str
    principal_id: str
    session_id: str
    channel: str
    bindings: Tuple[SemanticBinding, ...]
    closure_certificate_hash: str
    evidence_refs: Tuple[str, ...] = ()

    def binding_map(self) -> dict[str, Any]:
        return {binding.terminal: binding.value for binding in self.bindings}


@dataclass(frozen=True)
class SemanticResult:
    disposition: SemanticDisposition
    intent: Optional[IntentEnvelope]
    unresolved: Tuple[SemanticRequirement, ...]
    alternatives: Tuple[SemanticAlternative, ...]
    certificate: SemanticClosureCertificate
    evidence_refs: Tuple[str, ...] = ()
