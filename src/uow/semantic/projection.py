"""H6.1: Deterministic Recipient Projection for Governed Egress.

Computes:
    I_B = pi_B(I)
deterministically.

Recipient classes determine what semantic material a recipient is entitled
or required to receive. Projection strictly isolates internal WorldState,
authority graph, WAL, and sensitive evidence from unauthorized recipients.
Projection must never invoke probabilistic models.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
from typing import Any, Mapping, Optional, Tuple

from .schema import BindingOrigin, IntentEnvelope, SemanticBinding, SemanticDisposition, SemanticResult
from ..state import canonical_json


class RecipientClass(str, Enum):
    """Categorized recipient classes for deterministic projection."""

    HUMAN_REQUESTER = "human_requester"
    OPERATOR = "operator"
    MACHINE_PEER = "machine_peer"
    EXTERNAL_SERVICE = "external_service"
    AUDITOR = "auditor"


@dataclass(frozen=True)
class RecipientProfile:
    """Security and semantic entitlement profile for an egress recipient."""

    recipient_id: str
    recipient_class: RecipientClass
    allowed_terminals: Optional[Tuple[str, ...]] = None
    include_audit_evidence: bool = False
    include_system_status: bool = False
    include_hashes: bool = False

    @classmethod
    def default_human(cls, recipient_id: str = "human-user") -> RecipientProfile:
        return cls(
            recipient_id=recipient_id,
            recipient_class=RecipientClass.HUMAN_REQUESTER,
            allowed_terminals=("operator", "recipient", "quantity", "unit", "temporal", "negation", "modality", "condition"),
            include_audit_evidence=False,
            include_system_status=False,
            include_hashes=False,
        )

    @classmethod
    def default_auditor(cls, recipient_id: str = "auditor-01") -> RecipientProfile:
        return cls(
            recipient_id=recipient_id,
            recipient_class=RecipientClass.AUDITOR,
            allowed_terminals=None,  # All terminals permitted
            include_audit_evidence=True,
            include_system_status=True,
            include_hashes=True,
        )

    @classmethod
    def default_operator(cls, recipient_id: str = "operator-01") -> RecipientProfile:
        return cls(
            recipient_id=recipient_id,
            recipient_class=RecipientClass.OPERATOR,
            allowed_terminals=None,
            include_audit_evidence=True,
            include_system_status=True,
            include_hashes=True,
        )

    @classmethod
    def default_machine(cls, recipient_id: str = "machine-peer-01") -> RecipientProfile:
        return cls(
            recipient_id=recipient_id,
            recipient_class=RecipientClass.MACHINE_PEER,
            allowed_terminals=None,
            include_audit_evidence=False,
            include_system_status=True,
            include_hashes=True,
        )


@dataclass(frozen=True)
class ProjectedSemanticIntent:
    """Projected semantic intent I_B = pi_B(I) for egress."""

    recipient_id: str
    recipient_class: RecipientClass
    disposition: SemanticDisposition
    status: str
    operator: Optional[str] = None
    bindings: Mapping[str, Any] = field(default_factory=dict)
    unresolved: Tuple[str, ...] = ()
    alternatives: Tuple[str, ...] = ()
    reason: Optional[str] = None
    uow_id: Optional[str] = None
    state_hash: Optional[str] = None
    certificate_hash: Optional[str] = None
    evidence_refs: Tuple[str, ...] = ()
    projection_hash: str = ""

    def __post_init__(self) -> None:
        payload = {
            "recipient_id": self.recipient_id,
            "recipient_class": self.recipient_class.value,
            "disposition": self.disposition.value,
            "status": self.status,
            "operator": self.operator,
            "bindings": dict(sorted(self.bindings.items())),
            "unresolved": sorted(list(self.unresolved)),
            "alternatives": sorted(list(self.alternatives)),
            "reason": self.reason,
            "uow_id": self.uow_id,
            "state_hash": self.state_hash,
            "certificate_hash": self.certificate_hash,
            "evidence_refs": sorted(list(self.evidence_refs)),
        }
        computed = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        if self.projection_hash and self.projection_hash != computed:
            raise ValueError("ProjectedSemanticIntent projection_hash mismatch.")
        object.__setattr__(self, "projection_hash", computed)


class SemanticRecipientProjector:
    """Deterministic projection oracle pi_B: I -> I_B."""

    def project(
        self,
        source: SemanticResult | IntentEnvelope | Mapping[str, Any],
        recipient: RecipientProfile,
        *,
        status: str = "COMPLETED",
        reason: Optional[str] = None,
        uow_id: Optional[str] = None,
        state_hash: Optional[str] = None,
    ) -> ProjectedSemanticIntent:
        """Project semantic source into recipient-specific view I_B."""
        # 1. Extract raw semantic properties
        if isinstance(source, SemanticResult):
            disposition = source.disposition
            cert_hash = source.certificate.certificate_hash if source.certificate else None
            unresolved = tuple(r.name for r in source.unresolved)
            alternatives = tuple(
                ", ".join(f"{b.terminal}={b.value}" for b in alt.bindings)
                for alt in source.alternatives
            )
            raw_evidence = source.evidence_refs
            source_state_hash = source.certificate.state_hash if source.certificate else None

            bindings_map: dict[str, Any] = {}
            if source.intent:
                bindings_map = source.intent.binding_map()
            elif source.certificate:
                for b in source.certificate.resolved_bindings:
                    bindings_map[b.terminal] = b.value
            op = bindings_map.get("operator")

        elif isinstance(source, IntentEnvelope):
            disposition = SemanticDisposition.YES
            cert_hash = source.closure_certificate_hash
            unresolved = ()
            alternatives = ()
            raw_evidence = source.evidence_refs
            source_state_hash = None
            bindings_map = source.binding_map()
            op = bindings_map.get("operator")

        elif isinstance(source, Mapping):
            disposition = SemanticDisposition(source.get("disposition", "YES"))
            cert_hash = source.get("certificate_hash")
            unresolved = tuple(source.get("unresolved", ()))
            alternatives = tuple(source.get("alternatives", ()))
            raw_evidence = tuple(source.get("evidence_refs", ()))
            source_state_hash = source.get("state_hash")
            bindings_map = dict(source.get("bindings", {}))
            op = bindings_map.get("operator")
        else:
            raise TypeError(f"Unsupported semantic source type for projection: {type(source)}")

        # 2. Filter bindings by recipient entitlement
        if recipient.allowed_terminals is not None:
            filtered_bindings = {
                k: v for k, v in bindings_map.items()
                if k in recipient.allowed_terminals
            }
        else:
            filtered_bindings = dict(bindings_map)

        # 3. Filter audit evidence by recipient entitlement
        if recipient.include_audit_evidence:
            filtered_evidence = raw_evidence
        else:
            filtered_evidence = ()

        # 4. Filter hashes by recipient entitlement
        effective_cert_hash = cert_hash if recipient.include_hashes else None
        effective_state_hash = (state_hash or source_state_hash) if recipient.include_hashes else None
        effective_uow_id = uow_id if recipient.include_hashes else None

        # 5. Determine effective status
        if disposition is SemanticDisposition.CLARIFY:
            effective_status = "CLARIFICATION_REQUIRED"
        elif disposition is SemanticDisposition.NO:
            effective_status = "REJECTED"
        else:
            effective_status = status

        return ProjectedSemanticIntent(
            recipient_id=recipient.recipient_id,
            recipient_class=recipient.recipient_class,
            disposition=disposition,
            status=effective_status,
            operator=str(op) if op is not None else None,
            bindings=filtered_bindings,
            unresolved=unresolved,
            alternatives=alternatives,
            reason=reason,
            uow_id=effective_uow_id,
            state_hash=effective_state_hash,
            certificate_hash=effective_cert_hash,
            evidence_refs=filtered_evidence,
        )
