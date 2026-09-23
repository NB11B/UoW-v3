"""OpenVINO Intel NPU integration package for canonical UoW adaptive proposers (Gate U15.5)."""
from .adapter import IntelNPUAdaptiveProposer
from .features import CandidateFeatureEncoder, FEATURE_DIM
from .model import UoWSchedulingNet, export_and_hash_onnx
from .training import extract_training_samples, train_surrogate_model

__all__ = [
    "CandidateFeatureEncoder",
    "FEATURE_DIM",
    "IntelNPUAdaptiveProposer",
    "UoWSchedulingNet",
    "export_and_hash_onnx",
    "extract_training_samples",
    "train_surrogate_model",
]
