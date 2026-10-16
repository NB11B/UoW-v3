"""Causal LoRA SVD Rank-Truncation Benchmark for Gate M4.

Tests whether dominant singular directions of trained adapters causally preserve
task competence (JSON validity and exact semantic match) under rank-1, rank-2, rank-4,
and full rank-8 reconstructions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any, Dict, List

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from experiments.uow_magazine_1.datasets.schemas import JsonCodec

FOUNDATION = "HuggingFaceTB/SmolLM2-135M-Instruct"
TEST_ADAPTERS = [
    "industrial.operational",
    "cybersecurity.temporal",
    "logistics.recovery",
]
RANKS_TO_EVALUATE = [1, 2, 4, 8]


def truncate_factors(A: torch.Tensor, B: torch.Tensor, k: int) -> tuple[torch.Tensor, torch.Tensor]:
    """Factorize rank-k approximation of BA, preserving PEFT alpha/r scaling."""
    if A.ndim != 2 or B.ndim != 2 or B.shape[1] != A.shape[0]:
        raise ValueError("Incompatible LoRA factor shapes")
    rank = A.shape[0]
    if not 0 <= k <= rank:
        raise ValueError("Rank outside LoRA adapter dimensions")
    outA = torch.zeros_like(A)
    outB = torch.zeros_like(B)
    if k:
        product = B.float() @ A.float()
        U, S, Vh = torch.linalg.svd(product, full_matrices=False)
        root = S[:k].clamp_min(0).sqrt()
        outB[:, :k] = (U[:, :k] * root[None, :]).to(B.dtype)
        outA[:k, :] = (root[:, None] * Vh[:k, :]).to(A.dtype)
    return outA, outB


def apply_rank_truncation(model: PeftModel, k: int) -> int:
    """Mutates LoRA factors in PEFT model to rank-k approximation."""
    modified_count = 0
    with torch.no_grad():
        for name, module in model.named_modules():
            if not (hasattr(module, "lora_A") and hasattr(module, "lora_B")):
                continue
            for key in module.lora_A.keys():
                A = module.lora_A[key].weight
                B = module.lora_B[key].weight
                trunc_A, trunc_B = truncate_factors(A, B, k)
                A.copy_(trunc_A)
                B.copy_(trunc_B)
                modified_count += 1
    return modified_count


def evaluate_adapter_at_rank(
    base_model_name: str,
    adapter_dir: Path,
    holdout_file: Path,
    k: int,
    device: str = "cuda",
) -> dict[str, Any]:
    tokenizer = AutoTokenizer.from_pretrained(base_model_name, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id or 0

    base = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        trust_remote_code=True,
        torch_dtype=torch.float32,
    )
    model = PeftModel.from_pretrained(base, str(adapter_dir), is_trainable=False)
    model.eval().to(device)

    # Apply rank truncation if k < 8
    if k < 8:
        apply_rank_truncation(model, k)

    holdout_data = json.loads(holdout_file.read_text(encoding="utf-8"))[:10]
    valid_json_count = 0
    exact_match_count = 0
    semantic_match_count = 0

    with torch.no_grad():
        for item in holdout_data:
            prompt = item["formatted_prompt"]
            target_dict = item["target_dict"]
            inputs = tokenizer(prompt, return_tensors="pt").to(device)

            out_tokens = model.generate(
                **inputs,
                max_new_tokens=140,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
            gen_text = tokenizer.decode(out_tokens[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
            parsed = JsonCodec.extract_json(gen_text)
            if parsed is not None:
                valid_json_count += 1
                if parsed == target_dict:
                    exact_match_count += 1
                
                # Semantic match criteria matching Gate M1
                grammar = holdout_file.parent.name.split(".")[1]
                matched = False
                if grammar == "operational":
                    if parsed.get("disposition") == target_dict.get("disposition") and parsed.get("action") == target_dict.get("action"):
                        matched = True
                elif grammar == "temporal":
                    if parsed.get("relation") == target_dict.get("relation") and parsed.get("target_action") == target_dict.get("target_action"):
                        matched = True
                elif grammar == "recovery":
                    if parsed.get("strategy") == target_dict.get("strategy"):
                        matched = True
                if matched:
                    semantic_match_count += 1

    del model
    del base
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return {
        "rank": k,
        "valid_json_rate": round(valid_json_count / len(holdout_data) * 100.0, 2),
        "semantic_match_rate": round(semantic_match_count / len(holdout_data) * 100.0, 2),
        "exact_dict_match_rate": round(exact_match_count / len(holdout_data) * 100.0, 2),
        "samples_evaluated": len(holdout_data),
    }


def run_causal_truncation_benchmark(
    checkpoints_dir: str = "checkpoints/uow_magazine_1",
    corpora_dir: str = "artifacts/uow_magazine_1/corpora",
    device: str = "cuda",
) -> dict[str, Any]:
    print("\n========================================================")
    print("Executing Gate M4: Causal LoRA Rank-Truncation Benchmark")
    print("========================================================")

    checkpoints_path = Path(checkpoints_dir)
    corpora_path = Path(corpora_dir)

    results = {}
    for ad_name in TEST_ADAPTERS:
        ad_dir = checkpoints_path / ad_name
        holdout_file = corpora_path / ad_name / "holdout.json"
        if not ad_dir.exists() or not holdout_file.exists():
            print(f"Skipping {ad_name} (missing files)")
            continue

        print(f"\n--- Testing Adapter: {ad_name} ---")
        ad_results = {}
        for k in RANKS_TO_EVALUATE:
            res = evaluate_adapter_at_rank(FOUNDATION, ad_dir, holdout_file, k, device=device)
            ad_results[f"rank_{k}"] = res
            print(f"Rank-{k:02d} | Valid JSON: {res['valid_json_rate']}% | Semantic: {res['semantic_match_rate']}% | Dict Match: {res['exact_dict_match_rate']}%", flush=True)

        results[ad_name] = ad_results

    out_file = Path("artifacts/uow_magazine_1/m4_causal_truncation.json")
    out_file.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"\nSaved causal truncation benchmark to {out_file}", flush=True)
    return results


if __name__ == "__main__":
    res = run_causal_truncation_benchmark()
    print(json.dumps(res, indent=2))
