"""Magazine Registry: Immutable registration and cryptographic verification of adapter weights."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from experiments.uow_magazine_1.magazine.manifest import (
    MagazineEntry,
    MagazineManifest,
    PROTOCOL_VERSION,
)


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class MagazineRegistry:
    def __init__(self, storage_root: Path):
        self.storage_root = Path(storage_root)
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self._manifests: dict[str, MagazineManifest] = {}

    def create_manifest(self, magazine_id: str, foundation_id: str, max_slots: int = 16) -> MagazineManifest:
        if magazine_id in self._manifests:
            raise ValueError(f"Magazine {magazine_id} already exists in registry")
        m = MagazineManifest(magazine_id=magazine_id, foundation_id=foundation_id, max_resident_slots=max_slots)
        self._manifests[magazine_id] = m
        return m

    def register_adapter(
        self,
        magazine_id: str,
        adapter_id: str,
        domain: str,
        grammar: str,
        foundation_id: str,
        rank: int,
        alpha: int,
        target_modules: list[str],
        adapter_weights_path: Path,
        metadata: Optional[dict[str, Any]] = None,
    ) -> MagazineEntry:
        if magazine_id not in self._manifests:
            raise KeyError(f"Magazine {magazine_id} not registered")
        manifest = self._manifests[magazine_id]
        if manifest.foundation_id != foundation_id:
            raise ValueError(f"Foundation mismatch: manifest expects {manifest.foundation_id}, got {foundation_id}")

        weights_path = Path(adapter_weights_path)
        if not weights_path.exists():
            raise FileNotFoundError(f"Adapter weights file not found: {weights_path}")

        sha256_hash = compute_sha256(weights_path)
        size_bytes = weights_path.stat().st_size

        entry = MagazineEntry(
            adapter_id=adapter_id,
            domain=domain,
            grammar=grammar,
            foundation_id=foundation_id,
            rank=rank,
            alpha=alpha,
            target_modules=target_modules,
            sha256=sha256_hash,
            size_bytes=size_bytes,
            metadata=metadata or {},
        )
        manifest.add_entry(entry)
        return entry

    def verify_entry(self, entry: MagazineEntry, weights_path: Path) -> bool:
        if not weights_path.is_file():
            return False
        curr_hash = compute_sha256(weights_path)
        return curr_hash == entry.sha256

    def save_manifest(self, magazine_id: str, target_path: Path) -> Path:
        if magazine_id not in self._manifests:
            raise KeyError(f"Magazine {magazine_id} not found")
        manifest = self._manifests[magazine_id]
        target_path = Path(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        data = manifest.to_dict()
        target_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return target_path

    def load_manifest(self, manifest_path: Path) -> MagazineManifest:
        manifest_path = Path(manifest_path)
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = MagazineManifest.from_dict(data)
        self._manifests[manifest.magazine_id] = manifest
        return manifest
