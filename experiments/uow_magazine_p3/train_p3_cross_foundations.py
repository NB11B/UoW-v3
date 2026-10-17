"""Cross-Foundation Training Pipeline for Milestone P3 (UOW-MAGAZINE-RC0)."""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import LoraConfig, get_peft_model

from experiments.uow_magazine_p3.foundations import FOUNDATION_ROSTER, FoundationSpec

GRAMMARS = ["operational", "temporal", "recovery"]


class PromptDataset(Dataset):
    def __init__(self, examples: list[dict], tokenizer, max_len: int = 320):
        self.items = []
        pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else 0

        for ex in examples:
            prompt_text = ex.get("formatted_prompt") or ex.get("prompt", "")
            target_json = ex.get("target_json", "")
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


def collate_fn(batch, pad_token_id: int):
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


def train_single_adapter(
    spec: FoundationSpec,
    grammar: str,
    train_file: Path,
    output_dir: Path,
    device: str = "cuda",
    batch_size: int = 4,
    grad_accum: int = 2,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(spec.model_id)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token or "<|pad|>"

    raw_examples = json.loads(train_file.read_text(encoding="utf-8"))
    dataset = PromptDataset(raw_examples, tokenizer, max_len=spec.max_len)
    pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else 0
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, collate_fn=lambda b: collate_fn(b, pad_id))

    print(f"[{spec.slug}] Loading base model '{spec.model_id}'...", flush=True)
    base_model = AutoModelForCausalLM.from_pretrained(spec.model_id, dtype=torch.float32)
    for p in base_model.parameters():
        p.requires_grad = False

    lora_config = LoraConfig(
        r=8,
        lora_alpha=16,
        target_modules=spec.target_modules,
        fan_in_fan_out=spec.fan_in_fan_out,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(base_model, lora_config)
    model.to(device)

    trainable_params, all_params = model.get_nb_trainable_parameters()
    print(f"[{spec.slug} - shared.{grammar}] Trainable params: {trainable_params:,} / {all_params:,} ({trainable_params / all_params * 100:.3f}%)", flush=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=spec.learning_rate, weight_decay=0.01)
    model.train()
    t0 = time.time()
    total_loss = 0.0
    steps = 0

    for epoch in range(1, spec.epochs + 1):
        for step, batch in enumerate(loader):
            input_ids = batch["input_ids"].to(device)
            labels = batch["labels"].to(device)
            attention_mask = batch["attention_mask"].to(device)

            out = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
            loss = out.loss / grad_accum
            loss.backward()

            total_loss += loss.item() * grad_accum
            steps += 1

            if (step + 1) % grad_accum == 0 or (step + 1) == len(loader):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad()

    elapsed = time.time() - t0
    mean_loss = total_loss / max(1, steps)
    print(f"[{spec.slug} - shared.{grammar}] Finished in {elapsed:.2f}s | Final Mean Loss: {mean_loss:.4f}", flush=True)

    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    del model
    del base_model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return {
        "foundation": spec.model_id,
        "slug": spec.slug,
        "grammar": grammar,
        "trainable_parameters": trainable_params,
        "total_parameters": all_params,
        "trainable_pct": round(trainable_params / all_params * 100, 3),
        "mean_loss": round(mean_loss, 4),
        "elapsed_seconds": round(elapsed, 2),
    }


def train_p3_cross_foundations(
    corpora_dir: str = "artifacts/uow_magazine_p2/corpora",
    checkpoints_base: str = "checkpoints/uow_magazine_p3",
    p2_checkpoints_base: str = "checkpoints/uow_magazine_p2/strategy_b",
    foundations: Optional[list[str]] = None,
) -> dict[str, Any]:
    corpora_path = Path(corpora_dir)
    checkpoints_path = Path(checkpoints_base)
    checkpoints_path.mkdir(parents=True, exist_ok=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    selected_slugs = foundations or list(FOUNDATION_ROSTER.keys())
    results: dict[str, Any] = {}

    print(f"=== Starting P3 Cross-Foundation Training on {device.upper()} ===")
    print(f"Foundations: {selected_slugs}")

    for slug in selected_slugs:
        if slug not in FOUNDATION_ROSTER:
            print(f"Warning: slug {slug} not found in FOUNDATION_ROSTER, skipping.")
            continue

        spec = FOUNDATION_ROSTER[slug]
        results[slug] = {}

        # If smollm2_135m, copy or link existing qualified P2 adapters to save time
        if slug == "smollm2_135m":
            p2_path = Path(p2_checkpoints_base)
            slug_out = checkpoints_path / slug
            slug_out.mkdir(parents=True, exist_ok=True)
            for g in GRAMMARS:
                src_adapter = p2_path / f"shared.{g}"
                dst_adapter = slug_out / f"shared.{g}"
                if src_adapter.exists() and not dst_adapter.exists():
                    shutil.copytree(src_adapter, dst_adapter)
                    print(f"[{slug}] Linked qualified P2 adapter for shared.{g}")
                results[slug][f"shared.{g}"] = {
                    "foundation": spec.model_id,
                    "slug": slug,
                    "grammar": g,
                    "reused_from_p2": True,
                }
            continue

        # Train shared adapters for this foundation
        for g in GRAMMARS:
            shared_comb = f"shared.{g}"
            train_file = corpora_path / shared_comb / "train.json"
            output_dir = checkpoints_path / slug / shared_comb

            if output_dir.exists() and (output_dir / "adapter_model.safetensors").exists():
                print(f"[{slug}] Adapter {shared_comb} already exists at {output_dir}, skipping training.")
                results[slug][shared_comb] = {"status": "ALREADY_EXISTS"}
                continue

            info = train_single_adapter(spec, g, train_file, output_dir, device=device)
            results[slug][shared_comb] = info

    print("\n=== P3 Cross-Foundation Training Complete! ===")
    return results


if __name__ == "__main__":
    train_p3_cross_foundations()
