"""Unified Magazine Manager: Subsystem S2 Reference Implementation.

Orchestrates adapter registration, cryptographic verification, compatibility checking,
in-memory residency, atomic switching, LRU eviction, request serialization, and rollback.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import time

from uow.magazine.schema import CapabilityManifest, AdapterLifecycleState
from uow.magazine.registry import CapabilityRegistry
from uow.magazine.compatibility import CompatibilityChecker
from uow.magazine.residency import ResidencyPool
from uow.magazine.scheduler import SerializedWorkerQueue
from uow.magazine.rollback import AdapterTransactionGuard, RollbackError
from uow.magazine.provenance import ProposalProvenance


class MagazineRuntimeError(Exception):
    """Raised when runtime magazine operations violate protocol invariants."""
    pass


class MagazineManager:
    """Production-grade reference implementation of the UoW Weight Magazine Manager."""

    def __init__(
        self,
        foundation_id: str,
        foundation_revision: str,
        foundation_architecture: str,
        device: str = "cuda",
        max_resident_slots: int = 16,
        memory_budget_mb: float = 1024.0,
        backend_loader: Optional[Callable[[str, Path], None]] = None,
        backend_switcher: Optional[Callable[[str], float]] = None,
        backend_unloader: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.foundation_id = foundation_id
        self.foundation_revision = foundation_revision
        self.foundation_architecture = foundation_architecture
        self.device = device

        self.registry = CapabilityRegistry()
        self.residency = ResidencyPool(max_resident_slots=max_resident_slots, memory_budget_mb=memory_budget_mb)
        self.worker_queue = SerializedWorkerQueue(worker_id=f"worker_{foundation_id.replace('/', '_')}")

        # Replaceable backend hooks
        self._backend_loader = backend_loader
        self._backend_switcher = backend_switcher
        self._backend_unloader = backend_unloader

        self._previous_adapter_id: Optional[str] = None
        self._switch_history: list[dict[str, Any]] = []

    def register_manifest(
        self,
        manifest: CapabilityManifest,
        adapter_path: Path,
        auto_verify: bool = True,
    ) -> AdapterLifecycleState:
        """Registers and verifies adapter. Enforces compatibility checking."""
        is_compat, reason = CompatibilityChecker.check_compatibility(
            manifest=manifest,
            foundation_id=self.foundation_id,
            foundation_architecture=self.foundation_architecture,
        )
        if not is_compat:
            # Register and immediately quarantine for incompatibility
            self.registry.register(manifest, adapter_path, auto_verify=False)
            self.registry.quarantine(manifest.adapter_id, reason or "Incompatible with foundation")
            return AdapterLifecycleState.QUARANTINED

        return self.registry.register(manifest, adapter_path, auto_verify=auto_verify)

    def load_adapter(self, adapter_id: str) -> None:
        """Loads verified adapter into residency pool.
        
        Enforces invariant:
        Load(a, m) => Compatible(a, m) and Verified(a)
        """
        state = self.registry.get_lifecycle_state(adapter_id)
        if state == AdapterLifecycleState.QUARANTINED:
            q_reason = self.registry.get_quarantine_reason(adapter_id)
            raise MagazineRuntimeError(f"Cannot load quarantined adapter '{adapter_id}': {q_reason}")

        if state == AdapterLifecycleState.REGISTERED:
            # Attempt verification on-demand
            state = self.registry.verify(adapter_id)
            if state == AdapterLifecycleState.QUARANTINED:
                raise MagazineRuntimeError(f"Verification failed on load for '{adapter_id}': {self.registry.get_quarantine_reason(adapter_id)}")

        manifest = self.registry.get_manifest(adapter_id)
        adapter_path = self.registry.get_adapter_path(adapter_id)

        # Handle capacity and eviction
        evicted_id = self.residency.register_loaded(adapter_id, size_bytes=manifest.weight_size_bytes)
        if evicted_id:
            self._handle_eviction(evicted_id)

        # Call underlying backend loader if provided
        if self._backend_loader:
            self._backend_loader(adapter_id, adapter_path)

        # Update lifecycle state in registry to LOADED
        self.registry._lifecycle_states[adapter_id] = AdapterLifecycleState.LOADED

    def _handle_eviction(self, evicted_id: str) -> None:
        """Executes backend unloading and transitions adapter state to EVICTED."""
        if self._backend_unloader:
            try:
                self._backend_unloader(evicted_id)
            except Exception:
                pass
        self.registry._lifecycle_states[evicted_id] = AdapterLifecycleState.EVICTED

    def switch_adapter(self, target_adapter_id: str) -> float:
        """Switches active adapter to target. Returns switch latency in milliseconds."""
        if not self.residency.is_resident(target_adapter_id):
            # Auto-load into residency pool if verified
            self.load_adapter(target_adapter_id)

        prev = self.residency.active_adapter_id
        if prev == target_adapter_id:
            return 0.0

        t0 = time.perf_counter_ns()
        if self._backend_switcher:
            latency_ms = self._backend_switcher(target_adapter_id)
        else:
            latency_ms = (time.perf_counter_ns() - t0) / 1_000_000.0

        self._previous_adapter_id = prev
        if prev and prev in self.registry._manifests:
            self.registry._lifecycle_states[prev] = AdapterLifecycleState.LOADED

        self.residency.mark_active(target_adapter_id)
        self.registry._lifecycle_states[target_adapter_id] = AdapterLifecycleState.ACTIVE

        self._switch_history.append({
            "from_adapter": prev,
            "to_adapter": target_adapter_id,
            "latency_ms": latency_ms,
            "timestamp": time.time(),
        })
        return latency_ms

    def rollback(self) -> Optional[str]:
        """Rolls back to the previous adapter on transaction failure."""
        if self._previous_adapter_id is None:
            return None
        prev = self._previous_adapter_id
        self.switch_adapter(prev)
        return prev

    def execute_request_transaction(
        self,
        request_id: str,
        adapter_id: str,
        inference_fn: Callable[[], Any],
    ) -> tuple[Any, ProposalProvenance]:
        """Executes inference request with serialized queue, rollback guard, and provenance.
        
        Guarantees:
        1. Serialized queue isolation across concurrent requests.
        2. Atomic switch and rollback on error.
        3. Cryptographic provenance attachment.
        """
        def _transaction_work() -> tuple[Any, ProposalProvenance]:
            manifest = self.registry.get_manifest(adapter_id)
            prev_id = self.residency.active_adapter_id

            guard = AdapterTransactionGuard(
                switch_func=self.switch_adapter,
                target_adapter_id=adapter_id,
                previous_adapter_id=prev_id,
                on_error_quarantine=self.registry.quarantine,
            )

            with guard:
                t_infer_start = time.perf_counter_ns()
                result = inference_fn()
                t_infer_end = time.perf_counter_ns()
                guard.commit()

            infer_latency_ms = (t_infer_end - t_infer_start) / 1_000_000.0

            provenance = ProposalProvenance(
                request_id=request_id,
                foundation_model=self.foundation_id,
                foundation_revision=self.foundation_revision,
                adapter_id=adapter_id,
                adapter_sha256=manifest.adapter_sha256,
                domain=manifest.domain,
                grammar=manifest.grammar,
                target_schema=manifest.target_schema,
                inference_device=self.device,
                switch_latency_ms=guard.switch_latency_ms,
                inference_latency_ms=infer_latency_ms,
                timestamp_utc=time.time(),
            )
            return result, provenance

        return self.worker_queue.execute_transaction(request_id, _transaction_work)

    def get_runtime_status(self) -> dict[str, Any]:
        """Summarizes magazine residency, capacity, and current active adapter."""
        return {
            "foundation_id": self.foundation_id,
            "foundation_revision": self.foundation_revision,
            "active_adapter": self.residency.active_adapter_id,
            "resident_count": self.residency.resident_count,
            "max_slots": self.residency.max_resident_slots,
            "resident_adapters": self.residency.list_resident(),
            "worker_queue_busy": self.worker_queue.is_busy,
            "total_transactions": self.worker_queue.total_transactions_executed,
            "catalog": self.registry.list_adapters(),
        }
