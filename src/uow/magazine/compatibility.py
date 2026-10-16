"""Foundation-Adapter Compatibility Engine for uow.magazine.v1."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from src.uow.magazine.schema import CapabilityManifest


class CompatibilityChecker:
    """Evaluates whether an adapter manifest is compatible with a candidate foundation engine.
    
    Enforces invariant:
    Load(a, m) => Compatible(a, m) and Verified(a)
    """

    @classmethod
    def check_compatibility(
        cls,
        manifest: CapabilityManifest,
        foundation_id: str,
        foundation_architecture: str,
        available_module_names: Optional[list[str]] = None,
    ) -> tuple[bool, Optional[str]]:
        """Validates architectural and parameter compatibility.
        
        Returns (is_compatible, failure_reason).
        """
        # 1. Foundation ID matching
        # Allow exact match or canonical normalized match
        norm_manifest_f = manifest.foundation_model.lower().strip()
        norm_target_f = foundation_id.lower().strip()

        if norm_manifest_f != norm_target_f and norm_manifest_f.split("/")[-1] != norm_target_f.split("/")[-1]:
            return False, (
                f"Foundation mismatch: Adapter '{manifest.adapter_id}' requires '{manifest.foundation_model}', "
                f"but runtime is running '{foundation_id}'"
            )

        # 2. Module targeting compatibility if module names provided
        if available_module_names is not None:
            for mod in manifest.target_modules:
                has_match = any(mod in name for name in available_module_names)
                if not has_match:
                    return False, (
                        f"Target module incompatible: Adapter requires target module '{mod}' "
                        f"which is not present in foundation architecture '{foundation_architecture}'"
                    )

        # 3. Rank and alpha bounds
        if manifest.rank <= 0 or manifest.rank > 64:
            return False, f"Invalid adapter rank: {manifest.rank} (must be in 1..64)"
        if manifest.alpha <= 0:
            return False, f"Invalid adapter alpha: {manifest.alpha} (must be > 0)"

        return True, None
