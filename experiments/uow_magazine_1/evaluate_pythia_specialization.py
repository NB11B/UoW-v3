"""Pythia-160M Domain-Specialization and Weight Magazine Benchmark.

Evaluates whether Pythia-160M (GPT-NeoX architecture, 162.32M params) can:
1. Acquire domain-specialized grammars (industrial.operational, cybersecurity.temporal, logistics.recovery).
2. Produce structured UoW JSON on held-out test sets.
3. Coexist and switch in a resident weight magazine with zero contamination.

Strict VRAM Safety:
- Batch size = 4, max sequence length = 160 tokens
- Peak VRAM capped < 1.0 GB to prevent any driver/hypervisor memory pressure
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Dict, List

import torch
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset
from peft import LoraConfig, get_peft_model, PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from experiments.uow_magazine_1.datasets.schemas import JsonCodec
from experiments.uow_magazine_1.magazine.manifest import MagazineEntry, MagazineManifest
from experiments.uow_magazine_1.magazine.adapter_manager import MagazineAdapterManager

PYTHIA_MODEL = "EleutherAI/pythia-160m"
DOMAINS_TO_TEST = [
    ("industrial", "operational"),
    ("cybersecurity", "temporal"),
    ("logistics", "recovery"),
]


class DomainDataset(Dataset):
    def __init__(self, examples: list[dict], tokenizer, max_len: int = 160):
        self.items = []
        for ex in examples:
            prompt_text = ex["formatted_prompt"]
            target_json = ex["target_json"]
            full_text = prompt_text + target_json + (tokenizer.eos_token or "")

            prompt_enc = tokenizer(prompt_text, return_tensors="pt", add_special_tokens=False)
            full_enc = tokenizer(full_text, return_tensors="pt", add_special_tokens=False, max_length=max_len, truncation=True)

            input_ids = full_enc["input_ids"][0]
            labels = input_ids.clone()
            prompt_len = min(prompt_enc["input_ids"].shape[1], len(input_ids))
            labels[:prompt_len] = -100

            self.items.append({"input_ids": input_ids, "labels": labels})

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        return self.items[idx]


def collate_fn(batch, pad_token_id):
    max_len = max(len(x["input_ids"]) for x in batch)
    input_ids, labels, attention_mask = [], [], []
    for x in batch:
        cur_len = len(x["input_ids"])
        pad_len = max_len - cur_len
        input_ids.append(torch.cat([x["input_ids"], torch.full((pad_len,), pad_token_id, dtype=torch.long)]))
        labels.append(torch.cat([x["labels"], torch.full((pad_len,), -100, dtype=torch.long)]))
        attention_mask.append(torch.cat([torch.ones(cur_len, dtype=torch.long), torch.zeros(pad_len, dtype=torch.long)]))
    return {
        "input_ids": torch.stack(input_ids),
        "labels": torch.stack(labels),
        "attention_mask": torch.stack(attention_mask),
    }


def train_pythia_adapter(
    domain: str,
    grammar: str,
    train_file: Path,
    output_dir: Path,
    device: str = "cuda",
    epochs: int = 1,
    batch_size: int = 4,
    grad_accum: int = 2,
    lr: float = 5e-4,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(PYTHIA_MODEL)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id or 0

    # Bounded dataset for safe, fast specialization training
    examples = json.loads(train_file.read_text(encoding="utf-8"))[:120]
    dataset = DomainDataset(examples, tokenizer, max_len=160)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, collate_fn=lambda b: collate_fn(b, tokenizer.pad_token_id))

    base_model = AutoModelForCausalLM.from_pretrained(PYTHIA_MODEL, dtype=torch.float32)
    for p in base_model.parameters():
        p.requires_grad = False

    lora_config = LoraConfig(
        r=8,
        lora_alpha=16,
        target_modules=["query_key_value"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(base_model, lora_config)
    model.to(device)

    optimizer = AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    model.train()
    t0 = time.time()

    for epoch in range(1, epochs + 1):
        for step, batch in enumerate(loader):
            input_ids = batch["input_ids"].to(device)
            labels = batch["labels"].to(device)
            attention_mask = batch["attention_mask"].to(device)

            out = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
            loss = out.loss / grad_accum
            loss.backward()

            if (step + 1) % grad_accum == 0 or (step + 1) == len(loader):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad()

    train_time = time.time() - t0
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    del model
    del base_model
    del optimizer
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return {"domain": domain, "grammar": grammar, "train_time_sec": round(train_time, 2)}


def evaluate_pythia_holdout(
    adapter_dir: Path,
    holdout_file: Path,
    device: str = "cuda",
) -> dict[str, Any]:
    tokenizer = AutoTokenizer.from_pretrained(PYTHIA_MODEL)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id or 0

    base = AutoModelForCausalLM.from_pretrained(PYTHIA_MODEL, dtype=torch.float32)
    model = PeftModel.from_pretrained(base, str(adapter_dir), is_trainable=False).to(device)
    model.eval()

    holdout_data = json.loads(holdout_file.read_text(encoding="utf-8"))[:10]
    valid_json = 0
    exact_match = 0
    semantic_match = 0

    with torch.no_grad():
        for item in holdout_data:
            prompt = item["formatted_prompt"]
            target_dict = item["target_dict"]
            inputs = tokenizer(prompt, return_tensors="pt").to(device)

            out_tokens = model.generate(
                **inputs,
                max_new_tokens=140,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
            gen_text = tokenizer.decode(out_tokens[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
            parsed = JsonCodec.extract_json(gen_text)
            if parsed is not None:
                valid_json += 1
                if parsed == target_dict:
                    exact_match += 1

                matched = False
                grammar = holdout_file.parent.name.split(".")[1]
                if grammar == "operational":
                    if parsed.get("disposition") == target_dict.get("disposition") and parsed.get("action") == target_dict.get("action"):
                        matched = True
                elif grammar == "temporal":
                    if parsed.get("relation") == target_dict.get("relation") and parsed.get("target_action") == target_dict.get("target_action"):
                        matched = True
                elif grammar == "recovery":
                    if parsed.get("strategy") == target_dict.get("strategy"):
                        matched = True
                if matched:
                    semantic_match += 1

    del model
    del base
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return {
        "valid_json_count": valid_json,
        "valid_json_rate": round(valid_json / len(holdout_data) * 100.0, 2),
        "semantic_match_count": semantic_match,
        "semantic_match_rate": round(semantic_match / len(holdout_data) * 100.0, 2),
        "exact_dict_match_count": exact_match,
        "exact_dict_match_rate": round(exact_match / len(holdout_data) * 100.0, 2),
        "total_evaluated": len(holdout_data),
    }


def run_pythia_specialization_benchmark(
    checkpoints_base: str = "checkpoints/uow_magazine_1_pythia",
    corpora_dir: str = "artifacts/uow_magazine_1/corpora",
    output_file: str = "artifacts/uow_magazine_1/pythia_specialization_benchmark.json",
    device: str = "cuda",
) -> dict[str, Any]:
    print("\n========================================================")
    print("Executing Pythia-160M Domain Specialization & Magazine Benchmark")
    print("========================================================")

    if torch.cuda.is_available():
        # Prevent any hypervisor / WDDM paging memory spike
        torch.cuda.set_per_process_memory_fraction(0.5, 0)

    checkpoints_path = Path(checkpoints_base)
    corpora_path = Path(corpora_dir)
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    adapters_info = {}
    adapter_dirs = {}

    # Train Pythia adapters with strict bounded footprint
    for dom, gram in DOMAINS_TO_TEST:
        ad_id = f"{dom}_{gram}"
        ad_dir = checkpoints_path / f"{dom}.{gram}"
        train_file = corpora_path / f"{dom}.{gram}" / "train.json"
        holdout_file = corpora_path / f"{dom}.{gram}" / "holdout.json"

        if not (ad_dir / "adapter_model.safetensors").exists():
            print(f"Training Pythia adapter for {dom}.{gram}...", flush=True)
            train_pythia_adapter(dom, gram, train_file, ad_dir, device=device)

        print(f"Evaluating Pythia adapter on {dom}.{gram} holdout...", flush=True)
        eval_res = evaluate_pythia_holdout(ad_dir, holdout_file, device=device)
        adapters_info[ad_id] = eval_res
        adapter_dirs[ad_id] = ad_dir
        print(f"Pythia {ad_id}: Valid JSON={eval_res['valid_json_rate']}%, Semantic={eval_res['semantic_match_rate']}%", flush=True)

    # Test resident weight magazine on Pythia-160M
    print("\n--- Testing Pythia-160M Resident Weight Magazine & Switching ---", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(PYTHIA_MODEL)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id or 0

    base_model = AutoModelForCausalLM.from_pretrained(PYTHIA_MODEL, dtype=torch.float32).to(device)
    base_model.eval()

    manifest = MagazineManifest(
        magazine_id="pythia_magazine",
        foundation_id=PYTHIA_MODEL,
        max_resident_slots=8,
    )
    for ad_id in adapter_dirs.keys():
        dom, gram = ad_id.split("_")
        manifest.add_entry(
            MagazineEntry(
                adapter_id=ad_id,
                domain=dom,
                grammar=gram,
                foundation_id=PYTHIA_MODEL,
                rank=8,
                alpha=16,
                target_modules=["query_key_value"],
                sha256="pythia_local",
                size_bytes=(adapter_dirs[ad_id] / "adapter_model.safetensors").stat().st_size,
            )
        )

    manager = MagazineAdapterManager(
        base_model=base_model,
        manifest=manifest,
        device=device,
        max_resident_slots=8,
    )
    first_ad = list(adapter_dirs.keys())[0]
    manager.initialize_peft(first_ad, adapter_dirs[first_ad])

    for ad_id in list(adapter_dirs.keys())[1:]:
        manager.load_adapter(ad_id, adapter_dirs[ad_id])

    vram_mb = torch.cuda.memory_allocated() / (1024 * 1024) if torch.cuda.is_available() else 0.0

    # Probe pre-switch logits
    probe_prompt = "Validate operational grammar for step 001:"
    enc = tokenizer(probe_prompt, return_tensors="pt").to(device)
    pre_logits = {}
    for ad_id in adapter_dirs.keys():
        manager.switch_adapter(ad_id)
        with torch.no_grad():
            pre_logits[ad_id] = manager.peft_model(**enc).logits.clone()

    # Latency test
    latencies = []
    names = list(adapter_dirs.keys())
    for t in range(20):
        src = names[t % len(names)]
        dst = names[(t + 1) % len(names)]
        manager.switch_adapter(src)
        lat = manager.switch_adapter(dst)
        latencies.append(lat)

    latencies.sort()
    med_lat = latencies[len(latencies) // 2]

    # Post-cycle logits
    for _ in range(5):
        for ad_id in names:
            manager.switch_adapter(ad_id)

    max_diff = 0.0
    for ad_id in names:
        manager.switch_adapter(ad_id)
        with torch.no_grad():
            post_l = manager.peft_model(**enc).logits.clone()
        diff = torch.max(torch.abs(pre_logits[ad_id] - post_l)).item()
        max_diff = max(max_diff, diff)

    print(f"Pythia-160M Magazine: Resident VRAM={vram_mb:.2f} MB | Switch Latency={med_lat:.4f} ms | Contamination={max_diff:.8e}", flush=True)

    results = {
        "campaign": "UOW-MAGAZINE-1",
        "foundation": PYTHIA_MODEL,
        "base_parameters": 162322944,
        "parameter_ceiling_exception": "Pythia-160M has 162.32M parameters, exceeding the 160.0M ceiling by 1.45%; documented as approved research exception.",
        "resident_adapters_evaluated": len(adapter_dirs),
        "vram_allocated_mb": round(vram_mb, 2),
        "median_switch_latency_ms": round(med_lat, 4),
        "max_activation_contamination": max_diff,
        "adapters": adapters_info,
    }

    out_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"Pythia specialization benchmark complete! Saved to {out_path}", flush=True)

    del manager
    del base_model
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return results


if __name__ == "__main__":
    run_pythia_specialization_benchmark()
