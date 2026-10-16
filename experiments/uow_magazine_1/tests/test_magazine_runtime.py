"""Unit Tests for Weight Magazine Runtime and Protocol."""
import pytest
import tempfile
from pathlib import Path
import torch

from experiments.uow_magazine_1.magazine.manifest import MagazineEntry, MagazineManifest
from experiments.uow_magazine_1.magazine.registry import MagazineRegistry
from experiments.uow_magazine_1.magazine.adapter_manager import MagazineAdapterManager


def test_manifest_digest_determinism():
    m1 = MagazineManifest(magazine_id="mag-test", foundation_id="smollm2_135m")
    e1 = MagazineEntry(
        adapter_id="adapter-1",
        domain="industrial",
        grammar="operational",
        foundation_id="smollm2_135m",
        rank=8,
        alpha=16,
        target_modules=["q_proj", "v_proj"],
        sha256="abc12345",
        size_bytes=1024,
    )
    m1.add_entry(e1)
    d1 = m1.compute_digest()

    m2 = MagazineManifest(magazine_id="mag-test", foundation_id="smollm2_135m")
    m2.add_entry(e1)
    d2 = m2.compute_digest()

    assert d1 == d2
    assert len(d1) == 64


def test_registry_registration_and_verification():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        weight_file = tmp_path / "dummy_adapter.bin"
        weight_file.write_bytes(b"TEST_WEIGHT_DATA_12345")

        registry = MagazineRegistry(tmp_path)
        manifest = registry.create_manifest("mag-001", "smollm2_135m")

        entry = registry.register_adapter(
            magazine_id="mag-001",
            adapter_id="ind_op_1",
            domain="industrial",
            grammar="operational",
            foundation_id="smollm2_135m",
            rank=8,
            alpha=16,
            target_modules=["q_proj", "v_proj"],
            adapter_weights_path=weight_file,
        )

        assert entry.adapter_id == "ind_op_1"
        assert registry.verify_entry(entry, weight_file) is True

        # Test corrupt weights detection
        corrupt_file = tmp_path / "corrupt_weights.bin"
        corrupt_file.write_bytes(b"CORRUPT_BYTES")
        assert registry.verify_entry(entry, corrupt_file) is False


def test_adapter_manager_lru_and_rollback():
    # Use a dummy Linear module to verify adapter switching & LRU logic
    base_model = torch.nn.Linear(10, 10)
    manifest = MagazineManifest(magazine_id="test_mag", foundation_id="test_model", max_resident_slots=3)

    # Register 4 dummy entries
    for i in range(1, 5):
        manifest.add_entry(
            MagazineEntry(
                adapter_id=f"ad_{i}",
                domain="industrial",
                grammar="operational",
                foundation_id="test_model",
                rank=8,
                alpha=16,
                target_modules=["linear"],
                sha256=f"hash_{i}",
                size_bytes=100,
            )
        )

    mgr = MagazineAdapterManager(base_model, manifest, device="cpu", max_resident_slots=3)
    
    # Mock peft model internals for unit test without loading heavy pretrained LLMs
    class MockPeft:
        def __init__(self):
            self.active = None
            self.adapters = set()
        def set_adapter(self, name):
            self.active = name
        def load_adapter(self, path, adapter_name):
            self.adapters.add(adapter_name)
        def delete_adapter(self, name):
            if name in self.adapters:
                self.adapters.remove(name)

    mgr.peft_model = MockPeft()
    mgr.resident_adapters["ad_1"] = manifest.entries["ad_1"]
    mgr.active_adapter_id = "ad_1"
    mgr.peft_model.adapters.add("ad_1")

    # Load ad_2, ad_3
    mgr.load_adapter("ad_2", Path("dummy_2"))
    mgr.load_adapter("ad_3", Path("dummy_3"))
    assert len(mgr.resident_adapters) == 3

    # Switch to ad_2
    lat = mgr.switch_adapter("ad_2")
    assert mgr.active_adapter_id == "ad_2"
    assert mgr.previous_adapter_id == "ad_1"
    assert lat >= 0

    # Test rollback
    rolled_back = mgr.rollback()
    assert rolled_back == "ad_1"
    assert mgr.active_adapter_id == "ad_1"

    # Now load ad_4 -> should trigger LRU eviction of least recently used (ad_3)
    mgr.load_adapter("ad_4", Path("dummy_4"))
    assert len(mgr.resident_adapters) == 3
    assert "ad_4" in mgr.resident_adapters
    assert "ad_1" in mgr.resident_adapters  # ad_1 was active
    assert "ad_3" not in mgr.resident_adapters  # ad_3 was evicted!
