"""Compatibility shim for the historical A2 wire realization path."""

from ..realizations.network.wire import (
    AdversarialChannel,
    WireEnvelope,
    sign_envelope,
    verify_envelope,
)

__all__ = ["AdversarialChannel", "WireEnvelope", "sign_envelope", "verify_envelope"]
