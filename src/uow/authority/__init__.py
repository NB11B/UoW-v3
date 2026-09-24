"""Authority-provider semantic protocols."""

from .protocol import (
    AuthorityApplyResult,
    AuthorityReplica,
    QuorumAuthorityProvider,
    QuorumRoundResult,
    authority_mode_is_active,
)

__all__ = [
    "AuthorityApplyResult",
    "AuthorityReplica",
    "QuorumAuthorityProvider",
    "QuorumRoundResult",
    "authority_mode_is_active",
]
