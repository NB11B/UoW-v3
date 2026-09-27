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
    SemanticAlternative,
    SemanticBinding,
    SemanticDisposition,
    SemanticRequirement,
    SemanticResult,
    SemanticTranslationRequest,
)
from .translator import NullSemanticTranslator, SemanticTranslator
from .validation import BindingValidationResult, SemanticBindingValidator, ValidationVerdict
from ..state import WorldState


class SemanticHarness:
    """Interpret external communication without acquiring execution authority."""

    def __init__(
        self,
        translator: SemanticTranslator | None = None,
        *,
        admissibility_validator: SemanticBindingValidator | None = None,
        context_projector: SemanticContextProjector | None = None,
        frontier_builder: SemanticFrontierBuilder | None = None,
    ) -> None:
        self._translator = translator or NullSemanticTranslator()
        self._admissibility_validator = admissibility_validator
        self._context_projector = context_projector or SemanticContextProjector()
        self._frontier_builder = frontier_builder or SemanticFrontierBuilder()
        self._closure_engine = SemanticClosureEngine(self._frontier_builder)

    def _filter_admissibility(
        self,
        translation: CandidateSemanticBindings,
        requirements: tuple[SemanticRequirement, ...],
        state: WorldState,
    ) -> CandidateSemanticBindings:
        if self._admissibility_validator is None:
            return translation

        req_by_name = {r.name: r for r in requirements}
        admitted: list[SemanticBinding] = []
        new_unknowns: list[str] = list(translation.unknowns)
        new_alternatives: list[SemanticAlternative] = list(translation.alternatives)

        for b in translation.candidate_bindings:
            req = req_by_name.get(b.terminal)
            if req is None:
                if b.terminal not in new_unknowns:
                    new_unknowns.append(b.terminal)
                continue
            res = self._admissibility_validator.validate(b, req, state)
            if res.verdict is ValidationVerdict.VALID:
                admitted.append(b)
            elif res.verdict is ValidationVerdict.UNKNOWN:
                if b.terminal not in new_unknowns:
                    new_unknowns.append(b.terminal)
            elif res.verdict is ValidationVerdict.AMBIGUOUS:
                if res.admissible_alternatives:
                    alt_bindings = [
                        SemanticAlternative(
                            bindings=(
                                SemanticBinding(
                                    terminal=b.terminal,
                                    value=alt_val,
                                    origin=b.origin,
                                    evidence_refs=("admissibility_resolver",),
                                ),
                            ),
                            reason="admissible_entity_alternative",
                        )
                        for alt_val in res.admissible_alternatives
                    ]
                    new_alternatives.extend(alt_bindings)
                else:
                    if b.terminal not in new_unknowns:
                        new_unknowns.append(b.terminal)
            elif res.verdict is ValidationVerdict.CONTRADICTORY:
                if b.terminal not in new_unknowns:
                    new_unknowns.append(b.terminal)

        return CandidateSemanticBindings(
            candidate_bindings=tuple(admitted),
            alternatives=tuple(new_alternatives),
            unknowns=tuple(new_unknowns),
            local_confidence=translation.local_confidence,
            evidence_refs=translation.evidence_refs + ("semantic_admissibility_filtered",),
        )

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
            translation = self._filter_admissibility(translation, requirements, state)
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
