"""Compatibility shim for the historical proposer engine path."""

from ..implementations.adaptation.runtime import (
    ProposerOrchestrationEngine,
    run_proposer_orchestration,
)

__all__ = ["ProposerOrchestrationEngine", "run_proposer_orchestration"]
