"""Model training and supervision derived from certified observations (Gate U15.5)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence, Tuple
import numpy as np
import torch
import torch.nn as nn

from uow.compat.v2 import AdaptationObservation
from .features import CandidateFeatureEncoder
from .model import UoWSchedulingNet, export_and_hash_onnx


def extract_training_samples(
    observations: Sequence[AdaptationObservation],
    encoder: CandidateFeatureEncoder,
    graph: Mapping[str, Any],
) -> Tuple[np.ndarray, np.ndarray]:
    """Derives feature vectors and authoritative supervision labels from certified feedback."""
    x_samples: List[np.ndarray] = []
    y_samples: List[float] = []

    for obs in observations:
        # Accepted tasks provide positive supervision
        for task_id in obs.accepted_tasks:
            if task_id in graph:
                vec = encoder.encode(task_id, graph, None)  # type: ignore[arg-type]
                x_samples.append(vec)
                y_samples.append(2.0)

        # Rejected tasks provide negative supervision
        for task_id, reason in obs.rejected_tasks.items():
            if task_id in graph:
                vec = encoder.encode(task_id, graph, None)  # type: ignore[arg-type]
                x_samples.append(vec)
                penalty = -2.0
                if "RESOURCE_CAPACITY_EXCEEDED" in reason:
                    penalty = -3.0
                elif "OCC" in reason:
                    penalty = -2.5
                y_samples.append(penalty)

    if not x_samples:
        return np.empty((0, encoder.feature_dim), dtype=np.float32), np.empty((0, 1), dtype=np.float32)

    X = np.stack(x_samples, axis=0).astype(np.float32)
    y = np.array(y_samples, dtype=np.float32).reshape(-1, 1)
    return X, y


def train_surrogate_model(
    model: UoWSchedulingNet,
    X: np.ndarray,
    y: np.ndarray,
    epochs: int = 100,
    lr: float = 1e-3,
    device: Optional[str] = None,
) -> float:
    """Optimizes neural weights using GPU if available, else CPU."""
    if len(X) == 0:
        return 0.0

    target_device = (
        torch.device(device)
        if device
        else torch.device("cuda" if torch.cuda.is_available() else "cpu")
    )
    model.to(target_device).train()

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    X_t = torch.tensor(X, dtype=torch.float32, device=target_device)
    y_t = torch.tensor(y, dtype=torch.float32, device=target_device)

    final_loss = 0.0
    for _ in range(epochs):
        optimizer.zero_grad()
        pred = model(X_t)
        loss = criterion(pred, y_t)
        loss.backward()
        optimizer.step()
        final_loss = float(loss.item())

    model.cpu().eval()
    return final_loss
