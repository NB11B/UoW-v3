"""R6 prototype authority-provider protocol.

Runtime code should depend on semantic authority behavior, not on qualification
packaging. Qualification, physical hardware, and simulated clusters are
realizations of this protocol.
"""
from __future__ import annotations

from typing import Any, Protocol, Tuple, runtime_checkable

from uow.contracts import UoW
from uow.engine import Proposal


@runtime_checkable
class QuorumAuthorityProvider(Protocol):
    threshold: int

    def collect_votes(self, uow: UoW, proposal: Proposal) -> Tuple[Any, ...]:
        ...

    def form_authorization(
        self,
        uow: UoW,
        proposal: Proposal,
        votes: Tuple[Any, ...],
    ) -> Any | None:
        ...

    def apply_authorization(
        self,
        node_id: str,
        uow: UoW,
        proposal: Proposal,
        authorization: Any,
    ) -> Any:
        ...


def submit_via_authority_provider(
    provider: QuorumAuthorityProvider,
    uow: UoW,
    proposal: Proposal,
):
    """Generic quorum orchestration independent of qualification package."""
    votes = provider.collect_votes(uow, proposal)
    authorization = provider.form_authorization(uow, proposal, votes)
    if authorization is None:
        return False, None, votes, {}

    results = {}
    # Providers may expose reachability as a realization-specific extension.
    node_ids = (
        provider.reachable_nodes()
        if hasattr(provider, "reachable_nodes")
        else tuple(sorted({getattr(v, "node_id") for v in votes}))
    )
    for node_id in node_ids:
        results[node_id] = provider.apply_authorization(
            node_id,
            uow,
            proposal,
            authorization,
        )
    return True, authorization, votes, results
