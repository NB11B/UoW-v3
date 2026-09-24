"""R7/relocation facade for the production common application seam."""

from uow.application import (
    ApplicationResult,
    ApplicationSpine,
    CursorPolicy,
    DEFAULT_APPLICATION_SPINE,
)

SpineResult = ApplicationResult

__all__ = [
    "ApplicationResult",
    "ApplicationSpine",
    "CursorPolicy",
    "DEFAULT_APPLICATION_SPINE",
    "SpineResult",
]
