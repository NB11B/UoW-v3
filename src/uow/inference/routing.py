"""Deterministic-First Capability Router with Discriminative Fallback."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from src.uow.inference.request_context import CapabilityTarget, InferenceRequest


class RoutingResolutionError(Exception):
    """Raised when capability routing fails closed due to ambiguity or unknown domain."""
    pass


class CapabilityRouter:
    """Routes work requests to specific domain-grammar adapters using deterministic-first policy."""

    SUPPORTED_GRAMMARS = {"operational", "temporal", "recovery"}

    def __init__(
        self,
        registered_capabilities: Optional[dict[str, tuple[str, str]]] = None,
        allow_dynamic_domains: bool = True,
    ) -> None:
        # Map of explicit capability keys -> (domain, grammar)
        self.registered_capabilities = registered_capabilities or {
            "industrial.operational": ("industrial", "operational"),
            "industrial.temporal": ("industrial", "temporal"),
            "industrial.recovery": ("industrial", "recovery"),
            "cybersecurity.operational": ("cybersecurity", "operational"),
            "cybersecurity.temporal": ("cybersecurity", "temporal"),
            "cybersecurity.recovery": ("cybersecurity", "recovery"),
            "logistics.operational": ("logistics", "operational"),
            "logistics.temporal": ("logistics", "temporal"),
            "logistics.recovery": ("logistics", "recovery"),
        }
        self.allow_dynamic_domains = allow_dynamic_domains

    def register_capability(self, domain: str, grammar: str) -> None:
        """Dynamically registers a domain-grammar capability pair."""
        key = f"{domain.lower()}.{grammar.lower()}"
        self.registered_capabilities[key] = (domain.lower(), grammar.lower())

    def route_request(self, request: InferenceRequest) -> tuple[str, str]:
        """Resolves target (domain, grammar) fail-closed.
        
        Resolution priority:
        1. Explicit capability target in request.
        2. Deterministic rule classification on input signal / payload keywords.
        3. Fails closed with RoutingResolutionError.
        """
        # 1. Explicit capability target
        if request.capability is not None:
            dom = request.capability.domain.lower()
            gram = request.capability.grammar.lower()
            key = f"{dom}.{gram}"
            if key in self.registered_capabilities:
                return dom, gram
            if self.allow_dynamic_domains and gram in self.SUPPORTED_GRAMMARS:
                return dom, gram
            raise RoutingResolutionError(f"Requested capability '{key}' is not registered in capability magazine")

        # 2. Deterministic rule classification based on input data
        input_data = request.input_data or {}
        text = str(request.prompt_text or input_data.get("signal", "")).lower()

        detected_domain = None
        if any(w in text for w in ["refinery", "pressure", "hydrocracker", "turbine", "valve", "sensor", "vibration", "interlock"]):
            detected_domain = "industrial"
        elif any(w in text for w in ["firewall", "quarantine", "endpoint", "cve", "ddos", "ransomware", "soc", "intrusion"]):
            detected_domain = "cybersecurity"
        elif any(w in text for w in ["shipment", "transit", "warehouse", "freight", "customs", "delivery", "container", "dock"]):
            detected_domain = "logistics"
        elif any(w in text for w in ["biomedical", "patient", "clinical", "infusion", "hemodialysis", "dosage"]):
            detected_domain = "biomedical"

        detected_grammar = None
        if any(w in text for w in ["timeout", "timed out", "retry", "failure", "compensate", "abort", "fallback"]):
            detected_grammar = "recovery"
        elif any(w in text for w in ["deadline", "before", "after", "schedule", "window", "concurrent"]):
            detected_grammar = "temporal"
        elif any(w in text for w in ["propose", "action", "disposition", "commit", "halt", "alert", "command"]):
            detected_grammar = "operational"

        if detected_domain and detected_grammar:
            key = f"{detected_domain}.{detected_grammar}"
            if key in self.registered_capabilities:
                return detected_domain, detected_grammar

        # 3. Fail closed if domain or grammar cannot be unambiguously determined
        raise RoutingResolutionError(
            f"Ambiguous or unknown work request: domain={detected_domain}, grammar={detected_grammar}. "
            "Failing closed to prevent unauthorized adapter substitution."
        )
