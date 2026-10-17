"""Local Package Store with Immutable Digest Verification."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Tuple

from src.uow.protocol.v1 import CapabilityPackageManifest, canonical_json


class PackageVerificationError(Exception):
    """Raised when package artifact integrity or manifest verification fails."""
    pass


class LocalPackageStore:
    """Manages physical storage of packages and verifies SHA-256 digests."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()
        self.packages_dir = self.root_dir / "packages"
        self.packages_dir.mkdir(parents=True, exist_ok=True)

    def compute_file_sha256(self, file_path: Path) -> str:
        """Compute SHA-256 digest of a physical file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def stage_package(
        self,
        manifest: CapabilityPackageManifest,
        artifact_files: Dict[str, Path],
    ) -> Path:
        """Stage and verify package artifacts into immutable local package directory.
        
        Args:
            manifest: The package manifest
            artifact_files: Mapping of declared artifact filename to local source Path
        """
        pkg_key = f"{manifest.package_id}-{manifest.version}"
        target_dir = self.packages_dir / pkg_key

        if target_dir.exists():
            # If already installed, verify immutable integrity
            self.verify_installed_package(target_dir, manifest)
            return target_dir

        temp_dir = self.packages_dir / f".tmp_{pkg_key}"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Copy and verify artifacts
            for rel_name, expected_hash in manifest.artifacts.items():
                src_path = artifact_files.get(rel_name)
                if not src_path or not src_path.exists():
                    raise PackageVerificationError(f"Missing declared artifact file: '{rel_name}'")
                
                actual_hash = self.compute_file_sha256(src_path)
                if actual_hash != expected_hash:
                    raise PackageVerificationError(
                        f"Artifact hash mismatch for '{rel_name}': expected {expected_hash}, got {actual_hash}"
                    )
                
                dest_path = temp_dir / rel_name
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dest_path)

            # Write verified manifest
            manifest_path = temp_dir / "manifest.json"
            manifest_path.write_text(manifest.to_canonical_json(), encoding="utf-8")

            # Atomic rename to final directory
            temp_dir.rename(target_dir)
            return target_dir

        except Exception:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            raise

    def verify_installed_package(
        self,
        package_dir: Path,
        manifest: CapabilityPackageManifest,
    ) -> bool:
        """Verify all declared artifacts in an installed package directory match their hashes."""
        for rel_name, expected_hash in manifest.artifacts.items():
            file_path = package_dir / rel_name
            if not file_path.exists():
                raise PackageVerificationError(f"Corrupt package {package_dir.name}: missing '{rel_name}'")
            actual_hash = self.compute_file_sha256(file_path)
            if actual_hash != expected_hash:
                raise PackageVerificationError(
                    f"Corrupt package {package_dir.name}: artifact '{rel_name}' hash mismatch"
                )
        return True
