"""Deterministic semantic closure and residual-frontier construction."""
from __future__ import annotations

from typing import Mapping, Protocol, runtime_checkable

from .schema import (
    BindingOrigin,
    MinimalSemanticContext,
    SemanticBinding,
    SemanticFrontierResult,
    SemanticInvariantError,
    SemanticRequirement,
)


@runtime_checkable
class DeterministicSemanticResolver(Protocol):
    """Optional deterministic derivation rule used during fixed-point closure."""

    def resolve(
        self,
        requirement: SemanticRequirement,
        known: Mapping[str, SemanticBinding],
        context: MinimalSemanticContext,
    ) -> SemanticBinding | None:
        ...


class SemanticFrontierBuilder:
    """Compute Cl_D to a fixed point, then expose only the unresolved frontier."""

    def __init__(
        self,
        resolvers: tuple[DeterministicSemanticResolver, ...] = (),
    ) -> None:
        self._resolvers = resolvers

    @staticmethod
    def _insert(
        known: dict[str, SemanticBinding],
        binding: SemanticBinding,
        *,
        deterministic_terminals: set[str],
    ) -> bool:
        existing = known.get(binding.terminal)
        if existing is None:
            known[binding.terminal] = binding
            return True
        if existing.value == binding.value:
            return False
        if binding.terminal in deterministic_terminals:
            raise SemanticInvariantError(
                f"Deterministic terminal {binding.terminal!r} cannot be overwritten."
            )
        raise SemanticInvariantError(
            f"Conflicting bindings for semantic terminal {binding.terminal!r}."
        )

    def build(
        self,
        requirements: tuple[SemanticRequirement, ...],
        context: MinimalSemanticContext,
        *,
        seed_bindings: tuple[SemanticBinding, ...] = (),
    ) -> SemanticFrontierResult:
        requirement_names = {requirement.name for requirement in requirements}
        if len(requirement_names) != len(requirements):
            raise SemanticInvariantError("Semantic requirement names must be unique.")

        known: dict[str, SemanticBinding] = {}
        deterministic_terminals: set[str] = set()
        evidence = list(context.evidence_refs)

        for binding in context.bindings:
            if binding.terminal not in requirement_names:
                raise SemanticInvariantError(
                    f"Context produced undeclared semantic terminal {binding.terminal!r}."
                )
            if binding.origin is not BindingOrigin.DETERMINISTIC:
                raise SemanticInvariantError(
                    "MinimalSemanticContext may contain only deterministic bindings."
                )
            self._insert(
                known,
                binding,
                deterministic_terminals=deterministic_terminals,
            )
            deterministic_terminals.add(binding.terminal)
            evidence.extend(binding.evidence_refs)

        for binding in seed_bindings:
            if binding.terminal not in requirement_names:
                raise SemanticInvariantError(
                    f"Seed binding targets undeclared semantic terminal {binding.terminal!r}."
                )
            if binding.terminal in deterministic_terminals:
                existing = known[binding.terminal]
                if existing.value != binding.value:
                    raise SemanticInvariantError(
                        f"Probabilistic binding attempted to overwrite deterministic terminal "
                        f"{binding.terminal!r}."
                    )
                continue
            self._insert(
                known,
                binding,
                deterministic_terminals=deterministic_terminals,
            )
            evidence.extend(binding.evidence_refs)

        changed = True
        while changed:
            changed = False
            for requirement in requirements:
                if requirement.name in known:
                    continue
                for resolver in self._resolvers:
                    derived = resolver.resolve(requirement, known, context)
                    if derived is None:
                        continue
                    if derived.terminal != requirement.name:
                        raise SemanticInvariantError(
                            "Deterministic resolver returned the wrong semantic terminal."
                        )
                    if derived.origin is BindingOrigin.PROBABILISTIC:
                        raise SemanticInvariantError(
                            "Deterministic resolver may not emit probabilistic bindings."
                        )
                    changed = self._insert(
                        known,
                        derived,
                        deterministic_terminals=deterministic_terminals,
                    ) or changed
                    evidence.extend(derived.evidence_refs)
                    break

        resolved = tuple(
            known[requirement.name]
            for requirement in requirements
            if requirement.name in known
        )
        frontier = tuple(
            requirement
            for requirement in requirements
            if requirement.required and requirement.name not in known
        )
        return SemanticFrontierResult(
            resolved=resolved,
            frontier=frontier,
            deterministic_evidence=tuple(dict.fromkeys(evidence)),
        )
