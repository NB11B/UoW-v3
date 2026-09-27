"""Milestone H5 Qualification Suite: Incremental Clarification over Residual Semantic Frontiers.

Verifies the 10 core H5 qualification invariants:
1. Single missing terminal resolution (CLARIFY -> continuation -> exactly 1 IntentEnvelope)
2. Multiple missing terminals multi-turn resolution (Turn 1 -> Turn 2 partial -> Turn 3 complete)
3. Ambiguous alternatives resolution ("Mike Jones" selects exact admissible alternative)
4. Unrelated answer fails closed (remains CLARIFY without forced hallucination)
5. Contradictory continuation rejection (ContradictoryContinuationError protects resolved bindings)
6. State drift during clarification (S_0 -> S_1 triggers StaleClarificationError)
7. Downstream authority revocation (Semantic YES halted closed by ApplicationSpine)
8. Replay / duplicate continuation idempotence and duplicate prevention
9. Ephemeral context crash/recovery (ClarificationContext != WorldState, zero inherent authority)
10. Multi-turn cryptographic provenance traversal (retains original and continuation signal IDs)

Core Invariant:
    resolved_t cap F_{P, t+1} = empty
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from uow import (
    DeterministicSequencer,
    EvidenceRecord,
    WorldState,
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
    ContradictoryContinuationError,
    DefaultSemanticAdmissibilityValidator,
    ExternalSignal,
    IngressContext,
    IntentEnvelope,
    PreparedSemanticUoW,
    SemanticAlternative,
    SemanticApplicationAdapter,
    SemanticBinding,
    SemanticCompilerRegistry,
    SemanticDisposition,
    SemanticHarness,
    SemanticRequirement,
    SemanticResult,
    SemanticStateDriftError,
    SemanticTranslationRequest,
    SemanticTranslator,
    StaleClarificationError,
    TransferUoWCompiler,
    ValidationVerdict,
)


class ConfigurableTranslator:
    """Translator returning pre-configured responses and recording frontiers."""

    def __init__(self, response: CandidateSemanticBindings | None = None) -> None:
        self.response = response or CandidateSemanticBindings()
        self.call_history: list[SemanticTranslationRequest] = []

    def propose(self, request: SemanticTranslationRequest) -> CandidateSemanticBindings:
        self.call_history.append(request)
        return self.response


# =========================================================================
# Gate 1: Single Missing Terminal Resolution
# =========================================================================

def test_h5_gate_1_single_missing_terminal_resolution() -> None:
    """Turn 1 missing recipient yields CLARIFY; Turn 2 continuation completes YES with 1 IntentEnvelope."""
    state_0 = WorldState(
        attributes={
            "entities": {"recipient": ["Mike", "Alice"]},
            "transfers.Mike": 0,
        }
    )
    ingress = IngressContext(principal_id="user-1", session_id="sess-h5-1", channel="text")

    # Turn 1: signal has operator and quantity, missing recipient
    turn1_translator = ConfigurableTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
                SemanticBinding("quantity", 3, BindingOrigin.PROBABILISTIC),
            ),
            unknowns=("recipient",),
        )
    )
    harness = SemanticHarness(
        turn1_translator,
        admissibility_validator=DefaultSemanticAdmissibilityValidator(),
    )

    reqs = (
        SemanticRequirement("operator"),
        SemanticRequirement("quantity"),
        SemanticRequirement("recipient"),
    )

    res_1 = harness.interpret(
        "Transfer 3 items",
        state=state_0,
        ingress=ingress,
        requirements=reqs,
    )

    assert res_1.disposition is SemanticDisposition.CLARIFY
    assert res_1.intent is None
    assert tuple(r.name for r in res_1.unresolved) == ("recipient",)

    # Ephemeral clarification created
    clarif = ClarificationContext.from_result(
        res_1,
        signal_id="sig-turn-1",
        state_hash=state_0.state_hash,
        source_signal="Transfer 3 items",
    )
    assert clarif.resolved_map() == {"operator": "transfer", "quantity": 3}
    assert clarif.unresolved_names() == ("recipient",)

    # Turn 2: user continuation provides "Mike"
    turn2_translator = ConfigurableTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),
            ),
        )
    )
    harness._translator = turn2_translator

    res_2 = harness.continue_interpretation(
        "Mike",
        clarification=clarif,
        state=state_0,
        ingress=ingress,
    )

    # Invariant: model was asked ONLY for residual frontier (recipient), NOT previously resolved bindings
    assert len(turn2_translator.call_history) == 1
    asked_frontier = tuple(r.name for r in turn2_translator.call_history[0].frontier)
    assert asked_frontier == ("recipient",)
    # Check invariant: resolved_t cap F_{P, t+1} = empty
    assert "operator" not in asked_frontier
    assert "quantity" not in asked_frontier

    # Closure succeeds: YES with exactly 1 IntentEnvelope containing all 3 bindings
    assert res_2.disposition is SemanticDisposition.YES
    assert res_2.intent is not None
    assert res_2.intent.binding_map() == {"operator": "transfer", "quantity": 3, "recipient": "Mike"}

    # Authoritative execution
    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()
    prep = adapter.prepare(res_2, state_0, compiler)
    seq = DeterministicSequencer(state_0)
    app_res = adapter.execute(prep, seq)

    assert app_res.state.attributes["transfers.Mike"] == 3
    assert len(seq.ledger.records) == 1


# =========================================================================
# Gate 2: Multiple Missing Terminals Multi-Turn Resolution
# =========================================================================

def test_h5_gate_2_multiple_missing_terminals_partial_continuation() -> None:
    """Turn 1 missing 2 terminals -> Turn 2 resolves 1 (still CLARIFY) -> Turn 3 resolves last (YES)."""
    state_0 = WorldState(
        attributes={
            "entities": {"recipient": ["Mike"], "destination": ["bay_1"]},
        }
    )
    ingress = IngressContext(principal_id="user-1", session_id="sess-h5-2", channel="text")

    # Turn 1: provides only operator
    t1 = ConfigurableTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
            ),
            unknowns=("recipient", "quantity"),
        )
    )
    harness = SemanticHarness(t1, admissibility_validator=DefaultSemanticAdmissibilityValidator())
    reqs = (
        SemanticRequirement("operator"),
        SemanticRequirement("recipient"),
        SemanticRequirement("quantity"),
    )
    res_1 = harness.interpret("Send transfer", state=state_0, ingress=ingress, requirements=reqs)
    assert res_1.disposition is SemanticDisposition.CLARIFY
    assert set(r.name for r in res_1.unresolved) == {"recipient", "quantity"}

    clarif_1 = ClarificationContext.from_result(res_1, signal_id="sig-turn-1", state_hash=state_0.state_hash)

    # Turn 2: continuation answers recipient="Mike", but quantity remains unknown
    t2 = ConfigurableTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),
            ),
            unknowns=("quantity",),
        )
    )
    harness._translator = t2
    res_2 = harness.continue_interpretation("Mike", clarification=clarif_1, state=state_0, ingress=ingress)

    # Still CLARIFY because quantity is open
    assert res_2.disposition is SemanticDisposition.CLARIFY
    assert res_2.intent is None
    assert tuple(r.name for r in res_2.unresolved) == ("quantity",)
    assert res_2.certificate.resolved_bindings == (
        SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
        SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),
    )

    clarif_2 = ClarificationContext.from_result(
        res_2,
        signal_id="sig-turn-2",
        state_hash=state_0.state_hash,
        turn=2,
    )
    assert clarif_2.unresolved_names() == ("quantity",)

    # Turn 3: continuation answers quantity=42
    t3 = ConfigurableTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("quantity", 42, BindingOrigin.PROBABILISTIC),
            ),
        )
    )
    harness._translator = t3
    res_3 = harness.continue_interpretation("42", clarification=clarif_2, state=state_0, ingress=ingress)

    # Invariant: model in Turn 3 was asked ONLY for quantity
    assert tuple(r.name for r in t3.call_history[0].frontier) == ("quantity",)

    # Turn 3 completes: YES
    assert res_3.disposition is SemanticDisposition.YES
    assert res_3.intent is not None
    assert res_3.intent.binding_map() == {"operator": "transfer", "recipient": "Mike", "quantity": 42}


# =========================================================================
# Gate 3: Ambiguous Alternatives Selection
# =========================================================================

def test_h5_gate_3_ambiguous_alternatives_exact_selection() -> None:
    """Turn 1 flags ambiguity (Mike Smith vs Mike Jones); Turn 2 selects 'Mike Jones' without model call."""
    state_0 = WorldState(
        attributes={
            "entities": {"recipient": ["Mike Smith", "Mike Jones"]},
        }
    )
    ingress = IngressContext(principal_id="user-1", session_id="s3", channel="text")

    # Turn 1: user says "Send 5 to Mike", admissibility returns ambiguous alternatives
    t1 = ConfigurableTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
                SemanticBinding("quantity", 5, BindingOrigin.PROBABILISTIC),
                SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),
            ),
        )
    )
    harness = SemanticHarness(
        t1,
        admissibility_validator=DefaultSemanticAdmissibilityValidator(
            entity_directory={"recipient": ["Mike Smith", "Mike Jones"]}
        ),
    )
    reqs = (
        SemanticRequirement("operator"),
        SemanticRequirement("quantity"),
        SemanticRequirement("recipient"),
    )
    res_1 = harness.interpret("Send 5 to Mike", state=state_0, ingress=ingress, requirements=reqs)

    assert res_1.disposition is SemanticDisposition.CLARIFY
    assert len(res_1.alternatives) == 2
    alt_values = [alt.bindings[0].value for alt in res_1.alternatives]
    assert "Mike Smith" in alt_values and "Mike Jones" in alt_values

    clarif = ClarificationContext.from_result(res_1, signal_id="sig-turn-1", state_hash=state_0.state_hash)

    # Turn 2: user says "Mike Jones"
    # Spy translator ensures translator is NOT called if direct alternative matches
    spy = ConfigurableTranslator()
    harness._translator = spy

    res_2 = harness.continue_interpretation(
        "Mike Jones",
        clarification=clarif,
        state=state_0,
        ingress=ingress,
    )

    # Invariant: direct alternative selection bypasses probabilistic model
    assert len(spy.call_history) == 0
    assert res_2.disposition is SemanticDisposition.YES
    assert res_2.intent is not None
    assert res_2.intent.binding_map()["recipient"] == "Mike Jones"
    assert res_2.intent.binding_map()["quantity"] == 5
    assert res_2.intent.binding_map()["operator"] == "transfer"


# =========================================================================
# Gate 4: Unrelated Answer Fails Closed
# =========================================================================

def test_h5_gate_4_unrelated_answer_fails_closed() -> None:
    """Continuation with an unrelated answer ('blue') does not force a binding; remains CLARIFY."""
    state_0 = WorldState(
        attributes={
            "entities": {"recipient": ["Mike", "Alice"]},
        }
    )
    ingress = IngressContext(principal_id="user-1", session_id="s4", channel="text")

    # Turn 1 missing recipient
    clarif = ClarificationContext(
        clarification_id="clarif-gate-4",
        original_signal_id="sig-g4",
        original_state_hash=state_0.state_hash,
        semantic_certificate_hash="a" * 64,
        resolved_bindings=(
            SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
            SemanticBinding("quantity", 10, BindingOrigin.PROBABILISTIC),
        ),
        unresolved=(SemanticRequirement("recipient"),),
        alternatives=(),
    )

    # Turn 2: user says "blue", model proposes recipient="blue", validator rejects it as UNKNOWN
    t2 = ConfigurableTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("recipient", "blue", BindingOrigin.PROBABILISTIC),
            ),
        )
    )
    harness = SemanticHarness(t2, admissibility_validator=DefaultSemanticAdmissibilityValidator())

    res_2 = harness.continue_interpretation(
        "blue",
        clarification=clarif,
        state=state_0,
        ingress=ingress,
    )

    # Must remain CLARIFY with 0 intent, never forcing an invalid entity
    assert res_2.disposition is SemanticDisposition.CLARIFY
    assert res_2.intent is None
    assert tuple(r.name for r in res_2.unresolved) == ("recipient",)


# =========================================================================
# Gate 5: Contradictory Continuation Rejection
# =========================================================================

def test_h5_gate_5_contradictory_continuation_rejection() -> None:
    """Continuation proposing to overwrite an already resolved binding raises ContradictoryContinuationError."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Mike"]}})
    ingress = IngressContext(principal_id="user-1", session_id="s5", channel="text")

    # Already resolved: operator="transfer"
    clarif = ClarificationContext(
        clarification_id="clarif-g5",
        original_signal_id="sig-g5",
        original_state_hash=state_0.state_hash,
        semantic_certificate_hash="b" * 64,
        resolved_bindings=(
            SemanticBinding("operator", "transfer", BindingOrigin.DETERMINISTIC),
            SemanticBinding("quantity", 10, BindingOrigin.PROBABILISTIC),
        ),
        unresolved=(SemanticRequirement("recipient"),),
        alternatives=(),
    )

    # Continuation attempts to overwrite operator to "purge"
    t_bad = ConfigurableTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),
                SemanticBinding("operator", "purge", BindingOrigin.PROBABILISTIC),  # Contradiction!
            ),
        )
    )
    harness = SemanticHarness(t_bad, admissibility_validator=DefaultSemanticAdmissibilityValidator())

    with pytest.raises(ContradictoryContinuationError) as exc_info:
        harness.continue_interpretation(
            "Purge instead to Mike",
            clarification=clarif,
            state=state_0,
            ingress=ingress,
        )
    assert "Continuation contradicts previously resolved terminal 'operator'" in str(exc_info.value)


# =========================================================================
# Gate 6: State Drift During Clarification
# =========================================================================

def test_h5_gate_6_state_drift_during_clarification_fails_closed() -> None:
    """State advancing between turns invalidates clarification context; raises StaleClarificationError."""
    state_0 = WorldState(attributes={"counter": 0, "entities": {"recipient": ["Mike"]}})
    ingress = IngressContext(principal_id="user-1", session_id="s6", channel="text")

    clarif = ClarificationContext(
        clarification_id="clarif-g6",
        original_signal_id="sig-g6",
        original_state_hash=state_0.state_hash,
        semantic_certificate_hash="c" * 64,
        resolved_bindings=(SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),),
        unresolved=(SemanticRequirement("recipient"),),
        alternatives=(),
    )

    # State drifts to S_1 before user responds
    state_1 = state_0.with_attribute("counter", 1).advance_sequence()

    harness = SemanticHarness(
        ConfigurableTranslator(
            CandidateSemanticBindings(
                candidate_bindings=(SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),)
            )
        ),
        admissibility_validator=DefaultSemanticAdmissibilityValidator(),
    )

    with pytest.raises(StaleClarificationError) as exc_info:
        harness.continue_interpretation(
            "Mike",
            clarification=clarif,
            state=state_1,
            ingress=ingress,
        )
    assert "State drift detected during clarification" in str(exc_info.value)


# =========================================================================
# Gate 7: Authority Revocation During Clarification
# =========================================================================

def test_h5_gate_7_authority_revocation_halts_downstream() -> None:
    """Semantic continuation succeeds to YES, but downstream authority revocation halts commit cleanly."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Mike"]}})
    ingress = IngressContext(principal_id="user-1", session_id="s7", channel="text")

    clarif = ClarificationContext(
        clarification_id="clarif-g7",
        original_signal_id="sig-g7",
        original_state_hash=state_0.state_hash,
        semantic_certificate_hash="d" * 64,
        resolved_bindings=(
            SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
            SemanticBinding("quantity", 7, BindingOrigin.PROBABILISTIC),
        ),
        unresolved=(SemanticRequirement("recipient"),),
        alternatives=(),
    )

    harness = SemanticHarness(
        ConfigurableTranslator(
            CandidateSemanticBindings(
                candidate_bindings=(SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),)
            )
        ),
        admissibility_validator=DefaultSemanticAdmissibilityValidator(),
    )

    # Semantic continuation completes
    res = harness.continue_interpretation("Mike", clarification=clarif, state=state_0, ingress=ingress)
    assert res.disposition is SemanticDisposition.YES
    assert res.intent is not None

    # Downstream authority revoked: system halted
    state_halted = state_0.with_status("HALTED")
    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()
    prepared_halted = PreparedSemanticUoW(
        uow=compiler.compile(res.intent, state_0),
        semantic_certificate_hash=res.certificate.certificate_hash,
        expected_state_hash=state_halted.state_hash,
        signal_id=res.intent.signal_id,
        compiler_id=compiler.compiler_id,
    )
    sequencer = DeterministicSequencer(state_halted)

    with pytest.raises(ValueError, match="requires RUNNING authoritative state"):
        adapter.execute(prepared_halted, sequencer)

    assert len(sequencer.ledger.records) == 0


# =========================================================================
# Gate 8: Replay / Duplicate Continuation
# =========================================================================

def test_h5_gate_8_replay_duplicate_continuation_idempotence() -> None:
    """Replaying identical continuation yields identical UoW and cannot double-commit."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Mike"]}})
    ingress = IngressContext(principal_id="user-1", session_id="s8", channel="text")

    clarif = ClarificationContext(
        clarification_id="clarif-g8",
        original_signal_id="sig-g8",
        original_state_hash=state_0.state_hash,
        semantic_certificate_hash="e" * 64,
        resolved_bindings=(SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),),
        unresolved=(SemanticRequirement("recipient"),),
        alternatives=(),
    )

    t = ConfigurableTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),)
        )
    )
    harness = SemanticHarness(t, admissibility_validator=DefaultSemanticAdmissibilityValidator())

    signal = ExternalSignal("Mike", signal_id="sig-cont-dup")
    res1 = harness.continue_interpretation(signal, clarification=clarif, state=state_0, ingress=ingress)
    res2 = harness.continue_interpretation(signal, clarification=clarif, state=state_0, ingress=ingress)

    # Identical deterministic certificate hash
    assert res1.certificate.certificate_hash == res2.certificate.certificate_hash
    assert res1.intent.closure_certificate_hash == res2.intent.closure_certificate_hash

    # Commit first
    compiler = TransferUoWCompiler()
    adapter = SemanticApplicationAdapter()
    prep1 = adapter.prepare(res1, state_0, compiler)
    seq = DeterministicSequencer(state_0)
    adapter.execute(prep1, seq)

    # Second commit fails state drift
    with pytest.raises(SemanticStateDriftError):
        adapter.execute(prep1, seq)

    assert len(seq.ledger.records) == 1


# =========================================================================
# Gate 9: Ephemeral Context Crash / Recovery
# =========================================================================

def test_h5_gate_9_ephemeral_clarification_no_authority() -> None:
    """ClarificationContext carries zero authority; can be deserialized but cannot bypass state drift."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Mike"]}})
    clarif = ClarificationContext(
        clarification_id="clarif-persist",
        original_signal_id="sig-persist",
        original_state_hash=state_0.state_hash,
        semantic_certificate_hash="f" * 64,
        resolved_bindings=(SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),),
        unresolved=(SemanticRequirement("recipient"),),
        alternatives=(),
        turn=1,
    )

    # Serialize to JSON-compatible dict and restore
    serialized = {
        "clarification_id": clarif.clarification_id,
        "original_signal_id": clarif.original_signal_id,
        "original_state_hash": clarif.original_state_hash,
        "semantic_certificate_hash": clarif.semantic_certificate_hash,
        "resolved_bindings": [
            {"terminal": b.terminal, "value": b.value, "origin": b.origin.value}
            for b in clarif.resolved_bindings
        ],
        "unresolved": [r.name for r in clarif.unresolved],
        "turn": clarif.turn,
    }

    # Restored context
    restored_clarif = ClarificationContext(
        clarification_id=serialized["clarification_id"],
        original_signal_id=serialized["original_signal_id"],
        original_state_hash=serialized["original_state_hash"],
        semantic_certificate_hash=serialized["semantic_certificate_hash"],
        resolved_bindings=tuple(
            SemanticBinding(b["terminal"], b["value"], BindingOrigin(b["origin"]))
            for b in serialized["resolved_bindings"]
        ),
        unresolved=tuple(SemanticRequirement(name) for name in serialized["unresolved"]),
        alternatives=(),
        turn=serialized["turn"],
    )

    # 1. Against identical state: continuation succeeds
    harness = SemanticHarness(
        ConfigurableTranslator(
            CandidateSemanticBindings(
                candidate_bindings=(SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),)
            )
        ),
        admissibility_validator=DefaultSemanticAdmissibilityValidator(),
    )
    res = harness.continue_interpretation(
        "Mike",
        clarification=restored_clarif,
        state=state_0,
        ingress=IngressContext("p", "s", "c"),
    )
    assert res.disposition is SemanticDisposition.YES

    # 2. Against drifted state: continuation fails closed
    state_drifted = state_0.with_attribute("new_tx", 1).advance_sequence()
    with pytest.raises(StaleClarificationError):
        harness.continue_interpretation(
            "Mike",
            clarification=restored_clarif,
            state=state_drifted,
            ingress=IngressContext("p", "s", "c"),
        )


# =========================================================================
# Gate 10: Multi-Turn Cryptographic Provenance Traversal
# =========================================================================

def test_h5_gate_10_multi_turn_provenance_traversal() -> None:
    """Final certificate and evidence refs retain both original signal and continuation signal IDs."""
    state_0 = WorldState(attributes={"entities": {"recipient": ["Alice"]}})
    ingress = IngressContext(principal_id="user-audit", session_id="sess-audit", channel="text")

    orig_signal = ExternalSignal("Send packages", signal_id="sig-orig-100")
    t1 = ConfigurableTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),),
            unknowns=("recipient",),
        )
    )
    harness = SemanticHarness(t1, admissibility_validator=DefaultSemanticAdmissibilityValidator())

    res1 = harness.interpret(
        orig_signal,
        state=state_0,
        ingress=ingress,
        requirements=(SemanticRequirement("operator"), SemanticRequirement("recipient")),
    )
    assert res1.disposition is SemanticDisposition.CLARIFY

    clarif = ClarificationContext.from_result(
        res1,
        signal_id=orig_signal.signal_id,
        state_hash=state_0.state_hash,
        source_signal=orig_signal.raw,
    )

    # Turn 2 continuation
    cont_signal = ExternalSignal("Alice", signal_id="sig-cont-200")
    t2 = ConfigurableTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(SemanticBinding("recipient", "Alice", BindingOrigin.PROBABILISTIC),)
        )
    )
    harness._translator = t2

    res2 = harness.continue_interpretation(
        cont_signal,
        clarification=clarif,
        state=state_0,
        ingress=ingress,
    )
    assert res2.disposition is SemanticDisposition.YES
    assert res2.intent is not None

    # Inspect provenance references
    ev_refs = res2.certificate.evidence_refs
    assert f"original_signal:{orig_signal.signal_id}" in ev_refs
    assert f"clarification:{clarif.clarification_id}" in ev_refs
    assert "continuation_turn:2" in ev_refs

    # Authoritative execution and ledger provenance
    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()
    prep = adapter.prepare(res2, state_0, compiler)
    seq = DeterministicSequencer(state_0)
    app_res = adapter.execute(prep, seq)

    # Traverse from EvidenceRecord back to original signal
    ev = app_res.evidence
    assert ev.uow_id == prep.uow.H.identity
    assert prep.uow.H.parent_context == f"semantic:{res2.certificate.certificate_hash}"
    assert res2.intent.closure_certificate_hash == res2.certificate.certificate_hash
    assert res2.intent.signal_id == cont_signal.signal_id
    assert f"original_signal:{orig_signal.signal_id}" in res2.intent.evidence_refs
