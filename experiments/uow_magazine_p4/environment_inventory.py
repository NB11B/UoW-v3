"""Environment Inventory and Immutable Candidate Pinning for Milestone P4."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict

import torch


def get_git_info() -> dict[str, str]:
    try:
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        is_dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())
        return {"branch": branch, "commit": commit, "dirty": str(is_dirty)}
    except Exception as e:
        return {"error": str(e)}


def hash_file(path: Path) -> str:
    if not path.exists():
        return "FILE_NOT_FOUND"
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def collect_adapter_hashes(checkpoints_base: Path = Path("checkpoints/uow_magazine_p3")) -> dict[str, Any]:
    candidates = ["cerebras_111m", "smollm2_135m"]
    grammars = ["shared.operational", "shared.temporal", "shared.recovery"]
    manifests: dict[str, Any] = {}

    for cand in candidates:
        manifests[cand] = {}
        for g in grammars:
            ad_dir = checkpoints_base / cand / g
            weight_file = ad_dir / "adapter_model.safetensors"
            config_file = ad_dir / "adapter_config.json"
            manifests[cand][g] = {
                "adapter_dir": str(ad_dir),
                "weights_sha256": hash_file(weight_file),
                "config_sha256": hash_file(config_file),
                "weight_size_bytes": weight_file.stat().st_size if weight_file.exists() else 0,
            }
    return manifests


def capture_environment(output_path: Path = Path("artifacts/uow_magazine_p4/environment.json")) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "None"
    cuda_ver = torch.version.cuda if torch.cuda.is_available() else "None"

    # Optional packages
    onnx_ver = "None"
    ort_ver = "None"
    try:
        import onnx
        onnx_ver = onnx.__version__
    except ImportError:
        pass
    try:
        import onnxruntime
        ort_ver = onnxruntime.__version__
    except ImportError:
        pass

    import transformers
    import peft

    env_data: dict[str, Any] = {
        "timestamp": time.time(),
        "date_iso": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "python": {
            "version": sys.version,
            "executable": sys.executable,
        },
        "git": get_git_info(),
        "runtime_libraries": {
            "torch": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_version": cuda_ver,
            "gpu_device": gpu_name,
            "transformers": transformers.__version__,
            "peft": peft.__version__,
            "onnx": onnx_ver,
            "onnxruntime": ort_ver,
        },
        "frozen_candidates": {
            "cerebras_111m": {
                "model_id": "cerebras-archive/Cerebras-GPT-111M",
                "pinned_revision": "b927d75e656e18f2d593fa883d6a5c1bbd9c1598",
                "role": "Efficiency candidate",
                "base_parameters": 111296256,
                "adapters": collect_adapter_hashes()["cerebras_111m"],
            },
            "smollm2_135m": {
                "model_id": "HuggingFaceTB/SmolLM2-135M-Instruct",
                "pinned_revision": "12fd25f773448f4305bc851493b8cae6d15a5f1e",
                "role": "Behavioral reference",
                "base_parameters": 134516736,
                "adapters": collect_adapter_hashes()["smollm2_135m"],
            },
        },
        "archived_controls": {
            "gpt_neo_125m": "EleutherAI/gpt-neo-125m",
            "pythia_160m": "EleutherAI/pythia-160m",
            "mamba_130m": "state-spaces/mamba-130m-hf (DISQUALIFIED_EDGE_AUTOGRAD_OOM)",
        },
    }

    output_path.write_text(json.dumps(env_data, indent=2), encoding="utf-8")
    print(f"Environment inventory written to: {output_path}")
    return env_data


if __name__ == "__main__":
    capture_environment()
