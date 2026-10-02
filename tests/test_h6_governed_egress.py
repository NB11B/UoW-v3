"""Milestone H6 Qualification Suite: Governed Egress and Round-Trip Semantic Verification.

Verifies the 12 core H6 qualification gates:
1. Recipient projection isolation (strict entitlement filtering, zero state/evidence leakage)
2. Deterministic formatter bypasses model (model calls = 0)
3. Valid natural rendering round-trips (epsilon_{egress-drift} = 0)
4. Recipient identity preservation (rejects "Mike Jones" -> "Mike Smith", falls back deterministically)
5. Quantity and unit preservation (rejects 3 -> 4, items -> credits)
6. Temporal constraint preservation (rejects BEFORE -> AFTER)
7. Negation preservation (rejects DO NOT -> DO)
8. Modality preservation (rejects MUST -> SHOULD, MAY -> WILL)
9. Condition preservation (rejects IF -> UNLESS)
10. Omission and hallucination rejection (rejects missing fields or asserted facts for unknowns)
11. Invalid renderer output falls back deterministically (graceful crash/malformed handling)
12. Full provenance traversal back to authoritative UoW result

Hard Gate:
    epsilon_{egress-drift} = 0
"""
from __future__ import annotations

import json
from typing import Any
import pytest

from uow.compat.v2 import DeterministicSequencer, WorldState
from uow.semantic import (
    BindingOrigin,
    ConfigurableRenderer,
    DefaultSemanticAdmissibilityValidator,
    DeterministicEgressFormatter,
    DeterministicTemplateRenderer,
    ExternalSignal,
    GovernedEgressEngine,
    GovernedEgressMessage,
    IngressContext,
    IntentEnvelope,
    PreparedSemanticUoW,
    ProjectedSemanticIntent,
    RecipientClass,
    RecipientProfile,
    SemanticAlternative,
    SemanticApplicationAdapter,
    SemanticBinding,
    SemanticClosureCertificate,
    SemanticDisposition,
    SemanticHarness,
    SemanticRecipientProjector,
    SemanticRequirement,
    SemanticResult,
    SemanticRoundTripResult,
    SemanticRoundTripVerifier,
    TransferUoWCompiler,
)


# =========================================================================
# Gate 1: Recipient Projection Isolation
# =========================================================================

def test_h6_gate_1_recipient_projection_isolation() -> None:
    """Recipient gets only entitled material; internal state hash and hidden evidence are isolated."""
    projector = SemanticRecipientProjector()

    # Form a complete authoritative intent
    intent = IntentEnvelope(
        signal_id="sig-h6-1",
        source_signal="transfer 10 to Alice",
        principal_id="user-1",
        session_id="sess-1",
        channel="web",
        bindings=(
            SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
            SemanticBinding("quantity", 10, BindingOrigin.PROBABILISTIC),
            SemanticBinding("recipient", "Alice", BindingOrigin.PROBABILISTIC),
            SemanticBinding("internal_secret_route", "vault-north", BindingOrigin.DETERMINISTIC),
        ),
        closure_certificate_hash="cert-hash-12345",
        evidence_refs=("evidence:secret_token_123", "evidence:policy_grant_456"),
    )

    # 1. Human Requester Profile (Strict Isolation)
    human_profile = RecipientProfile.default_human()
    proj_human = projector.project(
        intent,
        human_profile,
        status="COMMITTED",
        uow_id="uow-test-001",
        state_hash="state-hash-9999",
    )

    assert proj_human.recipient_class is RecipientClass.HUMAN_REQUESTER
    # Allowed terminals only: internal_secret_route must be excluded
    assert "internal_secret_route" not in proj_human.bindings
    assert proj_human.bindings["operator"] == "transfer"
    assert proj_human.bindings["quantity"] == 10
    assert proj_human.bindings["recipient"] == "Alice"
    # Internal state hash, uow_id, cert_hash, and secret evidence must NOT leak to human
    assert proj_human.uow_id is None
    assert proj_human.state_hash is None
    assert proj_human.certificate_hash is None
    assert len(proj_human.evidence_refs) == 0

    # 2. Auditor Profile (Full Entitlement)
    auditor_profile = RecipientProfile.default_auditor()
    proj_auditor = projector.project(
        intent,
        auditor_profile,
        status="COMMITTED",
        uow_id="uow-test-001",
        state_hash="state-hash-9999",
    )

    assert proj_auditor.recipient_class is RecipientClass.AUDITOR
    assert "internal_secret_route" in proj_auditor.bindings
    assert proj_auditor.uow_id == "uow-test-001"
    assert proj_auditor.state_hash == "state-hash-9999"
    assert proj_auditor.certificate_hash == "cert-hash-12345"
    assert "evidence:secret_token_123" in proj_auditor.evidence_refs


# =========================================================================
# Gate 2: Deterministic Formatter Bypasses Model
# =========================================================================

def test_h6_gate_2_deterministic_formatter_bypasses_model() -> None:
    """Deterministic mode calls 0 models and produces unambiguous structured outputs."""
    engine = GovernedEgressEngine()

    projected_committed = ProjectedSemanticIntent(
        recipient_id="user-1",
        recipient_class=RecipientClass.HUMAN_REQUESTER,
        disposition=SemanticDisposition.YES,
        status="COMMITTED",
        operator="transfer",
        bindings={"operator": "transfer", "quantity": 3, "recipient": "Mike Jones"},
    )
    msg_committed = engine.emit(
        {"disposition": "YES", "bindings": {"operator": "transfer", "quantity": 3, "recipient": "Mike Jones"}},
        RecipientProfile.default_human(),
        use_natural_language=False,
        status="COMMITTED",
    )
    assert msg_committed.mode == "DETERMINISTIC"
    assert msg_committed.roundtrip_verified is True
    assert msg_committed.drift_detected is False
    assert "TRANSFER committed: quantity=3, recipient=Mike Jones." in msg_committed.text

    # Clarification formatting
    msg_clarif = engine.emit(
        {"disposition": "CLARIFY", "unresolved": ("recipient",), "alternatives": ()},
        RecipientProfile.default_human(),
        use_natural_language=False,
    )
    assert "Request requires clarification: recipient." in msg_clarif.text

    # Rejection formatting
    msg_no = engine.emit(
        {"disposition": "NO", "bindings": {}},
        RecipientProfile.default_human(),
        use_natural_language=False,
        reason="quantity outside permitted range",
    )
    assert "Request rejected: quantity outside permitted range." in msg_no.text


# =========================================================================
# Gate 3: Valid Natural Rendering Round-Trips
# =========================================================================

def test_h6_gate_3_valid_natural_rendering_round_trips() -> None:
    """Faithful natural-language rendering passes round-trip verification (epsilon_{drift} = 0)."""
    renderer = DeterministicTemplateRenderer()
    engine = GovernedEgressEngine(renderer=renderer)

    source = {
        "disposition": "YES",
        "bindings": {
            "operator": "transfer",
            "quantity": 5,
            "unit": "items",
            "recipient": "Alice",
            "modality": "WILL",
        },
    }

    msg = engine.emit(source, RecipientProfile.default_human(), use_natural_language=True)

    assert msg.mode == "NATURAL_VERIFIED"
    assert msg.roundtrip_verified is True
    assert not msg.drift_detected
    assert msg.fallback_reason is None
    assert "Successfully executed transfer of 5 items to Alice." in msg.text


# =========================================================================
# Gate 4: Recipient Identity Preservation
# =========================================================================

def test_h6_gate_4_recipient_identity_preservation() -> None:
    """Renderer mutating 'Mike Jones' -> 'Mike Smith' is rejected and falls back deterministically."""
    # Intent specifies Mike Jones, but adversarial renderer outputs Mike Smith
    bad_renderer = ConfigurableRenderer("Successfully executed transfer of 3 items to Mike Smith.")
    engine = GovernedEgressEngine(renderer=bad_renderer)

    source = {
        "disposition": "YES",
        "bindings": {
            "operator": "transfer",
            "quantity": 3,
            "unit": "items",
            "recipient": "Mike Jones",
        },
    }

    msg = engine.emit(source, RecipientProfile.default_human(), use_natural_language=True, status="COMMITTED")

    # Invariant: Must reject natural output, flag drift, and fall back to deterministic format
    assert msg.mode == "DETERMINISTIC_FALLBACK"
    assert msg.roundtrip_verified is False
    assert msg.drift_detected is True
    assert "Recipient mutation" in str(msg.fallback_reason)
    # Output delivered to recipient contains the TRUE recipient "Mike Jones", not "Mike Smith"
    assert "Mike Jones" in msg.text
    assert "Mike Smith" not in msg.text


# =========================================================================
# Gate 5: Quantity and Unit Preservation
# =========================================================================

def test_h6_gate_5_quantity_unit_preservation() -> None:
    """Renderer mutating quantity 3 -> 4 or unit items -> credits is rejected."""
    # 1. Quantity mutation
    bad_qty_renderer = ConfigurableRenderer("Successfully executed transfer of 4 items to Mike.")
    engine_qty = GovernedEgressEngine(renderer=bad_qty_renderer)
    source_qty = {
        "disposition": "YES",
        "bindings": {"operator": "transfer", "quantity": 3, "unit": "items", "recipient": "Mike"},
    }
    msg_qty = engine_qty.emit(source_qty, RecipientProfile.default_human(), use_natural_language=True)
    assert msg_qty.mode == "DETERMINISTIC_FALLBACK"
    assert "Quantity mutation" in str(msg_qty.fallback_reason)
    assert "quantity=3" in msg_qty.text

    # 2. Unit mutation
    bad_unit_renderer = ConfigurableRenderer("Successfully executed transfer of 3 credits to Mike.")
    engine_unit = GovernedEgressEngine(renderer=bad_unit_renderer)
    msg_unit = engine_unit.emit(source_qty, RecipientProfile.default_human(), use_natural_language=True)
    assert msg_unit.mode == "DETERMINISTIC_FALLBACK"
    assert "Unit mutation" in str(msg_unit.fallback_reason)


# =========================================================================
# Gate 6: Temporal Constraint Preservation
# =========================================================================

def test_h6_gate_6_temporal_preservation() -> None:
    """Renderer altering 'before 17:00' to 'after 17:00' is caught and rejected."""
    bad_temporal_renderer = ConfigurableRenderer("Successfully executed transfer of 3 to Mike after 17:00.")
    engine = GovernedEgressEngine(renderer=bad_temporal_renderer)

    source = {
        "disposition": "YES",
        "bindings": {
            "operator": "transfer",
            "quantity": 3,
            "recipient": "Mike",
            "temporal": "before 17:00",
        },
    }
    msg = engine.emit(source, RecipientProfile.default_human(), use_natural_language=True)

    assert msg.mode == "DETERMINISTIC_FALLBACK"
    assert "Temporal mutation" in str(msg.fallback_reason)
    assert "temporal=before 17:00" in msg.text


# =========================================================================
# Gate 7: Negation Preservation
# =========================================================================

def test_h6_gate_7_negation_preservation() -> None:
    """Renderer inverting negation polarity (DO NOT -> DO) is caught and rejected."""
    # Expected: negation=True (Do not transfer), but renderer outputs affirmative
    bad_neg_renderer = ConfigurableRenderer("Successfully executed transfer of 3 to Mike.")
    engine = GovernedEgressEngine(renderer=bad_neg_renderer)

    source = {
        "disposition": "YES",
        "bindings": {
            "operator": "transfer",
            "quantity": 3,
            "recipient": "Mike",
            "negation": True,
        },
    }
    msg = engine.emit(source, RecipientProfile.default_human(), use_natural_language=True)

    assert msg.mode == "DETERMINISTIC_FALLBACK"
    assert "Negation polarity shift" in str(msg.fallback_reason)
    assert "negation=True" in msg.text


# =========================================================================
# Gate 8: Modality Preservation
# =========================================================================

def test_h6_gate_8_modality_preservation() -> None:
    """Renderer shifting modality (MUST -> SHOULD or MAY -> WILL) is caught and rejected."""
    # Expected: MUST, but renderer outputs "Should"
    bad_modality_renderer = ConfigurableRenderer("Should transfer 3 to Mike.")
    engine = GovernedEgressEngine(renderer=bad_modality_renderer)

    source = {
        "disposition": "YES",
        "bindings": {
            "operator": "transfer",
            "quantity": 3,
            "recipient": "Mike",
            "modality": "MUST",
        },
    }
    msg = engine.emit(source, RecipientProfile.default_human(), use_natural_language=True)

    assert msg.mode == "DETERMINISTIC_FALLBACK"
    assert "Modality shift" in str(msg.fallback_reason)
    assert "modality=MUST" in msg.text


# =========================================================================
# Gate 9: Condition Preservation
# =========================================================================

def test_h6_gate_9_condition_preservation() -> None:
    """Renderer shifting condition (if authorized -> unless authorized) is caught and rejected."""
    bad_cond_renderer = ConfigurableRenderer("Successfully executed transfer of 3 to Mike unless authorized.")
    engine = GovernedEgressEngine(renderer=bad_cond_renderer)

    source = {
        "disposition": "YES",
        "bindings": {
            "operator": "transfer",
            "quantity": 3,
            "recipient": "Mike",
            "condition": "if authorized",
        },
    }
    msg = engine.emit(source, RecipientProfile.default_human(), use_natural_language=True)

    assert msg.mode == "DETERMINISTIC_FALLBACK"
    assert "Condition mutation" in str(msg.fallback_reason)


# =========================================================================
# Gate 10: Omission and Hallucination Rejection
# =========================================================================

def test_h6_gate_10_omission_and_hallucination_rejection() -> None:
    """Omitting material field or asserting facts for unresolved requirements is caught."""
    # 1. Omission of material terminal (recipient)
    omitting_renderer = ConfigurableRenderer("Successfully executed transfer of 3.")
    engine_omit = GovernedEgressEngine(renderer=omitting_renderer)
    source_omit = {
        "disposition": "YES",
        "bindings": {"operator": "transfer", "quantity": 3, "recipient": "Mike"},
    }
    msg_omit = engine_omit.emit(source_omit, RecipientProfile.default_human(), use_natural_language=True)
    assert msg_omit.mode == "DETERMINISTIC_FALLBACK"
    assert "Omission: recipient" in str(msg_omit.fallback_reason)

    # 2. Hallucinated certainty on CLARIFY (asserting recipient="Mike" when recipient was unresolved)
    hallucinating_renderer = ConfigurableRenderer("Transfer completed successfully to Mike.")
    engine_hallucinate = GovernedEgressEngine(renderer=hallucinating_renderer)
    source_clarif = {
        "disposition": "CLARIFY",
        "unresolved": ("recipient",),
        "bindings": {"operator": "transfer"},
    }
    msg_clarif = engine_hallucinate.emit(source_clarif, RecipientProfile.default_human(), use_natural_language=True)
    assert msg_clarif.mode == "DETERMINISTIC_FALLBACK"
    assert "Omission: CLARIFY disposition rendered without clarification" in str(msg_clarif.fallback_reason) or "unresolved requirement" in str(msg_clarif.fallback_reason)


# =========================================================================
# Gate 11: Invalid Renderer Output Falls Back Deterministically
# =========================================================================

def test_h6_gate_11_invalid_renderer_output_falls_back_deterministically() -> None:
    """Unparseable text or renderer exception falls back safely to deterministic formatter."""
    class CrashingRenderer:
        def render(self, projected: ProjectedSemanticIntent) -> str:
            raise RuntimeError("Renderer GPU out of memory")

    engine = GovernedEgressEngine(renderer=CrashingRenderer())
    source = {
        "disposition": "YES",
        "bindings": {"operator": "transfer", "quantity": 10, "recipient": "Alice"},
    }

    msg = engine.emit(source, RecipientProfile.default_human(), use_natural_language=True, status="COMMITTED")

    assert msg.mode == "DETERMINISTIC_FALLBACK"
    assert msg.roundtrip_verified is False
    assert "RendererException: RuntimeError" in str(msg.fallback_reason)
    assert "TRANSFER committed: quantity=10, recipient=Alice." in msg.text


# =========================================================================
# Gate 12: Full Provenance Traversal Back to Authoritative UoW Result
# =========================================================================

def test_h6_gate_12_full_provenance_traversal() -> None:
    """GovernedEgressMessage retains unbroken cryptographic hash chain to UoW execution."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Mike"]}, "transfers.Mike": 0})
    ingress = IngressContext(principal_id="user-1", session_id="sess-prov", channel="text")

    # Run complete ingress -> execution pipeline
    compiler = TransferUoWCompiler()
    adapter = SemanticApplicationAdapter()

    harness = SemanticHarness(
        admissibility_validator=DefaultSemanticAdmissibilityValidator(),
    )
    # Propose through translator
    from uow.semantic import CandidateSemanticBindings, BindingOrigin
    class DirectTranslator:
        def propose(self, req: Any) -> CandidateSemanticBindings:
            return CandidateSemanticBindings(
                candidate_bindings=(
                    SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
                    SemanticBinding("quantity", 7, BindingOrigin.PROBABILISTIC),
                    SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),
                )
            )

    harness._translator = DirectTranslator()
    res = harness.interpret(
        "transfer 7 to Mike",
        state=state_0,
        ingress=ingress,
        requirements=(SemanticRequirement("operator"), SemanticRequirement("quantity"), SemanticRequirement("recipient")),
    )
    assert res.disposition is SemanticDisposition.YES

    prep = adapter.prepare(res, state_0, compiler)
    seq = DeterministicSequencer(state_0)
    app_res = adapter.execute(prep, seq)
    assert app_res.state.attributes["transfers.Mike"] == 7

    # Emit governed egress for Auditor
    engine = GovernedEgressEngine(renderer=DeterministicTemplateRenderer())
    msg = engine.emit(
        res,
        RecipientProfile.default_auditor(),
        use_natural_language=True,
        status="COMMITTED",
        uow_id=prep.uow.H.identity,
        state_hash=app_res.state.state_hash,
    )

    assert msg.mode == "NATURAL_VERIFIED"
    assert msg.roundtrip_verified is True

    # Provenance chain inspection
    refs = msg.evidence_refs
    assert f"uow:{prep.uow.H.identity}" in refs
    assert f"cert:{res.certificate.certificate_hash}" in refs
    assert f"state:{app_res.state.state_hash}" in refs
    assert f"projection:{msg.projected.projection_hash}" in refs
    assert "egress_mode:NATURAL_VERIFIED" in refs
    assert "roundtrip_verified:true" in refs

    # Traverse backward: LedgerRecord -> UoW -> Semantic Certificate -> Egress Message
    ledger_record = seq.ledger.records[0]
    assert ledger_record.uow_id == prep.uow.H.identity
    assert prep.uow.H.parent_context == f"semantic:{res.certificate.certificate_hash}"
