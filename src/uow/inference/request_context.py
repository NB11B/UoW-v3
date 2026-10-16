"""Request and Response Context Specification for uow.inference.v1."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import json


@dataclass(frozen=True)
class StateReference:
    """Cryptographic reference to the current UoW transaction state."""
    state_hash: str
    sequence: int

    def to_dict(self) -> dict[str, Any]:
        return {"hash": self.state_hash, "sequence": self.sequence}


@dataclass(frozen=True)
class CapabilityTarget:
    """Target capability requested for the inference transaction."""
    domain: str
    grammar: str
    version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InferenceRequest:
    """Model-independent work request entering the inference gateway."""
    protocol: str = "uow.inference.v1"
    request_id: str = ""
    state: Optional[StateReference] = None
    capability: Optional[CapabilityTarget] = None
    input_data: dict[str, Any] = field(default_factory=dict)
    prompt_text: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "request_id": self.request_id,
            "state": self.state.to_dict() if self.state else None,
            "capability": self.capability.to_dict() if self.capability else None,
            "input": self.input_data,
            "prompt_text": self.prompt_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InferenceRequest:
        state_data = data.get("state")
        state = StateReference(state_hash=state_data.get("hash", ""), sequence=state_data.get("sequence", 0)) if state_data else None

        cap_data = data.get("capability")
        cap = CapabilityTarget(**cap_data) if cap_data else None

        return cls(
            protocol=data.get("protocol", "uow.inference.v1"),
            request_id=data.get("request_id", ""),
            state=state,
            capability=cap,
            input_data=data.get("input", {}),
            prompt_text=data.get("prompt_text"),
        )


@dataclass(frozen=True)
class TypedProposal:
    """Advisory, unprivileged proposal emitted by a neural specialist."""
    proposal_type: str = "PROPOSAL"
    grammar: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    confidence_status: str = "UNVERIFIED"
    requires_certification: bool = True

    def to_dict(self) -> dict[str, Any]:
        d = {"type": self.proposal_type, "grammar": self.grammar}
        d.update(self.payload)
        d["confidence_status"] = self.confidence_status
        d["requires_certification"] = self.requires_certification
        return d


@dataclass(frozen=True)
class InferenceResponse:
    """Standardized response from the uow.inference.v1 gateway."""
    protocol: str = "uow.inference.v1"
    request_id: str = ""
    result: Optional[TypedProposal] = None
    provenance: dict[str, Any] = field(default_factory=dict)
    status: str = "OK"  # OK | REJECTED | CLARIFICATION_REQUIRED | ERROR
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "request_id": self.request_id,
            "status": self.status,
            "result": self.result.to_dict() if self.result else None,
            "provenance": self.provenance,
            "error_message": self.error_message,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
