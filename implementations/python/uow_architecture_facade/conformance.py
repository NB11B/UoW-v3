"""R7 facade for the typed conformance-registry seam."""

from uow_shadow.conformance_registry import (
    ConformanceDomain,
    ConformanceRegistry,
    DEFAULT_CONFORMANCE_REGISTRY,
    build_default_registry,
)

__all__ = [
    "ConformanceDomain",
    "ConformanceRegistry",
    "DEFAULT_CONFORMANCE_REGISTRY",
    "build_default_registry",
]
