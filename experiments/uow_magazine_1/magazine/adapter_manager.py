"""Magazine Adapter Manager: Dynamic runtime adapter loading, atomic switching, and LRU eviction."""
from __future__ import annotations

from collections import OrderedDict
import time
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

import torch
from peft import PeftModel

from experiments.uow_magazine_1.magazine.manifest import MagazineEntry, MagazineManifest


class MagazineAdapterManager:
    """Orchestrates runtime weight magazine on a frozen foundation model."""

    def __init__(
        self,
        base_model: torch.nn.Module,
        manifest: MagazineManifest,
        device: str = "cuda",
        max_resident_slots: int = 16,
    ):
        self.base_model = base_model
        self.manifest = manifest
        self.device = device
        self.max_resident_slots = max_resident_slots

        # PeftModel wrapper
        self.peft_model: Optional[PeftModel] = None
        self.resident_adapters: OrderedDict[str, MagazineEntry] = OrderedDict()
        self.active_adapter_id: Optional[str] = None
        self.previous_adapter_id: Optional[str] = None
        self.switch_history: list[dict[str, Any]] = []

    def initialize_peft(self, first_adapter_id: str, adapter_dir: Path) -> None:
        """Initialize the base model as a PeftModel with the first adapter."""
        if first_adapter_id not in self.manifest.entries:
            raise KeyError(f"Adapter {first_adapter_id} not in manifest")

        entry = self.manifest.entries[first_adapter_id]
        self.peft_model = PeftModel.from_pretrained(
            self.base_model,
            str(adapter_dir),
            adapter_name=first_adapter_id,
            is_trainable=False,
        )
        self.peft_model.to(self.device).eval()
        self.resident_adapters[first_adapter_id] = entry
        self.active_adapter_id = first_adapter_id

    def load_adapter(self, adapter_id: str, adapter_dir: Path) -> None:
        """Load an additional adapter into the resident pool, applying LRU eviction if full."""
        if self.peft_model is None:
            self.initialize_peft(adapter_id, adapter_dir)
            return

        if adapter_id in self.resident_adapters:
            # Already loaded; bump to MRU
            self.resident_adapters.move_to_end(adapter_id)
            return

        if adapter_id not in self.manifest.entries:
            raise KeyError(f"Adapter {adapter_id} not in manifest")

        # Evict LRU if capacity reached
        if len(self.resident_adapters) >= self.max_resident_slots:
            self._evict_lru()

        entry = self.manifest.entries[adapter_id]
        self.peft_model.load_adapter(str(adapter_dir), adapter_name=adapter_id)
        self.resident_adapters[adapter_id] = entry

    def _evict_lru(self) -> str:
        """Evicts the least recently used adapter (excluding active)."""
        evict_candidate = None
        for k in self.resident_adapters.keys():
            if k != self.active_adapter_id:
                evict_candidate = k
                break

        if evict_candidate is None:
            # Fallback if active is the only one
            evict_candidate = next(iter(self.resident_adapters))

        if self.peft_model is not None and hasattr(self.peft_model, "delete_adapter"):
            try:
                self.peft_model.delete_adapter(evict_candidate)
            except Exception:
                pass
        del self.resident_adapters[evict_candidate]
        return evict_candidate

    def switch_adapter(self, adapter_id: str) -> float:
        """Atomically switches active adapter. Returns switch latency in milliseconds."""
        if self.peft_model is None:
            raise RuntimeError("PeftModel not initialized")

        if adapter_id not in self.resident_adapters:
            raise KeyError(f"Adapter {adapter_id} not resident in magazine")

        if adapter_id == self.active_adapter_id:
            return 0.0

        target_prev = self.active_adapter_id

        if torch.cuda.is_available() and self.device.startswith("cuda"):
            start_event = torch.cuda.Event(enable_timing=True)
            end_event = torch.cuda.Event(enable_timing=True)

            start_event.record()
            self.peft_model.set_adapter(adapter_id)
            end_event.record()
            torch.cuda.synchronize()
            latency_ms = start_event.elapsed_time(end_event)
        else:
            t0 = time.perf_counter_ns()
            self.peft_model.set_adapter(adapter_id)
            latency_ms = (time.perf_counter_ns() - t0) / 1_000_000.0

        self.previous_adapter_id = target_prev
        self.active_adapter_id = adapter_id
        self.resident_adapters.move_to_end(adapter_id)

        self.switch_history.append({
            "from_adapter": target_prev,
            "to_adapter": adapter_id,
            "latency_ms": latency_ms,
            "timestamp": time.time(),
        })
        return latency_ms

    def rollback(self) -> Optional[str]:
        """Rolls back to previous adapter in case of transaction abort or error."""
        if self.previous_adapter_id is None:
            return None
        prev = self.previous_adapter_id
        self.switch_adapter(prev)
        return prev

    def get_stats(self) -> dict[str, Any]:
        """Returns runtime performance statistics."""
        latencies = [s["latency_ms"] for s in self.switch_history if s["latency_ms"] > 0]
        vram_allocated_mb = (
            torch.cuda.memory_allocated() / (1024 * 1024)
            if torch.cuda.is_available() and self.device.startswith("cuda")
            else 0.0
        )
        return {
            "active_adapter": self.active_adapter_id,
            "resident_count": len(self.resident_adapters),
            "max_slots": self.max_resident_slots,
            "total_switches": len(self.switch_history),
            "median_latency_ms": sorted(latencies)[len(latencies) // 2] if latencies else 0.0,
            "mean_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
            "vram_allocated_mb": round(vram_allocated_mb, 2),
        }
