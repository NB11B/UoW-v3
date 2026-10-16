"""Fine-tune specialized LoRA grammar adapters on frozen SmolLM2-135M-Instruct."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time

import torch
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

from experiments.uow_grammar_1.grammars.temporal import TemporalPromptBuilder
from experiments.uow_grammar_1.grammars.recovery import RecoveryPromptBuilder

BASE = "HuggingFaceTB/SmolLM2-135M-Instruct"
REV = "12fd25f77366fa6b3b4b768ec3050bf629380bac"


class GrammarDataset(Dataset):
    def __init__(self, examples: list[dict], tokenizer, prompt_builder):
        self.items = []
        for ex in examples:
            sig = ex["signal"]
            target_json = json.dumps(ex["target"], indent=2)
            messages = prompt_builder.build_chat_messages(sig)
            
            prompt_text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
            full_text = prompt_text + target_json + tokenizer.eos_token
            
            prompt_enc = tokenizer(prompt_text, return_tensors="pt", add_special_tokens=False)
            full_enc = tokenizer(full_text, return_tensors="pt", add_special_tokens=False)
            
            input_ids = full_enc["input_ids"][0]
            labels = input_ids.clone()
            # Mask prompt tokens with -100 so loss is computed ONLY on completion
            prompt_len = prompt_enc["input_ids"].shape[1]
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


def train(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--grammar", choices=("temporal", "recovery"), required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--grad-accum", type=int, default=2)
    p.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    args = p.parse_args(argv)

    manifest_path = Path(args.manifest)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    train_ex = data["train_examples"]
    print(f"\nTraining Grammar Adapter: {args.grammar.upper()}")
    print(f"Loaded {len(train_ex)} training examples from {manifest_path}")

    tokenizer = AutoTokenizer.from_pretrained(BASE, revision=REV, trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    prompt_builder = TemporalPromptBuilder() if args.grammar == "temporal" else RecoveryPromptBuilder()
    dataset = GrammarDataset(train_ex, tokenizer, prompt_builder)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True,
                        collate_fn=lambda b: collate_fn(b, tokenizer.pad_token_id))

    print(f"Loading base model {BASE} (frozen)...")
    base_model = AutoModelForCausalLM.from_pretrained(BASE, revision=REV, trust_remote_code=False).to(args.device)
    for param in base_model.parameters():
        param.requires_grad = False

    lora_config = LoraConfig(
        r=8,
        lora_alpha=16,
        target_modules=["q_proj", "v_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM"
    )
    model = get_peft_model(base_model, lora_config)
    model.print_trainable_parameters()

    optimizer = AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    model.train()

    t0 = time.time()
    for epoch in range(args.epochs):
        epoch_loss = 0.0
        step_count = 0
        optimizer.zero_grad()
        for i, batch in enumerate(loader):
            input_ids = batch["input_ids"].to(args.device)
            labels = batch["labels"].to(args.device)
            mask = batch["attention_mask"].to(args.device)

            outputs = model(input_ids=input_ids, attention_mask=mask, labels=labels)
            loss = outputs.loss / args.grad_accum
            loss.backward()

            epoch_loss += outputs.loss.item()
            step_count += 1

            if (i + 1) % args.grad_accum == 0 or (i + 1) == len(loader):
                optimizer.step()
                optimizer.zero_grad()

        avg_loss = epoch_loss / max(1, step_count)
        print(f"Epoch {epoch+1}/{args.epochs} - Loss: {avg_loss:.4f}")

    elapsed = time.time() - t0
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(out_dir))
    print(f"Training completed in {elapsed:.1f}s. Adapter saved to {out_dir}")
    return str(out_dir)


if __name__ == "__main__":
    train()
