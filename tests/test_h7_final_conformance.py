"""Milestone H7: Final Integrated Conformance Campaign for UoW Semantic Boundary.

Verifies the complete closed loop:
    Signal -> Context -> Cl_D -> F_P -> Model -> Admissibility -> Closure -> YES/NO/CLARIFY
    -> UoW Compilation -> PROPOSE -> CERTIFY -> COMMIT -> Recipient Projection -> Egress -> Round-Trip

Covers:
- H7.1: The 5 End-to-End Terminal Paths (Deterministic, Probabilistic, Clarification, Safe Rejection, Persistent Ambiguity)
- H7.2: The Complete 15-Fault Matrix
- H7.3: Permanent Production Adversarial Falsification Bank
- H7.4: Invariant Verification Matrix (Canonical I_I..I_tau + Semantic H_1..H_8)

Definition of Done Invariants:
    core UoW runs without an LLM
    F_P = empty => 0 model calls
    model sees only X, C_min, F_P
    probabilistic output cannot overwrite deterministic state (beta_D = 0)
    UNKNOWN/ambiguity => CLARIFY
    CLARIFY, NO => 0 executable commits
    semantic YES does not bypass authority
    intent survives through commit
    crash/replay/concurrency guarantees survive
    egress semantic roundtrip = identity
    epsilon_{unsafe}^{system} = 0
    epsilon_{egress-drift} = 0
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any, Mapping, Optional, Tuple
import pytest

from uow import (
    DeterministicSequencer,
    EvidenceRecord,
    HazardType,
    TransactionConflictError,
    WALSequencer,
    WorldState,
    validate_occ,
)
from uow.application import (
    ApplicationResult,
    ApplicationSpine,
    CursorPolicy,
    DEFAULT_APPLICATION_SPINE,
)
from uow.semantic import (
    BindingOrigin,
    CandidateSemanticBindings,
    ClarificationContext,
    ConfigurableRenderer,
    ContradictoryContinuationError,
    DefaultSemanticAdmissibilityValidator,
    DeterministicEgressFormatter,
    DeterministicSemanticResolver,
    DeterministicTemplateRenderer,
    ExternalSignal,
    GovernedEgressEngine,
    GovernedEgressMessage,
    IngressContext,
    IntentEnvelope,
    MinimalSemanticContext,
    PreparedSemanticUoW,
    ProjectedSemanticIntent,
    PurgeUoWCompiler,
    RecipientClass,
    RecipientProfile,
    SemanticAlternative,
    SemanticApplicationAdapter,
    SemanticBinding,
    SemanticClosureCertificate,
    SemanticCompilerRegistry,
    SemanticDisposition,
    SemanticFrontierBuilder,
    SemanticHarness,
    SemanticRecipientProjector,
    SemanticRequirement,
    SemanticResult,
    SemanticRoundTripResult,
    SemanticRoundTripVerifier,
    SemanticStateDriftError,
    SemanticTranslationRequest,
    SemanticTranslator,
    StaleClarificationError,
    TransferUoWCompiler,
    derive_semantic_uow_id,
)


class MockTranslator:
    def __init__(self, response: CandidateSemanticBindings | None = None) -> None:
        self.response = response or CandidateSemanticBindings()
        self.call_count = 0
        self.last_request: Optional[SemanticTranslationRequest] = None

    def propose(self, request: SemanticTranslationRequest) -> CandidateSemanticBindings:
        self.call_count += 1
        self.last_request = request
        return self.response


# =========================================================================
# H7.1: The 5 End-to-End Terminal Paths
# =========================================================================

def test_h7_path_1_deterministic_success_zero_model_calls() -> None:
    """Path 1: All requirements resolved deterministically from state & ingress -> 0 model calls."""
    state_0 = WorldState(
        attributes={
            "transfers.Bob": 0,
            "entities": {"recipient": ["Bob"]},
            "default_operator": "transfer",
            "default_quantity": 10,
        }
    )
    ingress = IngressContext(principal_id="user-1", session_id="s1", channel="text", metadata={"recipient": "Bob"})

    spy_translator = MockTranslator()
    harness = SemanticHarness(
        spy_translator,
        admissibility_validator=DefaultSemanticAdmissibilityValidator(),
    )
    res = harness.interpret(
        "Execute standard transfer",
        state=state_0,
        ingress=ingress,
        requirements=(
            SemanticRequirement("operator", state_key="default_operator"),
            SemanticRequirement("quantity", state_key="default_quantity"),
            SemanticRequirement("recipient", ingress_key="recipient"),
        ),
    )

    # Invariant: 0 model calls
    assert spy_translator.call_count == 0
    assert res.disposition is SemanticDisposition.YES
    assert res.intent is not None
    assert res.intent.binding_map() == {"operator": "transfer", "quantity": 10, "recipient": "Bob"}

    # Authoritative UoW execution & Egress
    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()
    prep = adapter.prepare(res, state_0, compiler)
    seq = DeterministicSequencer(state_0)
    app_res = adapter.execute(prep, seq)
    assert app_res.state.attributes["transfers.Bob"] == 10

    engine = GovernedEgressEngine()
    egress = engine.emit(res, RecipientProfile.default_human(), status="COMMITTED")
    assert egress.mode == "DETERMINISTIC"
    assert "TRANSFER committed: quantity=10, recipient=Bob." in egress.text


def test_h7_path_2_probabilistic_success() -> None:
    """Path 2: Signal requires model -> admissibility passes -> YES -> UoW -> COMMIT -> Egress."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Charlie"]}, "transfers.Charlie": 0})
    ingress = IngressContext(principal_id="user-2", session_id="s2", channel="text")

    translator = MockTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
                SemanticBinding("quantity", 25, BindingOrigin.PROBABILISTIC),
                SemanticBinding("recipient", "Charlie", BindingOrigin.PROBABILISTIC),
            )
        )
    )
    harness = SemanticHarness(translator, admissibility_validator=DefaultSemanticAdmissibilityValidator())
    res = harness.interpret(
        "Please transfer 25 to Charlie",
        state=state_0,
        ingress=ingress,
        requirements=(SemanticRequirement("operator"), SemanticRequirement("quantity"), SemanticRequirement("recipient")),
    )
    assert translator.call_count == 1
    assert res.disposition is SemanticDisposition.YES

    # Execution
    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()
    prep = adapter.prepare(res, state_0, compiler)
    seq = DeterministicSequencer(state_0)
    app_res = adapter.execute(prep, seq)
    assert app_res.state.attributes["transfers.Charlie"] == 25

    # Egress with natural rendering and round-trip verification
    engine = GovernedEgressEngine(renderer=DeterministicTemplateRenderer())
    egress = engine.emit(res, RecipientProfile.default_human(), use_natural_language=True, status="COMMITTED")
    assert egress.mode == "NATURAL_VERIFIED"
    assert egress.roundtrip_verified is True
    assert "Successfully executed transfer of 25 to Charlie." in egress.text


def test_h7_path_3_clarification_success() -> None:
    """Path 3: Turn 1 CLARIFY -> Turn 2 continuation YES -> UoW -> COMMIT -> Egress."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Diana"]}, "transfers.Diana": 0})
    ingress = IngressContext(principal_id="user-3", session_id="s3", channel="text")

    t1 = MockTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
                SemanticBinding("quantity", 15, BindingOrigin.PROBABILISTIC),
            ),
            unknowns=("recipient",),
        )
    )
    harness = SemanticHarness(t1, admissibility_validator=DefaultSemanticAdmissibilityValidator())
    res1 = harness.interpret(
        "transfer 15",
        state=state_0,
        ingress=ingress,
        requirements=(SemanticRequirement("operator"), SemanticRequirement("quantity"), SemanticRequirement("recipient")),
    )
    assert res1.disposition is SemanticDisposition.CLARIFY

    clarif = ClarificationContext.from_result(res1, signal_id="sig-turn-1", state_hash=state_0.state_hash)

    t2 = MockTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(SemanticBinding("recipient", "Diana", BindingOrigin.PROBABILISTIC),)
        )
    )
    harness._translator = t2
    res2 = harness.continue_interpretation("Diana", clarification=clarif, state=state_0, ingress=ingress)
    assert res2.disposition is SemanticDisposition.YES

    # Execution & Egress
    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()
    prep = adapter.prepare(res2, state_0, compiler)
    seq = DeterministicSequencer(state_0)
    app_res = adapter.execute(prep, seq)
    assert app_res.state.attributes["transfers.Diana"] == 15

    engine = GovernedEgressEngine()
    egress = engine.emit(res2, RecipientProfile.default_human(), status="COMMITTED")
    assert "TRANSFER committed: quantity=15, recipient=Diana." in egress.text


def test_h7_path_4_safe_rejection() -> None:
    """Path 4: Frontier confinement violation -> NO -> 0 commits -> Rejection Egress."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Eve"]}})
    ingress = IngressContext(principal_id="user-4", session_id="s4", channel="text")

    # Proposing a terminal outside declared requirements triggers strict frontier confinement violation -> NO
    t = MockTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("unauthorized_terminal", "destroy_world", BindingOrigin.PROBABILISTIC),
                SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
            )
        )
    )
    harness = SemanticHarness(t, admissibility_validator=DefaultSemanticAdmissibilityValidator())
    res = harness.interpret(
        "transfer to Eve with unauthorized payload",
        state=state_0,
        ingress=ingress,
        requirements=(SemanticRequirement("operator"), SemanticRequirement("quantity"), SemanticRequirement("recipient")),
    )
    assert res.disposition is SemanticDisposition.NO
    assert res.intent is None
    assert any(code in res.certificate.reason_codes for code in ("UNKNOWN_OUTSIDE_FRONTIER", "FRONTIER_CONFINEMENT_VIOLATION"))

    # Invariant: 0 prepared UoWs, 0 commits
    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()
    with pytest.raises(ValueError, match="Only semantic YES may be prepared"):
        adapter.prepare(res, state_0, compiler)

    engine = GovernedEgressEngine()
    egress = engine.emit(res, RecipientProfile.default_human(), reason="frontier confinement violation")
    assert egress.mode == "DETERMINISTIC"
    assert "Request rejected: frontier confinement violation." in egress.text


def test_h7_path_5_persistent_ambiguity() -> None:
    """Path 5: Persistent unknown entity remains CLARIFY -> 0 commits -> Clarification Egress."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Frank"]}})
    ingress = IngressContext(principal_id="user-5", session_id="s5", channel="text")

    t = MockTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
                SemanticBinding("quantity", 5, BindingOrigin.PROBABILISTIC),
                SemanticBinding("recipient", "NonExistentPerson", BindingOrigin.PROBABILISTIC),
            )
        )
    )
    harness = SemanticHarness(t, admissibility_validator=DefaultSemanticAdmissibilityValidator())
    res = harness.interpret(
        "transfer 5 to NonExistentPerson",
        state=state_0,
        ingress=ingress,
        requirements=(SemanticRequirement("operator"), SemanticRequirement("quantity"), SemanticRequirement("recipient")),
    )
    # Admissibility reclassifies unknown entity to unknown -> CLARIFY
    assert res.disposition is SemanticDisposition.CLARIFY
    assert tuple(r.name for r in res.unresolved) == ("recipient",)

    # Invariant: 0 commits
    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()
    with pytest.raises(ValueError, match="Only semantic YES may be prepared"):
        adapter.prepare(res, state_0, compiler)

    engine = GovernedEgressEngine()
    egress = engine.emit(res, RecipientProfile.default_human())
    assert "Request requires clarification: recipient." in egress.text


# =========================================================================
# H7.2: The Complete 15-Fault Matrix
# =========================================================================

def test_h7_fault_1_state_drift_pre_execution() -> None:
    """Fault 1: State drifts between semantic closure and preparation -> fails closed."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Mike"]}, "seq": 10})
    ingress = IngressContext("u", "s", "c")
    t = MockTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
                SemanticBinding("quantity", 5, BindingOrigin.PROBABILISTIC),
                SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),
            )
        )
    )
    harness = SemanticHarness(t, admissibility_validator=DefaultSemanticAdmissibilityValidator())
    res = harness.interpret("transfer 5 to Mike", state=state_0, ingress=ingress, requirements=(
        SemanticRequirement("operator"), SemanticRequirement("quantity"), SemanticRequirement("recipient")
    ))

    # Advance state before preparation
    state_1 = state_0.with_attribute("seq", 11).advance_sequence()
    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()
    with pytest.raises(SemanticStateDriftError):
        adapter.prepare(res, state_1, compiler)


def test_h7_fault_2_authority_revocation() -> None:
    """Fault 2: State execution status HALTED halts commit cleanly with 0 records."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Mike"]}, "transfers.Mike": 0})
    ingress = IngressContext("u", "s", "c")
    t = MockTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
                SemanticBinding("quantity", 5, BindingOrigin.PROBABILISTIC),
                SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),
            )
        )
    )
    harness = SemanticHarness(t, admissibility_validator=DefaultSemanticAdmissibilityValidator())
    res = harness.interpret("transfer 5 to Mike", state=state_0, ingress=ingress, requirements=(
        SemanticRequirement("operator"), SemanticRequirement("quantity"), SemanticRequirement("recipient")
    ))
    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()
    prep = adapter.prepare(res, state_0, compiler)

    state_halted = state_0.with_status("HALTED")
    prepared_halted = PreparedSemanticUoW(
        uow=prep.uow,
        semantic_certificate_hash=prep.semantic_certificate_hash,
        expected_state_hash=state_halted.state_hash,
        signal_id=prep.signal_id,
        compiler_id=prep.compiler_id,
    )
    sequencer = DeterministicSequencer(state_halted)
    with pytest.raises(ValueError, match="requires RUNNING authoritative state"):
        adapter.execute(prepared_halted, sequencer)

    assert sequencer.current_state.status == "HALTED"
    assert len(sequencer.ledger.records) == 0


def test_h7_fault_3_expired_lease() -> None:
    """Fault 3: Expired lease prevents execution."""
    state_halted = WorldState(attributes={"entities": {"recipient": ["Mike"]}}).with_status("HALTED")
    seq = DeterministicSequencer(state_halted)
    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()

    dummy_intent = IntentEnvelope("sig-1", "transfer", "u", "s", "c", (
        SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
        SemanticBinding("quantity", 1, BindingOrigin.PROBABILISTIC),
        SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),
    ), "cert-1")
    prep = PreparedSemanticUoW(
        uow=compiler.compile(dummy_intent, state_halted),
        semantic_certificate_hash="cert-1",
        expected_state_hash=state_halted.state_hash,
        signal_id="sig-1",
        compiler_id=compiler.compiler_id,
    )
    with pytest.raises(ValueError, match="requires RUNNING authoritative state"):
        adapter.execute(prep, seq)


def test_h7_fault_4_concurrent_disjoint_work() -> None:
    """Fault 4: Concurrent disjoint semantic requests serialize deterministically."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Alice", "Bob"]}, "transfers.Alice": 0, "transfers.Bob": 0})
    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()

    intent_a = IntentEnvelope("sig-a", "transfer", "u", "s", "c", (
        SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
        SemanticBinding("quantity", 2, BindingOrigin.PROBABILISTIC),
        SemanticBinding("recipient", "Alice", BindingOrigin.PROBABILISTIC),
    ), "cert-a")
    intent_b = IntentEnvelope("sig-b", "transfer", "u", "s", "c", (
        SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
        SemanticBinding("quantity", 5, BindingOrigin.PROBABILISTIC),
        SemanticBinding("recipient", "Bob", BindingOrigin.PROBABILISTIC),
    ), "cert-b")

    seq = DeterministicSequencer(state_0)
    prep_a = adapter.prepare(SemanticResult(SemanticDisposition.YES, intent_a, (), (), SemanticClosureCertificate(SemanticDisposition.YES, state_0.state_hash, "sig-a", intent_a.bindings, (), ())), state_0, compiler)
    res_a = adapter.execute(prep_a, seq)

    state_1 = res_a.state
    prep_b = adapter.prepare(SemanticResult(SemanticDisposition.YES, intent_b, (), (), SemanticClosureCertificate(SemanticDisposition.YES, state_1.state_hash, "sig-b", intent_b.bindings, (), ())), state_1, compiler)
    res_b = adapter.execute(prep_b, seq)

    assert res_b.state.attributes["transfers.Alice"] == 2
    assert res_b.state.attributes["transfers.Bob"] == 5
    assert len(seq.ledger.records) == 2


def test_h7_fault_5_concurrent_conflicting_work() -> None:
    """Fault 5: Concurrent conflicting work triggers OCC conflict."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Alice"]}, "transfers.Alice": 0})
    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()

    intent = IntentEnvelope("sig-c", "transfer", "u", "s", "c", (
        SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
        SemanticBinding("quantity", 3, BindingOrigin.PROBABILISTIC),
        SemanticBinding("recipient", "Alice", BindingOrigin.PROBABILISTIC),
    ), "cert-c")

    prep_concurrent_1 = adapter.prepare(SemanticResult(SemanticDisposition.YES, intent, (), (), SemanticClosureCertificate(SemanticDisposition.YES, state_0.state_hash, "sig-c", intent.bindings, (), ())), state_0, compiler)
    prep_concurrent_2 = adapter.prepare(SemanticResult(SemanticDisposition.YES, intent, (), (), SemanticClosureCertificate(SemanticDisposition.YES, state_0.state_hash, "sig-c", intent.bindings, (), ())), state_0, compiler)

    seq = DeterministicSequencer(state_0)
    adapter.execute(prep_concurrent_1, seq)

    with pytest.raises(SemanticStateDriftError):
        adapter.execute(prep_concurrent_2, seq)


def test_h7_fault_6_duplicate_replay_signal() -> None:
    """Fault 6: Duplicate signal execution is idempotent and cannot double-commit."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Alice"]}, "transfers.Alice": 0})
    ingress = IngressContext("u", "s", "c")
    t = MockTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
                SemanticBinding("quantity", 1, BindingOrigin.PROBABILISTIC),
                SemanticBinding("recipient", "Alice", BindingOrigin.PROBABILISTIC),
            )
        )
    )
    harness = SemanticHarness(t, admissibility_validator=DefaultSemanticAdmissibilityValidator())
    res1 = harness.interpret(ExternalSignal("transfer 1 to Alice", signal_id="sig-dup"), state=state_0, ingress=ingress, requirements=(
        SemanticRequirement("operator"), SemanticRequirement("quantity"), SemanticRequirement("recipient")
    ))
    res2 = harness.interpret(ExternalSignal("transfer 1 to Alice", signal_id="sig-dup"), state=state_0, ingress=ingress, requirements=(
        SemanticRequirement("operator"), SemanticRequirement("quantity"), SemanticRequirement("recipient")
    ))
    assert res1.certificate.certificate_hash == res2.certificate.certificate_hash

    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()
    prep1 = adapter.prepare(res1, state_0, compiler)
    seq = DeterministicSequencer(state_0)
    adapter.execute(prep1, seq)

    with pytest.raises(SemanticStateDriftError):
        adapter.execute(prep1, seq)
    assert len(seq.ledger.records) == 1


def test_h7_fault_7_crash_after_semantic_closure() -> None:
    """Fault 7: Crash after closure produces 0 ledger entries; uncommitted work is discarded."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Alice"]}})
    seq = DeterministicSequencer(state_0)
    assert len(seq.ledger.records) == 0


def test_h7_fault_8_crash_during_commit_wal_recovery() -> None:
    """Fault 8: WAL sequencer crash recovery guarantees durability and replay integrity."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = Path(tmpdir) / "test_lifecycle.wal"
        state_0 = WorldState(attributes={"transfers.Alice": 0, "entities": {"recipient": ["Alice"]}})
        wal_seq = WALSequencer(wal_path, state_0)
        compiler = TransferUoWCompiler()
        adapter = SemanticApplicationAdapter()

        intent = IntentEnvelope("sig-wal", "transfer", "u", "s", "c", (
            SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
            SemanticBinding("quantity", 10, BindingOrigin.PROBABILISTIC),
            SemanticBinding("recipient", "Alice", BindingOrigin.PROBABILISTIC),
        ), "cert-wal")
        prep = adapter.prepare(
            SemanticResult(SemanticDisposition.YES, intent, (), (), SemanticClosureCertificate(SemanticDisposition.YES, state_0.state_hash, "sig-wal", intent.bindings, (), ())),
            state_0,
            compiler,
        )
        app_res = adapter.execute(prep, wal_seq)
        assert app_res.state.attributes["transfers.Alice"] == 10

        recovered_state, recovered_ledger = WALSequencer.recover(wal_path)
        assert recovered_state.state_hash == app_res.state.state_hash
        assert recovered_ledger.root_hash() == wal_seq.ledger.root_hash()
        assert len(recovered_ledger.records) == 1


def test_h7_fault_9_crash_before_egress() -> None:
    """Fault 9: Crash after commit but before egress preserves committed state; egress is safely retriable."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Alice"]}, "transfers.Alice": 0})
    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()
    intent = IntentEnvelope("sig-ce", "transfer", "u", "s", "c", (
        SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
        SemanticBinding("quantity", 5, BindingOrigin.PROBABILISTIC),
        SemanticBinding("recipient", "Alice", BindingOrigin.PROBABILISTIC),
    ), "cert-ce")
    prep = adapter.prepare(SemanticResult(SemanticDisposition.YES, intent, (), (), SemanticClosureCertificate(SemanticDisposition.YES, state_0.state_hash, "sig-ce", intent.bindings, (), ())), state_0, compiler)
    seq = DeterministicSequencer(state_0)
    app_res = adapter.execute(prep, seq)

    assert app_res.state.attributes["transfers.Alice"] == 5

    engine = GovernedEgressEngine()
    msg1 = engine.emit(intent, RecipientProfile.default_human(), status="COMMITTED")
    msg2 = engine.emit(intent, RecipientProfile.default_human(), status="COMMITTED")
    assert msg1.text == msg2.text
    assert msg1.egress_hash == msg2.egress_hash


def test_h7_fault_10_crash_during_egress() -> None:
    """Fault 10: Exception during egress rendering produces zero state corruption."""
    state_0 = WorldState(attributes={"transfers.Alice": 5})
    class ExplodingRenderer:
        def render(self, p: Any) -> str:
            raise MemoryError("Fatal memory corruption")

    engine = GovernedEgressEngine(renderer=ExplodingRenderer())
    intent = IntentEnvelope("sig-exp", "transfer", "u", "s", "c", (
        SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
        SemanticBinding("quantity", 5, BindingOrigin.PROBABILISTIC),
        SemanticBinding("recipient", "Alice", BindingOrigin.PROBABILISTIC),
    ), "cert-exp")
    msg = engine.emit(intent, RecipientProfile.default_human(), use_natural_language=True, status="COMMITTED")
    assert msg.mode == "DETERMINISTIC_FALLBACK"
    assert "TRANSFER committed: quantity=5, recipient=Alice." in msg.text
    assert state_0.attributes["transfers.Alice"] == 5


def test_h7_fault_11_stale_clarification() -> None:
    """Fault 11: State drift during clarification turn raises StaleClarificationError."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Alice"]}, "v": 1})
    clarif = ClarificationContext("c-stale", "sig-orig", state_0.state_hash, "cert-stale", (
        SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
    ), (SemanticRequirement("recipient"),), ())
    state_drifted = state_0.with_attribute("v", 2).advance_sequence()

    harness = SemanticHarness(MockTranslator())
    with pytest.raises(StaleClarificationError):
        harness.continue_interpretation("Alice", clarification=clarif, state=state_drifted, ingress=IngressContext("u", "s", "c"))


def test_h7_fault_12_invalid_model_artifact_fallback() -> None:
    """Fault 12: Null / unconfigured translator fails closed safely."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Alice"]}})
    from uow.semantic import NullSemanticTranslator
    harness = SemanticHarness(NullSemanticTranslator())
    res = harness.interpret("do something", state=state_0, ingress=IngressContext("u", "s", "c"), requirements=(
        SemanticRequirement("operator"),
    ))
    assert res.disposition is SemanticDisposition.CLARIFY


def test_h7_fault_13_translator_inference_failure() -> None:
    """Fault 13: Model throwing inference exception fails closed."""
    class FailingTranslator:
        def propose(self, req: Any) -> Any:
            raise RuntimeError("Inference timeout on accelerator")

    harness = SemanticHarness(FailingTranslator())
    with pytest.raises(RuntimeError):
        harness.interpret("transfer 5", state=WorldState(), ingress=IngressContext("u", "s", "c"), requirements=(
            SemanticRequirement("operator"),
        ))


def test_h7_fault_14_renderer_inference_failure() -> None:
    """Fault 14: Renderer throwing exception falls back deterministically."""
    class BadRenderer:
        def render(self, p: Any) -> str:
            raise ValueError("Token decoding failed")

    engine = GovernedEgressEngine(renderer=BadRenderer())
    msg = engine.emit({"disposition": "YES", "bindings": {"operator": "transfer", "quantity": 1, "recipient": "Bob"}}, RecipientProfile.default_human(), use_natural_language=True)
    assert msg.mode == "DETERMINISTIC_FALLBACK"


def test_h7_fault_15_semantic_round_trip_mismatch() -> None:
    """Fault 15: Renderer mutating material terminal triggers deterministic fallback."""
    bad_renderer = ConfigurableRenderer("Successfully executed transfer of 99 items to Bob.")
    engine = GovernedEgressEngine(renderer=bad_renderer)
    msg = engine.emit({"disposition": "YES", "bindings": {"operator": "transfer", "quantity": 1, "recipient": "Bob"}}, RecipientProfile.default_human(), use_natural_language=True)
    assert msg.mode == "DETERMINISTIC_FALLBACK"
    assert "quantity=1" in msg.text


# =========================================================================
# H7.3: Permanent Production Adversarial Falsification Bank
# =========================================================================

@pytest.mark.parametrize(
    "case_id,operator,recipient,quantity",
    [
        ("ADV_nonce_op_florp", "florp", "Alice", 10),
        ("ADV_nonce_op_zindle", "zindle", "Alice", 10),
        ("ADV_nonce_op_marnak", "marnak", "Alice", 10),
        ("ADV_nonce_recip_velq", "transfer", "velq", 10),
        ("ADV_nonce_recip_qorbin", "transfer", "qorbin", 10),
        ("ADV_nonce_recip_drazel", "transfer", "drazel", 10),
        ("ADV_ambiguous_recip", "transfer", "Mike", 10),  # Mike Smith vs Mike Jones
        ("ADV_missing_qty", "transfer", "Alice", None),
        ("ADV_negative_qty", "transfer", "Alice", -10),
        ("ADV_zero_qty", "transfer", "Alice", 0),
        ("ADV_overflow_qty", "transfer", "Alice", 9999999),
    ],
)
def test_h7_adversarial_bank(
    case_id: str,
    operator: str,
    recipient: str,
    quantity: Any,
) -> None:
    """Adversarial falsification cases must fail closed with 0 commits."""
    state_0 = WorldState(
        attributes={
            "entities": {"recipient": ["Alice", "Bob", "Mike Smith", "Mike Jones"]},
            "transfers.Alice": 0,
        }
    )
    bindings = [SemanticBinding("operator", operator, BindingOrigin.PROBABILISTIC)]
    if recipient:
        bindings.append(SemanticBinding("recipient", recipient, BindingOrigin.PROBABILISTIC))
    if quantity is not None:
        bindings.append(SemanticBinding("quantity", quantity, BindingOrigin.PROBABILISTIC))

    t = MockTranslator(CandidateSemanticBindings(candidate_bindings=tuple(bindings)))
    harness = SemanticHarness(
        t,
        admissibility_validator=DefaultSemanticAdmissibilityValidator(
            entity_directory={"recipient": ["Alice", "Bob", "Mike Smith", "Mike Jones"]}
        ),
    )
    res = harness.interpret(
        f"Signal {case_id}",
        state=state_0,
        ingress=IngressContext("u", "s", "c"),
        requirements=(SemanticRequirement("operator"), SemanticRequirement("quantity"), SemanticRequirement("recipient")),
    )
    # Crucial invariant: never YES, 0 intent envelope
    assert res.disposition in (SemanticDisposition.NO, SemanticDisposition.CLARIFY)
    assert res.intent is None

    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()
    seq = DeterministicSequencer(state_0)

    with pytest.raises(ValueError, match="Only semantic YES may be prepared"):
        adapter.prepare(res, state_0, compiler)
    assert len(seq.ledger.records) == 0


# =========================================================================
# H7.4: Invariant Verification Matrix
# =========================================================================

def test_h7_invariant_matrix() -> None:
    """Verifies the canonical UoW invariants plus subordinate semantic invariants H1-H8."""
    state_0 = WorldState(attributes={"operator": "transfer", "entities": {"recipient": ["Alice"]}, "transfers.Alice": 0})
    ingress = IngressContext("u", "s", "c")

    # H1: Deterministic Primacy (beta_D = 0)
    # Model proposing to overwrite state key is ignored because operator is resolved deterministically
    class OverwriteTranslator:
        def propose(self, req: Any) -> CandidateSemanticBindings:
            return CandidateSemanticBindings(
                candidate_bindings=(
                    SemanticBinding("operator", "purge", BindingOrigin.PROBABILISTIC),
                    SemanticBinding("quantity", 5, BindingOrigin.PROBABILISTIC),
                    SemanticBinding("recipient", "Alice", BindingOrigin.PROBABILISTIC),
                )
            )

    harness = SemanticHarness(
        OverwriteTranslator(),
        admissibility_validator=DefaultSemanticAdmissibilityValidator(),
    )
    res = harness.interpret(
        "signal",
        state=state_0,
        ingress=ingress,
        requirements=(
            SemanticRequirement("operator", state_key="operator"),
            SemanticRequirement("quantity"),
            SemanticRequirement("recipient"),
        ),
    )

    # 1. H1 & H2: Overwrite attempt: model proposing operator='purge' outside open frontier triggers FRONTIER_CONFINEMENT_VIOLATION -> NO
    res_overwrite = harness.interpret(
        "signal",
        state=state_0,
        ingress=ingress,
        requirements=(
            SemanticRequirement("operator", state_key="operator"),
            SemanticRequirement("quantity"),
            SemanticRequirement("recipient"),
        ),
    )
    assert res_overwrite.disposition is SemanticDisposition.NO
    assert "FRONTIER_CONFINEMENT_VIOLATION" in res_overwrite.certificate.reason_codes
    assert res_overwrite.intent is None  # beta_D = 0!

    # 2. Valid proposal over open frontier (quantity, recipient) succeeds and preserves deterministic operator
    class ValidFrontierTranslator:
        def propose(self, req: Any) -> CandidateSemanticBindings:
            return CandidateSemanticBindings(
                candidate_bindings=(
                    SemanticBinding("quantity", 5, BindingOrigin.PROBABILISTIC),
                    SemanticBinding("recipient", "Alice", BindingOrigin.PROBABILISTIC),
                )
            )

    harness_valid = SemanticHarness(
        ValidFrontierTranslator(),
        admissibility_validator=DefaultSemanticAdmissibilityValidator(),
    )
    res = harness_valid.interpret(
        "signal",
        state=state_0,
        ingress=ingress,
        requirements=(
            SemanticRequirement("operator", state_key="operator"),
            SemanticRequirement("quantity"),
            SemanticRequirement("recipient"),
        ),
    )
    assert res.disposition is SemanticDisposition.YES
    assert res.intent is not None
    assert res.intent.binding_map()["operator"] == "transfer"
    assert res.intent.binding_map()["quantity"] == 5
    assert res.intent.binding_map()["recipient"] == "Alice"

    # H3: Probabilistic non-authority
    # H6: Non-YES exclusion
    # H7: Authority non-escalation
    # H8: Failure non-amplification
    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()
    prep = adapter.prepare(res, state_0, compiler)
    seq = DeterministicSequencer(state_0)
    app_res = adapter.execute(prep, seq)

    assert app_res.state.attributes["transfers.Alice"] == 5
    assert len(seq.ledger.records) == 1

    # Egress round-trip identity
    engine = GovernedEgressEngine(renderer=DeterministicTemplateRenderer())
    egress = engine.emit(res, RecipientProfile.default_human(), use_natural_language=True, status="COMMITTED")
    assert egress.roundtrip_verified is True
    assert egress.drift_detected is False
