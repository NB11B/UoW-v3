"""R7 facade for the qualification-independent authority-provider seam."""

from uow_shadow.authority_protocol import (
    QuorumAuthorityProvider,
    submit_via_authority_provider,
)

__all__ = [
    "QuorumAuthorityProvider",
    "submit_via_authority_provider",
]
