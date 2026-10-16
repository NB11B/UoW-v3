"""Domain-Grammar LoRA Adapter Trainer for Milestone P2.

Trains:
- Strategy A: 9 specialized adapters (3 domains x 3 grammars)
- Strategy B: 3 shared grammar adapters (shared.operational, shared.temporal, shared.recovery)

Strict Hardware Profile:
- Frozen SmolLM2-135M-Instruct foundation (no parameter expansion)
- LoRA r=8, alpha=16 on q_proj, v_proj
- batch_size=4, grad_accum=2, max_len=220, epochs=2
- Memory capped at 50% VRAM (peak < 650 MB)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List

os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

import torch
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

FOUNDATION = "HuggingFaceTB/SmolLM2-135M-Instruct"
TARGET_MODULES = ["q_proj", "v_proj"]


class GroundedDataset(Dataset):
    def __init__(self, examples: list[dict], tokenizer: Any, max_len: int = 320):
        self.items = []
        eos_token = tokenizer.eos_token or "<|im_end|>"
        for ex in examples:
            prompt_text = ex["formatted_prompt"]
            target_json = ex["target_json"]
            full_text = prompt_text + target_json + eos_token

            prompt_enc = tokenizer(prompt_text, return_tensors="pt", add_special_tokens=False)
            full_enc = tokenizer(full_text, return_tensors="pt", add_special_tokens=False, max_length=max_len, truncation=True)

            input_ids = full_enc["input_ids"][0]
            labels = input_ids.clone()
            prompt_len = min(prompt_enc["input_ids"].shape[1], len(input_ids))
            labels[:prompt_len] = -100  # Only compute loss on target JSON

            self.items.append({"input_ids": input_ids, "labels": labels})

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        return self.items[idx]


def collate_fn(batch: list[dict], pad_token_id: int):
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
    adapter_id: str,
    train_file: Path,
    output_dir: Path,
    device: str = "cuda",
    epochs: int = 2,
    batch_size: int = 4,
    grad_accum: int = 2,
    lr: float = 5e-4,
) -> dict[str, Any]:
    print(f"\n========================================================")
    print(f"Training Adapter: {adapter_id} on Foundation: {FOUNDATION}")
    print(f"Target Modules: {TARGET_MODULES}, Epochs: {epochs}, LR: {lr}")
    print(f"========================================================")

    output_dir.mkdir(parents=True, exist_ok=True)
    examples = json.loads(train_file.read_text(encoding="utf-8"))
    print(f"Loaded {len(examples)} training examples from {train_file}")

    if torch.cuda.is_available() and device.startswith("cuda"):
        torch.cuda.set_per_process_memory_fraction(0.5, 0)
        torch.cuda.empty_cache()

    tokenizer = AutoTokenizer.from_pretrained(FOUNDATION, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id or 0

    dataset = GroundedDataset(examples, tokenizer, max_len=320)
    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=True,
        collate_fn=lambda b: collate_fn(b, tokenizer.pad_token_id),
    )

    base_model = AutoModelForCausalLM.from_pretrained(
        FOUNDATION,
        trust_remote_code=True,
        dtype=torch.float32,
    )
    for p in base_model.parameters():
        p.requires_grad = False

    lora_config = LoraConfig(
        r=8,
        lora_alpha=16,
        target_modules=TARGET_MODULES,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(base_model, lora_config)
    model.to(device)

    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Trainable params: {trainable_params} / {total_params} ({trainable_params/total_params*100:.3f}%)", flush=True)

    optimizer = AdamW(model.parameters(), lr=lr, weight_decay=0.01)

    t0 = time.time()
    model.train()
    total_steps = len(loader) * epochs
    step = 0
    final_loss = 0.0

    for epoch in range(epochs):
        epoch_loss = 0.0
        optimizer.zero_grad()
        for batch_idx, batch in enumerate(loader):
            step += 1
            input_ids = batch["input_ids"].to(device)
            labels = batch["labels"].to(device)
            attention_mask = batch["attention_mask"].to(device)

            outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
            loss = outputs.loss / grad_accum
            loss.backward()

            epoch_loss += loss.item() * grad_accum

            if (batch_idx + 1) % grad_accum == 0 or (batch_idx + 1) == len(loader):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad()

            if step % 50 == 0 or step == total_steps:
                cur_loss = epoch_loss / (batch_idx + 1)
                print(f"Epoch {epoch+1}/{epochs} | Step {step}/{total_steps} | Loss: {cur_loss:.4f}", flush=True)

        final_loss = epoch_loss / len(loader)

    duration = time.time() - t0
    peak_vram_mb = 0.0
    if torch.cuda.is_available() and device.startswith("cuda"):
        peak_vram_mb = torch.cuda.max_memory_allocated() / (1024 * 1024)

    print(f"Training finished in {duration:.2f}s | Final Loss: {final_loss:.4f} | Peak VRAM: {peak_vram_mb:.1f} MB")

    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    weight_file = output_dir / "adapter_model.safetensors"
    if not weight_file.exists():
        weight_file = output_dir / "adapter_model.bin"

    sha256 = hashlib.sha256(weight_file.read_bytes()).hexdigest()
    weight_size = weight_file.stat().st_size

    # Clean up GPU memory
    del model
    del base_model
    del optimizer
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return {
        "adapter_id": adapter_id,
        "foundation": FOUNDATION,
        "epochs": epochs,
        "final_loss": final_loss,
        "training_time_seconds": round(duration, 2),
        "peak_vram_mb": round(peak_vram_mb, 2),
        "weight_file": str(weight_file),
        "sha256": sha256,
        "size_bytes": weight_size,
    }


def train_all_p2_adapters(
    corpora_root: str = "artifacts/uow_magazine_p2/corpora",
    checkpoints_root: str = "checkpoints/uow_magazine_p2",
    device: str = "cuda" if torch.cuda.is_available() else "cpu",
) -> dict[str, Any]:
    sys.stdout.reconfigure(line_buffering=True)
    corpora_path = Path(corpora_root)
    checkpoints_path = Path(checkpoints_root)
    checkpoints_path.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {
        "strategy_a": {},
        "strategy_b": {},
    }

    # 1. Strategy A: 9 Dedicated Adapters
    domains = ["industrial", "cybersecurity", "logistics"]
    grammars = ["operational", "temporal", "recovery"]

    for d in domains:
        for g in grammars:
            comb = f"{d}.{g}"
            out_dir = checkpoints_path / "strategy_a" / comb
            train_file = corpora_path / comb / "train.json"

            meta = train_single_adapter(
                adapter_id=comb,
                train_file=train_file,
                output_dir=out_dir,
                device=device,
                epochs=2,
            )
            results["strategy_a"][comb] = meta

    # 2. Strategy B: 3 Shared Grammar Adapters
    for g in grammars:
        shared_comb = f"shared.{g}"
        out_dir = checkpoints_path / "strategy_b" / shared_comb
        train_file = corpora_path / shared_comb / "train.json"

        meta = train_single_adapter(
            adapter_id=shared_comb,
            train_file=train_file,
            output_dir=out_dir,
            device=device,
            epochs=2,
        )
        results["strategy_b"][shared_comb] = meta

    summary_file = checkpoints_path / "training_summary.json"
    summary_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nAll P2 adapters successfully trained! Summary written to {summary_file}")
    return results


if __name__ == "__main__":
    train_all_p2_adapters()
