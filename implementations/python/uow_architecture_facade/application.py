"""R7 facade for the validated common authority-application seam."""

from uow_shadow.spine import (
    ApplicationSpine,
    CursorPolicy,
    DEFAULT_APPLICATION_SPINE,
    SpineResult,
)

__all__ = [
    "ApplicationSpine",
    "CursorPolicy",
    "DEFAULT_APPLICATION_SPINE",
    "SpineResult",
]
