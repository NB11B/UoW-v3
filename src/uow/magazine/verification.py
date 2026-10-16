"""Cryptographic Verification and Manifest Integrity for uow.magazine.v1."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Tuple, Optional

from src.uow.magazine.schema import CapabilityManifest


class VerificationError(Exception):
    """Raised when cryptographic verification or manifest validation fails."""
    pass


class ManifestVerifier:
    """Verifies adapter manifests and weight artifacts fail-closed."""

    @staticmethod
    def compute_sha256(file_path: Path) -> str:
        """Computes SHA-256 hex digest of a binary file."""
        if not file_path.is_file():
            raise FileNotFoundError(f"Weight file not found: {file_path}")
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @classmethod
    def verify_adapter(
        cls,
        manifest: CapabilityManifest,
        adapter_dir: Path,
    ) -> tuple[bool, Optional[str]]:
        """Validates manifest integrity and checks weight file SHA-256 against manifest.
        
        Returns (is_valid, error_reason).
        """
        # 1. Manifest structural validation
        if manifest.manifest_version != "uow.magazine.v1":
            return False, f"Unsupported manifest version: {manifest.manifest_version}"
        if not manifest.adapter_id:
            return False, "Missing adapter_id in manifest"
        if not manifest.foundation_model:
            return False, "Missing foundation_model in manifest"
        if not manifest.adapter_sha256:
            return False, "Missing adapter_sha256 digest in manifest"

        # 2. Locate weight file
        weight_file = adapter_dir / "adapter_model.safetensors"
        if not weight_file.exists():
            weight_file = adapter_dir / "adapter_model.bin"
        if not weight_file.exists():
            return False, f"Weight artifact not found in directory: {adapter_dir}"

        # 3. Cryptographic digest verification
        try:
            actual_sha = cls.compute_sha256(weight_file)
        except Exception as e:
            return False, f"Failed to compute weight digest: {e}"

        if actual_sha.lower() != manifest.adapter_sha256.lower():
            return False, (
                f"Cryptographic digest mismatch for {manifest.adapter_id}: "
                f"expected {manifest.adapter_sha256}, got {actual_sha}"
            )

        return True, None
