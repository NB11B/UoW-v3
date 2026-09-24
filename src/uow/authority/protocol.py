"""Semantic authority-provider protocols for production runtime code.

Runtime code depends on these structural contracts rather than on qualification
packages. Qualification, physical hardware, simulation, and alternate
implementations are realizations of the same authority behavior.
"""
from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from ..contracts import UoW
from ..engine import EvidenceLedger, Proposal
from ..state import WorldState


@runtime_checkable
class AuthorityReplica(Protocol):
    state: WorldState
    ledger: EvidenceLedger
    mode: Any


@runtime_checkable
class AuthorityApplyResult(Protocol):
    applied: bool


@runtime_checkable
class QuorumRoundResult(Protocol):
    committed: bool
    quorum_certificate: Any | None
    reason: str
    reachable_nodes: Sequence[str]
    votes: Sequence[Any]
    apply_results: Mapping[str, AuthorityApplyResult]


@runtime_checkable
class QuorumAuthorityProvider(Protocol):
    nodes: Mapping[str, AuthorityReplica]

    def reachable_nodes(self) -> Sequence[str]:
        ...

    def submit(self, uow: UoW, proposal: Proposal) -> QuorumRoundResult:
        ...


def authority_mode_is_active(mode: Any) -> bool:
    """Normalize enum/string authority modes without depending on one provider."""
    return str(getattr(mode, "value", mode)) == "ACTIVE"
