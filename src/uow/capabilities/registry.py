"""Universal Capability Registry for Deterministic, Neural, and Knowledge-Backed Capabilities.

Subsystem S2 universal reference implementation complying with WP02 specification.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from uow.protocol.v1 import (
    CapabilityDescriptor,
    CapabilityKind,
    CapabilityPackageManifest,
    QualificationStatus,
)
from .models import CapabilityLifecycleState, CapabilityRecord
from .store import LocalPackageStore, PackageVerificationError


class RegistryError(Exception):
    """Base exception for capability registry errors."""
    pass


class CapabilityNotFoundError(RegistryError):
    """Raised when requesting an unregistered capability."""
    pass


class CapabilityQuarantinedError(RegistryError):
    """Raised when attempting to invoke or route to a quarantined capability."""
    pass


class DependencyUnsatisfiedError(RegistryError):
    """Raised when required package or capability dependencies are not met."""
    pass


class UniversalCapabilityRegistry:
    """Universal registry managing deterministic, neural, and knowledge capabilities."""

    def __init__(self, store: Optional[LocalPackageStore] = None) -> None:
        self.store = store or LocalPackageStore(Path(".uow_runtime"))
        # Active capabilities: capability_id -> CapabilityRecord
        self._active: Dict[str, CapabilityRecord] = {}
        # Version history: capability_id -> list of CapabilityRecord
        self._history: Dict[str, List[CapabilityRecord]] = {}
        # Installed packages: package_id -> CapabilityPackageManifest
        self._packages: Dict[str, CapabilityPackageManifest] = {}

    def register_deterministic(
        self,
        descriptor: CapabilityDescriptor,
        handler: Callable[[Dict[str, Any]], Dict[str, Any]],
        package_id: str = "core.deterministic",
    ) -> CapabilityRecord:
        """Register an exact deterministic provider (code, algorithm, or rule transform)."""
        if descriptor.kind != CapabilityKind.DETERMINISTIC:
            raise RegistryError(f"Cannot register deterministic provider with kind: {descriptor.kind}")

        record = CapabilityRecord(
            descriptor=descriptor,
            state=CapabilityLifecycleState.ACTIVE,
            package_id=package_id,
            installed_at=time.time(),
            deterministic_handler=handler,
        )
        self._commit_record(record)
        return record

    def register_neural(
        self,
        descriptor: CapabilityDescriptor,
        artifact_path: Optional[Path] = None,
        package_id: str = "core.neural",
    ) -> CapabilityRecord:
        """Register a learned adapter capability operating on a small neural foundation."""
        if descriptor.kind != CapabilityKind.NEURAL_INTERPRETER:
            raise RegistryError(f"Cannot register neural capability with kind: {descriptor.kind}")

        record = CapabilityRecord(
            descriptor=descriptor,
            state=CapabilityLifecycleState.ACTIVE,
            package_id=package_id,
            installed_at=time.time(),
            artifact_path=artifact_path,
        )
        self._commit_record(record)
        return record

    def register_knowledge(
        self,
        descriptor: CapabilityDescriptor,
        ontology_payload: Dict[str, Any],
        package_id: str = "core.knowledge",
    ) -> CapabilityRecord:
        """Register a knowledge-backed capability providing domain ontologies and schema guards."""
        if descriptor.kind != CapabilityKind.KNOWLEDGE_BACKED:
            raise RegistryError(f"Cannot register knowledge capability with kind: {descriptor.kind}")

        record = CapabilityRecord(
            descriptor=descriptor,
            state=CapabilityLifecycleState.ACTIVE,
            package_id=package_id,
            installed_at=time.time(),
            knowledge_payload=ontology_payload,
        )
        self._commit_record(record)
        return record

    def install_package(
        self,
        manifest: CapabilityPackageManifest,
        artifact_files: Optional[Dict[str, Path]] = None,
    ) -> List[CapabilityRecord]:
        """Install an immutable capability package and activate its declared capabilities."""
        # 1. Check dependencies
        for dep in manifest.dependencies:
            if not self.has_dependency(dep):
                raise DependencyUnsatisfiedError(
                    f"Package '{manifest.package_id}' requires unsatisfied dependency: '{dep}'"
                )

        # 2. Stage and verify physical files in package store
        staged_dir: Optional[Path] = None
        if manifest.artifacts and artifact_files:
            staged_dir = self.store.stage_package(manifest, artifact_files)

        # 3. Register declared capabilities
        registered_records: List[CapabilityRecord] = []
        for desc in manifest.capabilities:
            art_path = staged_dir / desc.capability_id if staged_dir else None
            record = CapabilityRecord(
                descriptor=desc,
                state=CapabilityLifecycleState.ACTIVE,
                package_id=manifest.package_id,
                installed_at=time.time(),
                artifact_path=art_path,
            )
            self._commit_record(record)
            registered_records.append(record)

        self._packages[manifest.package_id] = manifest
        return registered_records

    def has_dependency(self, dep_id: str) -> bool:
        """Check if dependency exists either as an installed package or an active capability."""
        if dep_id in self._packages:
            return True
        if dep_id in self._active:
            return True
        return False

    def quarantine(self, capability_id: str, reason: str) -> None:
        """Quarantine a capability immediately, preventing routing and execution."""
        record = self.get(capability_id)
        if not record:
            raise CapabilityNotFoundError(f"Capability '{capability_id}' not found for quarantine.")
        record.state = CapabilityLifecycleState.QUARANTINED
        record.quarantine_reason = reason

    def rollback(self, capability_id: str, target_version: Optional[str] = None) -> CapabilityRecord:
        """Rollback capability to a previous version in history."""
        history = self._history.get(capability_id, [])
        if not history:
            raise RegistryError(f"No history available to rollback capability '{capability_id}'.")

        selected_record: Optional[CapabilityRecord] = None
        if target_version:
            for rec in reversed(history):
                if rec.version == target_version and rec.state != CapabilityLifecycleState.QUARANTINED:
                    selected_record = rec
                    break
        else:
            # Pick latest non-quarantined previous version
            current = self._active.get(capability_id)
            for rec in reversed(history):
                if current and rec.version != current.version and rec.state != CapabilityLifecycleState.QUARANTINED:
                    selected_record = rec
                    break

        if not selected_record:
            raise RegistryError(
                f"No suitable rollback version found for '{capability_id}' (target: {target_version})."
            )

        # Restore as active
        restored = CapabilityRecord(
            descriptor=selected_record.descriptor,
            state=CapabilityLifecycleState.ACTIVE,
            package_id=selected_record.package_id,
            installed_at=time.time(),
            deterministic_handler=selected_record.deterministic_handler,
            artifact_path=selected_record.artifact_path,
            knowledge_payload=selected_record.knowledge_payload,
        )
        self._commit_record(restored)
        return restored

    def invoke_deterministic(self, capability_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an active deterministic capability directly."""
        record = self.get(capability_id)
        if not record:
            raise CapabilityNotFoundError(f"Deterministic capability '{capability_id}' is not registered.")
        if record.state == CapabilityLifecycleState.QUARANTINED:
            raise CapabilityQuarantinedError(
                f"Capability '{capability_id}' is quarantined: {record.quarantine_reason}"
            )
        if not record.deterministic_handler:
            raise RegistryError(f"Capability '{capability_id}' has no registered deterministic handler.")

        return record.deterministic_handler(payload)

    def get(self, capability_id: str) -> Optional[CapabilityRecord]:
        """Retrieve active capability record."""
        return self._active.get(capability_id)

    def list_capabilities(self, kind: Optional[CapabilityKind] = None) -> List[CapabilityRecord]:
        """List all active capabilities, optionally filtered by kind."""
        records = list(self._active.values())
        if kind:
            records = [r for r in records if r.kind == kind]
        return records

    def _commit_record(self, record: CapabilityRecord) -> None:
        """Commit record to active slot and append to version history."""
        cap_id = record.capability_id
        if cap_id not in self._history:
            self._history[cap_id] = []
        self._history[cap_id].append(record)
        self._active[cap_id] = record
