"""Deterministic semantic closure oracle: YES | NO | CLARIFY."""
from __future__ import annotations

from dataclasses import dataclass

from .frontier import SemanticFrontierBuilder
from .schema import (
    BindingOrigin,
    CandidateSemanticBindings,
    ExternalSignal,
    MinimalSemanticContext,
    SemanticBinding,
    SemanticClosureCertificate,
    SemanticDisposition,
    SemanticFrontierResult,
    SemanticInvariantError,
    SemanticRequirement,
)


@dataclass(frozen=True)
class SemanticClosureOutcome:
    certificate: SemanticClosureCertificate
    frontier: SemanticFrontierResult


class SemanticClosureEngine:
    def __init__(self, frontier_builder: SemanticFrontierBuilder) -> None:
        self._frontier_builder = frontier_builder

    def close(
        self,
        *,
        signal: ExternalSignal,
        requirements: tuple[SemanticRequirement, ...],
        context: MinimalSemanticContext,
        initial_frontier: SemanticFrontierResult,
        translation: CandidateSemanticBindings,
    ) -> SemanticClosureOutcome:
        allowed_targets = {requirement.name for requirement in initial_frontier.frontier}
        probabilistic: list[SemanticBinding] = []
        reason_codes: list[str] = []

        for binding in translation.candidate_bindings:
            if binding.origin is not BindingOrigin.PROBABILISTIC:
                return self._no(
                    signal=signal,
                    context=context,
                    initial_frontier=initial_frontier,
                    probabilistic=tuple(probabilistic),
                    reason_codes=("INVALID_TRANSLATOR_BINDING_ORIGIN",),
                    translation=translation,
                )
            if binding.terminal not in allowed_targets:
                return self._no(
                    signal=signal,
                    context=context,
                    initial_frontier=initial_frontier,
                    probabilistic=tuple(probabilistic),
                    reason_codes=("FRONTIER_CONFINEMENT_VIOLATION",),
                    translation=translation,
                )
            probabilistic.append(binding)

        for unknown in translation.unknowns:
            if unknown not in allowed_targets:
                return self._no(
                    signal=signal,
                    context=context,
                    initial_frontier=initial_frontier,
                    probabilistic=tuple(probabilistic),
                    reason_codes=("UNKNOWN_OUTSIDE_FRONTIER",),
                    translation=translation,
                )

        alternative_targets: set[str] = set()
        for alternative in translation.alternatives:
            for binding in alternative.bindings:
                if binding.origin is not BindingOrigin.PROBABILISTIC:
                    return self._no(
                        signal=signal,
                        context=context,
                        initial_frontier=initial_frontier,
                        probabilistic=tuple(probabilistic),
                        reason_codes=("INVALID_ALTERNATIVE_BINDING_ORIGIN",),
                        translation=translation,
                    )
                if binding.terminal not in allowed_targets:
                    return self._no(
                        signal=signal,
                        context=context,
                        initial_frontier=initial_frontier,
                        probabilistic=tuple(probabilistic),
                        reason_codes=("ALTERNATIVE_OUTSIDE_FRONTIER",),
                        translation=translation,
                    )
                alternative_targets.add(binding.terminal)

        primary_by_terminal: dict[str, SemanticBinding] = {}
        ambiguous_terminals: set[str] = set()
        for binding in probabilistic:
            existing = primary_by_terminal.get(binding.terminal)
            if existing is None:
                primary_by_terminal[binding.terminal] = binding
            elif existing.value != binding.value:
                ambiguous_terminals.add(binding.terminal)

        if ambiguous_terminals:
            reason_codes.append("AMBIGUOUS_PRIMARY_BINDINGS")

        explicitly_open = (
            set(translation.unknowns)
            | alternative_targets
            | ambiguous_terminals
        )
        seed_bindings = tuple(
            binding
            for terminal, binding in primary_by_terminal.items()
            if terminal not in explicitly_open
        )

        try:
            final_frontier = self._frontier_builder.build(
                requirements,
                context,
                seed_bindings=seed_bindings,
            )
        except SemanticInvariantError:
            return self._no(
                signal=signal,
                context=context,
                initial_frontier=initial_frontier,
                probabilistic=tuple(probabilistic),
                reason_codes=("DETERMINISTIC_PRIMACY_VIOLATION",),
                translation=translation,
            )

        if translation.unknowns:
            reason_codes.append("EXPLICIT_UNKNOWN")
        if translation.alternatives:
            reason_codes.append("EXPLICIT_ALTERNATIVES")
        if final_frontier.frontier:
            reason_codes.append("REQUIRED_TERMINALS_OPEN")

        unresolved_names = set(requirement.name for requirement in final_frontier.frontier)
        unresolved_names.update(explicitly_open)
        unresolved = tuple(
            requirement.name
            for requirement in requirements
            if requirement.required and requirement.name in unresolved_names
        )

        disposition = (
            SemanticDisposition.CLARIFY
            if unresolved
            else SemanticDisposition.YES
        )

        certificate = SemanticClosureCertificate(
            disposition=disposition,
            state_hash=context.state_hash,
            signal_id=signal.signal_id,
            resolved_bindings=final_frontier.resolved,
            probabilistic_bindings=tuple(probabilistic),
            unresolved=unresolved,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            evidence_refs=tuple(
                dict.fromkeys(
                    final_frontier.deterministic_evidence + translation.evidence_refs
                )
            ),
        )
        return SemanticClosureOutcome(certificate=certificate, frontier=final_frontier)

    @staticmethod
    def _no(
        *,
        signal: ExternalSignal,
        context: MinimalSemanticContext,
        initial_frontier: SemanticFrontierResult,
        probabilistic: tuple[SemanticBinding, ...],
        reason_codes: tuple[str, ...],
        translation: CandidateSemanticBindings,
    ) -> SemanticClosureOutcome:
        certificate = SemanticClosureCertificate(
            disposition=SemanticDisposition.NO,
            state_hash=context.state_hash,
            signal_id=signal.signal_id,
            resolved_bindings=initial_frontier.resolved,
            probabilistic_bindings=probabilistic,
            unresolved=tuple(requirement.name for requirement in initial_frontier.frontier),
            reason_codes=reason_codes,
            evidence_refs=tuple(
                dict.fromkeys(
                    initial_frontier.deterministic_evidence + translation.evidence_refs
                )
            ),
        )
        return SemanticClosureOutcome(
            certificate=certificate,
            frontier=initial_frontier,
        )
