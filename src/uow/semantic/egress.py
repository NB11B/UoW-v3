"""H6: Governed Egress Engine with Deterministic Fallback and Provenance.

Coordinates:
1. Deterministic recipient projection pi_B: I -> I_B
2. Optional natural language rendering render(I_B)
3. Round-trip verification parse(render(I_B)) === I_B
4. Deterministic fallback when drift is detected (epsilon_{egress-drift} = 0)
5. Cryptographic audit provenance chaining linking egress message to UoW execution
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Optional, Tuple

from .projection import ProjectedSemanticIntent, RecipientProfile, SemanticRecipientProjector
from .rendering import DeterministicEgressFormatter, SemanticRenderer
from .roundtrip import SemanticRoundTripResult, SemanticRoundTripVerifier
from .schema import IntentEnvelope, SemanticResult
from ..state import canonical_json


@dataclass(frozen=True)
class GovernedEgressMessage:
    """Certified governed egress message delivered to an external recipient."""

    text: str
    projected: ProjectedSemanticIntent
    mode: str  # "DETERMINISTIC", "NATURAL_VERIFIED", "DETERMINISTIC_FALLBACK"
    roundtrip_verified: bool
    drift_detected: bool
    fallback_reason: Optional[str] = None
    evidence_refs: Tuple[str, ...] = ()
    egress_hash: str = ""

    def __post_init__(self) -> None:
        payload = {
            "text": self.text,
            "projection_hash": self.projected.projection_hash,
            "mode": self.mode,
            "roundtrip_verified": self.roundtrip_verified,
            "drift_detected": self.drift_detected,
            "fallback_reason": self.fallback_reason,
            "evidence_refs": sorted(list(self.evidence_refs)),
        }
        computed = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        if self.egress_hash and self.egress_hash != computed:
            raise ValueError("GovernedEgressMessage egress_hash mismatch.")
        object.__setattr__(self, "egress_hash", computed)


class GovernedEgressEngine:
    """Authoritative semantic egress boundary enforcing the zero-drift invariant."""

    def __init__(
        self,
        projector: Optional[SemanticRecipientProjector] = None,
        formatter: Optional[DeterministicEgressFormatter] = None,
        verifier: Optional[SemanticRoundTripVerifier] = None,
        renderer: Optional[SemanticRenderer] = None,
    ) -> None:
        self.projector = projector or SemanticRecipientProjector()
        self.formatter = formatter or DeterministicEgressFormatter()
        self.verifier = verifier or SemanticRoundTripVerifier()
        self.renderer = renderer

    def emit(
        self,
        source: SemanticResult | IntentEnvelope | Mapping[str, Any],
        recipient: RecipientProfile,
        *,
        use_natural_language: bool = False,
        status: str = "COMPLETED",
        reason: Optional[str] = None,
        uow_id: Optional[str] = None,
        state_hash: Optional[str] = None,
    ) -> GovernedEgressMessage:
        """Project, render, verify, and emit a governed semantic message."""
        # 1. Deterministic recipient projection: I_B = pi_B(I)
        projected = self.projector.project(
            source,
            recipient,
            status=status,
            reason=reason,
            uow_id=uow_id,
            state_hash=state_hash,
        )

        # 2. Pure deterministic mode (default, model calls = 0)
        if not use_natural_language or self.renderer is None:
            text = self.formatter.format(projected)
            provenance = self._build_provenance(projected, mode="DETERMINISTIC", verified=True)
            return GovernedEgressMessage(
                text=text,
                projected=projected,
                mode="DETERMINISTIC",
                roundtrip_verified=True,
                drift_detected=False,
                fallback_reason=None,
                evidence_refs=provenance,
            )

        # 3. Natural language rendering with round-trip verification
        try:
            rendered_text = self.renderer.render(projected)
        except Exception as e:
            # Renderer crash / exception: immediate deterministic fallback
            text = self.formatter.format(projected)
            fallback_msg = f"RendererException: {type(e).__name__}: {e}"
            provenance = self._build_provenance(projected, mode="DETERMINISTIC_FALLBACK", verified=False, note=fallback_msg)
            return GovernedEgressMessage(
                text=text,
                projected=projected,
                mode="DETERMINISTIC_FALLBACK",
                roundtrip_verified=False,
                drift_detected=True,
                fallback_reason=fallback_msg,
                evidence_refs=provenance,
            )

        # 4. Mandatory round-trip verification: parse(render(I_B)) === I_B
        rt_result = self.verifier.verify(projected, rendered_text)

        if rt_result.verified:
            # Verification passed with epsilon_drift = 0
            provenance = self._build_provenance(projected, mode="NATURAL_VERIFIED", verified=True)
            return GovernedEgressMessage(
                text=rendered_text,
                projected=projected,
                mode="NATURAL_VERIFIED",
                roundtrip_verified=True,
                drift_detected=False,
                fallback_reason=None,
                evidence_refs=provenance,
            )
        else:
            # Drift detected! Reject natural output and fall back deterministically
            fallback_text = self.formatter.format(projected)
            drift_reasons = "; ".join(rt_result.mismatches)
            fallback_msg = f"EgressDriftRejected: {drift_reasons}"
            provenance = self._build_provenance(projected, mode="DETERMINISTIC_FALLBACK", verified=False, note=fallback_msg)
            return GovernedEgressMessage(
                text=fallback_text,
                projected=projected,
                mode="DETERMINISTIC_FALLBACK",
                roundtrip_verified=False,
                drift_detected=True,
                fallback_reason=fallback_msg,
                evidence_refs=provenance,
            )

    def _build_provenance(
        self,
        projected: ProjectedSemanticIntent,
        mode: str,
        verified: bool,
        note: Optional[str] = None,
    ) -> Tuple[str, ...]:
        """Construct unbroken cryptographic audit trail from egress back to UoW execution."""
        refs: list[str] = list(projected.evidence_refs)
        refs.append(f"projection:{projected.projection_hash}")
        refs.append(f"egress_mode:{mode}")
        refs.append(f"roundtrip_verified:{str(verified).lower()}")
        if projected.uow_id:
            refs.append(f"uow:{projected.uow_id}")
        if projected.state_hash:
            refs.append(f"state:{projected.state_hash}")
        if projected.certificate_hash:
            refs.append(f"cert:{projected.certificate_hash}")
        if note:
            digest = hashlib.sha256(note.encode("utf-8")).hexdigest()[:16]
            refs.append(f"fallback_note_hash:{digest}")
        return tuple(dict.fromkeys(refs))
