"""Compatibility shim for the historical proposer-layer quorum sequencer path.

The implementation now lives under the commit-realization package.
"""
from ..realizations.commit.quorum import QuorumCommitError, QuorumCommitSequencer

__all__ = ["QuorumCommitError", "QuorumCommitSequencer"]
