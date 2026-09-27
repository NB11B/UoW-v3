"""Train reproduced J2.10 M_VG adapter checkpoint (SmolLM2-135M-Instruct).

Reproduces the exact physical training condition from J2.10:
- Base: SmolLM2-135M-Instruct (revision 12fd25f77366fa6b3b4b768ec3050bf629380bac)
- Training corpus: 37 M_VG operational examples (20 vocab + 17 grammar)
- LoRA config: r=8, alpha=16, targets=['q_proj', 'v_proj'] (460,800 trainable parameters)
- Optimizer: AdamW(lr=2e-4)
- Epochs: 3
- Loss masking: target-only (prompt tokens = -100)
- Output: checkpoints/reproduced_j2_10_mvg_135m
"""
from __future__ import annotations

import gc
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

from peft import LoraConfig, get_peft_model
import torch
from torch.optim import AdamW
from transformers import AutoModelForCausalLM, AutoTokenizer

# Import JEV corpus and codec from jevtest
JEVTEST_DIR = Path(r"C:\Users\nateb\OneDrive\Documents\jevtest")
if str(JEVTEST_DIR) not in sys.path:
    sys.path.insert(0, str(JEVTEST_DIR))

from jevl.adaptation.corpus import AdaptationCondition
from jevl.adaptation.physical_tuning import PhysicalCorpusManager, PhysicalTrainingExample
from jevl.semantic.prompt_codec import SYSTEM_PROMPT, format_j2_prompt


OUTPUT_CHECKPOINT_DIR = JEVTEST_DIR / "checkpoints" / "reproduced_j2_10_mvg_135m"
SPEC_FILE = Path(__file__).resolve().parent / "j2_10_mvg_reproduction_spec.json"


def train_reproduced_mvg(device: str | None = None) -> dict[str, Any]:
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    print("=" * 80)
    print("  REPRODUCING J2.10 M_VG ADAPTER CHECKPOINT (SmolLM2-135M-Instruct)")
    print("=" * 80)

    # 1. Load and verify reproduction spec
    spec = json.loads(SPEC_FILE.read_text(encoding="utf-8"))
    base_model_id = spec["base_model"]
    base_revision = spec["revision"]
    expected_params = spec["expected_trainable_parameters"]
    expected_corpus_digest = spec["training_corpus_digest"]
    epochs = spec["epochs"]
    learning_rate = spec["learning_rate"]

    print(f"Base model: {base_model_id} (revision: {base_revision[:8]}...)")
    print(f"Device: {device}")

    # 2. Build training corpus and verify digest
    corpus_mgr = PhysicalCorpusManager()
    train_sets = corpus_mgr.build_training_corpus()
    mvg_examples: list[PhysicalTrainingExample] = train_sets[AdaptationCondition.M_VG_COMBINED]
    assert len(mvg_examples) == spec["training_examples"], f"Expected {spec['training_examples']} examples, got {len(mvg_examples)}"

    corpus_dump = []
    for ex in mvg_examples:
        corpus_dump.append({
            "id": ex.example_id,
            "signal": ex.signal,
            "category": ex.category_label,
            "frontier": [item.req_id for item in ex.frontier],
            "target_json": ex.to_target_json(),
        })
    observed_corpus_digest = hashlib.sha256(json.dumps(corpus_dump, sort_keys=True).encode("utf-8")).hexdigest()
    assert observed_corpus_digest == expected_corpus_digest, (
        f"Corpus digest mismatch: observed {observed_corpus_digest} != expected {expected_corpus_digest}"
    )
    print(f"Training corpus verified: {len(mvg_examples)} examples, SHA256={observed_corpus_digest}")

    # 3. Load tokenizer and base model
    tokenizer = AutoTokenizer.from_pretrained(base_model_id, revision=base_revision)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        revision=base_revision,
        dtype=torch.float16 if device == "cuda" else torch.float32,
        device_map=device,
    )

    # 4. Configure PEFT LoRA
    peft_config = LoraConfig(
        r=spec["lora_r"],
        lora_alpha=spec["lora_alpha"],
        target_modules=spec["target_modules"],
        lora_dropout=spec["lora_dropout"],
        bias=spec["bias"],
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(base_model, peft_config)
    trainable_params, all_params = model.get_nb_trainable_parameters()
    trainable_pct = 100.0 * (trainable_params / all_params)

    print(f"Trainable parameters: {trainable_params:,d} / {all_params:,d} ({trainable_pct:.4f}%)")
    assert trainable_params == expected_params, f"Parameter count mismatch: {trainable_params} != {expected_params}"

    # 5. Tokenize and mask training examples
    input_ids_list = []
    labels_list = []

    for ex in mvg_examples:
        req = ex.to_j2_request()
        prompt = format_j2_prompt(req)
        full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}\n\nJSON Output:\n"
        target_json = ex.to_target_json()
        full_text = full_prompt + target_json + tokenizer.eos_token

        enc_prompt = tokenizer(full_prompt, add_special_tokens=False)["input_ids"]
        enc_full = tokenizer(full_text, add_special_tokens=False)["input_ids"]

        # Target-only loss masking: prompt tokens set to -100
        labels = [-100] * len(enc_prompt) + enc_full[len(enc_prompt):]

        input_ids_list.append(torch.tensor(enc_full, dtype=torch.long))
        labels_list.append(torch.tensor(labels, dtype=torch.long))

    # 6. Training loop
    optimizer = AdamW(model.parameters(), lr=learning_rate)
    model.train()

    t0 = time.perf_counter()
    initial_loss = 0.0
    final_loss = 0.0
    epoch_losses = []

    print(f"Starting physical LoRA training: {epochs} epochs over {len(input_ids_list)} examples...")
    for epoch in range(epochs):
        epoch_loss = 0.0
        for idx in range(len(input_ids_list)):
            inp = input_ids_list[idx].unsqueeze(0).to(device)
            lab = labels_list[idx].unsqueeze(0).to(device)

            optimizer.zero_grad()
            out = model(input_ids=inp, labels=lab)
            loss = out.loss
            loss.backward()
            optimizer.step()

            loss_val = loss.item()
            epoch_loss += loss_val
            if epoch == 0 and idx == 0:
                initial_loss = loss_val
            final_loss = loss_val

        avg_epoch_loss = epoch_loss / len(input_ids_list)
        epoch_losses.append(avg_epoch_loss)
        print(f"  Epoch {epoch + 1}/{epochs}: avg_loss={avg_epoch_loss:.4f} (step_final={final_loss:.4f})")

    t_train = time.perf_counter() - t0
    loss_reduction = max(0.0, (1.0 - (final_loss / max(0.001, initial_loss))) * 100.0)
    print(f"Training completed in {t_train:.2f}s | Initial loss: {initial_loss:.4f} | Final loss: {final_loss:.4f} | Reduction: {loss_reduction:.2f}%")

    # 7. Save reproduced checkpoint
    OUTPUT_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(OUTPUT_CHECKPOINT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_CHECKPOINT_DIR))

    # 8. Compute cryptographic file hashes
    weights_path = OUTPUT_CHECKPOINT_DIR / "adapter_model.safetensors"
    config_path = OUTPUT_CHECKPOINT_DIR / "adapter_config.json"
    weights_sha256 = hashlib.sha256(weights_path.read_bytes()).hexdigest()
    config_sha256 = hashlib.sha256(config_path.read_bytes()).hexdigest()

    metrics = {
        "model_name": "SmolLM2-135M-Instruct",
        "condition": "M_VG_COMBINED",
        "trainable_parameters": trainable_params,
        "total_parameters": all_params,
        "trainable_percentage": round(trainable_pct, 4),
        "initial_loss": round(initial_loss, 4),
        "final_loss": round(final_loss, 4),
        "epoch_losses": [round(l, 4) for l in epoch_losses],
        "loss_reduction_pct": round(loss_reduction, 2),
        "training_duration_s": round(t_train, 2),
        "device": device,
        "primary_weights_sha256": weights_sha256,
        "config_sha256": config_sha256,
    }
    (OUTPUT_CHECKPOINT_DIR / "training_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    manifest = {
        "artifact_label": "M_VG_repro",
        "checkpoint_dir": str(OUTPUT_CHECKPOINT_DIR),
        "base_model": base_model_id,
        "base_revision": base_revision,
        "adapter_sha256": weights_sha256,
        "adapter_config_sha256": config_sha256,
        "spec_digest": hashlib.sha256(SPEC_FILE.read_bytes()).hexdigest(),
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (OUTPUT_CHECKPOINT_DIR / "reproduction_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\nCheckpoint saved to: {OUTPUT_CHECKPOINT_DIR}")
    print(f"  adapter_model.safetensors SHA256: {weights_sha256}")
    print(f"  adapter_config.json SHA256:       {config_sha256}")

    # Clean VRAM
    del model
    del base_model
    del tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return {
        "metrics": metrics,
        "manifest": manifest,
    }


if __name__ == "__main__":
    train_reproduced_mvg()
