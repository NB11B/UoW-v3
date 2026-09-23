"""Portable distributed-authority qualification package.

This package is a research/qualification realization, not a canonical UoW
runtime dependency. It exercises independent authority replicas, quorum
certification, replicated evidence, partition behavior, and bounded self-healing.
"""
from .authority import (
    AuthorityNode,
    AuthorityVote,
    DistributedAuthorityCluster,
    JournalEntry,
    NodeMode,
    QuorumCertificate,
    RoundResult,
    proposal_digest,
)
from .network import (
    HealingAction,
    HealingResult,
    NetworkFabric,
    SelfHealingController,
)

__all__ = [
    "AuthorityNode",
    "AuthorityVote",
    "DistributedAuthorityCluster",
    "HealingAction",
    "HealingResult",
    "JournalEntry",
    "NetworkFabric",
    "NodeMode",
    "QuorumCertificate",
    "RoundResult",
    "SelfHealingController",
    "proposal_digest",
]
