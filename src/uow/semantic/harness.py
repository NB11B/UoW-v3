"""Bounded semantic ingress harness."""
from __future__ import annotations

from .clarification import (
    ClarificationContext,
    ContradictoryContinuationError,
    StaleClarificationError,
)
from .closure import SemanticClosureEngine
from .context import SemanticContextProjector
from .frontier import SemanticFrontierBuilder
from .schema import (
    BindingOrigin,
    CandidateSemanticBindings,
    ExternalSignal,
    IngressContext,
    IntentEnvelope,
    MinimalSemanticContext,
    SemanticAlternative,
    SemanticBinding,
    SemanticClosureCertificate,
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

    def continue_interpretation(
        self,
        signal: str | ExternalSignal,
        *,
        clarification: ClarificationContext,
        state: WorldState,
        ingress: IngressContext,
    ) -> SemanticResult:
        """Continue a partial semantic closure over the residual frontier.

        Enforces:
        1. Pre-condition state-drift check: state.state_hash == clarification.original_state_hash
        2. Residual frontier isolation: resolved_t cap F_{P, t+1} = empty
        3. Contradiction rejection: continuation cannot alter previously resolved bindings
        4. Provenance tracking: combines original signal and continuation audit trails
        """
        # 1. State drift pre-execution check: fail-closed if state drifted between turns
        if state.state_hash != clarification.original_state_hash:
            raise StaleClarificationError(
                f"State drift detected during clarification: clarification was evaluated against "
                f"state {clarification.original_state_hash}, but current state is {state.state_hash}."
            )

        continuation_signal = signal if isinstance(signal, ExternalSignal) else ExternalSignal(signal)
        raw_text = continuation_signal.raw.strip()

        residual_requirements = clarification.unresolved
        if not residual_requirements:
            raise ValueError("Clarification has no open residual requirements to resolve.")

        # Invariant: resolved_t cap F_{P, t+1} = empty
        residual_req_names = {r.name for r in residual_requirements}
        already_resolved_names = {b.terminal for b in clarification.resolved_bindings}
        overlap = residual_req_names & already_resolved_names
        if overlap:
            raise ValueError(
                f"Invariant violation: residual frontier overlaps with already resolved bindings: {overlap}"
            )

        # 2. Check for direct alternative selection
        matched_alt_bindings: list[SemanticBinding] | None = None
        if clarification.alternatives:
            for alt in clarification.alternatives:
                for b in alt.bindings:
                    if raw_text.lower() == str(b.value).lower():
                        matched_alt_bindings = list(alt.bindings)
                        break
                if matched_alt_bindings is not None:
                    break

        if matched_alt_bindings is not None:
            translation = CandidateSemanticBindings(
                candidate_bindings=tuple(matched_alt_bindings),
                evidence_refs=("alternative_direct_match",),
            )
        else:
            # 3. Probabilistic proposal over RESIDUAL frontier ONLY
            minimal_context = MinimalSemanticContext(
                state_hash=state.state_hash,
                state_sequence=state.sequence,
                bindings=tuple(
                    b for b in clarification.resolved_bindings
                    if b.origin is BindingOrigin.DETERMINISTIC
                ),
                evidence_refs=clarification.evidence_refs,
            )
            translation = self._translator.propose(
                SemanticTranslationRequest(
                    signal=continuation_signal,
                    minimal_context=minimal_context,
                    frontier=residual_requirements,
                )
            )
            if not isinstance(translation, CandidateSemanticBindings):
                raise TypeError(
                    "SemanticTranslator.propose() must return CandidateSemanticBindings."
                )

        # 4. Contradiction Check: continuation must not contradict previously resolved bindings
        already_resolved_map = clarification.resolved_map()
        for b in translation.candidate_bindings:
            if b.terminal in already_resolved_map and b.value != already_resolved_map[b.terminal]:
                raise ContradictoryContinuationError(
                    f"Continuation contradicts previously resolved terminal {b.terminal!r}: "
                    f"existing={already_resolved_map[b.terminal]!r}, proposed={b.value!r}."
                )

        # 5. Admissibility validation over candidate bindings
        translation = self._filter_admissibility(translation, residual_requirements, state)

        # 6. Reconstitute complete requirements and build closure
        det_bindings = tuple(
            b for b in clarification.resolved_bindings
            if b.origin is BindingOrigin.DETERMINISTIC
        )
        prob_seed_bindings = tuple(
            b for b in clarification.resolved_bindings
            if b.origin is BindingOrigin.PROBABILISTIC
        )

        all_requirements = tuple(
            SemanticRequirement(name=b.terminal, required=True)
            for b in clarification.resolved_bindings
        ) + residual_requirements

        closure_context = MinimalSemanticContext(
            state_hash=state.state_hash,
            state_sequence=state.sequence,
            bindings=det_bindings,
            evidence_refs=clarification.evidence_refs,
        )

        initial_frontier = self._frontier_builder.build(
            all_requirements,
            closure_context,
        )

        combined_translation = CandidateSemanticBindings(
            candidate_bindings=prob_seed_bindings + translation.candidate_bindings,
            alternatives=translation.alternatives,
            unknowns=translation.unknowns,
            local_confidence=translation.local_confidence,
            evidence_refs=translation.evidence_refs,
        )

        outcome = self._closure_engine.close(
            signal=continuation_signal,
            requirements=all_requirements,
            context=closure_context,
            initial_frontier=initial_frontier,
            translation=combined_translation,
        )

        # 7. Form IntentEnvelope with full audit provenance if YES
        provenance_refs = tuple(
            dict.fromkeys(
                outcome.certificate.evidence_refs
                + clarification.evidence_refs
                + (
                    f"clarification:{clarification.clarification_id}",
                    f"original_signal:{clarification.original_signal_id}",
                    f"continuation_turn:{clarification.turn + 1}",
                )
            )
        )

        updated_cert = SemanticClosureCertificate(
            disposition=outcome.certificate.disposition,
            state_hash=outcome.certificate.state_hash,
            signal_id=continuation_signal.signal_id,
            resolved_bindings=outcome.certificate.resolved_bindings,
            probabilistic_bindings=outcome.certificate.probabilistic_bindings,
            unresolved=outcome.certificate.unresolved,
            reason_codes=outcome.certificate.reason_codes,
            evidence_refs=provenance_refs,
        )

        intent = None
        if updated_cert.disposition is SemanticDisposition.YES:
            intent = IntentEnvelope(
                signal_id=continuation_signal.signal_id,
                source_signal=continuation_signal.raw,
                principal_id=ingress.principal_id,
                session_id=ingress.session_id,
                channel=ingress.channel,
                bindings=updated_cert.resolved_bindings,
                closure_certificate_hash=updated_cert.certificate_hash,
                evidence_refs=provenance_refs,
            )

        unresolved_by_name = {
            requirement.name: requirement for requirement in all_requirements
        }
        unresolved = tuple(
            unresolved_by_name[name]
            for name in updated_cert.unresolved
            if name in unresolved_by_name
        )

        return SemanticResult(
            disposition=updated_cert.disposition,
            intent=intent,
            unresolved=unresolved,
            alternatives=translation.alternatives,
            certificate=updated_cert,
            evidence_refs=provenance_refs,
        )
