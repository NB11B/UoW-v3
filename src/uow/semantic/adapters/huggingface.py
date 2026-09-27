"""Qualified Hugging Face SmolLM2-135M / LoRA SemanticTranslator adapter."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .codec import (
    AdapterFailureCategory,
    SemanticOutputParser,
    SemanticPromptBuilder,
)
from .manifest import (
    ArtifactVerificationError,
    ManifestValidationError,
    SemanticModelManifest,
    verify_adapter_artifact,
)
from ..schema import (
    CandidateSemanticBindings,
    SemanticTranslationRequest,
)


class AdapterLifecycleState(str, Enum):
    """Lifecycle states of the lazy-loaded model adapter."""

    UNLOADED = "UNLOADED"
    LOADING = "LOADING"
    READY = "READY"
    FAILED = "FAILED"


@dataclass(frozen=True)
class HuggingFaceSemanticTranslatorConfig:
    """Runtime configuration for HuggingFace semantic translator adapter."""

    model_path: str | Path = ""
    device: str = "cpu"
    dtype: str = "auto"
    max_new_tokens: int = 128
    local_files_only: bool = True
    verify_manifest: bool = True

    def __post_init__(self) -> None:
        if not self.model_path:
            env_path = os.environ.get("UOW_SEMANTIC_MODEL_PATH", "")
            if env_path:
                object.__setattr__(self, "model_path", env_path)


@runtime_checkable
class HuggingFaceBackend(Protocol):
    """Abstract model runner backend allowing fake-backend injection for testing."""

    def load(
        self,
        config: HuggingFaceSemanticTranslatorConfig,
        manifest: SemanticModelManifest,
    ) -> None:
        ...

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_new_tokens: int,
    ) -> str:
        ...


class DefaultHuggingFaceBackend:
    """Real Transformers + PEFT inference backend with lazy framework imports."""

    def __init__(self) -> None:
        self._tokenizer: Any = None
        self._model: Any = None

    def load(
        self,
        config: HuggingFaceSemanticTranslatorConfig,
        manifest: SemanticModelManifest,
    ) -> None:
        # Lazy imports strictly isolated to load()
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel

        model_dir = Path(config.model_path)
        base_id = manifest.base_model_id

        self._tokenizer = AutoTokenizer.from_pretrained(
            manifest.tokenizer_id,
            revision=manifest.tokenizer_revision,
            local_files_only=config.local_files_only,
        )

        torch_dtype = (
            getattr(torch, config.dtype)
            if hasattr(torch, config.dtype)
            else "auto"
        )

        base_model = AutoModelForCausalLM.from_pretrained(
            base_id,
            revision=manifest.base_model_revision,
            torch_dtype=torch_dtype,
            local_files_only=config.local_files_only,
        )

        self._model = PeftModel.from_pretrained(
            base_model,
            str(model_dir),
            local_files_only=config.local_files_only,
        )
        self._model.to(config.device)
        self._model.eval()

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_new_tokens: int,
    ) -> str:
        import torch

        if self._tokenizer is None or self._model is None:
            raise RuntimeError("Backend generate() called before load() completed.")

        prompt = self._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)

        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                temperature=0.0,
                top_p=1.0,
                num_beams=1,
            )

        # Slice generated response tokens after input
        input_len = inputs["input_ids"].shape[1]
        response_tokens = outputs[0][input_len:]
        return self._tokenizer.decode(response_tokens, skip_special_tokens=True)


class HuggingFaceSemanticTranslator:
    """Qualified 135M SmolLM2/LoRA translator satisfying SemanticTranslator protocol.

    This adapter adheres strictly to the authority rule:
    probabilistic translation != authority.
    It exposes no commit, execute, certify, or mutation methods.
    """

    def __init__(
        self,
        config: HuggingFaceSemanticTranslatorConfig | None = None,
        *,
        backend: HuggingFaceBackend | None = None,
        prompt_builder: SemanticPromptBuilder | None = None,
        output_parser: SemanticOutputParser | None = None,
    ) -> None:
        self.config = config or HuggingFaceSemanticTranslatorConfig()
        self._backend = backend or DefaultHuggingFaceBackend()
        self._prompt_builder = prompt_builder or SemanticPromptBuilder()
        self._output_parser = output_parser or SemanticOutputParser()

        # Lazy lifecycle state: no framework import or model allocation in constructor
        self._state = AdapterLifecycleState.UNLOADED
        self._manifest: SemanticModelManifest | None = None
        self._last_failure: tuple[AdapterFailureCategory, str] | None = None
        self._last_validation_failure: tuple[AdapterFailureCategory, str] | None = None

    @property
    def state(self) -> AdapterLifecycleState:
        return self._state

    @property
    def manifest(self) -> SemanticModelManifest | None:
        return self._manifest

    @property
    def last_failure(self) -> tuple[AdapterFailureCategory, str] | None:
        return self._last_failure

    @property
    def last_validation_failure(self) -> tuple[AdapterFailureCategory, str] | None:
        return self._last_validation_failure

    def _evidence_ref(self) -> str:
        if self._manifest is not None:
            return f"semantic-codec:{self._manifest.semantic_codec_id}:{self._manifest.manifest_hash()}"
        return "semantic-codec:unloaded"

    def _ensure_loaded(self) -> bool:
        """Lazily initialize and verify model artifact if needed. Returns True on success."""
        if self._state is AdapterLifecycleState.READY:
            return True
        if self._state is AdapterLifecycleState.FAILED:
            return False

        self._state = AdapterLifecycleState.LOADING
        model_path = Path(self.config.model_path) if self.config.model_path else Path()

        # Step 1: Verification
        try:
            if self.config.verify_manifest:
                manifest, _ = verify_adapter_artifact(model_path)
            else:
                manifest = SemanticModelManifest.load(model_path)
            self._manifest = manifest
        except (ArtifactVerificationError, ManifestValidationError) as exc:
            self._state = AdapterLifecycleState.FAILED
            self._last_failure = (AdapterFailureCategory.MANIFEST_FAILURE, str(exc))
            return False
        except Exception as exc:
            self._state = AdapterLifecycleState.FAILED
            self._last_failure = (AdapterFailureCategory.LOAD_FAILURE, str(exc))
            return False

        # Step 2: Backend loading
        try:
            self._backend.load(self.config, self._manifest)
            self._state = AdapterLifecycleState.READY
            return True
        except Exception as exc:
            self._state = AdapterLifecycleState.FAILED
            self._last_failure = (AdapterFailureCategory.LOAD_FAILURE, str(exc))
            return False

    def propose(
        self,
        request: SemanticTranslationRequest,
    ) -> CandidateSemanticBindings:
        """Propose candidate bindings for unresolved semantic frontier F_P."""
        # Section 1: Model bypass invariant when frontier is empty
        if not request.frontier:
            return CandidateSemanticBindings()

        # Lazy loading check
        if not self._ensure_loaded():
            fail_cat, err_msg = self._last_failure or (
                AdapterFailureCategory.LOAD_FAILURE,
                "Adapter failed to load.",
            )
            # Infrastructure failure fails closed to UNKNOWN, never becomes YES
            return CandidateSemanticBindings(
                unknowns=tuple(r.name for r in request.frontier),
                evidence_refs=(f"adapter_failure:{fail_cat.value}:{err_msg}",),
            )

        evidence_ref = self._evidence_ref()

        # Construct minimal prompt (X, C_min, F_P)
        messages = self._prompt_builder.build_chat_messages(request)

        # Generate candidate text
        try:
            raw_text = self._backend.generate(
                messages,
                max_new_tokens=self.config.max_new_tokens,
            )
        except Exception as exc:
            # Inference failure transitions to terminal FAILED
            self._state = AdapterLifecycleState.FAILED
            self._last_failure = (AdapterFailureCategory.INFERENCE_FAILURE, str(exc))
            return CandidateSemanticBindings(
                unknowns=tuple(r.name for r in request.frontier),
                evidence_refs=(
                    evidence_ref,
                    f"adapter_failure:{AdapterFailureCategory.INFERENCE_FAILURE.value}:{exc}",
                ),
            )

        # Deterministically parse and validate candidate bindings IR
        parsed = self._output_parser.parse(
            raw_text,
            request,
            evidence_ref=evidence_ref,
            fail_closed=True,
        )
        if any("codec_parse_failure" in ref for ref in parsed.evidence_refs):
            # OUTPUT_VALIDATION_FAILURE fails individual translation to UNKNOWN, preserves READY, records diagnostic
            self._last_validation_failure = (
                AdapterFailureCategory.OUTPUT_VALIDATION_FAILURE,
                raw_text[:100],
            )
        return parsed
