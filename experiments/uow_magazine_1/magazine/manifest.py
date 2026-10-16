"""Specification and Data Model for Weight Magazine Protocol (uow.magazine.v1)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import time
from typing import Any, Dict, List, Optional


PROTOCOL_VERSION = "uow.magazine.v1"


@dataclass(frozen=True)
class MagazineEntry:
    adapter_id: str
    domain: str
    grammar: str
    foundation_id: str
    rank: int
    alpha: int
    target_modules: list[str]
    sha256: str
    size_bytes: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "domain": self.domain,
            "grammar": self.grammar,
            "foundation_id": self.foundation_id,
            "rank": self.rank,
            "alpha": self.alpha,
            "target_modules": list(self.target_modules),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MagazineEntry:
        return cls(
            adapter_id=data["adapter_id"],
            domain=data["domain"],
            grammar=data["grammar"],
            foundation_id=data["foundation_id"],
            rank=data["rank"],
            alpha=data["alpha"],
            target_modules=list(data["target_modules"]),
            sha256=data["sha256"],
            size_bytes=data["size_bytes"],
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class MagazineManifest:
    magazine_id: str
    foundation_id: str
    max_resident_slots: int = 16
    version: str = PROTOCOL_VERSION
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    entries: dict[str, MagazineEntry] = field(default_factory=dict)

    def add_entry(self, entry: MagazineEntry) -> None:
        if entry.adapter_id in self.entries:
            raise ValueError(f"Entry {entry.adapter_id} already registered in manifest")
        self.entries[entry.adapter_id] = entry

    def compute_digest(self) -> str:
        canonical_entries = sorted(self.entries.keys())
        hasher = hashlib.sha256()
        hasher.update(self.magazine_id.encode("utf-8"))
        hasher.update(self.foundation_id.encode("utf-8"))
        for k in canonical_entries:
            e = self.entries[k]
            hasher.update(e.adapter_id.encode("utf-8"))
            hasher.update(e.sha256.encode("utf-8"))
        return hasher.hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "magazine_id": self.magazine_id,
            "foundation_id": self.foundation_id,
            "max_resident_slots": self.max_resident_slots,
            "created_at": self.created_at,
            "digest": self.compute_digest(),
            "entries_count": len(self.entries),
            "entries": {k: v.to_dict() for k, v in self.entries.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MagazineManifest:
        manifest = cls(
            magazine_id=data["magazine_id"],
            foundation_id=data["foundation_id"],
            max_resident_slots=data.get("max_resident_slots", 16),
            version=data.get("version", PROTOCOL_VERSION),
            created_at=data.get("created_at", ""),
        )
        for k, v in data.get("entries", {}).items():
            manifest.entries[k] = MagazineEntry.from_dict(v)
        return manifest
