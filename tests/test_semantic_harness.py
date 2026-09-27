from __future__ import annotations

import pytest

from uow import Guard, GuardOp, Route, Successor, WorldState
from uow.semantic import (
    BindingOrigin,
    CandidateSemanticBindings,
    IngressContext,
    SemanticAlternative,
    SemanticBinding,
    SemanticDisposition,
    SemanticHandoff,
    SemanticHarness,
    SemanticRequirement,
)


class SpyTranslator:
    def __init__(self, response: CandidateSemanticBindings) -> None:
        self.response = response
        self.calls = 0
        self.last_request = None

    def propose(self, request):
        self.calls += 1
        self.last_request = request
        return self.response


def _ingress() -> IngressContext:
    return IngressContext(
        principal_id="operator-1",
        session_id="session-1",
        channel="text",
        evidence_refs=("authn:operator-1",),
    )


def test_deterministic_closure_bypasses_translator() -> None:
    translator = SpyTranslator(CandidateSemanticBindings())
    harness = SemanticHarness(translator)
    state = WorldState({"recipient": "mike", "amount": 5})
    requirements = (
        SemanticRequirement("recipient", state_key="recipient"),
        SemanticRequirement("amount", state_key="amount"),
        SemanticRequirement("principal", ingress_key="principal_id"),
    )

    result = harness.interpret(
        "send five units to mike",
        state=state,
        ingress=_ingress(),
        requirements=requirements,
    )

    assert result.disposition is SemanticDisposition.YES
    assert translator.calls == 0
    assert result.intent is not None
    assert result.intent.binding_map() == {
        "recipient": "mike",
        "amount": 5,
        "principal": "operator-1",
    }


def test_probabilistic_translator_sees_only_residual_frontier() -> None:
    translator = SpyTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding(
                    terminal="recipient",
                    value="mike",
                    origin=BindingOrigin.PROBABILISTIC,
                    evidence_refs=("model:smollm2-135m:test",),
                ),
            ),
            local_confidence={"recipient": 0.62},
        )
    )
    harness = SemanticHarness(translator)
    state = WorldState({"amount": 5})
    requirements = (
        SemanticRequirement("recipient"),
        SemanticRequirement("amount", state_key="amount"),
    )

    result = harness.interpret(
        "send five units to mike",
        state=state,
        ingress=_ingress(),
        requirements=requirements,
    )

    assert result.disposition is SemanticDisposition.YES
    assert translator.calls == 1
    assert translator.last_request is not None
    assert tuple(r.name for r in translator.last_request.frontier) == ("recipient",)
    assert tuple(b.terminal for b in translator.last_request.minimal_context.bindings) == (
        "amount",
    )
    assert translator.response.local_confidence["recipient"] == 0.62


def test_unknown_is_clarify_and_cannot_form_intent() -> None:
    translator = SpyTranslator(CandidateSemanticBindings(unknowns=("recipient",)))
    harness = SemanticHarness(translator)

    result = harness.interpret(
        "send five units to them",
        state=WorldState({"amount": 5}),
        ingress=_ingress(),
        requirements=(
            SemanticRequirement("recipient"),
            SemanticRequirement("amount", state_key="amount"),
        ),
    )

    assert result.disposition is SemanticDisposition.CLARIFY
    assert result.intent is None
    assert tuple(r.name for r in result.unresolved) == ("recipient",)


def test_alternatives_force_clarification() -> None:
    translator = SpyTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("recipient", "mike-a", BindingOrigin.PROBABILISTIC),
            ),
            alternatives=(
                SemanticAlternative(
                    bindings=(
                        SemanticBinding(
                            "recipient",
                            "mike-b",
                            BindingOrigin.PROBABILISTIC,
                        ),
                    ),
                    reason="two admissible recipients",
                ),
            ),
        )
    )
    harness = SemanticHarness(translator)

    result = harness.interpret(
        "send five units to mike",
        state=WorldState({"amount": 5}),
        ingress=_ingress(),
        requirements=(
            SemanticRequirement("recipient"),
            SemanticRequirement("amount", state_key="amount"),
        ),
    )

    assert result.disposition is SemanticDisposition.CLARIFY
    assert result.intent is None
    assert tuple(r.name for r in result.unresolved) == ("recipient",)
    assert result.alternatives


def test_frontier_confinement_violation_fails_closed() -> None:
    translator = SpyTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("amount", 9000, BindingOrigin.PROBABILISTIC),
            )
        )
    )
    harness = SemanticHarness(translator)

    result = harness.interpret(
        "send five units to mike",
        state=WorldState({"amount": 5}),
        ingress=_ingress(),
        requirements=(
            SemanticRequirement("recipient"),
            SemanticRequirement("amount", state_key="amount"),
        ),
    )

    assert result.disposition is SemanticDisposition.NO
    assert result.intent is None
    assert "FRONTIER_CONFINEMENT_VIOLATION" in result.certificate.reason_codes


def test_only_yes_lowers_through_native_make_uow_api() -> None:
    harness = SemanticHarness()
    handoff = SemanticHandoff()
    state = WorldState({"recipient": "mike"})
    requirements = (SemanticRequirement("recipient", state_key="recipient"),)

    yes = harness.interpret(
        "contact mike",
        state=state,
        ingress=_ingress(),
        requirements=requirements,
    )
    uow = handoff.to_uow(
        yes,
        uow_id="semantic-contact-1",
        route_builder=lambda intent: (
            Route(
                guard=Guard(GuardOp.ALWAYS),
                mutations=(),
                successor=Successor.halt(),
            ),
        ),
    )

    assert uow.H.identity == "semantic-contact-1"
    assert uow.H.layer == "semantic-handoff"
    assert uow.H.parent_context == f"semantic:{yes.certificate.certificate_hash}"

    clarify = SemanticHarness().interpret(
        "contact someone",
        state=WorldState({}),
        ingress=_ingress(),
        requirements=(SemanticRequirement("recipient"),),
    )
    with pytest.raises(ValueError, match="Only semantic YES"):
        handoff.to_uow(
            clarify,
            uow_id="must-not-exist",
            route_builder=lambda intent: (),
        )
