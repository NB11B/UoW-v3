"""Causal LoRA SVD ablation / reconstruction. No training and no UoW authority writes."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import torch

def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def adapter_factors(module):
    """Read an activated PEFT LoRA layer with one named adapter."""
    if not hasattr(module, "lora_A") or not hasattr(module, "lora_B"):
        raise TypeError("Not a PEFT LoRA projection")
    names = set(module.lora_A.keys()) & set(module.lora_B.keys())
    if len(names) != 1:
        raise ValueError(f"Expected one adapter per projection, found {sorted(names)}")
    key = next(iter(names))
    A = module.lora_A[key].weight
    B = module.lora_B[key].weight
    scale = module.scaling[key]
    return key, A, B, scale

@torch.no_grad()
def svd_spectrum(A: torch.Tensor, B: torch.Tensor, scale: float):
    delta = (B.float() @ A.float()) * float(scale)
    s = torch.linalg.svdvals(delta)
    energy = s.square()
    total = energy.sum().clamp_min(1e-30)
    return {"frobenius_norm": float(torch.linalg.vector_norm(delta)),
            "top1_energy": float(energy[0] / total),
            "top2_energy": float(energy[:2].sum() / total),
            "effective_rank": int((s > 1e-5 * s[0]).sum().item()) if float(s[0]) > 0 else 0}

@torch.no_grad()
def truncate_factors(A: torch.Tensor, B: torch.Tensor, k: int):
    """Factorize rank-k approximation of BA, preserving PEFT alpha/r scaling."""
    if A.ndim != 2 or B.ndim != 2 or B.shape[1] != A.shape[0]:
        raise ValueError("Incompatible LoRA factor shapes")
    rank = A.shape[0]
    if not 0 <= k <= rank:
        raise ValueError("Rank outside LoRA adapter dimensions")
    outA = torch.zeros_like(A)
    outB = torch.zeros_like(B)
    if k:
        # Work in float32 to avoid half precision SVD instability.
        product = B.float() @ A.float()
        U, S, Vh = torch.linalg.svd(product, full_matrices=False)
        root = S[:k].clamp_min(0).sqrt()
        outB[:, :k] = (U[:, :k] * root[None, :]).to(B.dtype)
        outA[:k, :] = (root[:, None] * Vh[:k, :]).to(A.dtype)
    return outA, outB

@torch.no_grad()
def apply_rank(model, k: int, layers: set[int] | None = None):
    """Mutate LoRA factors in a newly loaded model. Never call twice on same model."""
    modified = []
    for name, module in model.named_modules():
        if not (name.endswith("q_proj") or name.endswith("v_proj")):
            continue
        if not hasattr(module, "lora_A"):
            continue
        prefix = name.split(".")
        if "layers" not in prefix:
            raise ValueError("Cannot identify layer index for " + name)
        i = int(prefix[prefix.index("layers") + 1])
        key, A, B, scale = adapter_factors(module)
        if layers is not None and i not in layers:
            continue
        aa, bb = truncate_factors(A, B, k)
        A.copy_(aa)
        B.copy_(bb)
        modified.append(name)
    if not modified:
        raise RuntimeError("No LoRA modules changed")
    return modified

def load_adapter(base_model: str, revision: str, adapter_dir: str, device: str):
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel
    tokenizer = AutoTokenizer.from_pretrained(base_model, revision=revision, trust_remote_code=False)
    base = AutoModelForCausalLM.from_pretrained(base_model, revision=revision, trust_remote_code=False)
    model = PeftModel.from_pretrained(base, adapter_dir, is_trainable=False)
    model.eval().to(device)
    for p in model.parameters():
        p.requires_grad_(False)
    return tokenizer, model

def run(args):
    path = Path(args.adapter_dir)
    weights = path / "adapter_model.safetensors"
    config = path / "adapter_config.json"
    if not weights.exists() or not config.exists():
        raise FileNotFoundError("H3 adapter weight/config missing. No results generated.")
    found = sha256(weights)
    if found != args.expected_sha256.lower():
        raise ValueError("H3 adapter hash mismatch: " + found)
    rev = args.revision
    if len(rev) != 40 or any(c not in "0123456789abcdef" for c in rev.lower()):
        raise ValueError("Revision must be a pinned 40-character hexadecimal commit")
    tokenizer, model = load_adapter(args.base_model, rev, str(path), args.device)
    entries = []
    for name, module in model.named_modules():
        if name.endswith(("q_proj", "v_proj")) and hasattr(module, "lora_A"):
            key, A, B, scale = adapter_factors(module)
            entries.append({"projection": name, **svd_spectrum(A, B, scale)})
    if len(entries) != 60:
        raise ValueError(f"Expected 60 LoRA projections, observed {len(entries)}")
    if args.rank is not None:
        apply_rank(model, args.rank)
    # Optional evaluation is intentionally separate: require the original H3
    # evaluator rather than inventing semantic disposition parsing rules.
    report = {"campaign": "UOW-NATIVE-3", "gate": "C0-spectral / C1-reconstruction",
              "model": args.base_model, "revision": rev, "adapter_sha256": found,
              "adapter_config_sha256": sha256(config), "rank": args.rank,
              "projections": entries,
              "behavioral_reproduction": "NOT_RUN: original H3 evaluator and 20 holdout cases required",
              "causal_claim": "NONE: spectrum alone is not behavioral attribution"}
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(f"Spectral report written: {destination}; {len(entries)} projections")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter-dir", required=True)
    parser.add_argument("--expected-sha256", default="64d77db036472c86403a1d98490526fc5412d56e8c1640a47fd9eeed5f92ad6a")
    parser.add_argument("--base-model", default="HuggingFaceTB/SmolLM2-135M-Instruct")
    parser.add_argument("--revision", default="12fd25f77366fa6b3b4b768ec3050bf629380bac")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--rank", type=int, choices=(0, 1, 2, 4, 8))
    parser.add_argument("--output", default="artifacts/uow_native_3/spectral_report.json")
    run(parser.parse_args())

if __name__ == "__main__":
    main()
