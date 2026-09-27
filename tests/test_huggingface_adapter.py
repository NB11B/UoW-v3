"""H3 Conformance Tests for HuggingFaceSemanticTranslator with fake backends."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
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
    SemanticHarness,
    SemanticRequirement,
    SemanticTranslationRequest,
)
from uow.semantic.adapters import (
    AdapterFailureCategory,
    AdapterLifecycleState,
    HuggingFaceBackend,
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
            raise RuntimeError("Simulated backend generation timeout")
        return self.response_text


def _setup_mock_model_dir(tmp_path: Path, *, tamper_weights: bool = False) -> Path:
    model_dir = tmp_path / "mock_smollm2_135m"
    model_dir.mkdir(parents=True, exist_ok=True)

    weights = b"fake_lora_safetensors_weights_data"
    weights_path = model_dir / "adapter_model.safetensors"
    weights_path.write_bytes(weights)

    import hashlib
    actual_hash = hashlib.sha256(weights).hexdigest()
    declared_hash = "f" * 64 if tamper_weights else actual_hash

    manifest_data = {
        "schema_version": "1.0.0",
        "semantic_codec_id": "uow-semantic-smollm2-135m",
        "base_model_id": "HuggingFaceTB/SmolLM2-135M-Instruct",
        "base_model_revision": "278297b83",
        "tokenizer_id": "HuggingFaceTB/SmolLM2-135M-Instruct",
        "tokenizer_revision": "278297b83",
        "adapter_format": "peft-lora",
        "adapter_sha256": declared_hash,
        "adapter_parameter_count": 460800,
        "corpus_version": "corpus-uow-v1.2",
        "grammar_version": "grammar-uow-v1.0",
        "qualification_version": "qual-2026.09",
        "conformance_suite_version": "suite-h3-v1",
        "supported_operator_families": ["argument", "reference"],
        "supported_output_schema": "uow.semantic.bindings.v1",
    }
    (model_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")
    return model_dir


def _dummy_req(frontier_names: tuple[str, ...]) -> SemanticTranslationRequest:
    return SemanticTranslationRequest(
        signal=ExternalSignal("dispatch order to charlie"),
        minimal_context=MinimalSemanticContext(
            state_hash="dummy_state_hash",
            state_sequence=1,
            bindings=(),
        ),
        frontier=tuple(SemanticRequirement(name) for name in frontier_names),
    )


# =========================================================================
# H3.1: Lazy Import
# =========================================================================

def test_h3_1_lazy_import_in_clean_subprocess() -> None:
    code = (
        "import sys\n"
        "import uow\n"
        "import uow.semantic\n"
        "import uow.semantic.adapters\n"
        "assert 'torch' not in sys.modules\n"
        "assert 'transformers' not in sys.modules\n"
        "assert 'peft' not in sys.modules\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert res.returncode == 0, f"Lazy import failed: {res.stderr}"


# =========================================================================
# H3.2: Lazy Load Contract & Frontier Bypass
# =========================================================================

def test_h3_2_lazy_load_lifecycle(tmp_path: Path) -> None:
    model_dir = _setup_mock_model_dir(tmp_path)
    backend = MockHuggingFaceBackend(
        response_text=json.dumps({
            "bindings": [{"terminal": "recipient", "value": "charlie"}],
            "alternatives": [],
            "unknowns": [],
        })
    )
    config = HuggingFaceSemanticTranslatorConfig(model_path=model_dir)
    translator = HuggingFaceSemanticTranslator(config, backend=backend)

    # 1. Constructor performs no allocation
    assert translator.state is AdapterLifecycleState.UNLOADED
    assert backend.load_calls == 0

    # 2. Frontier-empty request triggers model bypass (0 loads, 0 generations)
    empty_res = translator.propose(_dummy_req(()))
    assert empty_res.candidate_bindings == ()
    assert translator.state is AdapterLifecycleState.UNLOADED
    assert backend.load_calls == 0
    assert backend.generate_calls == 0

    # 3. First non-empty frontier call lazily loads backend exactly once
    req = _dummy_req(("recipient",))
    res1 = translator.propose(req)
    assert translator.state is AdapterLifecycleState.READY
    assert backend.load_calls == 1
    assert backend.generate_calls == 1
    assert len(res1.candidate_bindings) == 1
    assert res1.candidate_bindings[0].value == "charlie"

    # 4. Subsequent propose calls reuse backend without re-initialization
    res2 = translator.propose(req)
    assert translator.state is AdapterLifecycleState.READY
    assert backend.load_calls == 1
    assert backend.generate_calls == 2


# =========================================================================
# H3.3: Manifest Hash Verification Fails Closed
# =========================================================================

def test_h3_3_manifest_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    model_dir = _setup_mock_model_dir(tmp_path, tamper_weights=True)
    backend = MockHuggingFaceBackend()
    config = HuggingFaceSemanticTranslatorConfig(model_path=model_dir, verify_manifest=True)
    translator = HuggingFaceSemanticTranslator(config, backend=backend)

    req = _dummy_req(("recipient",))
    res = translator.propose(req)

    # Must transition to FAILED, record MANIFEST_FAILURE, return fail-closed UNKNOWN
    assert translator.state is AdapterLifecycleState.FAILED
    assert translator.last_failure is not None
    assert translator.last_failure[0] is AdapterFailureCategory.MANIFEST_FAILURE
    assert res.candidate_bindings == ()
    assert res.unknowns == ("recipient",)
    assert backend.load_calls == 0

    # No automatic retry on subsequent call
    res_retry = translator.propose(req)
    assert translator.state is AdapterLifecycleState.FAILED
    assert backend.load_calls == 0
    assert res_retry.unknowns == ("recipient",)


# =========================================================================
# H3.4 & H3.5: Output Parsing & Frontier Confinement
# =========================================================================

def test_h3_4_and_5_frontier_confinement_fails_closed(tmp_path: Path) -> None:
    model_dir = _setup_mock_model_dir(tmp_path)
    # Model returns binding for terminal 'amount' which was NOT requested in frontier ('recipient')
    backend = MockHuggingFaceBackend(
        response_text=json.dumps({
            "bindings": [{"terminal": "amount", "value": 9000}],
            "alternatives": [],
            "unknowns": [],
        })
    )
    config = HuggingFaceSemanticTranslatorConfig(model_path=model_dir)
    translator = HuggingFaceSemanticTranslator(config, backend=backend)

    req = _dummy_req(("recipient",))
    res = translator.propose(req)

    # In fail-closed mode, all frontier terminals remain unknown
    assert res.candidate_bindings == ()
    assert res.unknowns == ("recipient",)


# =========================================================================
# H3.6: Deterministic Primacy Invariant through SemanticHarness
# =========================================================================

def test_h3_6_deterministic_primacy_protected(tmp_path: Path) -> None:
    model_dir = _setup_mock_model_dir(tmp_path)
    # Model attempts to return both recipient and overwrite balance
    backend = MockHuggingFaceBackend(
        response_text=json.dumps({
            "bindings": [
                {"terminal": "recipient", "value": "alice"},
                {"terminal": "balance", "value": 999999},
            ],
            "alternatives": [],
            "unknowns": [],
        })
    )
    config = HuggingFaceSemanticTranslatorConfig(model_path=model_dir)
    translator = HuggingFaceSemanticTranslator(config, backend=backend)
    harness = SemanticHarness(translator)

    ingress = IngressContext(principal_id="user-1", session_id="s-1", channel="text")
    state = WorldState({"balance": 100})
    requirements = (
        SemanticRequirement("recipient"),
        SemanticRequirement("balance", state_key="balance"),
    )

    result = harness.interpret(
        "pay alice",
        state=state,
        ingress=ingress,
        requirements=requirements,
    )

    # Must fail closed: cannot overwrite deterministic balance
    assert result.disposition in (SemanticDisposition.NO, SemanticDisposition.CLARIFY)
    assert result.intent is None


# =========================================================================
# H3.7: UNKNOWN and Insufficient Information
# =========================================================================

def test_h3_7_explicit_unknown_yields_clarify(tmp_path: Path) -> None:
    model_dir = _setup_mock_model_dir(tmp_path)
    backend = MockHuggingFaceBackend(
        response_text=json.dumps({
            "bindings": [],
            "alternatives": [],
            "unknowns": ["recipient"],
        })
    )
    config = HuggingFaceSemanticTranslatorConfig(model_path=model_dir)
    translator = HuggingFaceSemanticTranslator(config, backend=backend)
    harness = SemanticHarness(translator)

    ingress = IngressContext(principal_id="user-1", session_id="s-1", channel="text")
    result = harness.interpret(
        "send to someone",
        state=WorldState({}),
        ingress=ingress,
        requirements=(SemanticRequirement("recipient"),),
    )

    assert result.disposition is SemanticDisposition.CLARIFY
    assert result.intent is None
    assert tuple(r.name for r in result.unresolved) == ("recipient",)


# =========================================================================
# H3.8: Ambiguity / Alternatives
# =========================================================================

def test_h3_8_alternatives_yield_clarify(tmp_path: Path) -> None:
    model_dir = _setup_mock_model_dir(tmp_path)
    backend = MockHuggingFaceBackend(
        response_text=json.dumps({
            "bindings": [],
            "alternatives": [
                {"bindings": [{"terminal": "recipient", "value": "mike-a"}]},
                {"bindings": [{"terminal": "recipient", "value": "mike-b"}]},
            ],
            "unknowns": [],
        })
    )
    config = HuggingFaceSemanticTranslatorConfig(model_path=model_dir)
    translator = HuggingFaceSemanticTranslator(config, backend=backend)
    harness = SemanticHarness(translator)

    ingress = IngressContext(principal_id="user-1", session_id="s-1", channel="text")
    result = harness.interpret(
        "send to mike",
        state=WorldState({}),
        ingress=ingress,
        requirements=(SemanticRequirement("recipient"),),
    )

    assert result.disposition is SemanticDisposition.CLARIFY
    assert result.intent is None
    assert tuple(r.name for r in result.unresolved) == ("recipient",)


# =========================================================================
# H3.9: Zero Authority Surface
# =========================================================================

def test_h3_9_zero_authority_surface() -> None:
    translator = HuggingFaceSemanticTranslator()
    forbidden_methods = [
        "commit",
        "execute",
        "certify",
        "mutate_world",
        "update_world",
        "apply",
        "propose_uow",
    ]
    for method in forbidden_methods:
        assert not hasattr(translator, method), f"Translator illegally exposed {method} authority"


# =========================================================================
# H3.10: Backend Generation Failure Fails Closed
# =========================================================================

def test_h3_10_generation_failure_fails_closed(tmp_path: Path) -> None:
    model_dir = _setup_mock_model_dir(tmp_path)
    backend = MockHuggingFaceBackend()
    backend.fail_generate = True  # simulate crash or timeout during generate()

    config = HuggingFaceSemanticTranslatorConfig(model_path=model_dir)
    translator = HuggingFaceSemanticTranslator(config, backend=backend)
    harness = SemanticHarness(translator)

    ingress = IngressContext(principal_id="user-1", session_id="s-1", channel="text")
    result = harness.interpret(
        "send to alice",
        state=WorldState({}),
        ingress=ingress,
        requirements=(SemanticRequirement("recipient"),),
    )

    # Must fail closed to CLARIFY, never produce executable intent
    assert result.disposition is SemanticDisposition.CLARIFY
    assert result.intent is None
    assert tuple(r.name for r in result.unresolved) == ("recipient",)
