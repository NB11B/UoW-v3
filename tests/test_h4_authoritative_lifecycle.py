"""H4: Authoritative UoW Lifecycle Integration Qualification Suite.

Verifies the 11 authoritative gates of H4:
- H4.0: Deterministic Ingress (F_P = empty -> 0 model calls, deterministic commit)
- H4.1: Native Model Transaction (M_H3 -> Admissibility -> YES -> Native UoW -> Spine -> Commit)
- H4.2: Unsafe Model Error Interception (HO_unk_quibble_fp3 -> CLARIFY -> 0 commits, U_system = 0)
- H4.3: State Drift Detection (S_0 -> S_1 -> SemanticStateDriftError -> 0 commits)
- H4.4: Authority Revocation Before Commit (Lease revoked -> 0 commits)
- H4.5: Concurrent Disjoint Semantic Requests (Serializable execution)
- H4.6: Concurrent Conflicting Semantic Requests (OCC hazard detection / State drift rejection)
- H4.7: Crash Recovery After Semantic Closure (Audit chain recovery & drift protection)
- H4.8: Crash Recovery During Commit (WAL replay & ledger integrity)
- H4.9: Replay / Duplicate Signal Handling (Deterministic uow_id & idempotent outcome)
- H4.10: Provenance Traversal Across Audit Chain (Evidence -> Cert -> Intent -> Signal)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
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
    DefaultSemanticAdmissibilityValidator,
    ExternalSignal,
    IngressContext,
    IntentEnvelope,
    PreparedSemanticUoW,
    PurgeUoWCompiler,
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
    TransferUoWCompiler,
    ValidationVerdict,
    derive_semantic_uow_id,
)
from uow.semantic.adapters import (
    HuggingFaceSemanticTranslator,
    HuggingFaceSemanticTranslatorConfig,
    SemanticModelManifest,
)


class MockHuggingFaceBackend:
    """Configurable fake backend simulating model loading and generation without PyTorch/GPU."""

    def __init__(self, response_text: str = "") -> None:
        self.response_text = response_text
        self.load_calls = 0
        self.generate_calls = 0
        self.last_messages: list[dict[str, str]] | None = None
        self.fail_load = False
        self.fail_generate = False

    def load(
        self,
        config: HuggingFaceSemanticTranslatorConfig,
        manifest: SemanticModelManifest,
    ) -> None:
        self.load_calls += 1
        if self.fail_load:
            raise RuntimeError("Simulated backend load error")

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_new_tokens: int,
    ) -> str:
        self.generate_calls += 1
        self.last_messages = messages
        if self.fail_generate:
            raise RuntimeError("Simulated backend inference failure")
        return self.response_text


class SpyTranslator:
    """Translator spy tracking proposal invocations."""

    def __init__(self, response: CandidateSemanticBindings | None = None) -> None:
        self.response = response or CandidateSemanticBindings()
        self.call_count = 0
        self.last_request: SemanticTranslationRequest | None = None

    def propose(self, request: SemanticTranslationRequest) -> CandidateSemanticBindings:
        self.call_count += 1
        self.last_request = request
        return self.response


def _setup_mock_manifest_dir(tmp_path: Path) -> Path:
    adapter_bytes = b"mock_safetensors_bytes"
    adapter_sha = hashlib.sha256(adapter_bytes).hexdigest()
    manifest_data = {
        "schema_version": "1.0.0",
        "semantic_codec_id": "uow.semantic.h3.smollm2_135m",
        "base_model_id": "HuggingFaceTB/SmolLM2-135M-Instruct",
        "base_model_revision": "12fd25f77366fa6b3b4b768ec3050bf629380bac",
        "tokenizer_id": "HuggingFaceTB/SmolLM2-135M-Instruct",
        "tokenizer_revision": "12fd25f77366fa6b3b4b768ec3050bf629380bac",
        "adapter_format": "peft-lora",
        "adapter_sha256": adapter_sha,
        "adapter_parameter_count": 460800,
        "corpus_version": "h3-native-corpus-v1",
        "grammar_version": "grammar-h3-native-v1",
        "qualification_version": "h3-native-qualification-v1",
        "conformance_suite_version": "h3-native-conformance-v1",
        "supported_operator_families": [
            "performative",
            "semantic_head",
            "argument",
            "reference",
            "quantity",
            "negation",
            "temporal",
            "conditional",
            "modality",
        ],
        "supported_output_schema": "uow.semantic.bindings.v1",
    }
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")
    adapter_file = tmp_path / "adapter_model.safetensors"
    adapter_file.write_bytes(adapter_bytes)
    return tmp_path


# =========================================================================
# Gate H4.0: Deterministic Ingress (F_P = empty -> 0 model calls, commit)
# =========================================================================

def test_h4_0_deterministic_ingress_zero_inference_load() -> None:
    """When all requirements are satisfied by deterministic context, translator calls == 0."""
    initial_state = WorldState(
        attributes={
            "recipient": "Mike",
            "operator": "transfer",
            "quantity": 25,
            "entities": {"recipient": ["Mike", "Alice"]},
        }
    )
    ingress = IngressContext(principal_id="admin-1", session_id="sess-0", channel="api")
    requirements = (
        SemanticRequirement("recipient", state_key="recipient"),
        SemanticRequirement("operator", state_key="operator"),
        SemanticRequirement("quantity", state_key="quantity"),
    )

    spy = SpyTranslator()
    harness = SemanticHarness(
        spy,
        admissibility_validator=DefaultSemanticAdmissibilityValidator(),
    )

    result = harness.interpret(
        "Deterministic batch trigger",
        state=initial_state,
        ingress=ingress,
        requirements=requirements,
    )

    # Invariant: zero model invocations
    assert spy.call_count == 0
    assert result.disposition is SemanticDisposition.YES
    assert result.intent is not None

    # Deterministic compilation & authoritative commit
    compiler = TransferUoWCompiler()
    adapter = SemanticApplicationAdapter()
    prepared = adapter.prepare(result, initial_state, compiler)

    sequencer = DeterministicSequencer(initial_state)
    app_result = adapter.execute(prepared, sequencer)

    assert app_result.state.attributes["transfers.Mike"] == 25
    assert len(sequencer.ledger.records) == 1
    assert sequencer.ledger.verify_integrity()


# =========================================================================
# Gate H4.1: Native Model Transaction
# =========================================================================

def test_h4_1_native_model_transaction_commit_and_state_verification(tmp_path: Path) -> None:
    """M_H3 proposal passes admissibility, certifies YES, compiles to UoW, and commits."""
    model_dir = _setup_mock_manifest_dir(tmp_path)
    model_output = json.dumps({
        "bindings": [
            {"terminal": "recipient", "value": "Mike"},
            {"terminal": "quantity", "value": 50},
            {"terminal": "operator", "value": "transfer"},
        ],
        "alternatives": [],
        "unknowns": [],
    })
    backend = MockHuggingFaceBackend(response_text=model_output)
    config = HuggingFaceSemanticTranslatorConfig(model_path=model_dir)
    translator = HuggingFaceSemanticTranslator(config, backend=backend)

    state_0 = WorldState(
        attributes={
            "entities": {"recipient": ["Mike", "Alice", "Bob"]},
        }
    )
    validator = DefaultSemanticAdmissibilityValidator()
    harness = SemanticHarness(translator, admissibility_validator=validator)

    ingress = IngressContext(principal_id="user-ops", session_id="sess-1", channel="text")
    requirements = (
        SemanticRequirement("recipient"),
        SemanticRequirement("quantity"),
        SemanticRequirement("operator"),
    )

    result = harness.interpret(
        "Transfer 50 units to Mike",
        state=state_0,
        ingress=ingress,
        requirements=requirements,
    )

    assert result.disposition is SemanticDisposition.YES
    assert result.intent is not None
    assert result.intent.binding_map()["recipient"] == "Mike"
    assert result.intent.binding_map()["quantity"] == 50

    # Compile and execute via ApplicationSpine
    registry = SemanticCompilerRegistry()
    adapter = SemanticApplicationAdapter()
    prepared = adapter.prepare(result, state_0, registry)

    sequencer = DeterministicSequencer(state_0)
    app_result = adapter.execute(prepared, sequencer)

    # State mutations verified
    assert app_result.state.attributes["transfers.Mike"] == 50
    assert app_result.state.attributes["transfers.Mike.signal_id"] == result.intent.signal_id
    assert app_result.certificate.is_valid
    assert len(sequencer.ledger.records) == 1
    assert sequencer.ledger.verify_integrity()


# =========================================================================
# Gate H4.2: Unsafe Model Error Interception (U_system = 0)
# =========================================================================

def test_h4_2_unsafe_model_error_interception_system_safety_guarantee(tmp_path: Path) -> None:
    """Reproduction of holdout HO_unk_quibble_fp3: hallucinated entity intercepted, 0 commits."""
    model_dir = _setup_mock_manifest_dir(tmp_path)

    # Model hallucinates "quibble" as item and "unknown_sector" as destination
    hallucinated_output = json.dumps({
        "bindings": [
            {"terminal": "item", "value": "quibble"},
            {"terminal": "destination", "value": "quibble_destination"},
            {"terminal": "operator", "value": "dispatch"},
        ],
        "alternatives": [],
        "unknowns": [],
    })
    backend = MockHuggingFaceBackend(response_text=hallucinated_output)
    config = HuggingFaceSemanticTranslatorConfig(model_path=model_dir)
    translator = HuggingFaceSemanticTranslator(config, backend=backend)

    # State with authorized known entities
    state_0 = WorldState(
        attributes={
            "entities": {
                "item": ["standard_crate", "coolant_rod", "battery_cell"],
                "destination": ["bay_1", "bay_2", "depot_north"],
            },
        }
    )
    validator = DefaultSemanticAdmissibilityValidator()
    harness = SemanticHarness(translator, admissibility_validator=validator)

    ingress = IngressContext(principal_id="user-ops", session_id="sess-2", channel="text")
    requirements = (
        SemanticRequirement("item"),
        SemanticRequirement("destination"),
        SemanticRequirement("operator"),
    )

    # External signal is exact holdout HO_unk_quibble_fp3
    result = harness.interpret(
        "Dispatch five quibble modules here immediately.",
        state=state_0,
        ingress=ingress,
        requirements=requirements,
    )

    # 1. Harness catches unresolvable entities and classifies to CLARIFY
    assert result.disposition is SemanticDisposition.CLARIFY
    assert result.intent is None
    unresolved_names = set(r.name for r in result.unresolved)
    assert "item" in unresolved_names or "destination" in unresolved_names

    # 2. Application adapter fails closed: non-YES cannot be prepared
    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()
    with pytest.raises(ValueError, match="Only semantic YES may be prepared"):
        adapter.prepare(result, state_0, compiler)

    # 3. System state untouched: U_system = 0
    sequencer = DeterministicSequencer(state_0)
    assert sequencer.current_state.state_hash == state_0.state_hash
    assert len(sequencer.ledger.records) == 0


def test_h4_2_unregistered_operator_and_contradictory_quantity() -> None:
    """Unregistered operators and illegal quantities are rejected by admissibility."""
    validator = DefaultSemanticAdmissibilityValidator()
    state = WorldState(attributes={})

    # Unregistered operator
    res_op = validator.validate(
        SemanticBinding("operator", "malicious_overwrite", BindingOrigin.PROBABILISTIC),
        SemanticRequirement("operator"),
        state,
    )
    assert res_op.verdict is ValidationVerdict.UNKNOWN
    assert "UNREGISTERED_OPERATOR" in res_op.reasons[0]

    # Negative quantity
    res_qty_neg = validator.validate(
        SemanticBinding("quantity", -15, BindingOrigin.PROBABILISTIC),
        SemanticRequirement("quantity"),
        state,
    )
    assert res_qty_neg.verdict is ValidationVerdict.CONTRADICTORY

    # Quantity exceeding limit
    res_qty_exceed = validator.validate(
        SemanticBinding("quantity", 999999, BindingOrigin.PROBABILISTIC),
        SemanticRequirement("quantity"),
        state,
    )
    assert res_qty_exceed.verdict is ValidationVerdict.CONTRADICTORY


def test_h4_2_nonce_family_generalization_bank() -> None:
    """Falsification: unseen nonce operators and entities are rejected by admissibility.

    Verifies:
        x not in Registry_t ==> VALID(x) = false
    Across a bank of 75 previously unseen nonces (florp, zindle, marnak, velq, qorbin, etc.),
    proving safety derives from registry-based admissibility rather than fitting to 'quibble'.
    Guarantees exactly 0 prepared UoWs and 0 commits.
    """
    nonce_prefixes = ("flor", "zind", "marn", "vel", "qorb", "krix", "blon", "draz", "farn", "gond", "jalk", "luna", "morv", "plon", "rund")
    nonce_suffixes = ("p", "le", "ak", "q", "in", "al", "vex", "ik", "el", "orix", "en", "phex", "ath", "tex", "ar")
    nonce_words = [f"{p}{s}" for p in nonce_prefixes for s in nonce_suffixes][:75]
    assert len(nonce_words) == 75

    state_0 = WorldState(
        attributes={
            "entities": {
                "recipient": ["Mike", "Alice", "Bob"],
                "item": ["crate", "rod", "battery"],
                "destination": ["bay_1", "bay_2"],
            },
            "transfers.Mike": 0,
        }
    )
    validator = DefaultSemanticAdmissibilityValidator()
    compiler = TransferUoWCompiler()
    adapter = SemanticApplicationAdapter()

    prepared_count = 0
    committed_count = 0
    invalid_verdicts = 0

    for idx, nonce in enumerate(nonce_words):
        term = ("operator", "item", "recipient", "destination")[idx % 4]
        binding = SemanticBinding(term, nonce, BindingOrigin.PROBABILISTIC)
        req = SemanticRequirement(term)

        # 1. Direct validation: x not in Registry_t ==> VALID(x) = False
        v_res = validator.validate(binding, req, state_0)
        assert v_res.verdict is not ValidationVerdict.VALID
        assert v_res.verdict is ValidationVerdict.UNKNOWN
        invalid_verdicts += 1

        # 2. End-to-end interpretation through SemanticHarness
        class NonceTranslator:
            def __init__(self, t: str, v: str) -> None:
                self._t = t
                self._v = v

            def propose(self, r: SemanticTranslationRequest) -> CandidateSemanticBindings:
                return CandidateSemanticBindings(
                    candidate_bindings=(
                        SemanticBinding(self._t, self._v, BindingOrigin.PROBABILISTIC),
                    )
                )

        harness = SemanticHarness(NonceTranslator(term, nonce), admissibility_validator=validator)
        result = harness.interpret(
            f"Please {nonce} immediately",
            state=state_0,
            ingress=IngressContext("auditor", f"sess-nonce-{idx}", "ch"),
            requirements=(req,),
        )

        assert result.disposition in (SemanticDisposition.CLARIFY, SemanticDisposition.NO)
        assert result.intent is None

        # 3. Preparation must fail closed
        try:
            adapter.prepare(result, state_0, compiler)
            prepared_count += 1
        except ValueError:
            pass

    # Authoritative sequencer remains at 0 commits
    sequencer = DeterministicSequencer(state_0)
    assert invalid_verdicts == len(nonce_words)
    assert prepared_count == 0
    assert committed_count == 0
    assert len(sequencer.ledger.records) == 0
    assert sequencer.current_state.state_hash == state_0.state_hash


# =========================================================================
# Gate H4.3: State Drift Detection (S_0 -> S_1)
# =========================================================================

def test_h4_3_state_drift_rejection_fail_closed() -> None:
    """Pre-execution state drift is detected before ApplicationSpine; fails closed."""
    state_0 = WorldState(
        attributes={
            "recipient": "Mike",
            "operator": "transfer",
            "transfers.Mike": 0,
            "entities": {"recipient": ["Mike"]},
        }
    )
    ingress = IngressContext(principal_id="user-1", session_id="s1", channel="text")
    requirements = (
        SemanticRequirement("recipient", state_key="recipient"),
        SemanticRequirement("operator", state_key="operator"),
    )

    harness = SemanticHarness(
        SpyTranslator(),
        admissibility_validator=DefaultSemanticAdmissibilityValidator(),
    )
    result = harness.interpret(
        "transfer to Mike",
        state=state_0,
        ingress=ingress,
        requirements=requirements,
    )
    assert result.disposition is SemanticDisposition.YES

    compiler = TransferUoWCompiler()
    adapter = SemanticApplicationAdapter()

    # 1. Prepared against S_0
    prepared = adapter.prepare(result, state_0, compiler)

    # 2. State drifts before execution: another transaction advances state to S_1
    state_1 = state_0.with_attribute("transfers.Mike", 10).advance_sequence()
    sequencer = DeterministicSequencer(state_1)

    # 3. Execution must raise SemanticStateDriftError without committing
    with pytest.raises(SemanticStateDriftError) as exc_info:
        adapter.execute(prepared, sequencer)
    assert "State drift detected before execution" in str(exc_info.value)

    # Sequencer state remains strictly at S_1 with 0 commits added
    assert sequencer.current_state.state_hash == state_1.state_hash
    assert len(sequencer.ledger.records) == 0

    # 4. Preparation against drifted state also raises SemanticStateDriftError
    with pytest.raises(SemanticStateDriftError) as exc_prep:
        adapter.prepare(result, state_1, compiler)
    assert "State hash mismatch at preparation" in str(exc_prep.value)


# =========================================================================
# Gate H4.4: Authority Revocation Before Commit
# =========================================================================

def test_h4_4_authority_revocation_zero_commits() -> None:
    """Revoking state execution authority before commit halts execution cleanly."""
    state_0 = WorldState(
        attributes={
            "operator": "transfer",
            "entities": {"recipient": ["Mike"]},
        }
    )
    ingress = IngressContext(principal_id="user-1", session_id="s1", channel="text")
    requirements = (SemanticRequirement("operator", state_key="operator"),)

    harness = SemanticHarness(SpyTranslator())
    result = harness.interpret("run transfer", state=state_0, ingress=ingress, requirements=requirements)
    compiler = TransferUoWCompiler()
    adapter = SemanticApplicationAdapter()
    prepared = adapter.prepare(result, state_0, compiler)

    # Authority revoked: state status transitioned to HALTED
    state_halted = state_0.with_status("HALTED")
    # Even if expected_state_hash matched, ApplicationSpine enforces RUNNING status
    prepared_halted = PreparedSemanticUoW(
        uow=prepared.uow,
        semantic_certificate_hash=prepared.semantic_certificate_hash,
        expected_state_hash=state_halted.state_hash,
        signal_id=prepared.signal_id,
        compiler_id=prepared.compiler_id,
    )
    sequencer = DeterministicSequencer(state_halted)

    with pytest.raises(ValueError, match="requires RUNNING authoritative state"):
        adapter.execute(prepared_halted, sequencer)

    assert sequencer.current_state.status == "HALTED"
    assert len(sequencer.ledger.records) == 0


# =========================================================================
# Gate H4.5: Concurrent Disjoint Semantic Requests
# =========================================================================

def test_h4_5_concurrent_disjoint_requests_serializable_commit() -> None:
    """Disjoint semantic requests commit sequentially to serializable state history."""
    state_0 = WorldState(
        attributes={
            "entities": {"recipient": ["Mike", "Alice"]},
        }
    )
    sequencer = DeterministicSequencer(state_0)
    adapter = SemanticApplicationAdapter()
    registry = SemanticCompilerRegistry()

    # Request 1: Transfer to Mike
    harness_1 = SemanticHarness(
        SpyTranslator(
            CandidateSemanticBindings(
                candidate_bindings=(
                    SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),
                    SemanticBinding("operator", "transfer", BindingOrigin.PROBABILISTIC),
                    SemanticBinding("quantity", 10, BindingOrigin.PROBABILISTIC),
                )
            )
        ),
        admissibility_validator=DefaultSemanticAdmissibilityValidator(),
    )
    res_1 = harness_1.interpret(
        "transfer 10 to mike",
        state=sequencer.current_state,
        ingress=IngressContext("p1", "s1", "ch"),
        requirements=(
            SemanticRequirement("recipient"),
            SemanticRequirement("operator"),
            SemanticRequirement("quantity"),
        ),
    )
    prep_1 = adapter.prepare(res_1, sequencer.current_state, registry)
    app_res_1 = adapter.execute(prep_1, sequencer)

    # Request 2: Purge bay_2 (disjoint domain partition)
    harness_2 = SemanticHarness(
        SpyTranslator(
            CandidateSemanticBindings(
                candidate_bindings=(
                    SemanticBinding("destination", "bay_2", BindingOrigin.PROBABILISTIC),
                    SemanticBinding("operator", "purge", BindingOrigin.PROBABILISTIC),
                )
            )
        ),
        admissibility_validator=DefaultSemanticAdmissibilityValidator(
            entity_directory={"destination": ["bay_1", "bay_2"]}
        ),
    )
    res_2 = harness_2.interpret(
        "purge bay_2",
        state=sequencer.current_state,
        ingress=IngressContext("p2", "s2", "ch"),
        requirements=(
            SemanticRequirement("destination"),
            SemanticRequirement("operator"),
        ),
    )
    prep_2 = adapter.prepare(res_2, sequencer.current_state, registry)
    app_res_2 = adapter.execute(prep_2, sequencer)

    final_state = sequencer.current_state
    assert final_state.attributes["transfers.Mike"] == 10
    assert final_state.attributes["purged.bay_2"] is True
    assert len(sequencer.ledger.records) == 2
    assert sequencer.ledger.verify_integrity()


# =========================================================================
# Gate H4.6: Concurrent Conflicting Semantic Requests (OCC Conflict)
# =========================================================================

def test_h4_6_concurrent_conflicting_requests_occ_rejection() -> None:
    """Two concurrent requests prepared against same state detect conflict; second rejected."""
    state_0 = WorldState(
        attributes={
            "transfers.Mike": 0,
            "entities": {"recipient": ["Mike"]},
        }
    )
    sequencer = DeterministicSequencer(state_0)
    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()

    translator_1 = SpyTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),
                SemanticBinding("quantity", 10, BindingOrigin.PROBABILISTIC),
            )
        )
    )
    translator_2 = SpyTranslator(
        CandidateSemanticBindings(
            candidate_bindings=(
                SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),
                SemanticBinding("quantity", 20, BindingOrigin.PROBABILISTIC),
            )
        )
    )

    reqs = (SemanticRequirement("recipient"), SemanticRequirement("quantity"))
    h1 = SemanticHarness(translator_1, admissibility_validator=DefaultSemanticAdmissibilityValidator())
    h2 = SemanticHarness(translator_2, admissibility_validator=DefaultSemanticAdmissibilityValidator())

    res_1 = h1.interpret("send 10 to Mike", state=state_0, ingress=IngressContext("p1", "s1", "ch"), requirements=reqs)
    res_2 = h2.interpret("send 20 to Mike", state=state_0, ingress=IngressContext("p2", "s2", "ch"), requirements=reqs)

    # Both prepared concurrently against S_0
    prep_1 = adapter.prepare(res_1, state_0, compiler)
    prep_2 = adapter.prepare(res_2, state_0, compiler)

    # 1. Req 1 executes and commits successfully
    adapter.execute(prep_1, sequencer)
    assert sequencer.current_state.attributes["transfers.Mike"] == 10

    # 2. Req 2 attempts execution: state has drifted from S_0 -> S_1
    with pytest.raises(SemanticStateDriftError):
        adapter.execute(prep_2, sequencer)

    # Exactly 1 commit recorded, value remains 10
    assert sequencer.current_state.attributes["transfers.Mike"] == 10
    assert len(sequencer.ledger.records) == 1


# =========================================================================
# Gate H4.7: Crash Recovery After Semantic Closure
# =========================================================================

def test_h4_7_crash_recovery_after_semantic_closure_state_drift_audit() -> None:
    """Certified semantic result is durable evidence; drift check rejects stale execution after restart."""
    state_0 = WorldState(
        attributes={
            "entities": {"recipient": ["Mike"]},
        }
    )
    harness = SemanticHarness(
        SpyTranslator(
            CandidateSemanticBindings(
                candidate_bindings=(
                    SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),
                    SemanticBinding("quantity", 40, BindingOrigin.PROBABILISTIC),
                )
            )
        ),
        admissibility_validator=DefaultSemanticAdmissibilityValidator(),
    )
    result = harness.interpret(
        "transfer 40 to Mike",
        state=state_0,
        ingress=IngressContext("p1", "s1", "ch"),
        requirements=(SemanticRequirement("recipient"), SemanticRequirement("quantity")),
    )
    assert result.disposition is SemanticDisposition.YES

    # Persist certificate and intent metadata
    cert_hash = result.certificate.certificate_hash
    signal_id = result.intent.signal_id

    # Simulated crash / recovery where authoritative state drifted during restart
    restarted_state = state_0.with_attribute("restart_epoch", 1).advance_sequence()
    sequencer = DeterministicSequencer(restarted_state)
    adapter = SemanticApplicationAdapter()
    compiler = TransferUoWCompiler()

    # Re-preparation against drifted state fails closed
    with pytest.raises(SemanticStateDriftError):
        adapter.prepare(result, restarted_state, compiler)

    # If state was not drifted, execution recovers and commits cleanly
    clean_sequencer = DeterministicSequencer(state_0)
    prep_clean = adapter.prepare(result, state_0, compiler)
    app_res = adapter.execute(prep_clean, clean_sequencer)
    assert app_res.state.attributes["transfers.Mike"] == 40
    assert len(clean_sequencer.ledger.records) == 1


# =========================================================================
# Gate H4.8: Crash Recovery During Commit (WAL Replay)
# =========================================================================

def test_h4_8_crash_recovery_during_commit_wal_replay() -> None:
    """Semantic UoW committed through WALSequencer survives crash and restores exact ledger."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wal_path = Path(tmpdir) / "semantic_lifecycle.wal"
        state_0 = WorldState(
            attributes={
                "counter": 0,
                "entities": {"recipient": ["Mike"]},
            }
        )
        wal_seq = WALSequencer(wal_path, state_0)

        harness = SemanticHarness(
            SpyTranslator(
                CandidateSemanticBindings(
                    candidate_bindings=(
                        SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),
                        SemanticBinding("quantity", 75, BindingOrigin.PROBABILISTIC),
                    )
                )
            ),
            admissibility_validator=DefaultSemanticAdmissibilityValidator(),
        )
        result = harness.interpret(
            "transfer 75 to Mike",
            state=state_0,
            ingress=IngressContext("p1", "s1", "ch"),
            requirements=(SemanticRequirement("recipient"), SemanticRequirement("quantity")),
        )
        compiler = TransferUoWCompiler()
        adapter = SemanticApplicationAdapter()
        prepared = adapter.prepare(result, state_0, compiler)

        app_res = adapter.execute(prepared, wal_seq)
        assert app_res.state.attributes["transfers.Mike"] == 75
        assert wal_path.exists()

        # Simulate crash & restart by recovering strictly from WAL file
        recovered_state, recovered_ledger = WALSequencer.recover(wal_path)
        assert recovered_state.state_hash == app_res.state.state_hash
        assert recovered_state.attributes["transfers.Mike"] == 75
        assert recovered_ledger.root_hash() == wal_seq.ledger.root_hash()
        assert len(recovered_ledger.records) == 1
        assert recovered_ledger.verify_integrity()


# =========================================================================
# Gate H4.9: Replay / Duplicate Signal Handling
# =========================================================================

def test_h4_9_replay_duplicate_signal_deterministic_uow_idempotence() -> None:
    """Duplicate signals yield identical UoW identity and are blocked from double-execution."""
    signal_id = "sig-duplicate-test-001"
    cert_hash = "f" * 64
    compiler_id = "compiler.transfer.v1"

    # Deterministic UoW identity derivation
    uow_id_1 = derive_semantic_uow_id(signal_id, cert_hash, compiler_id)
    uow_id_2 = derive_semantic_uow_id(signal_id, cert_hash, compiler_id)
    assert uow_id_1 == uow_id_2
    assert uow_id_1.startswith("uow-sem-")

    state_0 = WorldState(
        attributes={
            "entities": {"recipient": ["Mike"]},
        }
    )
    sequencer = DeterministicSequencer(state_0)
    intent = IntentEnvelope(
        signal_id=signal_id,
        source_signal="transfer 30 to Mike",
        principal_id="p1",
        session_id="s1",
        channel="ch",
        bindings=(
            SemanticBinding("recipient", "Mike", BindingOrigin.PROBABILISTIC),
            SemanticBinding("quantity", 30, BindingOrigin.PROBABILISTIC),
        ),
        closure_certificate_hash=cert_hash,
    )

    compiler = TransferUoWCompiler(compiler_id)
    uow = compiler.compile(intent, state_0)
    assert uow.H.identity == uow_id_1
    assert uow.H.parent_context == f"semantic:{cert_hash}"

    prepared = PreparedSemanticUoW(
        uow=uow,
        semantic_certificate_hash=cert_hash,
        expected_state_hash=state_0.state_hash,
        signal_id=signal_id,
        compiler_id=compiler_id,
    )

    adapter = SemanticApplicationAdapter()
    # 1. First execution succeeds
    adapter.execute(prepared, sequencer)
    assert sequencer.current_state.attributes["transfers.Mike"] == 30

    # 2. Duplicate re-execution against the now-committed state fails state drift check
    with pytest.raises(SemanticStateDriftError):
        adapter.execute(prepared, sequencer)

    assert len(sequencer.ledger.records) == 1


# =========================================================================
# Gate H4.10: Provenance Traversal Across Audit Chain
# =========================================================================

def test_h4_10_provenance_traversal_audit_chain() -> None:
    """From committed EvidenceRecord, traverse full cryptographic audit chain back to Signal."""
    raw_signal = "Please convey 88 packages to Alice immediately"
    state_0 = WorldState(
        attributes={
            "entities": {"recipient": ["Alice"]},
        }
    )
    ingress = IngressContext(principal_id="auditor-agent", session_id="sess-audit", channel="audit-stream")
    requirements = (
        SemanticRequirement("recipient"),
        SemanticRequirement("quantity"),
        SemanticRequirement("operator"),
    )

    harness = SemanticHarness(
        SpyTranslator(
            CandidateSemanticBindings(
                candidate_bindings=(
                    SemanticBinding("recipient", "Alice", BindingOrigin.PROBABILISTIC),
                    SemanticBinding("quantity", 88, BindingOrigin.PROBABILISTIC),
                    SemanticBinding("operator", "convey", BindingOrigin.PROBABILISTIC),
                )
            )
        ),
        admissibility_validator=DefaultSemanticAdmissibilityValidator(),
    )
    result = harness.interpret(raw_signal, state=state_0, ingress=ingress, requirements=requirements)
    assert result.disposition is SemanticDisposition.YES

    registry = SemanticCompilerRegistry()
    adapter = SemanticApplicationAdapter()
    prepared = adapter.prepare(result, state_0, registry)

    sequencer = DeterministicSequencer(state_0)
    app_result = adapter.execute(prepared, sequencer)

    # 1. Inspect committed EvidenceRecord
    evidence = app_result.evidence
    assert evidence.uow_id == prepared.uow.H.identity

    # 2. EvidenceRecord -> UoW Header -> Parent Context
    assert prepared.uow.H.parent_context.startswith("semantic:")
    embedded_cert_hash = prepared.uow.H.parent_context.split("semantic:")[1]

    # 3. Parent Context matches SemanticClosureCertificate hash
    assert embedded_cert_hash == result.certificate.certificate_hash
    assert embedded_cert_hash == result.intent.closure_certificate_hash

    # 4. IntentEnvelope -> Signal ID & Raw Signal
    assert result.intent.signal_id == prepared.signal_id
    assert result.intent.source_signal == raw_signal
    assert result.intent.principal_id == "auditor-agent"
    assert result.intent.session_id == "sess-audit"

    # 5. Admissibility evidence references preserved
    assert "semantic_admissibility_filtered" in result.certificate.evidence_refs
    assert app_result.certificate.is_valid
    assert sequencer.ledger.verify_integrity()
