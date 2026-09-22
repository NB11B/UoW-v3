"""Backwards-compatible alias module for learned/TFWR scheduling proposers.

The reference scheduling heuristic is defined in `uow.proposer.heuristic` as
`HeuristicSchedulingProposer`. Real learned or hardware runtime adapters
(such as TFWR / NPU adapters) live under `integrations/tfwr/`.
"""
from __future__ import annotations

from .heuristic import HeuristicSchedulingProposer, ReferenceSchedulingProposer

# Backwards-compatible alias for existing imports
TFWRProposer = HeuristicSchedulingProposer

__all__ = [
    "HeuristicSchedulingProposer",
    "ReferenceSchedulingProposer",
    "TFWRProposer",
]
