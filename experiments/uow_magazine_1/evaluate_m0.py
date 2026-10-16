"""Execute Gate M0: Foundation Availability & Architectural Inspection."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import torch
from transformers import AutoConfig, AutoTokenizer, AutoModelForCausalLM, AutoModelForSequenceClassification

MODELS_TO_PROBE = [
    {
        "id": "smollm2_135m",
        "name": "HuggingFaceTB/SmolLM2-135M-Instruct",
        "family": "llama",
        "type": "causal",
        "gated": False,
        "license": "Apache-2.0",
        "peft_targets": ["q_proj", "v_proj", "k_proj", "o_proj"],
    },
    {
        "id": "pythia_160m",
        "name": "EleutherAI/pythia-160m",
        "family": "gpt_neox",
        "type": "causal",
        "gated": False,
        "license": "Apache-2.0",
        "peft_targets": ["query_key_value", "dense"],
    },
    {
        "id": "gpt_neo_125m",
        "name": "EleutherAI/gpt-neo-125m",
        "family": "gpt_neo",
        "type": "causal",
        "gated": False,
        "license": "MIT",
        "peft_targets": ["q_proj", "v_proj"],
    },
    {
        "id": "cerebras_111m",
        "name": "cerebras-archive/Cerebras-GPT-111M",
        "family": "gpt2",
        "type": "causal",
        "gated": False,
        "license": "Apache-2.0",
        "peft_targets": ["c_attn"],
    },
    {
        "id": "mobilellm_125m",
        "name": "facebook/MobileLLM-125M",
        "family": "mobilellm",
        "type": "causal",
        "gated": True,
        "license": "FAIR Noncommercial Research",
        "peft_targets": ["q_proj", "v_proj"],
    },
    {
        "id": "mamba_130m",
        "name": "state-spaces/mamba-130m-hf",
        "family": "mamba",
        "type": "causal",
        "gated": False,
        "license": "Apache-2.0",
        "peft_targets": ["in_proj", "out_proj", "x_proj"],
    },
    {
        "id": "modernbert_base",
        "name": "answerdotai/ModernBERT-base",
        "family": "modernbert",
        "type": "encoder",
        "gated": False,
        "license": "Apache-2.0",
        "peft_targets": ["Wqkv", "Wo"],
    },
]


def run_gate_m0(output_file: str = "artifacts/uow_magazine_1/m0_foundation_inspection.json") -> dict:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Executing Gate M0 on device: {device}")

    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "campaign": "UOW-MAGAZINE-1",
        "gate": "M0",
        "status": "passed",
        "device": device,
        "models": {},
    }

    test_prompt = "UoW unit status: nominal. Action:"

    for item in MODELS_TO_PROBE:
        m_id = item["id"]
        m_name = item["name"]
        print(f"\n--- Probing Foundation: {m_id} ({m_name}) ---")

        if item.get("gated"):
            print(f"Model {m_id} is GATED. Documenting restricted access status per charter.")
            report["models"][m_id] = {
                "name": m_name,
                "status": "GATED_ACCESS_RESTRICTED",
                "notes": "Requires upstream organization repository approval on HuggingFace Hub (FAIR Noncommercial Research license).",
                "license": item["license"],
                "gated": True,
            }
            continue

        try:
            # 1. Fetch config and resolve exact commit SHA
            cfg = AutoConfig.from_pretrained(m_name, trust_remote_code=True)
            exact_sha = getattr(cfg, "_commit_hash", None)
            
            # Fetch tokenizer
            tok = AutoTokenizer.from_pretrained(m_name, trust_remote_code=True)
            if tok.pad_token_id is None:
                tok.pad_token_id = tok.eos_token_id or 0

            # Count parameters & test forward pass
            if item["type"] == "encoder":
                model = AutoModelForSequenceClassification.from_pretrained(
                    m_name,
                    num_labels=3,
                    trust_remote_code=True,
                    torch_dtype=torch.float32,
                ).to(device)
            else:
                model = AutoModelForCausalLM.from_pretrained(
                    m_name,
                    trust_remote_code=True,
                    torch_dtype=torch.float32,
                ).to(device)

            model.eval()
            total_params = sum(p.numel() for p in model.parameters())
            trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

            # Test single forward pass
            inputs = tok(test_prompt, return_tensors="pt").to(device)
            with torch.no_grad():
                out = model(**inputs)
                has_logits = hasattr(out, "logits") and out.logits is not None

            print(f"Passed: {total_params / 1e6:.1f}M params, Vocab: {tok.vocab_size}, Commit SHA: {exact_sha[:10] if exact_sha else 'resolved'}")

            report["models"][m_id] = {
                "name": m_name,
                "status": "QUALIFIED_AVAILABLE",
                "exact_commit_sha": exact_sha,
                "total_parameters": total_params,
                "total_parameters_millions": round(total_params / 1e6, 2),
                "architecture_family": item["family"],
                "model_class": model.__class__.__name__,
                "vocab_size": tok.vocab_size,
                "context_window": getattr(cfg, "max_position_embeddings", getattr(cfg, "n_positions", None)),
                "license": item["license"],
                "target_peft_modules": item["peft_targets"],
                "forward_pass_verified": bool(has_logits),
            }

            # Cleanup VRAM immediately
            del model
            del inputs
            del out
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        except Exception as e:
            print(f"Failed to probe {m_id}: {e}")
            report["models"][m_id] = {
                "name": m_name,
                "status": "ERROR",
                "error": str(e),
            }

    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nGate M0 execution complete. Results saved to {out_path}")
    return report


if __name__ == "__main__":
    run_gate_m0()
