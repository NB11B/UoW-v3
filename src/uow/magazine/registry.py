"""Capability Registry: Catalog, verify, and resolve domain adapter manifests."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from uow.magazine.schema import CapabilityManifest, AdapterLifecycleState
from uow.magazine.verification import ManifestVerifier


class CapabilityRegistry:
    """Immutable catalog of domain adapters, tracking verification and lifecycle state."""

    def __init__(self) -> None:
        self._manifests: dict[str, CapabilityManifest] = {}
        self._adapter_paths: dict[str, Path] = {}
        self._lifecycle_states: dict[str, AdapterLifecycleState] = {}
        self._quarantine_reasons: dict[str, str] = {}

    def register(
        self,
        manifest: CapabilityManifest,
        adapter_path: Path,
        auto_verify: bool = True,
    ) -> AdapterLifecycleState:
        """Registers a new adapter manifest. Optionally executes immediate verification."""
        adapter_id = manifest.adapter_id
        if not adapter_id:
            raise ValueError("Manifest must have a non-empty adapter_id")

        self._manifests[adapter_id] = manifest
        self._adapter_paths[adapter_id] = adapter_path
        self._lifecycle_states[adapter_id] = AdapterLifecycleState.REGISTERED

        if auto_verify:
            return self.verify(adapter_id)
        return AdapterLifecycleState.REGISTERED

    def verify(self, adapter_id: str) -> AdapterLifecycleState:
        """Cryptographically verifies registered adapter against weight files."""
        if adapter_id not in self._manifests:
            raise KeyError(f"Adapter '{adapter_id}' not found in registry")

        manifest = self._manifests[adapter_id]
        adapter_path = self._adapter_paths[adapter_id]

        is_valid, error_reason = ManifestVerifier.verify_adapter(manifest, adapter_path)
        if is_valid:
            self._lifecycle_states[adapter_id] = AdapterLifecycleState.VERIFIED
            self._quarantine_reasons.pop(adapter_id, None)
            return AdapterLifecycleState.VERIFIED
        else:
            self._lifecycle_states[adapter_id] = AdapterLifecycleState.QUARANTINED
            self._quarantine_reasons[adapter_id] = error_reason or "Verification failed"
            return AdapterLifecycleState.QUARANTINED

    def quarantine(self, adapter_id: str, reason: str) -> None:
        """Explicitly quarantines an adapter, prohibiting loading or execution."""
        if adapter_id not in self._manifests:
            raise KeyError(f"Adapter '{adapter_id}' not found in registry")
        self._lifecycle_states[adapter_id] = AdapterLifecycleState.QUARANTINED
        self._quarantine_reasons[adapter_id] = reason

    def get_manifest(self, adapter_id: str) -> CapabilityManifest:
        if adapter_id not in self._manifests:
            raise KeyError(f"Adapter '{adapter_id}' not found in registry")
        return self._manifests[adapter_id]

    def get_adapter_path(self, adapter_id: str) -> Path:
        if adapter_id not in self._adapter_paths:
            raise KeyError(f"Adapter '{adapter_id}' not found in registry")
        return self._adapter_paths[adapter_id]

    def get_lifecycle_state(self, adapter_id: str) -> AdapterLifecycleState:
        return self._lifecycle_states.get(adapter_id, AdapterLifecycleState.QUARANTINED)

    def get_quarantine_reason(self, adapter_id: str) -> Optional[str]:
        return self._quarantine_reasons.get(adapter_id)

    def resolve_capability(self, domain: str, grammar: str) -> Optional[str]:
        """Resolves verified adapter_id matching the requested domain and grammar.
        
        Priority:
        1. Exact match on (domain, grammar).
        2. Shared grammar adapter with domain in ("shared", "*", "any").
        """
        exact_match = None
        shared_match = None
        for aid, manifest in self._manifests.items():
            if self._lifecycle_states.get(aid) not in (
                AdapterLifecycleState.VERIFIED,
                AdapterLifecycleState.LOADED,
                AdapterLifecycleState.ACTIVE,
            ):
                continue
            if manifest.grammar.lower() == grammar.lower():
                if manifest.domain.lower() == domain.lower():
                    exact_match = aid
                    break
                elif manifest.domain.lower() in ("shared", "*", "any"):
                    shared_match = aid

        return exact_match or shared_match

    def list_adapters(self) -> list[dict[str, Any]]:
        """Returns catalog of all registered adapters with current states."""
        return [
            {
                "adapter_id": aid,
                "domain": m.domain,
                "grammar": m.grammar,
                "version": m.version,
                "foundation": m.foundation_model,
                "state": self._lifecycle_states.get(aid, AdapterLifecycleState.QUARANTINED).value,
                "quarantine_reason": self._quarantine_reasons.get(aid),
            }
            for aid, m in self._manifests.items()
        ]

    def save_catalog(self, path: Path) -> None:
        """Persists catalog metadata to disk for crash consistency and restart."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "uow.magazine.catalog.v1",
            "entries": [
                {
                    "manifest": m.to_dict(),
                    "adapter_path": str(self._adapter_paths[aid]),
                    "lifecycle_state": self._lifecycle_states[aid].value,
                    "quarantine_reason": self._quarantine_reasons.get(aid),
                }
                for aid, m in self._manifests.items()
            ],
        }
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temp_path.replace(path)

    def load_catalog(self, path: Path, auto_verify_on_reload: bool = True) -> int:
        """Loads and restores catalog from disk, verifying integrity against files."""
        if not path.exists():
            return 0
        raw = json.loads(path.read_text(encoding="utf-8"))
        count = 0
        for entry in raw.get("entries", []):
            m = CapabilityManifest.from_dict(entry["manifest"])
            adapter_path = Path(entry["adapter_path"])
            self.register(m, adapter_path, auto_verify=auto_verify_on_reload)
            count += 1
        return count
