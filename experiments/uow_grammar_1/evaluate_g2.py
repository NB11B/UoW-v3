"""Execute Gate G2: Cross-grammar weight alignment and 3x3 behavioral interference matrix."""
from __future__ import annotations
import argparse
import gc
import json
from pathlib import Path
import sys
import torch

from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from experiments.uow_grammar_1.grammars.temporal import TemporalPromptBuilder, TemporalOutputParser
from experiments.uow_grammar_1.grammars.recovery import RecoveryPromptBuilder, RecoveryOutputParser
from experiments.uow_grammar_1.evaluate_g1 import evaluate_temporal, evaluate_recovery

BASE = "HuggingFaceTB/SmolLM2-135M-Instruct"
REV = "12fd25f77366fa6b3b4b768ec3050bf629380bac"


def calculate_weight_alignment(adapter_dirs: dict[str, str]) -> dict[str, Any]:
    """Calculate Frobenius inner product alignment kappa(g, h) across adapters."""
    from safetensors.torch import load_file
    
    weights = {}
    configs = {}
    for name, path in adapter_dirs.items():
        p = Path(path)
        weights[name] = load_file(str(p / "adapter_model.safetensors"))
        configs[name] = json.loads((p / "adapter_config.json").read_text(encoding="utf-8"))

    grammars = list(adapter_dirs.keys())
    matrix = {g1: {g2: 0.0 for g2 in grammars} for g1 in grammars}

    for g1 in grammars:
        for g2 in grammars:
            if g1 == g2:
                matrix[g1][g2] = 1.0
                continue
            
            total_inner = 0.0
            total_norm1_sq = 0.0
            total_norm2_sq = 0.0

            scale1 = configs[g1]["lora_alpha"] / configs[g1]["r"]
            scale2 = configs[g2]["lora_alpha"] / configs[g2]["r"]

            for l in range(30):
                for proj in ("q_proj", "v_proj"):
                    key_a = f"base_model.model.model.layers.{l}.self_attn.{proj}.lora_A.weight"
                    key_b = f"base_model.model.model.layers.{l}.self_attn.{proj}.lora_B.weight"
                    
                    if key_a not in weights[g1] or key_a not in weights[g2]:
                        continue
                    
                    A1, B1 = weights[g1][key_a].float(), weights[g1][key_b].float()
                    A2, B2 = weights[g2][key_a].float(), weights[g2][key_b].float()
                    
                    dW1 = (B1 @ A1) * scale1
                    dW2 = (B2 @ A2) * scale2
                    
                    inner = (dW1 * dW2).sum().item()
                    n1_sq = (dW1 * dW1).sum().item()
                    n2_sq = (dW2 * dW2).sum().item()
                    
                    total_inner += inner
                    total_norm1_sq += n1_sq
                    total_norm2_sq += n2_sq

            denom = (total_norm1_sq ** 0.5) * (total_norm2_sq ** 0.5)
            kappa = total_inner / max(1e-12, denom)
            matrix[g1][g2] = round(kappa, 4)

    return {"matrix": matrix}


def evaluate_operational(model, tokenizer, holdout_examples, device, uow_v2_root: Path):
    sys.path.insert(0, str(uow_v2_root / "src"))
    sys.path.insert(0, str(uow_v2_root))
    from qualification.semantic.evaluate_h3_native_135m import evaluate_model_on_holdout
    eval_res = evaluate_model_on_holdout("eval", model, tokenizer, holdout_examples, device)
    return {
        "total_cases": eval_res["total_cases"],
        "valid_json": eval_res["counts"]["valid_json"],
        "valid_json_rate": eval_res["rates"]["valid_serialization_rate"],
        "exact_matches": eval_res["counts"]["exact_disposition"],
        "exact_match_rate": eval_res["rates"]["exact_closure_rate"],
        "unsafe_yes": eval_res["counts"]["unsafe_yes"]
    }


def run(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--uow-v2-root", default="C:\\Users\\nateb\\OneDrive\\Documents\\UoW-v2")
    p.add_argument("--op-adapter", default="C:\\Users\\nateb\\OneDrive\\Documents\\UoW-v2\\checkpoints\\uow_h3_native_smollm2_135m_arm_nb")
    p.add_argument("--temp-adapter", default="checkpoints/uow_temporal_smollm2_135m")
    p.add_argument("--rec-adapter", default="checkpoints/uow_recovery_smollm2_135m")
    p.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    p.add_argument("--output", default="artifacts/uow_grammar_1/g2_results.json")
    args = p.parse_args(argv)

    adapters = {
        "operational": args.op_adapter,
        "temporal": args.temp_adapter,
        "recovery": args.rec_adapter
    }

    print("\n--- Gate G2: Computing Weight-Space Alignment Matrix kappa(g, h) ---")
    alignment = calculate_weight_alignment(adapters)
    print("Alignment Matrix:")
    print(json.dumps(alignment["matrix"], indent=2))

    # Load holdout datasets
    root = Path(args.uow_v2_root).resolve()
    manifest_op = root / "qualification" / "artifacts" / "semantic_h3_native_corpus_manifest.json"
    from qualification.semantic.h3_native_corpus import H3NativeExample
    raw_op = json.loads(manifest_op.read_text(encoding="utf-8"))["holdout_examples"]
    allowed = set(H3NativeExample.__dataclass_fields__)
    holdout_op = [H3NativeExample(**{k: v for k, v in d.items() if k in allowed}) for d in raw_op]

    holdout_temp = json.loads(Path("artifacts/uow_grammar_1/temporal_corpus_manifest.json").read_text(encoding="utf-8"))["holdout_examples"]
    holdout_rec = json.loads(Path("artifacts/uow_grammar_1/recovery_corpus_manifest.json").read_text(encoding="utf-8"))["holdout_examples"]

    tokenizer = AutoTokenizer.from_pretrained(BASE, revision=REV, trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    grid = {}
    grammars = ["operational", "temporal", "recovery"]

    for g_name in grammars:
        adapter_path = adapters[g_name]
        print(f"\n--- Loading Adapter: {g_name.upper()} ({adapter_path}) ---")
        base = AutoModelForCausalLM.from_pretrained(BASE, revision=REV, trust_remote_code=False)
        model = PeftModel.from_pretrained(base, adapter_path, is_trainable=False).to(args.device).eval()

        grid[g_name] = {}

        # 1. On Operational
        print(f"Testing {g_name} on Operational holdout (20 cases)...")
        res_op = evaluate_operational(model, tokenizer, holdout_op, args.device, root)
        grid[g_name]["on_operational"] = res_op
        print(f"  Valid JSON: {res_op['valid_json']}/20, Match: {res_op['exact_matches']}/20")

        # 2. On Temporal
        print(f"Testing {g_name} on Temporal holdout (24 cases)...")
        res_temp = evaluate_temporal(model, tokenizer, holdout_temp, args.device)
        grid[g_name]["on_temporal"] = res_temp
        print(f"  Valid JSON: {res_temp['valid_json']}/24, Match: {res_temp['exact_matches']}/24")

        # 3. On Recovery
        print(f"Testing {g_name} on Recovery holdout (24 cases)...")
        res_rec = evaluate_recovery(model, tokenizer, holdout_rec, args.device)
        grid[g_name]["on_recovery"] = res_rec
        print(f"  Valid JSON: {res_rec['valid_json']}/24, Match: {res_rec['exact_matches']}/24")

        del model
        del base
        gc.collect()
        if args.device == "cuda":
            torch.cuda.empty_cache()

    final_results = {
        "campaign": "UOW-GRAMMAR-1",
        "gate": "G2",
        "weight_alignment_matrix": alignment["matrix"],
        "behavioral_grid": grid
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(final_results, indent=2) + "\n", encoding="utf-8")
    print(f"\nGate G2 Complete Report written to {out}")
    return final_results


if __name__ == "__main__":
    run()
