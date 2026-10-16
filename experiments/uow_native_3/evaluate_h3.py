"""Execute C0/C1 using the ORIGINAL UoW-v2 H3 semantic evaluator, not a proxy."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from experiments.uow_native_3.spectral_adapter import load_adapter, apply_rank, sha256

EXPECTED = "64d77db036472c86403a1d98490526fc5412d56e8c1640a47fd9eeed5f92ad6a"
BASE = "HuggingFaceTB/SmolLM2-135M-Instruct"
REV = "12fd25f77366fa6b3b4b768ec3050bf629380bac"

def run(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--uow-v2-root", required=True)
    p.add_argument("--adapter-dir", required=True)
    p.add_argument("--device", choices=("cpu","cuda"), default="cpu")
    p.add_argument("--ranks", type=int, nargs="+", default=[1,2,4,8], choices=(1,2,4,8))
    p.add_argument("--output", default="artifacts/uow_native_3/c0_c1_results.json")
    args=p.parse_args(argv)
    root=Path(args.uow_v2_root).resolve()
    adapter=Path(args.adapter_dir).resolve()
    manifest_path=root/"qualification"/"artifacts"/"semantic_h3_native_corpus_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("Missing original UoW-v2 H3 corpus manifest: "+str(manifest_path))
    weight_path=adapter/"adapter_model.safetensors"
    if sha256(weight_path)!=EXPECTED:
        raise ValueError("Adapter SHA-256 mismatch")
    # The original evaluator's production semantic parser and closure engine must
    # resolve from UoW-v2; never substitute the UoW-v3 semantic implementation.
    sys.path.insert(0,str(root/"src"))
    sys.path.insert(0,str(root))
    from qualification.semantic.evaluate_h3_native_135m import evaluate_model_on_holdout
    from qualification.semantic.h3_native_corpus import H3NativeExample
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch
    import gc
    raw=json.loads(manifest_path.read_text(encoding="utf8"))["holdout_examples"]
    if len(raw)!=20:
        raise ValueError("Expected original 20 family-disjoint H3 holdout cases")
    allowed=set(H3NativeExample.__dataclass_fields__)
    holdout=[H3NativeExample(**{k:v for k,v in d.items() if k in allowed}) for d in raw]
    tokenizer=AutoTokenizer.from_pretrained(BASE,revision=REV,trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id=tokenizer.eos_token_id
    results={"campaign":"UOW-NATIVE-3","adapter_sha256":EXPECTED,
             "corpus_manifest_sha256":sha256(manifest_path),
             "base_revision":REV,"evaluator":"UoW-v2/qualification/semantic/evaluate_h3_native_135m.py",
             "models":{}}
    # Evaluate unchanged base model under identical original evaluator.
    model=AutoModelForCausalLM.from_pretrained(BASE,revision=REV,trust_remote_code=False).to(args.device).eval()
    results["models"]["M0"]=evaluate_model_on_holdout("M0",model,tokenizer,holdout,args.device)
    del model
    gc.collect()
    if args.device=="cuda": torch.cuda.empty_cache()
    # Each variant loads a fresh unchanged base+adapter. Never truncate iteratively.
    for k in [None,*sorted(set(args.ranks))]:
        label="H3_full" if k is None else f"H3_rank_{k}"
        _,model=load_adapter(BASE,REV,str(adapter),args.device)
        if k is not None:
            apply_rank(model,k)
        results["models"][label]=evaluate_model_on_holdout(label,model,tokenizer,holdout,args.device)
        del model
        gc.collect()
        if args.device=="cuda": torch.cuda.empty_cache()
    out=Path(args.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(results,indent=2)+"\n",encoding="utf8")
    print("Original H3 evaluator report:",out)
    return results

if __name__=="__main__":
    run()
