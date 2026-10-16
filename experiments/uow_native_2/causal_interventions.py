"""Causal neural interventions (ablation, clamping, restoration) for UOW-NATIVE-2.

Provides PyTorch hooks for targeted intervention on MLP projections:
  - Multi-neuron zero ablation
  - Activation caching and restoration
  - Projection module locator across model layers
"""

from contextlib import contextmanager
from typing import Dict, List, Optional, Sequence, Tuple
import torch
import torch.nn as nn


def find_mlp_projections(model: nn.Module) -> Dict[str, nn.Module]:
    """Discover all MLP projection modules (down_proj, gate_proj, up_proj) across layers."""
    projections = {}
    for name, module in model.named_modules():
        if any(proj in name for proj in ["mlp.down_proj", "mlp.gate_proj", "mlp.up_proj"]):
            if hasattr(module, "in_features") or hasattr(module, "weight"):
                projections[name] = module
    return projections


@contextmanager
def ablate_neurons(module: nn.Module, indices: Sequence[int]):
    """Context manager applying zero-ablation to specified neuron indices on forward pre-hook."""
    if not indices:
        yield
        return

    idx_tensor = torch.tensor(indices, dtype=torch.long)

    def hook(mod, args):
        x = args[0].clone()
        device_idx = idx_tensor.to(x.device)
        x[..., device_idx] = 0.0
        return (x, *args[1:])

    handle = module.register_forward_pre_hook(hook)
    try:
        yield
    finally:
        handle.remove()


@contextmanager
def restore_activations(module: nn.Module, cached_activations: torch.Tensor, indices: Sequence[int]):
    """Context manager restoring specific neuron activations to pre-cached values."""
    if not indices:
        yield
        return

    idx_tensor = torch.tensor(indices, dtype=torch.long)

    def hook(mod, args):
        x = args[0].clone()
        device_idx = idx_tensor.to(x.device)
        cached = cached_activations.to(x.device)
        x[..., device_idx] = cached[..., device_idx]
        return (x, *args[1:])

    handle = module.register_forward_pre_hook(hook)
    try:
        yield
    finally:
        handle.remove()
