"""Residency Pool and LRU Eviction Manager for in-memory adapter slots."""
from __future__ import annotations

from collections import OrderedDict
import time
from typing import Any, Dict, List, Optional


class ResidencyPool:
    """Tracks and bounds in-memory resident adapter slots using LRU eviction."""

    def __init__(self, max_resident_slots: int = 16, memory_budget_mb: float = 1024.0) -> None:
        self.max_resident_slots = max_resident_slots
        self.memory_budget_mb = memory_budget_mb
        # OrderedDict maintains insertion / access order for LRU: MRU at end, LRU at start
        self._resident_slots: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._active_adapter_id: Optional[str] = None

    @property
    def active_adapter_id(self) -> Optional[str]:
        return self._active_adapter_id

    @property
    def resident_count(self) -> int:
        return len(self._resident_slots)

    def is_resident(self, adapter_id: str) -> bool:
        return adapter_id in self._resident_slots

    def mark_active(self, adapter_id: str) -> None:
        """Sets active adapter for current transaction and bumps to MRU."""
        if adapter_id not in self._resident_slots:
            raise KeyError(f"Adapter '{adapter_id}' is not loaded in residency pool")
        self._active_adapter_id = adapter_id
        self._resident_slots.move_to_end(adapter_id)
        self._resident_slots[adapter_id]["last_accessed_ns"] = time.perf_counter_ns()

    def mark_inactive(self) -> None:
        """Clears active adapter transaction lock."""
        self._active_adapter_id = None

    def register_loaded(self, adapter_id: str, size_bytes: int = 0) -> Optional[str]:
        """Registers an adapter as loaded into memory.
        
        If capacity is reached, evicts the least-recently used inactive adapter
        and returns the evicted adapter_id.
        """
        evicted_id = None
        if adapter_id in self._resident_slots:
            self._resident_slots.move_to_end(adapter_id)
            return None

        # Check if eviction required
        if len(self._resident_slots) >= self.max_resident_slots:
            evicted_id = self.select_eviction_candidate()
            if evicted_id:
                del self._resident_slots[evicted_id]

        self._resident_slots[adapter_id] = {
            "loaded_at_ns": time.perf_counter_ns(),
            "last_accessed_ns": time.perf_counter_ns(),
            "size_bytes": size_bytes,
        }
        return evicted_id

    def select_eviction_candidate(self) -> Optional[str]:
        """Finds the least recently used adapter that is NOT currently active."""
        for candidate in self._resident_slots.keys():
            if candidate != self._active_adapter_id:
                return candidate
        # If all slots are somehow active (rare), select oldest
        return next(iter(self._resident_slots), None)

    def remove(self, adapter_id: str) -> bool:
        """Removes adapter from pool on manual unload or quarantine."""
        if adapter_id in self._resident_slots:
            if self._active_adapter_id == adapter_id:
                self._active_adapter_id = None
            del self._resident_slots[adapter_id]
            return True
        return False

    def list_resident(self) -> list[str]:
        return list(self._resident_slots.keys())
