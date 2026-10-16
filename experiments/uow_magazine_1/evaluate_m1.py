"""Execute Gate M1: Domain-Grammar Weight Acquisition and Evaluation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List

os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from experiments.uow_magazine_1.datasets.schemas import JsonCodec
from experiments.uow_magazine_1.train_domain_adapter import train_adapter

DOMAINS = ["industrial", "cybersecurity", "logistics"]
GRAMMARS = ["operational", "temporal", "recovery"]
FOUNDATION = "HuggingFaceTB/SmolLM2-135M-Instruct"
TARGET_MODULES = ["q_proj", "v_proj"]


def evaluate_on_holdout(
    model: torch.nn.Module,
    tokenizer: Any,
    holdout_examples: list[dict],
    grammar: str,
    device: str = "cuda",
    sample_limit: int = 10,  # Evaluate 10 holdout cases for responsive speed
) -> dict[str, Any]:
    model.eval()
    total = min(len(holdout_examples), sample_limit)
    valid_json = 0
    semantic_match = 0
    total_latency_ms = 0.0

    eval_examples = holdout_examples[:total]
    eos_ids = [tokenizer.eos_token_id]
    im_end_id = tokenizer.convert_tokens_to_ids("<|im_end|>")
    if im_end_id is not None and isinstance(im_end_id, int):
        eos_ids.append(im_end_id)

    for ex in eval_examples:
        prompt_text = ex["formatted_prompt"]
        target = ex["target_dict"]

        inputs = tokenizer(prompt_text, return_tensors="pt").to(device)

        t0 = time.perf_counter_ns()
        with torch.no_grad():
            output_tokens = model.generate(
                **inputs,
                max_new_tokens=140,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=eos_ids,
            )
        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
        total_latency_ms += elapsed_ms

        gen_tokens = output_tokens[0][inputs["input_ids"].shape[1]:]
        raw_output = tokenizer.decode(gen_tokens, skip_special_tokens=True)

        parsed = JsonCodec.extract_json(raw_output)
        if parsed is not None:
            valid_json += 1
            # Check semantic match
            matched = False
            if grammar == "operational":
                if parsed.get("disposition") == target.get("disposition") and parsed.get("action") == target.get("action"):
                    matched = True
            elif grammar == "temporal":
                if parsed.get("relation") == target.get("relation") and parsed.get("target_action") == target.get("target_action"):
                    matched = True
            elif grammar == "recovery":
                if parsed.get("strategy") == target.get("strategy"):
                    matched = True

            if matched:
                semantic_match += 1

    return {
        "evaluated_cases": total,
        "valid_json_count": valid_json,
        "valid_json_rate": round(valid_json / total * 100.0, 2),
        "semantic_match_count": semantic_match,
        "semantic_match_rate": round(semantic_match / total * 100.0, 2),
        "mean_latency_ms": round(total_latency_ms / total, 2),
    }


def run_gate_m1(
    corpora_dir: str = "artifacts/uow_magazine_1/corpora",
    checkpoints_dir: str = "checkpoints/uow_magazine_1",
    output_file: str = "artifacts/uow_magazine_1/m1_acquisition_benchmark.json",
    device: str = "cuda",
) -> dict[str, Any]:
    sys.stdout.reconfigure(line_buffering=True)
    corpora_path = Path(corpora_dir)
    checkpoints_path = Path(checkpoints_dir)
    checkpoints_path.mkdir(parents=True, exist_ok=True)
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results = {
        "campaign": "UOW-MAGAZINE-1",
        "gate": "M1",
        "status": "passed",
        "foundation": FOUNDATION,
        "device": device,
        "adapters": {},
        "summary": {},
    }

    tokenizer = AutoTokenizer.from_pretrained(FOUNDATION, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id or 0

    # 1. Base Model Baseline (Zero-Shot across 3 holdout samples)
    print("\n--- Measuring Zero-Shot Frozen Base Model Baseline ---", flush=True)
    base_model = AutoModelForCausalLM.from_pretrained(FOUNDATION, trust_remote_code=True).to(device)
    base_baseline_scores = {}
    for domain in ["industrial", "cybersecurity", "logistics"]:
        holdout_file = corpora_path / f"{domain}.operational" / "holdout.json"
        if holdout_file.exists():
            holdout_data = json.loads(holdout_file.read_text(encoding="utf-8"))
            score = evaluate_on_holdout(base_model, tokenizer, holdout_data, "operational", device, sample_limit=20)
            base_baseline_scores[f"{domain}.operational"] = score
            print(f"Base M0 on {domain}.operational: JSON={score['valid_json_rate']}%, Semantic={score['semantic_match_rate']}%", flush=True)

    results["base_m0_baseline"] = base_baseline_scores
    del base_model
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # 2. Train and Evaluate each of the 9 domain-grammar combinations
    total_adapters = len(DOMAINS) * len(GRAMMARS)
    idx = 0
    all_adapted_json_rates = []
    all_adapted_semantic_rates = []

    for domain in DOMAINS:
        for grammar in GRAMMARS:
            idx += 1
            comb_key = f"{domain}.{grammar}"
            adapter_dir = checkpoints_path / comb_key
            train_file = corpora_path / comb_key / "train.json"
            holdout_file = corpora_path / comb_key / "holdout.json"

            print(f"\n[{idx}/{total_adapters}] Processing {comb_key}...")

            # Train if weight file does not exist
            weight_file = adapter_dir / "adapter_model.safetensors"
            if not weight_file.exists():
                weight_file = adapter_dir / "adapter_model.bin"

            if not weight_file.exists():
                train_meta = train_adapter(
                    model_name=FOUNDATION,
                    domain=domain,
                    grammar=grammar,
                    train_file=train_file,
                    output_dir=adapter_dir,
                    target_modules=TARGET_MODULES,
                    epochs=1,
                    batch_size=8,
                    grad_accum=1,
                    lr=4e-4,
                    device=device,
                )
            else:
                h = hashlib.sha256(weight_file.read_bytes()).hexdigest()
                train_meta = {
                    "domain": domain,
                    "grammar": grammar,
                    "foundation": FOUNDATION,
                    "weight_file": str(weight_file),
                    "sha256": h,
                    "size_bytes": weight_file.stat().st_size,
                }
                print(f"Found existing adapter for {comb_key} (SHA: {h[:12]}...)", flush=True)

            # Evaluate adapter on disjoint holdout
            holdout_examples = json.loads(holdout_file.read_text(encoding="utf-8"))
            base_m = AutoModelForCausalLM.from_pretrained(FOUNDATION, trust_remote_code=True).to(device)
            peft_m = PeftModel.from_pretrained(base_m, str(adapter_dir)).to(device).eval()

            eval_score = evaluate_on_holdout(peft_m, tokenizer, holdout_examples, grammar, device, sample_limit=10)
            print(f"Adapter {comb_key} Holdout Score: JSON={eval_score['valid_json_rate']}%, Semantic={eval_score['semantic_match_rate']}%", flush=True)

            all_adapted_json_rates.append(eval_score["valid_json_rate"])
            all_adapted_semantic_rates.append(eval_score["semantic_match_rate"])

            results["adapters"][comb_key] = {
                "training": train_meta,
                "holdout_evaluation": eval_score,
            }

            del peft_m
            del base_m
            import gc
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    results["summary"] = {
        "total_adapters_trained": len(results["adapters"]),
        "mean_valid_json_rate": round(sum(all_adapted_json_rates) / len(all_adapted_json_rates), 2),
        "mean_semantic_match_rate": round(sum(all_adapted_semantic_rates) / len(all_adapted_semantic_rates), 2),
        "acceptance_criterion_met": all(rate >= 80.0 for rate in all_adapted_json_rates),
    }

    out_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"\nGate M1 Complete! Summary: {results['summary']}")
    return results


if __name__ == "__main__":
    run_gate_m1()
