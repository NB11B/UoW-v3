"""Deterministic model manifest contract and cryptographic artifact verification."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from ...state import canonical_json


HEX64_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
SUPPORTED_OUTPUT_SCHEMA = "uow.semantic.bindings.v1"
SUPPORTED_ADAPTER_FORMATS = ("peft-lora", "safetensors")


class ManifestValidationError(ValueError):
    """Raised when a semantic model manifest fails schema or field constraints."""


class ArtifactVerificationError(ValueError):
    """Raised when physical model artifacts fail cryptographic or structure verification."""


@dataclass(frozen=True)
class SemanticModelManifest:
    """Deterministic lineage and verification manifest for semantic adapters."""

    schema_version: str
    semantic_codec_id: str
    base_model_id: str
    base_model_revision: str
    tokenizer_id: str
    tokenizer_revision: str
    adapter_format: str
    adapter_sha256: str
    adapter_parameter_count: int
    corpus_version: str
    grammar_version: str
    qualification_version: str
    conformance_suite_version: str
    supported_operator_families: tuple[str, ...]
    supported_output_schema: str = SUPPORTED_OUTPUT_SCHEMA

    def __post_init__(self) -> None:
        validate_manifest(self)

    def manifest_hash(self) -> str:
        """Return canonical SHA-256 digest of this manifest."""
        data = self.to_dict()
        canonical_str = canonical_json(data)
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Convert manifest to plain dictionary with sorted tuple fields."""
        data = asdict(self)
        data["supported_operator_families"] = list(self.supported_operator_families)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SemanticModelManifest:
        """Instantiate manifest from dictionary."""
        families = data.get("supported_operator_families", ())
        if isinstance(families, list):
            families = tuple(families)
        return cls(
            schema_version=str(data.get("schema_version", "")),
            semantic_codec_id=str(data.get("semantic_codec_id", "")),
            base_model_id=str(data.get("base_model_id", "")),
            base_model_revision=str(data.get("base_model_revision", "")),
            tokenizer_id=str(data.get("tokenizer_id", "")),
            tokenizer_revision=str(data.get("tokenizer_revision", "")),
            adapter_format=str(data.get("adapter_format", "")),
            adapter_sha256=str(data.get("adapter_sha256", "")),
            adapter_parameter_count=int(data.get("adapter_parameter_count", 0)),
            corpus_version=str(data.get("corpus_version", "")),
            grammar_version=str(data.get("grammar_version", "")),
            qualification_version=str(data.get("qualification_version", "")),
            conformance_suite_version=str(data.get("conformance_suite_version", "")),
            supported_operator_families=families,
            supported_output_schema=str(
                data.get("supported_output_schema", SUPPORTED_OUTPUT_SCHEMA)
            ),
        )

    @classmethod
    def load(cls, path: str | Path) -> SemanticModelManifest:
        """Load and validate manifest from a JSON file or directory containing manifest.json."""
        target = Path(path)
        if target.is_dir():
            target = target / "manifest.json"
        if not target.is_file():
            raise ArtifactVerificationError(f"Manifest file not found: {target}")
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ManifestValidationError(f"Invalid JSON in manifest file: {target}") from exc
        return cls.from_dict(data)


def validate_manifest(manifest: SemanticModelManifest) -> None:
    """Validate manifest fields against qualification invariants."""
    if manifest.schema_version != "1.0.0":
        raise ManifestValidationError(
            f"Unsupported schema_version: {manifest.schema_version!r}. Must be '1.0.0'."
        )

    if not manifest.semantic_codec_id:
        raise ManifestValidationError("semantic_codec_id must not be empty.")

    if not manifest.base_model_id:
        raise ManifestValidationError("base_model_id must not be empty.")

    # Revisions and versions must be explicit and not contain unresolved placeholders
    for field_name in (
        "base_model_revision",
        "tokenizer_id",
        "tokenizer_revision",
        "corpus_version",
        "grammar_version",
        "qualification_version",
        "conformance_suite_version",
    ):
        val = getattr(manifest, field_name)
        if not val or not isinstance(val, str):
            raise ManifestValidationError(f"{field_name} must be a non-empty string.")
        if val.startswith("<") and val.endswith(">"):
            raise ManifestValidationError(
                f"{field_name} contains unpinned placeholder: {val!r}"
            )

    if manifest.adapter_format not in SUPPORTED_ADAPTER_FORMATS:
        raise ManifestValidationError(
            f"Unsupported adapter_format: {manifest.adapter_format!r}. "
            f"Must be one of {SUPPORTED_ADAPTER_FORMATS}."
        )

    if not HEX64_PATTERN.match(manifest.adapter_sha256):
        raise ManifestValidationError(
            f"adapter_sha256 must be a 64-character hex digest, got {manifest.adapter_sha256!r}"
        )

    if manifest.adapter_parameter_count <= 0:
        raise ManifestValidationError(
            f"adapter_parameter_count must be positive, got {manifest.adapter_parameter_count}"
        )

    if not manifest.supported_operator_families:
        raise ManifestValidationError("supported_operator_families must not be empty.")

    for family in manifest.supported_operator_families:
        if not family or not isinstance(family, str):
            raise ManifestValidationError("All operator families must be non-empty strings.")

    if manifest.supported_output_schema != SUPPORTED_OUTPUT_SCHEMA:
        raise ManifestValidationError(
            f"Unsupported output schema: {manifest.supported_output_schema!r}. "
            f"Must be {SUPPORTED_OUTPUT_SCHEMA!r}."
        )


def compute_file_sha256(file_path: str | Path, chunk_size: int = 65536) -> str:
    """Compute SHA-256 digest of a physical file."""
    path = Path(file_path)
    if not path.is_file():
        raise ArtifactVerificationError(f"Target file does not exist: {path}")
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_adapter_artifact(
    model_dir: str | Path,
    manifest: SemanticModelManifest | None = None,
    *,
    adapter_filename: str = "adapter_model.safetensors",
) -> tuple[SemanticModelManifest, str]:
    """Verify cryptographic integrity of adapter artifacts before loading.

    Fails closed if the manifest is missing or invalid, or if the adapter
    weights do not match the expected SHA-256 digest declared in the manifest.
    """
    directory = Path(model_dir)
    if not directory.is_dir():
        raise ArtifactVerificationError(f"Model directory does not exist: {directory}")

    loaded_manifest = manifest or SemanticModelManifest.load(directory)

    adapter_path = directory / adapter_filename
    if not adapter_path.is_file():
        raise ArtifactVerificationError(
            f"Adapter weights file missing in {directory}: {adapter_filename}"
        )

    computed_hash = compute_file_sha256(adapter_path)
    if computed_hash.lower() != loaded_manifest.adapter_sha256.lower():
        raise ArtifactVerificationError(
            f"Adapter SHA-256 mismatch for {adapter_path.name}: "
            f"expected {loaded_manifest.adapter_sha256}, got {computed_hash}"
        )

    return loaded_manifest, computed_hash
