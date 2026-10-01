"""Neural surrogate model architecture and ONNX artifact compilation (Gate U15.5)."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Tuple
import onnx
import torch
import torch.nn as nn

from .features import FEATURE_DIM


class UoWSchedulingNet(nn.Module):
    """Neural scoring surrogate network for UoW candidate schedules."""

    def __init__(self, input_dim: int = FEATURE_DIM) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.net = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def export_and_hash_onnx(
    model: nn.Module,
    onnx_path: Path,
) -> Tuple[Path, str]:
    """Exports PyTorch model to self-contained ONNX and computes its SHA-256 artifact hash."""
    onnx_path = Path(onnx_path)
    onnx_path.parent.mkdir(parents=True, exist_ok=True)

    model_cpu = model.cpu().eval()
    dummy_input = torch.zeros(1, FEATURE_DIM, dtype=torch.float32)

    torch.onnx.export(
        model_cpu,
        dummy_input,
        str(onnx_path),
        input_names=["candidate_features"],
        output_names=["score"],
        opset_version=18,
        dynamo=False,
    )

    # Ensure self-contained ONNX model (no external tensor data files)
    loaded_model = onnx.load(str(onnx_path), load_external_data=True)
    onnx.save(loaded_model, str(onnx_path), save_as_external_data=False)

    data_file = onnx_path.with_name(onnx_path.name + ".data")
    if data_file.exists():
        data_file.unlink()

    # Cryptographic SHA-256 hash over raw ONNX bytes
    with open(onnx_path, "rb") as f:
        artifact_hash = hashlib.sha256(f.read()).hexdigest()

    return onnx_path, artifact_hash
