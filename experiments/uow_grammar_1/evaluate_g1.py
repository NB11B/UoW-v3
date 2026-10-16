"""Execute Gate G1 evaluation: Verify independent grammar specialization on holdouts."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import torch

from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from experiments.uow_grammar_1.grammars.temporal import TemporalPromptBuilder, TemporalOutputParser
from experiments.uow_grammar_1.grammars.recovery import RecoveryPromptBuilder, RecoveryOutputParser

BASE = "HuggingFaceTB/SmolLM2-135M-Instruct"
REV = "12fd25f77366fa6b3b4b768ec3050bf629380bac"


def evaluate_temporal(model, tokenizer, holdout_examples, device):
    prompt_builder = TemporalPromptBuilder()
    parser = TemporalOutputParser()
    total = len(holdout_examples)
    valid_json = 0
    exact_matches = 0
    records = []

    for ex in holdout_examples:
        sig = ex["signal"]
        target = ex["target"]
        messages = prompt_builder.build_chat_messages(sig)
        prompt_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt_text, return_tensors="pt").to(device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=128,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id
            )
            input_len = inputs["input_ids"].shape[1]
            raw_text = tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True).strip()

        parsed = parser.parse(raw_text)
        is_valid = parsed is not None
        if is_valid:
            valid_json += 1
            # Check match against target
            actual = parsed.to_dict()
            is_match = (
                actual.get("target_action") == target.get("target_action") and
                actual.get("relation") == target.get("relation") and
                actual.get("reference_event") == target.get("reference_event") and
                actual.get("window") == target.get("window") and
                actual.get("deadline") == target.get("deadline")
            )
            if is_match:
                exact_matches += 1
        else:
            is_match = False

        records.append({
            "example_id": ex.get("example_id", "anon"),
            "signal": sig,
            "target": target,
            "raw_text": raw_text,
            "is_valid_json": is_valid,
            "is_exact_match": is_match
        })

    return {
        "total_cases": total,
        "valid_json": valid_json,
        "valid_json_rate": valid_json / total,
        "exact_matches": exact_matches,
        "exact_match_rate": exact_matches / total,
        "records": records
    }


def evaluate_recovery(model, tokenizer, holdout_examples, device):
    prompt_builder = RecoveryPromptBuilder()
    parser = RecoveryOutputParser()
    total = len(holdout_examples)
    valid_json = 0
    exact_matches = 0
    records = []

    for ex in holdout_examples:
        sig = ex["signal"]
        target = ex["target"]
        messages = prompt_builder.build_chat_messages(sig)
        prompt_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt_text, return_tensors="pt").to(device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=128,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id
            )
            input_len = inputs["input_ids"].shape[1]
            raw_text = tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True).strip()

        parsed = parser.parse(raw_text)
        is_valid = parsed is not None
        if is_valid:
            valid_json += 1
            actual = parsed.to_dict()
            is_match = (
                actual.get("failed_uow") == target.get("failed_uow") and
                actual.get("strategy") == target.get("strategy") and
                actual.get("compensation_uow") == target.get("compensation_uow") and
                actual.get("fallback_uow") == target.get("fallback_uow")
            )
            if is_match:
                exact_matches += 1
        else:
            is_match = False

        records.append({
            "example_id": ex.get("example_id", "anon"),
            "signal": sig,
            "target": target,
            "raw_text": raw_text,
            "is_valid_json": is_valid,
            "is_exact_match": is_match
        })

    return {
        "total_cases": total,
        "valid_json": valid_json,
        "valid_json_rate": valid_json / total,
        "exact_matches": exact_matches,
        "exact_match_rate": exact_matches / total,
        "records": records
    }


def run(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--temporal-manifest", default="artifacts/uow_grammar_1/temporal_corpus_manifest.json")
    p.add_argument("--recovery-manifest", default="artifacts/uow_grammar_1/recovery_corpus_manifest.json")
    p.add_argument("--temporal-adapter", default="checkpoints/uow_temporal_smollm2_135m")
    p.add_argument("--recovery-adapter", default="checkpoints/uow_recovery_smollm2_135m")
    p.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    p.add_argument("--output", default="artifacts/uow_grammar_1/g1_results.json")
    args = p.parse_args(argv)

    t_data = json.loads(Path(args.temporal_manifest).read_text(encoding="utf-8"))["holdout_examples"]
    r_data = json.loads(Path(args.recovery_manifest).read_text(encoding="utf-8"))["holdout_examples"]

    tokenizer = AutoTokenizer.from_pretrained(BASE, revision=REV, trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    results = {
        "campaign": "UOW-GRAMMAR-1",
        "gate": "G1",
        "evaluations": {}
    }

    # 1. Base Model on Temporal
    print("\n--- Evaluating Base Model M0 on Temporal Holdout ---")
    base = AutoModelForCausalLM.from_pretrained(BASE, revision=REV, trust_remote_code=False).to(args.device).eval()
    results["evaluations"]["M0_temporal"] = evaluate_temporal(base, tokenizer, t_data, args.device)
    print(f"M0 Temporal: Valid JSON={results['evaluations']['M0_temporal']['valid_json']}/24, "
          f"Exact Matches={results['evaluations']['M0_temporal']['exact_matches']}/24")

    # 2. Temporal Adapter on Temporal
    print(f"\n--- Evaluating Temporal Adapter on Temporal Holdout ({args.temporal_adapter}) ---")
    temp_model = PeftModel.from_pretrained(base, args.temporal_adapter, is_trainable=False).to(args.device).eval()
    results["evaluations"]["Temporal_adapter"] = evaluate_temporal(temp_model, tokenizer, t_data, args.device)
    print(f"Temporal Adapter: Valid JSON={results['evaluations']['Temporal_adapter']['valid_json']}/24, "
          f"Exact Matches={results['evaluations']['Temporal_adapter']['exact_matches']}/24")
    del temp_model

    # 3. Base Model on Recovery
    print("\n--- Evaluating Base Model M0 on Recovery Holdout ---")
    results["evaluations"]["M0_recovery"] = evaluate_recovery(base, tokenizer, r_data, args.device)
    print(f"M0 Recovery: Valid JSON={results['evaluations']['M0_recovery']['valid_json']}/24, "
          f"Exact Matches={results['evaluations']['M0_recovery']['exact_matches']}/24")

    # 4. Recovery Adapter on Recovery
    print(f"\n--- Evaluating Recovery Adapter on Recovery Holdout ({args.recovery_adapter}) ---")
    rec_model = PeftModel.from_pretrained(base, args.recovery_adapter, is_trainable=False).to(args.device).eval()
    results["evaluations"]["Recovery_adapter"] = evaluate_recovery(rec_model, tokenizer, r_data, args.device)
    print(f"Recovery Adapter: Valid JSON={results['evaluations']['Recovery_adapter']['valid_json']}/24, "
          f"Exact Matches={results['evaluations']['Recovery_adapter']['exact_matches']}/24")
    del rec_model
    del base

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"\nGate G1 results written to: {out}")
    return results


if __name__ == "__main__":
    run()
