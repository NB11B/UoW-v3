"""R7 additive Python facade for the validated language-neutral UoW architecture.

Research-only during R7. It re-exports validated R6 seams without changing the
canonical src/uow public API.
"""

from .application import ApplicationSpine, CursorPolicy, DEFAULT_APPLICATION_SPINE, SpineResult
from .authority import QuorumAuthorityProvider, submit_via_authority_provider
from .conformance import (
    ConformanceDomain,
    ConformanceRegistry,
    DEFAULT_CONFORMANCE_REGISTRY,
    build_default_registry,
)

__all__ = [
    "ApplicationSpine",
    "CursorPolicy",
    "DEFAULT_APPLICATION_SPINE",
    "SpineResult",
    "QuorumAuthorityProvider",
    "submit_via_authority_provider",
    "ConformanceDomain",
    "ConformanceRegistry",
    "DEFAULT_CONFORMANCE_REGISTRY",
    "build_default_registry",
]
