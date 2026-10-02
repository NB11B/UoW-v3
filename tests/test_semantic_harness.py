from __future__ import annotations

import pytest

from uow.compat.v2 import (
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    Route,
    Successor,
    WorldState,
    certify,
    commit,
    propose,
)
from uow.semantic import (
    BindingOrigin,
    CandidateSemanticBindings,
    DeterministicSemanticResolver,
    IngressContext,
    SemanticAlternative,
    SemanticBinding,
    SemanticClosureCertificate,
    SemanticDisposition,
    SemanticFrontierBuilder,
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


def test_semantic_yes_executes_through_native_propose_certify_commit_lifecycle() -> None:
    class MockTranslator:
        def propose(self, req):
            return CandidateSemanticBindings(
                candidate_bindings=(
                    SemanticBinding("target", "user-42", BindingOrigin.PROBABILISTIC),
                    SemanticBinding("amount", 200, BindingOrigin.PROBABILISTIC),
                )
            )

    harness = SemanticHarness(MockTranslator())
    state = WorldState({"balance": 500, "user-42": 0})
    result = harness.interpret(
        "transfer 200 to user-42",
        state=state,
        ingress=_ingress(),
        requirements=(
            SemanticRequirement("target"),
            SemanticRequirement("amount"),
            SemanticRequirement("balance", state_key="balance"),
        ),
    )

    assert result.disposition is SemanticDisposition.YES
    assert result.intent is not None

    handoff = SemanticHandoff()
    uow = handoff.to_uow(
        result,
        uow_id="transfer-e2e-uow",
        route_builder=lambda intent: (
            Route(
                guard=Guard(GuardOp.ALWAYS),
                mutations=(
                    Mutation(
                        MutationOp.SET,
                        "balance",
                        intent.binding_map()["balance"] - intent.binding_map()["amount"],
                    ),
                    Mutation(
                        MutationOp.SET,
                        intent.binding_map()["target"],
                        intent.binding_map()["amount"],
                    ),
                ),
                successor=Successor.halt(),
            ),
        ),
    )

    # Authority spine: PROPOSE -> CERTIFY -> COMMIT
    proposal = propose(uow, state)
    assert proposal.uow_id == "transfer-e2e-uow"

    cert = certify(uow, state, proposal)
    assert cert.is_valid

    new_state, record = commit(
        uow,
        state,
        proposal,
        cert,
        prev_evidence_hash="genesis",
        step_number=1,
    )
    assert new_state.attributes["balance"] == 300
    assert new_state.attributes["user-42"] == 200
    assert uow.H.parent_context == f"semantic:{result.certificate.certificate_hash}"


def test_semantic_handoff_has_no_execution_authority_and_validates_routes() -> None:
    handoff = SemanticHandoff()
    assert not hasattr(handoff, "execute")
    assert not hasattr(handoff, "commit")
    assert not hasattr(handoff, "apply")

    yes = SemanticHarness().interpret(
        "ping",
        state=WorldState({"key": "val"}),
        ingress=_ingress(),
        requirements=(SemanticRequirement("key", state_key="key"),),
    )
    with pytest.raises(ValueError, match="at least one deterministic route"):
        handoff.to_uow(yes, uow_id="empty-routes", route_builder=lambda intent: ())


def test_multi_step_deterministic_resolver_fixed_point_derivation() -> None:
    class TaxResolver:
        def resolve(self, requirement, known, context):
            if requirement.name == "tax" and "amount" in known:
                return SemanticBinding(
                    "tax",
                    known["amount"].value * 0.10,
                    BindingOrigin.DERIVED,
                    ("rule:tax_10pct",),
                )
            return None

    class TotalResolver:
        def resolve(self, requirement, known, context):
            if requirement.name == "total" and "amount" in known and "tax" in known:
                return SemanticBinding(
                    "total",
                    known["amount"].value + known["tax"].value,
                    BindingOrigin.DERIVED,
                    ("rule:total_sum",),
                )
            return None

    class AmountOnlyTranslator:
        def propose(self, req):
            return CandidateSemanticBindings(
                candidate_bindings=(
                    SemanticBinding("amount", 100.0, BindingOrigin.PROBABILISTIC),
                )
            )

    frontier_builder = SemanticFrontierBuilder(
        resolvers=(TaxResolver(), TotalResolver())
    )
    harness = SemanticHarness(
        AmountOnlyTranslator(),
        frontier_builder=frontier_builder,
    )

    result = harness.interpret(
        "pay 100",
        state=WorldState({}),
        ingress=_ingress(),
        requirements=(
            SemanticRequirement("amount"),
            SemanticRequirement("tax"),
            SemanticRequirement("total"),
        ),
    )

    assert result.disposition is SemanticDisposition.YES
    assert result.intent is not None
    assert result.intent.binding_map()["amount"] == 100.0
    assert result.intent.binding_map()["tax"] == 10.0
    assert result.intent.binding_map()["total"] == 110.0
    assert "rule:tax_10pct" in result.evidence_refs
    assert "rule:total_sum" in result.evidence_refs


def test_certificate_hash_tamper_detection() -> None:
    harness = SemanticHarness()
    result = harness.interpret(
        "noop",
        state=WorldState({"k": "v"}),
        ingress=_ingress(),
        requirements=(SemanticRequirement("k", state_key="k"),),
    )
    cert = result.certificate

    with pytest.raises(ValueError, match="hash does not match contents"):
        SemanticClosureCertificate(
            disposition=cert.disposition,
            state_hash=cert.state_hash,
            signal_id=cert.signal_id,
            resolved_bindings=cert.resolved_bindings,
            probabilistic_bindings=cert.probabilistic_bindings,
            unresolved=cert.unresolved,
            reason_codes=cert.reason_codes,
            evidence_refs=cert.evidence_refs,
            certificate_hash="0000000000000000000000000000000000000000000000000000000000000000",
        )


def test_frozen_facade_and_zero_framework_import_leaks() -> None:
    import subprocess
    import sys
    import uow

    # Frozen top-level facade
    assert not hasattr(uow, "SemanticHarness")
    assert not hasattr(uow, "SemanticHandoff")
    assert not hasattr(uow, "SemanticTranslator")

    # Framework quarantine verified in an isolated process
    code = (
        "import sys, uow, uow.semantic, uow.semantic.adapters\n"
        "assert 'torch' not in sys.modules, 'torch leaked into sys.modules'\n"
        "assert 'transformers' not in sys.modules, 'transformers leaked into sys.modules'\n"
        "assert 'peft' not in sys.modules, 'peft leaked into sys.modules'\n"
        "assert 'huggingface_hub' not in sys.modules, 'huggingface_hub leaked into sys.modules'\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert res.returncode == 0, f"Import quarantine failed: {res.stderr}"


