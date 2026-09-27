"""H3 Physical Latency Benchmark: Cold vs Warm Inference.

Accurately measures physical inference latency on GPU:
1. T_load: model and LoRA adapter load time into VRAM
2. T_cold: first generation latency immediately after load
3. T_warm: steady-state inference latency over 50 warm iterations for:
   - Single-terminal frontier (|F_P| = 1)
   - Multi-terminal frontier (|F_P| = 3)

Outputs: qualification/artifacts/semantic_h3_physical_latency.json
"""
from __future__ import annotations

import gc
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Dict, List

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(PACKAGE_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT / "src"))
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from uow.semantic.adapters.codec import SemanticOutputParser, SemanticPromptBuilder
from uow.semantic.schema import (
    BindingOrigin,
    ExternalSignal,
    MinimalSemanticContext,
    SemanticBinding,
    SemanticRequirement,
    SemanticTranslationRequest,
)

CHECKPOINT_DIR = PACKAGE_ROOT / "checkpoints" / "uow_h3_native_smollm2_135m"
RESULTS_PATH = PACKAGE_ROOT / "qualification" / "artifacts" / "semantic_h3_physical_latency.json"
BASE_MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"
BASE_REVISION = "12fd25f77366fa6b3b4b768ec3050bf629380bac"


def run_latency_benchmark(device: str = "cuda", warm_iterations: int = 50) -> dict[str, Any]:
    print(f"=== H3 Physical Latency Benchmark on {device} ({warm_iterations} warm iterations) ===")

    # 1. Measure T_load
    t_load_start = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID, revision=BASE_REVISION)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID,
        revision=BASE_REVISION,
        dtype=torch.float16 if device == "cuda" else torch.float32,
        device_map=device,
    )
    model = PeftModel.from_pretrained(base_model, str(CHECKPOINT_DIR))
    model.eval()
    if device == "cuda":
        torch.cuda.synchronize()
    t_load_ms = (time.perf_counter() - t_load_start) * 1000.0
    print(f"T_load: {t_load_ms:.2f} ms ({t_load_ms/1000.0:.2f}s)")

    prompt_builder = SemanticPromptBuilder()
    output_parser = SemanticOutputParser()

    # Define test requests:
    # Request A: Single-cut |F_P| = 1
    req_fp1 = SemanticTranslationRequest(
        signal=ExternalSignal(raw="Send three batteries to Alice immediately."),
        minimal_context=MinimalSemanticContext(
            state_hash="0" * 64,
            state_sequence=1,
            bindings=(
                SemanticBinding(terminal="operator", value="transfer", origin=BindingOrigin.DETERMINISTIC),
                SemanticBinding(terminal="quantity", value=3, origin=BindingOrigin.DETERMINISTIC),
                SemanticBinding(terminal="temporal", value="IMMEDIATE", origin=BindingOrigin.DETERMINISTIC),
            ),
        ),
        frontier=(SemanticRequirement(name="recipient"),),
    )

    # Request B: Multi-cut |F_P| = 3
    req_fp3 = SemanticTranslationRequest(
        signal=ExternalSignal(raw="Send three batteries to Alice immediately."),
        minimal_context=MinimalSemanticContext(
            state_hash="0" * 64,
            state_sequence=1,
            bindings=(
                SemanticBinding(terminal="operator", value="transfer", origin=BindingOrigin.DETERMINISTIC),
            ),
        ),
        frontier=(
            SemanticRequirement(name="recipient"),
            SemanticRequirement(name="quantity"),
            SemanticRequirement(name="temporal"),
        ),
    )

    def prepare_tokens(req: SemanticTranslationRequest) -> torch.Tensor:
        msgs = prompt_builder.build_chat_messages(req)
        formatted = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        return tokenizer(formatted, return_tensors="pt").to(device)

    inp_fp1 = prepare_tokens(req_fp1)
    inp_fp3 = prepare_tokens(req_fp3)

    # 2. Measure T_cold (first inference on fp1)
    if device == "cuda":
        torch.cuda.synchronize()
    t_cold_start = time.perf_counter()
    with torch.no_grad():
        out_cold = model.generate(
            **inp_fp1,
            max_new_tokens=64,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    if device == "cuda":
        torch.cuda.synchronize()
    t_cold_ms = (time.perf_counter() - t_cold_start) * 1000.0
    cold_text = tokenizer.decode(out_cold[0][inp_fp1["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    print(f"T_cold (|F_P|=1): {t_cold_ms:.2f} ms")
    print(f"  Cold generation snippet: {cold_text[:80]!r}")

    # 3. Measure T_warm on |F_P| = 1
    fp1_latencies_ms: list[float] = []
    for _ in range(warm_iterations):
        if device == "cuda":
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        with torch.no_grad():
            _ = model.generate(
                **inp_fp1,
                max_new_tokens=64,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        if device == "cuda":
            torch.cuda.synchronize()
        fp1_latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    # 4. Measure T_warm on |F_P| = 3
    fp3_latencies_ms: list[float] = []
    for _ in range(warm_iterations):
        if device == "cuda":
            torch.cuda.synchronize()
        t0 = time.perf_counter()
        with torch.no_grad():
            _ = model.generate(
                **inp_fp3,
                max_new_tokens=96,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        if device == "cuda":
            torch.cuda.synchronize()
        fp3_latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    def stats_dict(vals: list[float]) -> dict[str, float]:
        sorted_vals = sorted(vals)
        p95_idx = int(len(sorted_vals) * 0.95)
        p99_idx = int(len(sorted_vals) * 0.99)
        return {
            "mean_ms": round(statistics.mean(vals), 2),
            "median_ms": round(statistics.median(vals), 2),
            "std_dev_ms": round(statistics.stdev(vals), 2) if len(vals) > 1 else 0.0,
            "min_ms": round(min(vals), 2),
            "max_ms": round(max(vals), 2),
            "p95_ms": round(sorted_vals[min(p95_idx, len(sorted_vals) - 1)], 2),
            "p99_ms": round(sorted_vals[min(p99_idx, len(sorted_vals) - 1)], 2),
        }

    stats_fp1 = stats_dict(fp1_latencies_ms)
    stats_fp3 = stats_dict(fp3_latencies_ms)

    benchmark_data = {
        "experiment": "H3-PHYSICAL-LATENCY-BENCHMARK",
        "title": "Cold vs Warm Physical Inference Latency on RTX 5070 GPU",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checkpoint": str(CHECKPOINT_DIR),
        "device": device,
        "warm_iterations": warm_iterations,
        "load_time": {
            "t_load_ms": round(t_load_ms, 2),
            "t_load_seconds": round(t_load_ms / 1000.0, 3),
        },
        "cold_inference": {
            "t_cold_ms": round(t_cold_ms, 2),
            "t_cold_seconds": round(t_cold_ms / 1000.0, 3),
            "output_preview": cold_text,
        },
        "warm_inference": {
            "single_cut_fp1": stats_fp1,
            "multi_cut_fp3": stats_fp3,
        },
        "raw_latencies_ms": {
            "fp1": [round(x, 2) for x in fp1_latencies_ms],
            "fp3": [round(x, 2) for x in fp3_latencies_ms],
        },
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(benchmark_data, indent=2), encoding="utf-8")
    print(f"\nSaved latency benchmark to: {RESULTS_PATH}")
    print(f"|F_P|=1 Warm Mean: {stats_fp1['mean_ms']} ms (median: {stats_fp1['median_ms']} ms, p95: {stats_fp1['p95_ms']} ms)")
    print(f"|F_P|=3 Warm Mean: {stats_fp3['mean_ms']} ms (median: {stats_fp3['median_ms']} ms, p95: {stats_fp3['p95_ms']} ms)")

    del model
    del base_model
    del tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return benchmark_data


if __name__ == "__main__":
    run_latency_benchmark()
