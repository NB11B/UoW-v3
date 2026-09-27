"""Authoritative UoW lifecycle integration for certified semantic intents."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .compiler import SemanticUoWCompiler
from .schema import IntentEnvelope, SemanticDisposition, SemanticResult
from ..application import ApplicationResult, ApplicationSpine, CursorPolicy, DEFAULT_APPLICATION_SPINE
from ..contracts import UoW
from ..state import WorldState
from ..transactions.protocol import CommitSequencer


class SemanticStateDriftError(ValueError):
    """Raised when authoritative state drifts before a prepared semantic UoW is applied."""


@dataclass(frozen=True)
class PreparedSemanticUoW:
    """Deterministic pairing of compiled native UoW and cryptographic state binding."""

    uow: UoW
    semantic_certificate_hash: str
    expected_state_hash: str
    signal_id: str
    compiler_id: str


class SemanticApplicationAdapter:
    """Adapter bridging certified semantic results into the authoritative ApplicationSpine.

    Enforces:
    1. Pre-execution state-hash verification: Cert_S(X, S_t) cannot be applied to S_{t+k} without revalidation.
    2. Zero commit authority: Delegates 100% of execution, certification, and commit to ApplicationSpine.
    """

    def __init__(self, application_spine: ApplicationSpine | None = None) -> None:
        self.application_spine = application_spine or DEFAULT_APPLICATION_SPINE

    def prepare(
        self,
        result: SemanticResult,
        state: WorldState,
        compiler: SemanticUoWCompiler,
    ) -> PreparedSemanticUoW:
        if result.disposition is not SemanticDisposition.YES or result.intent is None:
            raise ValueError("Only semantic YES may be prepared for native UoW application.")

        if state.state_hash != result.certificate.state_hash:
            raise SemanticStateDriftError(
                f"State hash mismatch at preparation: current state is {state.state_hash}, "
                f"certificate was evaluated against {result.certificate.state_hash}."
            )

        actual_compiler = compiler
        if hasattr(compiler, "resolve") and callable(getattr(compiler, "resolve")):
            actual_compiler = compiler.resolve(result.intent)

        uow = actual_compiler.compile(result.intent, state)
        return PreparedSemanticUoW(
            uow=uow,
            semantic_certificate_hash=result.certificate.certificate_hash,
            expected_state_hash=state.state_hash,
            signal_id=result.intent.signal_id,
            compiler_id=actual_compiler.compiler_id,
        )

    def execute(
        self,
        prepared: PreparedSemanticUoW,
        sequencer: CommitSequencer,
        *,
        cursor_policy: CursorPolicy = CursorPolicy.DETACHED,
    ) -> ApplicationResult:
        # Pre-execution state drift check: fail-closed before invoking ApplicationSpine
        current_state = sequencer.current_state
        if current_state.state_hash != prepared.expected_state_hash:
            raise SemanticStateDriftError(
                f"State drift detected before execution: sequencer state is {current_state.state_hash}, "
                f"prepared UoW expected {prepared.expected_state_hash}."
            )

        # Delegate execution directly to ApplicationSpine without implementing commit logic
        return self.application_spine.execute(
            prepared.uow,
            sequencer,
            cursor_policy=cursor_policy,
        )
