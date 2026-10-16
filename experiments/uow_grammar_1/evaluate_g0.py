"""Execute Gate G0 for UOW-GRAMMAR-1: Baseline operational grammar reproduction."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from experiments.uow_native_3.spectral_adapter import load_adapter, apply_rank, sha256

EXPECTED_H3 = "64d77db036472c86403a1d98490526fc5412d56e8c1640a47fd9eeed5f92ad6a"
BASE = "HuggingFaceTB/SmolLM2-135M-Instruct"
REV = "12fd25f77366fa6b3b4b768ec3050bf629380bac"

def run(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--uow-v2-root", default="C:\\Users\\nateb\\OneDrive\\Documents\\UoW-v2")
    p.add_argument("--adapter-dir", default="C:\\Users\\nateb\\OneDrive\\Documents\\UoW-v2\\checkpoints\\uow_h3_native_smollm2_135m_arm_nb")
    p.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    p.add_argument("--output", default="artifacts/uow_grammar_1/g0_results.json")
    args = p.parse_args(argv)

    root = Path(args.uow_v2_root).resolve()
    adapter = Path(args.adapter_dir).resolve()
    manifest_path = root / "qualification" / "artifacts" / "semantic_h3_native_corpus_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing original UoW-v2 H3 corpus manifest: {manifest_path}")
    weight_path = adapter / "adapter_model.safetensors"
    if sha256(weight_path) != EXPECTED_H3:
        raise ValueError("Adapter SHA-256 mismatch")

    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root))
    from qualification.semantic.evaluate_h3_native_135m import evaluate_model_on_holdout
    from qualification.semantic.h3_native_corpus import H3NativeExample
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch
    import gc

    raw = json.loads(manifest_path.read_text(encoding="utf8"))["holdout_examples"]
    allowed = set(H3NativeExample.__dataclass_fields__)
    holdout = [H3NativeExample(**{k: v for k, v in d.items() if k in allowed}) for d in raw]
    tokenizer = AutoTokenizer.from_pretrained(BASE, revision=REV, trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    results = {
        "campaign": "UOW-GRAMMAR-1",
        "gate": "G0",
        "base_model": BASE,
        "base_revision": REV,
        "adapter_sha256": EXPECTED_H3,
        "evaluator": "UoW-v2/qualification/semantic/evaluate_h3_native_135m.py",
        "models": {}
    }

    # Evaluate unadapted base model M0
    print("\n--- Running Gate G0: Evaluating Base Model M0 ---")
    base_model = AutoModelForCausalLM.from_pretrained(BASE, revision=REV, trust_remote_code=False).to(args.device).eval()
    results["models"]["M0"] = evaluate_model_on_holdout("M0", base_model, tokenizer, holdout, args.device)
    del base_model
    gc.collect()
    if args.device == "cuda":
        torch.cuda.empty_cache()

    # Evaluate full H3 adapter
    print("\n--- Running Gate G0: Evaluating Unmodified H3 Adapter ---")
    _, full_model = load_adapter(BASE, REV, str(adapter), args.device)
    results["models"]["H3_full"] = evaluate_model_on_holdout("H3_full", full_model, tokenizer, holdout, args.device)
    del full_model
    gc.collect()
    if args.device == "cuda":
        torch.cuda.empty_cache()

    # Evaluate rank-8 SVD reconstruction control
    print("\n--- Running Gate G0: Evaluating Rank-8 Reconstruction Control ---")
    _, rec_model = load_adapter(BASE, REV, str(adapter), args.device)
    apply_rank(rec_model, 8)
    results["models"]["H3_rank_8_control"] = evaluate_model_on_holdout("H3_rank_8_control", rec_model, tokenizer, holdout, args.device)
    del rec_model
    gc.collect()
    if args.device == "cuda":
        torch.cuda.empty_cache()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf8")
    print(f"\nGate G0 results written to: {out}")

    # Summary
    m0_json = results["models"]["M0"]["counts"]["valid_json"]
    h3_json = results["models"]["H3_full"]["counts"]["valid_json"]
    h3_disp = results["models"]["H3_full"]["counts"]["exact_disposition"]
    rec_disp = results["models"]["H3_rank_8_control"]["counts"]["exact_disposition"]
    print(f"M0 Valid JSON: {m0_json}/20")
    print(f"H3 Full Valid JSON: {h3_json}/20, Exact Disp: {h3_disp}/20")
    print(f"H3 Rank-8 Control Valid JSON: {results['models']['H3_rank_8_control']['counts']['valid_json']}/20, Exact Disp: {rec_disp}/20")
    assert h3_json == 20
    assert h3_disp == 16
    print("Gate G0 Baseline PASSED and LOCKED.")
    return results

if __name__ == "__main__":
    run()
