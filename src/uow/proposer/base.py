"""Abstract protocol and base classes for external and learned proposers (Gate U14)."""
from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from ..state import WorldState
from .identity import ModelIdentity
from .observation import AdaptationObservation
from .types import ModelProposal


@runtime_checkable
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


@runtime_checkable
class AdaptiveProposer(BaseProposer, Protocol):
    """Abstract interface for continual learning and adaptive proposers (Gate U15.1).

    The adaptive proposer has ZERO commit authority over world state.
    The fundamental architectural separation is:
        propose()           -> allowed to influence candidate selection
        observe_feedback()  -> allowed to collect certified evidence
        update()            -> allowed to modify internal model parameters

        commit()            -> DOES NOT EXIST HERE
        mutate_world()      -> DOES NOT EXIST HERE

    An adaptive model gets exactly the same authority as a static model: ZERO.
    """

    def model_identity(self) -> ModelIdentity:
        """Returns the current cryptographic identity and lineage of this model."""
        ...

    def observe_feedback(self, observation: AdaptationObservation) -> None:
        """Collects verified deterministic judge feedback for training.

        Must not mutate world state.
        """
        ...

    def update(self) -> ModelIdentity:
        """Performs atomic parameter update or model checkpoint transition.

        Returns the new ModelIdentity for generation theta_{t+1}.
        Must not mutate world state.
        """
        ...
