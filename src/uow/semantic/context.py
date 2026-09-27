"""Minimal deterministic context projection from authoritative UoW state."""
from __future__ import annotations

from .schema import (
    BindingOrigin,
    IngressContext,
    MinimalSemanticContext,
    SemanticBinding,
    SemanticRequirement,
)
from ..state import WorldState


class SemanticContextProjector:
    """Project only deterministic fields explicitly required by this translation."""

    def project(
        self,
        state: WorldState,
        ingress: IngressContext,
        requirements: tuple[SemanticRequirement, ...],
    ) -> MinimalSemanticContext:
        bindings: list[SemanticBinding] = []
        evidence = list(ingress.evidence_refs)
        evidence.append(f"world-state:{state.state_hash}")

        for requirement in requirements:
            if requirement.state_key:
                if requirement.state_key in state.attributes:
                    bindings.append(
                        SemanticBinding(
                            terminal=requirement.name,
                            value=state.require(requirement.state_key),
                            origin=BindingOrigin.DETERMINISTIC,
                            evidence_refs=(
                                f"world-state:{state.state_hash}:{requirement.state_key}",
                            ),
                        )
                    )
                continue

            if requirement.ingress_key:
                found, value = ingress.lookup(requirement.ingress_key)
                if found:
                    bindings.append(
                        SemanticBinding(
                            terminal=requirement.name,
                            value=value,
                            origin=BindingOrigin.DETERMINISTIC,
                            evidence_refs=(f"ingress:{requirement.ingress_key}",),
                        )
                    )

        return MinimalSemanticContext(
            state_hash=state.state_hash,
            state_sequence=state.sequence,
            bindings=tuple(bindings),
            evidence_refs=tuple(dict.fromkeys(evidence)),
        )
