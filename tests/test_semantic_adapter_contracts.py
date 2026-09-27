"""Tests for model-independent semantic adapter contracts: manifest and codec."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pytest

from uow import WorldState
from uow.semantic import (
    BindingOrigin,
    CandidateSemanticBindings,
    ExternalSignal,
    IngressContext,
    MinimalSemanticContext,
    SemanticBinding,
    SemanticDisposition,
    SemanticHandoff,
    SemanticHarness,
    SemanticRequirement,
    SemanticTranslationRequest,
)
from uow.semantic.adapters import (
    ArtifactVerificationError,
    ManifestValidationError,
    SemanticModelManifest,
    SemanticOutputParser,
    SemanticOutputValidationError,
    SemanticPromptBuilder,
    compute_file_sha256,
    validate_manifest,
    verify_adapter_artifact,
)


def _valid_manifest_dict() -> dict:
    return {
        "schema_version": "1.0.0",
        "semantic_codec_id": "uow-semantic-smollm2-135m",
        "base_model_id": "HuggingFaceTB/SmolLM2-135M-Instruct",
        "base_model_revision": "278297b83",
        "tokenizer_id": "HuggingFaceTB/SmolLM2-135M-Instruct",
        "tokenizer_revision": "278297b83",
        "adapter_format": "peft-lora",
        "adapter_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "adapter_parameter_count": 460800,
        "corpus_version": "corpus-uow-v1.2",
        "grammar_version": "grammar-uow-v1.0",
        "qualification_version": "qual-2026.09",
        "conformance_suite_version": "suite-h3-v1",
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


def _dummy_request(
    frontier_names: tuple[str, ...] = ("recipient",),
    signal_text: str = "send units to mike",
    context_bindings: tuple[SemanticBinding, ...] = (),
) -> SemanticTranslationRequest:
    return SemanticTranslationRequest(
        signal=ExternalSignal(signal_text),
        minimal_context=MinimalSemanticContext(
            state_hash="dummy_state_hash",
            state_sequence=1,
            bindings=context_bindings,
        ),
        frontier=tuple(SemanticRequirement(name) for name in frontier_names),
    )


# =========================================================================
# 1. Manifest Contract & Validation Falsification Tests
# =========================================================================

def test_valid_manifest_instantiation_and_canonical_hash() -> None:
    data = _valid_manifest_dict()
    manifest = SemanticModelManifest.from_dict(data)

    assert manifest.schema_version == "1.0.0"
    assert manifest.semantic_codec_id == "uow-semantic-smollm2-135m"
    digest = manifest.manifest_hash()
    assert isinstance(digest, str) and len(digest) == 64

    # Round-trip fidelity
    serialized = manifest.to_dict()
    reloaded = SemanticModelManifest.from_dict(serialized)
    assert reloaded == manifest
    assert reloaded.manifest_hash() == digest


def test_manifest_rejects_unpinned_placeholders() -> None:
    bad_data = _valid_manifest_dict()
    bad_data["base_model_revision"] = "<PINNED_REVISION>"

    with pytest.raises(ManifestValidationError, match="contains unpinned placeholder"):
        SemanticModelManifest.from_dict(bad_data)


def test_manifest_rejects_invalid_adapter_sha256() -> None:
    bad_data = _valid_manifest_dict()
    bad_data["adapter_sha256"] = "not_a_64_char_hex_hash"

    with pytest.raises(ManifestValidationError, match="must be a 64-character hex digest"):
        SemanticModelManifest.from_dict(bad_data)


def test_manifest_rejects_unsupported_schema_version() -> None:
    bad_data = _valid_manifest_dict()
    bad_data["schema_version"] = "2.0.0"

    with pytest.raises(ManifestValidationError, match="Unsupported schema_version"):
        SemanticModelManifest.from_dict(bad_data)


def test_manifest_rejects_unsupported_output_schema() -> None:
    bad_data = _valid_manifest_dict()
    bad_data["supported_output_schema"] = "legacy.v0"

    with pytest.raises(ManifestValidationError, match="Unsupported output schema"):
        SemanticModelManifest.from_dict(bad_data)


def test_manifest_rejects_zero_or_negative_parameter_count() -> None:
    bad_data = _valid_manifest_dict()
    bad_data["adapter_parameter_count"] = 0

    with pytest.raises(ManifestValidationError, match="must be positive"):
        SemanticModelManifest.from_dict(bad_data)


def test_manifest_rejects_empty_operator_families() -> None:
    bad_data = _valid_manifest_dict()
    bad_data["supported_operator_families"] = []

    with pytest.raises(ManifestValidationError, match="must not be empty"):
        SemanticModelManifest.from_dict(bad_data)


# =========================================================================
# 2. Cryptographic Artifact Verification Falsification Tests
# =========================================================================

def test_artifact_verification_passes_on_matching_sha256(tmp_path: Path) -> None:
    content = b"safetensors_binary_test_payload_12345"
    content_hash = hashlib.sha256(content).hexdigest()

    model_dir = tmp_path / "model_checkpoint"
    model_dir.mkdir()

    weights_file = model_dir / "adapter_model.safetensors"
    weights_file.write_bytes(content)

    manifest_data = _valid_manifest_dict()
    manifest_data["adapter_sha256"] = content_hash
    manifest = SemanticModelManifest.from_dict(manifest_data)

    manifest_file = model_dir / "manifest.json"
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    verified_manifest, observed_hash = verify_adapter_artifact(model_dir)
    assert verified_manifest.semantic_codec_id == manifest.semantic_codec_id
    assert observed_hash == content_hash


def test_artifact_verification_fails_on_hash_mismatch(tmp_path: Path) -> None:
    model_dir = tmp_path / "model_tampered"
    model_dir.mkdir()

    weights_file = model_dir / "adapter_model.safetensors"
    weights_file.write_bytes(b"tampered_weights")

    manifest_data = _valid_manifest_dict()
    # manifest claims a different sha256
    manifest_data["adapter_sha256"] = "a" * 64
    manifest_file = model_dir / "manifest.json"
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    with pytest.raises(ArtifactVerificationError, match="Adapter SHA-256 mismatch"):
        verify_adapter_artifact(model_dir)


def test_artifact_verification_fails_on_missing_weights_file(tmp_path: Path) -> None:
    model_dir = tmp_path / "model_missing_weights"
    model_dir.mkdir()

    manifest_data = _valid_manifest_dict()
    manifest_file = model_dir / "manifest.json"
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    with pytest.raises(ArtifactVerificationError, match="Adapter weights file missing"):
        verify_adapter_artifact(model_dir)


def test_artifact_verification_fails_on_missing_manifest(tmp_path: Path) -> None:
    model_dir = tmp_path / "empty_dir"
    model_dir.mkdir()

    with pytest.raises(ArtifactVerificationError, match="Manifest file not found"):
        verify_adapter_artifact(model_dir)


# =========================================================================
# 3. Prompt Builder (X, C_min, F_P) Contract Tests
# =========================================================================

def test_prompt_builder_confinement() -> None:
    builder = SemanticPromptBuilder()
    req = _dummy_request(
        frontier_names=("target_node",),
        signal_text="route packet to node 4",
        context_bindings=(
            SemanticBinding("port", 8080, BindingOrigin.DETERMINISTIC),
        ),
    )

    payload = builder.build_user_payload(req)
    assert payload["signal"] == "route packet to node 4"
    assert payload["context"] == {"port": 8080}
    assert payload["frontier"] == [{"name": "target_node"}]
    # Must not contain unprompted or external keys
    assert set(payload.keys()) == {"signal", "context", "frontier"}

    messages = builder.build_chat_messages(req)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "bounded semantic translator" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "route packet to node 4" in messages[1]["content"]


# =========================================================================
# 4. Deterministic Output Parser & Falsification Tests
# =========================================================================

def test_parser_valid_canonical_json() -> None:
    parser = SemanticOutputParser()
    req = _dummy_request(frontier_names=("recipient", "amount"))
    raw_output = json.dumps({
        "bindings": [
            {"terminal": "recipient", "value": "mike"},
            {"terminal": "amount", "value": 50},
        ],
        "alternatives": [],
        "unknowns": [],
    })

    candidate = parser.parse(raw_output, req, evidence_ref="test:codec:1", fail_closed=False)
    assert len(candidate.candidate_bindings) == 2
    assert candidate.unknowns == ()
    assert candidate.alternatives == ()

    b_map = {b.terminal: b.value for b in candidate.candidate_bindings}
    assert b_map == {"recipient": "mike", "amount": 50}
    for b in candidate.candidate_bindings:
        assert b.origin is BindingOrigin.PROBABILISTIC
        assert b.evidence_refs == ("test:codec:1",)


def test_parser_handles_markdown_code_fences() -> None:
    parser = SemanticOutputParser()
    req = _dummy_request(frontier_names=("recipient",))
    fenced_output = (
        "```json\n"
        '{\n  "bindings": [{"terminal": "recipient", "value": "alice"}],\n'
        '  "alternatives": [],\n'
        '  "unknowns": []\n'
        "}\n"
        "```"
    )

    candidate = parser.parse(fenced_output, req, fail_closed=False)
    assert len(candidate.candidate_bindings) == 1
    assert candidate.candidate_bindings[0].terminal == "recipient"
    assert candidate.candidate_bindings[0].value == "alice"


def test_parser_rejects_unknown_top_level_keys() -> None:
    parser = SemanticOutputParser()
    req = _dummy_request(frontier_names=("recipient",))
    bad_output = json.dumps({
        "bindings": [{"terminal": "recipient", "value": "alice"}],
        "alternatives": [],
        "unknowns": [],
        "unauthorized_key": "injected",
    })

    with pytest.raises(SemanticOutputValidationError, match="disallowed top-level keys"):
        parser.parse(bad_output, req, fail_closed=False)

    # Fail closed fallback test
    fail_closed_candidate = parser.parse(bad_output, req, fail_closed=True)
    assert fail_closed_candidate.candidate_bindings == ()
    assert fail_closed_candidate.unknowns == ("recipient",)


def test_parser_rejects_terminal_outside_frontier() -> None:
    parser = SemanticOutputParser()
    req = _dummy_request(frontier_names=("recipient",))
    # Model attempts to hallucinate or overwrite 'amount' which is not in frontier
    rogue_output = json.dumps({
        "bindings": [
            {"terminal": "recipient", "value": "alice"},
            {"terminal": "amount", "value": 999},
        ],
        "alternatives": [],
        "unknowns": [],
    })

    with pytest.raises(SemanticOutputValidationError, match="outside frontier"):
        parser.parse(rogue_output, req, fail_closed=False)

    # In fail-closed mode: all frontier terminals remain unknown
    fail_closed_candidate = parser.parse(rogue_output, req, fail_closed=True)
    assert fail_closed_candidate.candidate_bindings == ()
    assert fail_closed_candidate.unknowns == ("recipient",)


def test_parser_rejects_nan_and_infinity() -> None:
    parser = SemanticOutputParser()
    req = _dummy_request(frontier_names=("score",))
    raw_nan = '{"bindings": [{"terminal": "score", "value": NaN}], "alternatives": [], "unknowns": []}'

    with pytest.raises(SemanticOutputValidationError, match="Invalid non-standard JSON literal"):
        parser.parse(raw_nan, req, fail_closed=False)


def test_parser_normalizes_duplicate_equal_bindings() -> None:
    parser = SemanticOutputParser()
    req = _dummy_request(frontier_names=("recipient",))
    output = json.dumps({
        "bindings": [
            {"terminal": "recipient", "value": "alice"},
            {"terminal": "recipient", "value": "alice"},
        ],
        "alternatives": [],
        "unknowns": [],
    })

    candidate = parser.parse(output, req, fail_closed=False)
    assert len(candidate.candidate_bindings) == 1
    assert candidate.candidate_bindings[0].value == "alice"


def test_parser_preserves_duplicate_conflicting_bindings_as_ambiguous() -> None:
    parser = SemanticOutputParser()
    req = _dummy_request(frontier_names=("recipient",))
    output = json.dumps({
        "bindings": [
            {"terminal": "recipient", "value": "alice"},
            {"terminal": "recipient", "value": "bob"},
        ],
        "alternatives": [],
        "unknowns": [],
    })

    candidate = parser.parse(output, req, fail_closed=False)
    # Parser preserves ambiguity with conflicting values
    values = [b.value for b in candidate.candidate_bindings]
    assert "alice" in values
    assert any("__conflict" in str(v) for v in values)


def test_parser_parses_unknowns_and_alternatives() -> None:
    parser = SemanticOutputParser()
    req = _dummy_request(frontier_names=("recipient", "amount"))
    output = json.dumps({
        "bindings": [],
        "alternatives": [
            {
                "bindings": [{"terminal": "recipient", "value": "alice"}],
                "reason": "option A",
            },
            {
                "bindings": [{"terminal": "recipient", "value": "bob"}],
                "reason": "option B",
            },
        ],
        "unknowns": ["amount"],
    })

    candidate = parser.parse(output, req, fail_closed=False)
    assert candidate.candidate_bindings == ()
    assert candidate.unknowns == ("amount",)
    assert len(candidate.alternatives) == 2
    assert candidate.alternatives[0].bindings[0].terminal == "recipient"
    assert candidate.alternatives[0].reason == "option A"


# =========================================================================
# 5. End-to-End Pipeline Integration with Fake Translator
# =========================================================================

class FakeCodecTranslator:
    """Mock model runner that simulates raw string generation through SemanticOutputParser."""

    def __init__(self, raw_response: str) -> None:
        self.raw_response = raw_response
        self.parser = SemanticOutputParser()
        self.invocations = 0

    def propose(self, request: SemanticTranslationRequest) -> CandidateSemanticBindings:
        self.invocations += 1
        return self.parser.parse(
            self.raw_response,
            request,
            evidence_ref="test:fake_codec",
            fail_closed=True,
        )


def test_fake_codec_translator_success_in_harness() -> None:
    raw_json = json.dumps({
        "bindings": [{"terminal": "recipient", "value": "charlie"}],
        "alternatives": [],
        "unknowns": [],
    })
    translator = FakeCodecTranslator(raw_json)
    harness = SemanticHarness(translator)
    ingress = IngressContext(principal_id="user-1", session_id="s-1", channel="web")

    result = harness.interpret(
        "message charlie",
        state=WorldState({"authorized": True}),
        ingress=ingress,
        requirements=(
            SemanticRequirement("recipient"),
            SemanticRequirement("auth", state_key="authorized"),
        ),
    )

    assert result.disposition is SemanticDisposition.YES
    assert translator.invocations == 1
    assert result.intent is not None
    assert result.intent.binding_map()["recipient"] == "charlie"
    assert result.intent.binding_map()["auth"] is True


def test_fake_codec_translator_malformed_json_fails_closed_to_clarify() -> None:
    raw_garbage = "{ this is not valid json at all ... "
    translator = FakeCodecTranslator(raw_garbage)
    harness = SemanticHarness(translator)
    ingress = IngressContext(principal_id="user-1", session_id="s-1", channel="web")

    result = harness.interpret(
        "message someone",
        state=WorldState({}),
        ingress=ingress,
        requirements=(SemanticRequirement("recipient"),),
    )

    # Malformed output -> UNKNOWN -> CLARIFY -> No native UoW created
    assert result.disposition is SemanticDisposition.CLARIFY
    assert result.intent is None
    assert tuple(r.name for r in result.unresolved) == ("recipient",)


def test_fake_codec_translator_undeclared_terminal_fails_closed_to_clarify() -> None:
    # Model generates binding for terminal 'balance' which is not in frontier ('recipient')
    raw_rogue = json.dumps({
        "bindings": [{"terminal": "balance", "value": 1000}],
        "alternatives": [],
        "unknowns": [],
    })
    translator = FakeCodecTranslator(raw_rogue)
    harness = SemanticHarness(translator)
    ingress = IngressContext(principal_id="user-1", session_id="s-1", channel="web")

    result = harness.interpret(
        "message someone",
        state=WorldState({}),
        ingress=ingress,
        requirements=(SemanticRequirement("recipient"),),
    )

    # In fail-closed mode, codec parser turns rogue output into UNKNOWN for open frontier
    assert result.disposition is SemanticDisposition.CLARIFY
    assert result.intent is None
    assert tuple(r.name for r in result.unresolved) == ("recipient",)
