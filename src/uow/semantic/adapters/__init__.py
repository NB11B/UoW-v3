"""Qualified semantic model adapter contracts and codecs.

This subpackage is intentionally kept separate from the frozen core and frozen
facade. It defines the lineage manifest, prompt construction, deterministic output
parsing, and model adapters satisfying the SemanticTranslator protocol.
"""
from __future__ import annotations

from .codec import (
    AdapterFailureCategory,
    SemanticOutputParser,
    SemanticOutputValidationError,
    SemanticPromptBuilder,
    SYSTEM_PROMPT,
)
from .huggingface import (
    AdapterLifecycleState,
    HuggingFaceBackend,
    HuggingFaceSemanticTranslator,
    HuggingFaceSemanticTranslatorConfig,
)
from .manifest import (
    ArtifactVerificationError,
    ManifestValidationError,
    SemanticModelManifest,
    compute_file_sha256,
    validate_manifest,
    verify_adapter_artifact,
)

__all__ = [
    "AdapterFailureCategory",
    "AdapterLifecycleState",
    "ArtifactVerificationError",
    "HuggingFaceBackend",
    "HuggingFaceSemanticTranslator",
    "HuggingFaceSemanticTranslatorConfig",
    "ManifestValidationError",
    "SYSTEM_PROMPT",
    "SemanticModelManifest",
    "SemanticOutputParser",
    "SemanticOutputValidationError",
    "SemanticPromptBuilder",
    "compute_file_sha256",
    "validate_manifest",
    "verify_adapter_artifact",
]
