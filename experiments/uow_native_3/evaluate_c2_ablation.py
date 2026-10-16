"""Execute C2 Layer Ablation experiments for UOW-NATIVE-3."""
from __future__ import annotations
import argparse
import gc
import json
from pathlib import Path
import sys
import torch

from experiments.uow_native_3.spectral_adapter import load_adapter, apply_rank, sha256

EXPECTED = "64d77db036472c86403a1d98490526fc5412d56e8c1640a47fd9eeed5f92ad6a"
BASE = "HuggingFaceTB/SmolLM2-135M-Instruct"
REV = "12fd25f77366fa6b3b4b768ec3050bf629380bac"

def ablate_model(model, zero_layers: set[int]):
    """Zero adapter weights at specified layer indices."""
    return apply_rank(model, k=0, layers=zero_layers)

def isolate_model(model, keep_layers: set[int]):
    """Zero adapter weights at all layers EXCEPT the specified layer indices."""
    zero_layers = set(range(30)) - set(keep_layers)
    return apply_rank(model, k=0, layers=zero_layers)

def run(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--uow-v2-root", required=True)
    p.add_argument("--adapter-dir", required=True)
    p.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    p.add_argument("--mode", choices=("preregistered", "all_layers", "full"), default="preregistered",
                   help="preregistered: blocks 0-9, 10-19, 20-29, layer 28, isolate 28. all_layers: 0..29. full: both.")
    p.add_argument("--output", default="artifacts/uow_native_3/c2_ablation_results.json")
    args = p.parse_args(argv)

    root = Path(args.uow_v2_root).resolve()
    adapter = Path(args.adapter_dir).resolve()
    manifest_path = root / "qualification" / "artifacts" / "semantic_h3_native_corpus_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("Missing original UoW-v2 H3 corpus manifest: " + str(manifest_path))
    weight_path = adapter / "adapter_model.safetensors"
    if sha256(weight_path) != EXPECTED:
        raise ValueError("Adapter SHA-256 mismatch")

    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root))
    from qualification.semantic.evaluate_h3_native_135m import evaluate_model_on_holdout
    from qualification.semantic.h3_native_corpus import H3NativeExample
    from transformers import AutoTokenizer

    raw = json.loads(manifest_path.read_text(encoding="utf8"))["holdout_examples"]
    if len(raw) != 20:
        raise ValueError("Expected original 20 family-disjoint H3 holdout cases")
    allowed = set(H3NativeExample.__dataclass_fields__)
    holdout = [H3NativeExample(**{k: v for k, v in d.items() if k in allowed}) for d in raw]

    tokenizer = AutoTokenizer.from_pretrained(BASE, revision=REV, trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    # Define ablation conditions
    conditions = {}
    if args.mode in ("preregistered", "full"):
        conditions["ablate_block_0_9"] = {"type": "ablate", "layers": set(range(0, 10)), "desc": "Zero layers 0-9"}
        conditions["ablate_block_10_19"] = {"type": "ablate", "layers": set(range(10, 20)), "desc": "Zero layers 10-19"}
        conditions["ablate_block_20_29"] = {"type": "ablate", "layers": set(range(20, 30)), "desc": "Zero layers 20-29"}
        conditions["ablate_layer_28"] = {"type": "ablate", "layers": {28}, "desc": "Zero layer 28 only"}
        conditions["isolate_layer_28"] = {"type": "isolate", "layers": {28}, "desc": "Zero all layers except 28"}

    if args.mode in ("all_layers", "full"):
        for l in range(30):
            conditions[f"ablate_layer_{l:02d}"] = {"type": "ablate", "layers": {l}, "desc": f"Zero layer {l} only"}

    results = {
        "campaign": "UOW-NATIVE-3",
        "gate": "C2",
        "adapter_sha256": EXPECTED,
        "corpus_manifest_sha256": sha256(manifest_path),
        "base_revision": REV,
        "mode": args.mode,
        "conditions": {}
    }

    for name, spec in conditions.items():
        print(f"\n--- Running condition: {name} ({spec['desc']}) ---")
        _, model = load_adapter(BASE, REV, str(adapter), args.device)
        if spec["type"] == "ablate":
            ablate_model(model, spec["layers"])
        elif spec["type"] == "isolate":
            isolate_model(model, spec["layers"])
        
        eval_res = evaluate_model_on_holdout(name, model, tokenizer, holdout, args.device)
        del model
        gc.collect()
        if args.device == "cuda":
            torch.cuda.empty_cache()

        results["conditions"][name] = {
            "description": spec["desc"],
            "type": spec["type"],
            "layers": sorted(spec["layers"]),
            "rates": eval_res["rates"],
            "counts": eval_res["counts"],
            "case_records": eval_res["case_records"]
        }
        print(f"Results for {name}: Valid JSON={eval_res['counts']['valid_json']}/20, "
              f"Exact Disp={eval_res['counts']['exact_disposition']}/20, "
              f"Unsafe YES={eval_res['counts']['unsafe_yes']}/20")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf8")
    print("\nC2 Ablation Report written to:", out)
    return results

if __name__ == "__main__":
    run()
