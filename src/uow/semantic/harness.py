"""Bounded semantic ingress harness."""
from __future__ import annotations

from .closure import SemanticClosureEngine
from .context import SemanticContextProjector
from .frontier import SemanticFrontierBuilder
from .schema import (
    CandidateSemanticBindings,
    ExternalSignal,
    IngressContext,
    IntentEnvelope,
    SemanticDisposition,
    SemanticRequirement,
    SemanticResult,
    SemanticTranslationRequest,
)
from .translator import NullSemanticTranslator, SemanticTranslator
from ..state import WorldState


class SemanticHarness:
    """Interpret external communication without acquiring execution authority."""

    def __init__(
        self,
        translator: SemanticTranslator | None = None,
        *,
        context_projector: SemanticContextProjector | None = None,
        frontier_builder: SemanticFrontierBuilder | None = None,
    ) -> None:
        self._translator = translator or NullSemanticTranslator()
        self._context_projector = context_projector or SemanticContextProjector()
        self._frontier_builder = frontier_builder or SemanticFrontierBuilder()
        self._closure_engine = SemanticClosureEngine(self._frontier_builder)

    def interpret(
        self,
        signal: str | ExternalSignal,
        *,
        state: WorldState,
        ingress: IngressContext,
        requirements: tuple[SemanticRequirement, ...],
    ) -> SemanticResult:
        external_signal = signal if isinstance(signal, ExternalSignal) else ExternalSignal(signal)
        context = self._context_projector.project(state, ingress, requirements)
        initial_frontier = self._frontier_builder.build(requirements, context)

        if initial_frontier.frontier:
            translation = self._translator.propose(
                SemanticTranslationRequest(
                    signal=external_signal,
                    minimal_context=context,
                    frontier=initial_frontier.frontier,
                )
            )
            if not isinstance(translation, CandidateSemanticBindings):
                raise TypeError(
                    "SemanticTranslator.propose() must return CandidateSemanticBindings."
                )
        else:
            translation = CandidateSemanticBindings()

        outcome = self._closure_engine.close(
            signal=external_signal,
            requirements=requirements,
            context=context,
            initial_frontier=initial_frontier,
            translation=translation,
        )

        intent = None
        if outcome.certificate.disposition is SemanticDisposition.YES:
            intent = IntentEnvelope(
                signal_id=external_signal.signal_id,
                source_signal=external_signal.raw,
                principal_id=ingress.principal_id,
                session_id=ingress.session_id,
                channel=ingress.channel,
                bindings=outcome.certificate.resolved_bindings,
                closure_certificate_hash=outcome.certificate.certificate_hash,
                evidence_refs=outcome.certificate.evidence_refs,
            )

        unresolved_by_name = {
            requirement.name: requirement for requirement in requirements
        }
        unresolved = tuple(
            unresolved_by_name[name]
            for name in outcome.certificate.unresolved
            if name in unresolved_by_name
        )

        return SemanticResult(
            disposition=outcome.certificate.disposition,
            intent=intent,
            unresolved=unresolved,
            alternatives=translation.alternatives,
            certificate=outcome.certificate,
            evidence_refs=outcome.certificate.evidence_refs,
        )
