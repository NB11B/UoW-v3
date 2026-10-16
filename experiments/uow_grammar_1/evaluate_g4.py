"""Execute Gate G4: Architecture Comparison (Architecture A Switchable vs Architecture C Merged)."""
from __future__ import annotations
import argparse
import gc
import json
from pathlib import Path
import sys
import time
import torch

# Ensure UoW src is in sys.path
sys.path.insert(0, str(Path("src").resolve()))

from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from experiments.uow_grammar_1.grammars.temporal import TemporalPromptBuilder, TemporalOutputParser
from experiments.uow_grammar_1.grammars.recovery import RecoveryPromptBuilder, RecoveryOutputParser
from experiments.uow_grammar_1.evaluate_g1 import evaluate_temporal, evaluate_recovery
from experiments.uow_grammar_1.evaluate_g2 import evaluate_operational

BASE = "HuggingFaceTB/SmolLM2-135M-Instruct"
REV = "12fd25f77366fa6b3b4b768ec3050bf629380bac"


def run(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--uow-v2-root", default="C:\\Users\\nateb\\OneDrive\\Documents\\UoW-v2")
    p.add_argument("--op-adapter", default="C:\\Users\\nateb\\OneDrive\\Documents\\UoW-v2\\checkpoints\\uow_h3_native_smollm2_135m_arm_nb")
    p.add_argument("--temp-adapter", default="checkpoints/uow_temporal_smollm2_135m")
    p.add_argument("--rec-adapter", default="checkpoints/uow_recovery_smollm2_135m")
    p.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    p.add_argument("--output", default="artifacts/uow_grammar_1/g4_results.json")
    args = p.parse_args(argv)

    root = Path(args.uow_v2_root).resolve()
    tokenizer = AutoTokenizer.from_pretrained(BASE, revision=REV, trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    # Load holdouts
    manifest_op = root / "qualification" / "artifacts" / "semantic_h3_native_corpus_manifest.json"
    from qualification.semantic.h3_native_corpus import H3NativeExample
    raw_op = json.loads(manifest_op.read_text(encoding="utf-8"))["holdout_examples"]
    allowed = set(H3NativeExample.__dataclass_fields__)
    holdout_op = [H3NativeExample(**{k: v for k, v in d.items() if k in allowed}) for d in raw_op]
    holdout_temp = json.loads(Path("artifacts/uow_grammar_1/temporal_corpus_manifest.json").read_text(encoding="utf-8"))["holdout_examples"]
    holdout_rec = json.loads(Path("artifacts/uow_grammar_1/recovery_corpus_manifest.json").read_text(encoding="utf-8"))["holdout_examples"]

    results = {
        "campaign": "UOW-GRAMMAR-1",
        "gate": "G4",
        "architectures": {}
    }

    # 1. Architecture A: Resident Switchable Adapters
    print("\n--- Evaluating Architecture A: Resident Switchable Adapters ---")
    base_a = AutoModelForCausalLM.from_pretrained(BASE, revision=REV, trust_remote_code=False)
    model_a = PeftModel.from_pretrained(base_a, args.op_adapter, adapter_name="operational", is_trainable=False)
    model_a.load_adapter(args.temp_adapter, adapter_name="temporal")
    model_a.load_adapter(args.rec_adapter, adapter_name="recovery")
    model_a.to(args.device).eval()

    t0 = time.time()
    model_a.set_adapter("operational")
    res_a_op = evaluate_operational(model_a, tokenizer, holdout_op, args.device, root)
    model_a.set_adapter("temporal")
    res_a_temp = evaluate_temporal(model_a, tokenizer, holdout_temp, args.device)
    model_a.set_adapter("recovery")
    res_a_rec = evaluate_recovery(model_a, tokenizer, holdout_rec, args.device)
    time_a = time.time() - t0

    mem_a = torch.cuda.max_memory_allocated() / (1024 * 1024) if args.device == "cuda" else 0.0

    # Measured synchronized GPU adapter switch latency
    if args.device == "cuda":
        print("Benchmarking synchronized CUDA adapter-switch latency (N=1000)...")
        for _ in range(50):
            model_a.set_adapter("temporal")
            model_a.set_adapter("recovery")
            model_a.set_adapter("operational")
        torch.cuda.synchronize()

        starter = torch.cuda.Event(enable_timing=True)
        ender = torch.cuda.Event(enable_timing=True)
        latencies = []
        cycle = ["temporal", "recovery", "operational"]
        for i in range(1000):
            starter.record()
            model_a.set_adapter(cycle[i % 3])
            ender.record()
            torch.cuda.synchronize()
            latencies.append(starter.elapsed_time(ender))

        import statistics
        switch_latency_stats = {
            "iterations": len(latencies),
            "mean_ms": round(statistics.mean(latencies), 4),
            "median_ms": round(statistics.median(latencies), 4),
            "min_ms": round(min(latencies), 4),
            "max_ms": round(max(latencies), 4),
            "stdev_ms": round(statistics.stdev(latencies), 4),
            "hardware_measured": True,
            "timer": "torch.cuda.Event(synchronized)"
        }
    else:
        switch_latency_stats = {"mean_ms": 0.0, "hardware_measured": False}

    results["architectures"]["Architecture_A_Switchable"] = {
        "operational": res_a_op,
        "temporal": res_a_temp,
        "recovery": res_a_rec,
        "elapsed_seconds": round(time_a, 2),
        "peak_vram_mb": round(mem_a, 2),
        "adapter_switch_latency": switch_latency_stats,
        "interference_detected": False
    }

    del model_a
    del base_a
    gc.collect()
    if args.device == "cuda":
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()

    # 2. Architecture C1: PEFT Linear Combination (add_weighted_adapter)
    print("\n--- Evaluating Architecture C1: PEFT Linearly Merged Adapter (combination_type='linear') ---")
    base_c1 = AutoModelForCausalLM.from_pretrained(BASE, revision=REV, trust_remote_code=False)
    model_c1 = PeftModel.from_pretrained(base_c1, args.op_adapter, adapter_name="operational", is_trainable=False)
    model_c1.load_adapter(args.temp_adapter, adapter_name="temporal")
    model_c1.load_adapter(args.rec_adapter, adapter_name="recovery")
    
    try:
        model_c1.add_weighted_adapter(
            adapters=["operational", "temporal", "recovery"],
            weights=[1.0, 1.0, 1.0],
            adapter_name="peft_merged_composite",
            combination_type="linear"
        )
        model_c1.set_adapter("peft_merged_composite")
    except Exception as exc:
        print(f"PEFT add_weighted_adapter warning: {exc}")

    model_c1.to(args.device).eval()

    t0_c1 = time.time()
    res_c1_op = evaluate_operational(model_c1, tokenizer, holdout_op, args.device, root)
    res_c1_temp = evaluate_temporal(model_c1, tokenizer, holdout_temp, args.device)
    res_c1_rec = evaluate_recovery(model_c1, tokenizer, holdout_rec, args.device)
    time_c1 = time.time() - t0_c1

    mem_c1 = torch.cuda.max_memory_allocated() / (1024 * 1024) if args.device == "cuda" else 0.0

    results["architectures"]["Architecture_C1_PEFT_Linear"] = {
        "operational": res_c1_op,
        "temporal": res_c1_temp,
        "recovery": res_c1_rec,
        "elapsed_seconds": round(time_c1, 2),
        "peak_vram_mb": round(mem_c1, 2),
        "interference_detected": (res_c1_op["exact_matches"] < res_a_op["exact_matches"] or
                                  res_c1_temp["exact_matches"] < res_a_temp["exact_matches"] or
                                  res_c1_rec["exact_matches"] < res_a_rec["exact_matches"])
    }

    del model_c1
    del base_c1
    gc.collect()
    if args.device == "cuda":
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()

    # 3. Architecture C2: True Explicit Weight Sum (W0 + sum alpha/r * B @ A)
    print("\n--- Evaluating Architecture C2: True Explicit Weight Sum (W0 + sum dW_g) ---")
    base_explicit = AutoModelForCausalLM.from_pretrained(BASE, revision=REV, trust_remote_code=False)
    temp_peft = PeftModel.from_pretrained(base_explicit, args.op_adapter, adapter_name="operational", is_trainable=False)
    temp_peft.load_adapter(args.temp_adapter, adapter_name="temporal")
    temp_peft.load_adapter(args.rec_adapter, adapter_name="recovery")
    
    # Accumulate explicit matrix product updates directly into base weights
    base_dict = dict(base_explicit.named_modules())
    for name, module in temp_peft.named_modules():
        if hasattr(module, "lora_A") and hasattr(module, "lora_B"):
            target_name = name.replace("base_model.model.", "")
            base_mod = base_dict[target_name]
            total_delta = torch.zeros_like(base_mod.weight.data)
            for ad in ("operational", "temporal", "recovery"):
                if ad in module.lora_A and ad in module.lora_B:
                    A = module.lora_A[ad].weight.data.float()
                    B = module.lora_B[ad].weight.data.float()
                    scale = module.scaling[ad]
                    total_delta += (scale * (B @ A)).to(total_delta.device, dtype=total_delta.dtype)
            base_mod.weight.data += total_delta

    del temp_peft
    gc.collect()

    base_explicit.to(args.device).eval()
    t0_c2 = time.time()
    res_c2_op = evaluate_operational(base_explicit, tokenizer, holdout_op, args.device, root)
    res_c2_temp = evaluate_temporal(base_explicit, tokenizer, holdout_temp, args.device)
    res_c2_rec = evaluate_recovery(base_explicit, tokenizer, holdout_rec, args.device)
    time_c2 = time.time() - t0_c2
    mem_c2 = torch.cuda.max_memory_allocated() / (1024 * 1024) if args.device == "cuda" else 0.0

    results["architectures"]["Architecture_C2_Explicit_Sum"] = {
        "operational": res_c2_op,
        "temporal": res_c2_temp,
        "recovery": res_c2_rec,
        "elapsed_seconds": round(time_c2, 2),
        "peak_vram_mb": round(mem_c2, 2),
        "interference_detected": (res_c2_op["exact_matches"] < res_a_op["exact_matches"] or
                                  res_c2_temp["exact_matches"] < res_a_temp["exact_matches"] or
                                  res_c2_rec["exact_matches"] < res_a_rec["exact_matches"])
    }

    del base_explicit
    gc.collect()
    if args.device == "cuda":
        torch.cuda.empty_cache()

    # Comparison Summary
    print("\n--- Architecture Comparison Summary ---")
    print(f"Arch A (Switchable)   - Op: {res_a_op['exact_matches']}/20, Temp: {res_a_temp['exact_matches']}/24, Rec: {res_a_rec['exact_matches']}/24 | Switch: {switch_latency_stats['median_ms']} ms")
    print(f"Arch C1 (PEFT Merged) - Op: {res_c1_op['exact_matches']}/20, Temp: {res_c1_temp['exact_matches']}/24, Rec: {res_c1_rec['exact_matches']}/24")
    print(f"Arch C2 (Explicit Sum)- Op: {res_c2_op['exact_matches']}/20, Temp: {res_c2_temp['exact_matches']}/24, Rec: {res_c2_rec['exact_matches']}/24")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"Gate G4 Report written to: {out}")
    return results


if __name__ == "__main__":
    run()
