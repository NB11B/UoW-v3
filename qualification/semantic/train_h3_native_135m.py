"""H3-N: Native UoW Semantic Grammar LoRA Training Script.

Trains two experimental arms on the RTX 5070 GPU:
- Arm N-A: Fresh H3 LoRA (M_0 -> M_H3) from unadapted base model.
- Arm N-B: Grammar transfer LoRA (M_VG -> M_J2->H3) initialized from reproduced J2 checkpoint.

Adheres strictly to the specification:
- Base: SmolLM2-135M-Instruct (revision 12fd25f7...)
- Grammar: grammar-h3-native-v1 / uow.semantic.bindings.v1
- LoRA: r=8, alpha=16, q_proj, v_proj, bias=none (460,800 params)
- Loss: Target-only causal cross-entropy (prompt masked with -100)
- Optimizer: AdamW, lr=3e-4, 3 epochs
"""
from __future__ import annotations

import gc
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional

import torch
from peft import LoraConfig, PeftModel, get_peft_model
from torch.optim import AdamW
from transformers import AutoModelForCausalLM, AutoTokenizer

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(PACKAGE_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT / "src"))
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from qualification.semantic.h3_native_corpus import H3NativeExample, generate_and_admit_corpus
from uow.semantic.adapters.codec import SemanticPromptBuilder

SPEC_PATH = PACKAGE_ROOT / "qualification" / "semantic" / "h3_native_training_spec.json"
MANIFEST_PATH = PACKAGE_ROOT / "qualification" / "artifacts" / "semantic_h3_native_corpus_manifest.json"
RESULTS_PATH = PACKAGE_ROOT / "qualification" / "artifacts" / "semantic_h3_native_training_results.json"
J2_CHECKPOINT_DIR = Path(r"C:\Users\nateb\OneDrive\Documents\jevtest\checkpoints\reproduced_j2_10_mvg_135m")
CHECKPOINTS_BASE = PACKAGE_ROOT / "checkpoints"


def prepare_training_tensors(
    examples: list[H3NativeExample],
    tokenizer: Any,
) -> tuple[list[torch.Tensor], list[torch.Tensor]]:
    """Convert admitted examples to input_ids and target-masked label tensors."""
    prompt_builder = SemanticPromptBuilder()
    input_ids_list: list[torch.Tensor] = []
    labels_list: list[torch.Tensor] = []

    for ex in examples:
        req = ex.to_request()
        messages = prompt_builder.build_chat_messages(req)
        prompt_text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        target_json = ex.to_target_json()
        full_text = prompt_text + target_json + tokenizer.eos_token

        enc_prompt = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
        enc_full = tokenizer(full_text, add_special_tokens=False)["input_ids"]

        # Target-only loss masking: prompt tokens set to -100
        labels = [-100] * len(enc_prompt) + enc_full[len(enc_prompt):]

        input_ids_list.append(torch.tensor(enc_full, dtype=torch.long))
        labels_list.append(torch.tensor(labels, dtype=torch.long))

    return input_ids_list, labels_list


def train_single_arm(
    arm_id: str,
    arm_name: str,
    base_model_id: str,
    base_revision: str,
    spec: dict[str, Any],
    train_inputs: list[torch.Tensor],
    train_labels: list[torch.Tensor],
    output_dir: Path,
    device: str,
    starting_weights: str,
) -> dict[str, Any]:
    print(f"\n{'='*70}")
    print(f"  TRAINING ARM {arm_id}: {arm_name}")
    print(f"  Starting Weights: {starting_weights}")
    print(f"  Output Checkpoint: {output_dir}")
    print(f"{'='*70}")

    output_dir.mkdir(parents=True, exist_ok=True)

    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        revision=base_revision,
        dtype=torch.float16 if device == "cuda" else torch.float32,
        device_map=device,
    )

    if starting_weights == "base_M0":
        # Arm N-A: Fresh LoRA initialized from scratch
        peft_config = LoraConfig(
            r=spec["lora_r"],
            lora_alpha=spec["lora_alpha"],
            target_modules=spec["target_modules"],
            lora_dropout=spec["lora_dropout"],
            bias=spec["bias"],
            task_type="CAUSAL_LM",
        )
        model = get_peft_model(base_model, peft_config)
    else:
        # Arm N-B: Grammar transfer initialized from reproduced J2 checkpoint
        print(f"Loading weights from prior J2 checkpoint: {J2_CHECKPOINT_DIR}")
        model = PeftModel.from_pretrained(
            base_model,
            str(J2_CHECKPOINT_DIR),
            is_trainable=True,
        )

    trainable_params, all_params = model.get_nb_trainable_parameters()
    trainable_pct = 100.0 * (trainable_params / all_params)
    print(f"Trainable parameters: {trainable_params:,d} / {all_params:,d} ({trainable_pct:.4f}%)")
    assert trainable_params == spec["expected_trainable_parameters"], (
        f"Parameter mismatch: {trainable_params} != {spec['expected_trainable_parameters']}"
    )

    optimizer = AdamW(model.parameters(), lr=spec["learning_rate"])
    model.train()

    epochs = spec["epochs"]
    t0 = time.perf_counter()
    initial_loss = 0.0
    final_loss = 0.0
    epoch_losses = []

    print(f"Starting {epochs} epochs over {len(train_inputs)} examples...")
    for epoch in range(1, epochs + 1):
        running_loss = 0.0
        # Deterministic ordering for exact reproducibility
        for step, (input_ids, labels) in enumerate(zip(train_inputs, train_labels)):
            optimizer.zero_grad()
            inp = input_ids.unsqueeze(0).to(device)
            lbl = labels.unsqueeze(0).to(device)

            outputs = model(input_ids=inp, labels=lbl)
            loss = outputs.loss
            loss.backward()
            optimizer.step()

            loss_val = loss.item()
            running_loss += loss_val
            if epoch == 1 and step == 0:
                initial_loss = loss_val

        avg_loss = running_loss / len(train_inputs)
        epoch_losses.append(round(avg_loss, 4))
        final_loss = avg_loss
        print(f"  Epoch {epoch}/{epochs} - Average Loss: {avg_loss:.4f}")

    wall_time = time.perf_counter() - t0
    reduction_pct = 100.0 * (1.0 - (final_loss / initial_loss)) if initial_loss > 0 else 0.0
    print(f"Training complete in {wall_time:.2f}s! Initial: {initial_loss:.4f} -> Final: {final_loss:.4f} ({reduction_pct:.2f}% reduction)")

    # Save trained adapter
    model.save_pretrained(str(output_dir))
    print(f"Saved adapter weights to: {output_dir}")

    # Manifest for this arm
    arm_summary = {
        "arm_id": arm_id,
        "arm_name": arm_name,
        "starting_weights": starting_weights,
        "output_dir": str(output_dir),
        "trainable_parameters": trainable_params,
        "total_parameters": all_params,
        "trainable_percent": round(trainable_pct, 4),
        "initial_loss": round(initial_loss, 4),
        "final_loss": round(final_loss, 4),
        "loss_reduction_pct": round(reduction_pct, 2),
        "epoch_losses": epoch_losses,
        "wall_time_seconds": round(wall_time, 2),
    }

    # Clean up GPU memory
    del model
    del base_model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return arm_summary


def run_h3_native_training_campaign(device: Optional[str] = None) -> dict[str, Any]:
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    print(f"=== H3-N: Native Grammar Training Program on {device} ===")

    # Ensure corpus manifest exists
    if not MANIFEST_PATH.exists():
        print("Corpus manifest not found. Generating...")
        generate_and_admit_corpus()

    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    train_raw = manifest["train_examples"]
    train_examples = [
        H3NativeExample(
            example_id=d["example_id"],
            partition=d["partition"],
            family=d["family"],
            behavior_class=d["behavior_class"],
            frontier_cardinality=d["frontier_cardinality"],
            signal=d["signal"],
            context=d["context"],
            frontier=d["frontier"],
            target_bindings=d["target_bindings"],
            target_alternatives=d["target_alternatives"],
            target_unknowns=d["target_unknowns"],
            expected_disposition=d["expected_disposition"],
        )
        for d in train_raw
    ]

    base_model_id = spec["base_model"]
    base_revision = spec["base_revision"]

    print(f"Loading tokenizer {base_model_id} (rev={base_revision[:8]})...")
    tokenizer = AutoTokenizer.from_pretrained(base_model_id, revision=base_revision)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    print("Tokenizing and masking training examples...")
    train_inputs, train_labels = prepare_training_tensors(train_examples, tokenizer)
    print(f"Prepared {len(train_inputs)} training sequences.")

    # Execute Arm N-A (Fresh LoRA)
    arm_na_dir = CHECKPOINTS_BASE / "uow_h3_native_smollm2_135m_arm_na"
    res_na = train_single_arm(
        arm_id="N_A",
        arm_name="Fresh H3 Native LoRA (M_0 -> M_H3)",
        base_model_id=base_model_id,
        base_revision=base_revision,
        spec=spec,
        train_inputs=train_inputs,
        train_labels=train_labels,
        output_dir=arm_na_dir,
        device=device,
        starting_weights="base_M0",
    )

    # Execute Arm N-B (Grammar Transfer LoRA)
    arm_nb_dir = CHECKPOINTS_BASE / "uow_h3_native_smollm2_135m_arm_nb"
    res_nb = train_single_arm(
        arm_id="N_B",
        arm_name="Grammar Transfer LoRA (M_VG -> M_J2->H3)",
        base_model_id=base_model_id,
        base_revision=base_revision,
        spec=spec,
        train_inputs=train_inputs,
        train_labels=train_labels,
        output_dir=arm_nb_dir,
        device=device,
        starting_weights="reproduced_j2_10_mvg_135m",
    )

    full_results = {
        "experiment": "H3-N-TRAINING",
        "title": "Native UoW Semantic Grammar Training Campaign (Arms N-A vs N-B)",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_model": base_model_id,
        "base_revision": base_revision,
        "device": device,
        "training_examples_count": len(train_examples),
        "arms": {
            "N_A": res_na,
            "N_B": res_nb,
        },
        "comparison": {
            "initial_loss_delta": round(res_na["initial_loss"] - res_nb["initial_loss"], 4),
            "final_loss_delta": round(res_na["final_loss"] - res_nb["final_loss"], 4),
            "loss_reduction_pct_delta": round(res_na["loss_reduction_pct"] - res_nb["loss_reduction_pct"], 2),
            "wall_time_delta_seconds": round(res_na["wall_time_seconds"] - res_nb["wall_time_seconds"], 2),
        },
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(full_results, indent=2), encoding="utf-8")
    print(f"\nSaved training campaign results to: {RESULTS_PATH}")
    return full_results


if __name__ == "__main__":
    run_h3_native_training_campaign()
