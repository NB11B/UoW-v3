"""Domain-Grammar LoRA Adapter Trainer for UOW-MAGAZINE-1.

Trains compact LoRA adapters (r=8, alpha=16) on frozen compact foundation models.
Base weights strictly frozen.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

import torch
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer


class DomainGrammarDataset(Dataset):
    def __init__(self, examples: list[dict], tokenizer, max_len: int = 512):
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
    input_ids = []
    labels = []
    attention_mask = []
    for x in batch:
        cur_len = len(x["input_ids"])
        pad_len = max_len - cur_len
        input_ids.append(torch.cat([x["input_ids"], torch.full((pad_len,), pad_token_id, dtype=torch.long)]))
        labels.append(torch.cat([x["labels"], torch.full((pad_len,), -100, dtype=torch.long)]))
        attention_mask.append(torch.cat([torch.ones(cur_len, dtype=torch.long), torch.zeros(pad_len, dtype=torch.long)]))
    return {
        "input_ids": torch.stack(input_ids),
        "labels": torch.stack(labels),
        "attention_mask": torch.stack(attention_mask)
    }


def train_adapter(
    model_name: str,
    domain: str,
    grammar: str,
    train_file: Path,
    output_dir: Path,
    target_modules: list[str],
    epochs: int = 1,
    batch_size: int = 8,
    grad_accum: int = 1,
    lr: float = 4e-4,
    device: str = "cuda",
) -> dict[str, Any]:
    print(f"\n========================================================")
    print(f"Training Adapter: {domain}.{grammar} on Foundation: {model_name}")
    print(f"Target Modules: {target_modules}, Epochs: {epochs}, LR: {lr}")
    print(f"========================================================")

    output_dir.mkdir(parents=True, exist_ok=True)
    examples = json.loads(train_file.read_text(encoding="utf-8"))
    print(f"Loaded {len(examples)} training examples from {train_file}")

    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id or 0

    dataset = DomainGrammarDataset(examples, tokenizer)
    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=True,
        collate_fn=lambda b: collate_fn(b, tokenizer.pad_token_id),
    )

    base_model = AutoModelForCausalLM.from_pretrained(
        model_name,
        trust_remote_code=True,
        torch_dtype=torch.float32,
    )
    for p in base_model.parameters():
        p.requires_grad = False

    lora_config = LoraConfig(
        r=8,
        lora_alpha=16,
        target_modules=target_modules,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(base_model, lora_config)
    model.to(device)

    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"LoRA Trainable params: {trainable_params} / {total_params} ({trainable_params/total_params*100:.3f}%)", flush=True)

    optimizer = AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    model.train()

    t0 = time.time()
    step = 0
    total_loss = 0.0

    for epoch in range(1, epochs + 1):
        epoch_loss = 0.0
        for batch_idx, batch in enumerate(loader):
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
                step += 1

        avg_loss = epoch_loss / len(loader)
        print(f"Epoch {epoch}/{epochs} | Avg Loss: {avg_loss:.4f} | Elapsed: {time.time() - t0:.1f}s", flush=True)

    elapsed_sec = time.time() - t0
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    # Calculate SHA256 of adapter weights
    weight_path = output_dir / "adapter_model.safetensors"
    if not weight_path.exists():
        weight_path = output_dir / "adapter_model.bin"

    sha256_hash = hashlib.sha256(weight_path.read_bytes()).hexdigest()
    size_bytes = weight_path.stat().st_size

    print(f"Saved adapter to {output_dir}")
    print(f"Weight File: {weight_path.name} | SHA256: {sha256_hash} | Size: {size_bytes} bytes")

    # Clean memory
    del model
    del base_model
    del optimizer
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return {
        "domain": domain,
        "grammar": grammar,
        "foundation": model_name,
        "epochs": epochs,
        "final_loss": avg_loss,
        "training_time_seconds": round(elapsed_sec, 2),
        "weight_file": str(weight_path),
        "sha256": sha256_hash,
        "size_bytes": size_bytes,
    }
