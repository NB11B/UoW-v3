"""Compatibility shim for the relocated reference heuristic proposer."""

from ..realizations.scheduling.heuristic import (
    HeuristicSchedulingProposer,
    ReferenceSchedulingProposer,
)

__all__ = [
    "HeuristicSchedulingProposer",
    "ReferenceSchedulingProposer",
]
