"""Abstract protocol and base classes for external and learned proposers (Gate U14)."""
from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence

from ..state import WorldState
from .types import ModelProposal


class BaseProposer(Protocol):
    """Abstract interface for external, learned, or stochastic proposers (Gate U14.1).

    The proposer has ZERO commit authority over world state.
    """

    def model_id(self) -> str:
        """Returns the unique identifier for this proposer model."""
        ...

    def model_version(self) -> str:
        """Returns the semantic version of this proposer model."""
        ...

    def propose(
        self,
        ready_candidates: Sequence[str],
        graph: Mapping[str, Any],
        state: WorldState,
    ) -> ModelProposal:
        """Emits a candidate schedule proposal.

        Must not mutate state or graph.
        """
        ...
