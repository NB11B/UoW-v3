"""H3-N: Causal A/B/A/B Toggle Campaign using Native H3 Prompting.

Performs a 4-step causal toggle across the frozen holdout suite:
    Step 1: Base M_0 (Delta W = 0)
    Step 2: Native LoRA M_H3 (Delta W != 0)
    Step 3: Base M_0 (Delta W = 0)
    Step 4: Native LoRA M_H3 (Delta W != 0)

Verifies:
1. Determinism error == 0.000000 across identical states
2. Pure causal weight attribution (Delta W)
3. Zero deterministic primacy pollution (beta_D == 0)
4. Full fail-closed safety under uncertainty
"""
from __future__ import annotations

import gc
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(PACKAGE_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT / "src"))
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from qualification.semantic.h3_native_corpus import H3NativeExample
from uow.semantic.adapters.codec import SemanticOutputParser, SemanticPromptBuilder
from uow.semantic.closure import SemanticClosureEngine
from uow.semantic.frontier import SemanticFrontierBuilder
from uow.semantic.schema import (
    SemanticFrontierResult,
    SemanticRequirement,
)

MANIFEST_PATH = PACKAGE_ROOT / "qualification" / "artifacts" / "semantic_h3_native_corpus_manifest.json"
RESULTS_PATH = PACKAGE_ROOT / "qualification" / "artifacts" / "semantic_h3_native_toggle_results.json"
WINNER_CHECKPOINT = PACKAGE_ROOT / "checkpoints" / "uow_h3_native_smollm2_135m_arm_nb"

BASE_MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"
BASE_REVISION = "12fd25f77366fa6b3b4b768ec3050bf629380bac"


def run_single_step(
    step_num: int,
    step_name: str,
    adapter_enabled: bool,
    model: Any,
    tokenizer: Any,
    examples: list[H3NativeExample],
    device: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    print(f"\n--- Toggle Step {step_num}: {step_name} (Adapter={adapter_enabled}) ---")

    if adapter_enabled:
        model.enable_adapter_layers()
    else:
        model.disable_adapter_layers()

    prompt_builder = SemanticPromptBuilder()
    output_parser = SemanticOutputParser()
    frontier_builder = SemanticFrontierBuilder()
    closure_engine = SemanticClosureEngine(frontier_builder)

    records: list[dict[str, Any]] = []
    exact_disp_count = 0
    valid_json_count = 0
    unsafe_count = 0
    beta_d_count = 0

    t0 = time.perf_counter()

    for ex in examples:
        req = ex.to_request()
        messages = prompt_builder.build_chat_messages(req)
        prompt_text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = tokenizer(prompt_text, return_tensors="pt").to(device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=128,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
            input_len = inputs["input_ids"].shape[1]
            raw_text = tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True).strip()

        is_valid_json = False
        try:
            parsed_json = json.loads(output_parser.extract_json_text(raw_text))
            if isinstance(parsed_json, dict) and all(k in parsed_json for k in ("bindings", "alternatives", "unknowns")):
                is_valid_json = True
        except Exception:
            is_valid_json = False

        if is_valid_json:
            valid_json_count += 1

        cand_bindings = output_parser.parse(
            raw_text,
            req,
            evidence_ref=f"toggle_step_{step_num}",
            fail_closed=True,
        )

        all_reqs = tuple(SemanticRequirement(name=b.terminal) for b in req.minimal_context.bindings) + req.frontier
        init_frontier = frontier_builder.build(all_reqs, req.minimal_context)

        closure_outcome = closure_engine.close(
            signal=req.signal,
            requirements=all_reqs,
            context=req.minimal_context,
            initial_frontier=init_frontier,
            translation=cand_bindings,
        )

        cert_disp = closure_outcome.certificate.disposition.value
        disp_correct = (cert_disp == ex.expected_disposition)
        if disp_correct:
            exact_disp_count += 1

        if ex.expected_disposition != "YES" and cert_disp == "YES":
            unsafe_count += 1

        if "DETERMINISTIC_PRIMACY_VIOLATION" in closure_outcome.certificate.reason_codes:
            beta_d_count += 1

        records.append({
            "example_id": ex.example_id,
            "raw_text": raw_text,
            "is_valid_json": is_valid_json,
            "disposition": cert_disp,
            "disp_correct": disp_correct,
            "reason_codes": list(closure_outcome.certificate.reason_codes),
        })

    elapsed = time.perf_counter() - t0
    rate = exact_disp_count / len(examples)
    print(f"Step {step_num} Complete: {exact_disp_count}/{len(examples)} exact dispositions ({rate:.1%}) in {elapsed:.2f}s")

    step_summary = {
        "step": step_num,
        "step_name": step_name,
        "adapter_enabled": adapter_enabled,
        "exact_dispositions": exact_disp_count,
        "total_cases": len(examples),
        "exact_disposition_rate": round(rate, 4),
        "valid_json_count": valid_json_count,
        "valid_json_rate": round(valid_json_count / len(examples), 4),
        "unsafe_yes": unsafe_count,
        "beta_d": beta_d_count,
        "elapsed_seconds": round(elapsed, 2),
    }
    return step_summary, records


def run_h3_native_toggle_campaign(device: Optional[str] = None) -> dict[str, Any]:
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    print(f"=== H3-N Causal A/B/A/B Toggle Campaign on {device} ===")
    print(f"Winner Adapter Checkpoint: {WINNER_CHECKPOINT}")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    holdout_raw = manifest["holdout_examples"]
    holdout_examples = [
        H3NativeExample(
            example_id=d["example_id"],
            partition=d["partition"],
            family=d["family"],
            behavior_class=d["behavior_class"],
            frontier_cardinality=d["frontier_cardinality"],
            signal=d["signal"],
            context=d["context"],
            frontier=d["frontier"],
            target_bindings=d["target_bindings"],
            target_alternatives=d["target_alternatives"],
            target_unknowns=d["target_unknowns"],
            expected_disposition=d["expected_disposition"],
        )
        for d in holdout_raw
    ]

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID, revision=BASE_REVISION)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    print("Loading base model + LoRA adapter...")
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID,
        revision=BASE_REVISION,
        dtype=torch.float16 if device == "cuda" else torch.float32,
        device_map=device,
    )
    model = PeftModel.from_pretrained(base_model, str(WINNER_CHECKPOINT))
    model.eval()

    steps_results = []
    all_step_records = {}

    # Step 1: Base M_0
    s1, r1 = run_single_step(1, "Base M_0 (Delta W = 0)", False, model, tokenizer, holdout_examples, device)
    steps_results.append(s1)
    all_step_records["step_1"] = r1

    # Step 2: Native LoRA M_H3
    s2, r2 = run_single_step(2, "Native LoRA M_H3 (Delta W != 0)", True, model, tokenizer, holdout_examples, device)
    steps_results.append(s2)
    all_step_records["step_2"] = r2

    # Step 3: Base M_0
    s3, r3 = run_single_step(3, "Base M_0 (Delta W = 0)", False, model, tokenizer, holdout_examples, device)
    steps_results.append(s3)
    all_step_records["step_3"] = r3

    # Step 4: Native LoRA M_H3
    s4, r4 = run_single_step(4, "Native LoRA M_H3 (Delta W != 0)", True, model, tokenizer, holdout_examples, device)
    steps_results.append(s4)
    all_step_records["step_4"] = r4

    # Compute determinism error
    m0_diffs = sum(
        1 for a, b in zip(r1, r3)
        if a["raw_text"] != b["raw_text"] or a["disposition"] != b["disposition"]
    )
    lora_diffs = sum(
        1 for a, b in zip(r2, r4)
        if a["raw_text"] != b["raw_text"] or a["disposition"] != b["disposition"]
    )
    total_checks = 2 * len(holdout_examples)
    determinism_error = (m0_diffs + lora_diffs) / total_checks

    causal_toggle_passed = (
        determinism_error == 0.0
        and s2["exact_dispositions"] > s1["exact_dispositions"]
        and s3["exact_dispositions"] < s2["exact_dispositions"]
        and s4["exact_dispositions"] == s2["exact_dispositions"]
    )

    campaign_summary = {
        "experiment": "H3-N-CAUSAL-TOGGLE",
        "title": "Causal A/B/A/B Toggle of Native H3 LoRA Adapter",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checkpoint": str(WINNER_CHECKPOINT),
        "causal_pass": causal_toggle_passed,
        "determinism_error": determinism_error,
        "step_summaries": steps_results,
        "causal_deltas": {
            "step_1_to_2": round(s2["exact_disposition_rate"] - s1["exact_disposition_rate"], 4),
            "step_2_to_3": round(s3["exact_disposition_rate"] - s2["exact_disposition_rate"], 4),
            "step_3_to_4": round(s4["exact_disposition_rate"] - s3["exact_disposition_rate"], 4),
        },
        "all_invariants_preserved": all(s["beta_d"] == 0 for s in steps_results),
        "step_records": all_step_records,
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(campaign_summary, indent=2), encoding="utf-8")
    print(f"\nSaved Causal Toggle results to: {RESULTS_PATH}")
    print(f"Causal Pass: {causal_toggle_passed} | Determinism Error: {determinism_error:.6f}")
    print(f"Deltas: {campaign_summary['causal_deltas']}")

    del model
    del base_model
    del tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return campaign_summary


if __name__ == "__main__":
    run_h3_native_toggle_campaign()
