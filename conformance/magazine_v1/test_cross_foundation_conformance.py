"""Cross-Foundation Compatibility & Isolation Conformance Vectors (Milestone P3)."""
from __future__ import annotations

import pytest
from pathlib import Path

from uow.magazine.schema import CapabilityManifest, AdapterLifecycleState
from uow.magazine.compatibility import CompatibilityChecker
from uow.magazine.manager import MagazineManager
from uow.magazine.registry import CapabilityRegistry
from experiments.uow_magazine_p3.foundations import FOUNDATION_ROSTER


def test_cross_foundation_manifest_mismatch_rejections():
    """Verify that adapters built for one foundation are strictly rejected on different foundations."""
    for f_slug_src, f_src in FOUNDATION_ROSTER.items():
        manifest = CapabilityManifest(
            adapter_id=f"{f_slug_src}_test_adapter",
            domain="shared",
            grammar="operational",
            foundation_model=f_src.model_id,
            adapter_sha256="test_sha_digest_123",
            target_modules=f_src.target_modules,
        )

        for f_slug_dst, f_dst in FOUNDATION_ROSTER.items():
            if f_slug_src == f_slug_dst:
                # Same foundation should be compatible
                is_compat, reason = CompatibilityChecker.check_compatibility(
                    manifest=manifest,
                    foundation_id=f_dst.model_id,
                    foundation_architecture=f_dst.model_class_name,
                )
                assert is_compat is True, f"Expected {f_slug_src} to be compatible with itself: {reason}"
            else:
                # Different foundation MUST be rejected fail-closed
                is_compat, reason = CompatibilityChecker.check_compatibility(
                    manifest=manifest,
                    foundation_id=f_dst.model_id,
                    foundation_architecture=f_dst.model_class_name,
                )
                assert is_compat is False, f"Expected {f_slug_src} to fail against {f_slug_dst}"
                assert "Foundation mismatch" in reason


def test_target_module_architecture_rejection():
    """Verify that target module lists incompatible with target architecture are rejected."""
    manifest = CapabilityManifest(
        adapter_id="pythia_on_llama",
        domain="shared",
        grammar="operational",
        foundation_model="HuggingFaceTB/SmolLM2-135M-Instruct",
        adapter_sha256="digest_abc",
        target_modules=["query_key_value"],  # GPT-NeoX module name, invalid on Llama
    )
    is_compat, reason = CompatibilityChecker.check_compatibility(
        manifest=manifest,
        foundation_id="HuggingFaceTB/SmolLM2-135M-Instruct",
        foundation_architecture="LlamaForCausalLM",
        available_module_names=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    assert is_compat is False
    assert "Target module incompatible" in reason


def test_magazine_manager_cross_foundation_load_rejection(tmp_path):
    """Verify that MagazineManager rejects registration/loading of an adapter from a foreign foundation."""
    fake_adapter_dir = tmp_path / "fake_pythia_adapter"
    fake_adapter_dir.mkdir(parents=True)
    fake_weights = fake_adapter_dir / "adapter_model.safetensors"
    fake_weights.write_bytes(b"dummy_weights")

    import hashlib
    sha = hashlib.sha256(b"dummy_weights").hexdigest()

    manifest = CapabilityManifest(
        adapter_id="foreign_pythia_adapter",
        domain="shared",
        grammar="operational",
        foundation_model="EleutherAI/pythia-160m",
        adapter_sha256=sha,
        target_modules=["query_key_value"],
    )

    manager = MagazineManager(
        foundation_id="HuggingFaceTB/SmolLM2-135M-Instruct",
        foundation_revision="main",
        foundation_architecture="LlamaForCausalLM",
    )

    # Registering foreign adapter should fail verification due to foundation mismatch
    state = manager.register_manifest(manifest, fake_adapter_dir, auto_verify=True)
    assert state == AdapterLifecycleState.QUARANTINED
    assert "Foundation mismatch" in manager.registry.get_quarantine_reason(manifest.adapter_id)
