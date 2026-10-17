"""Foundation model roster and architectural configuration for Milestone P3."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FoundationSpec:
    model_id: str
    slug: str
    architecture_family: str
    model_class_name: str
    target_modules: list[str]
    fan_in_fan_out: bool = False
    requires_chat_template: bool = False
    max_len: int = 320
    learning_rate: float = 5e-4
    epochs: int = 2
    notes: str = ""


FOUNDATION_ROSTER: dict[str, FoundationSpec] = {
    "smollm2_135m": FoundationSpec(
        model_id="HuggingFaceTB/SmolLM2-135M-Instruct",
        slug="smollm2_135m",
        architecture_family="llama",
        model_class_name="LlamaForCausalLM",
        target_modules=["q_proj", "v_proj"],
        requires_chat_template=True,
        epochs=1,
        notes="Reference instruction-tuned foundation baseline qualified in P2",
    ),
    "pythia_160m": FoundationSpec(
        model_id="EleutherAI/pythia-160m",
        slug="pythia_160m",
        architecture_family="gpt_neox",
        model_class_name="GPTNeoXForCausalLM",
        target_modules=["query_key_value"],
        epochs=2,
        notes="Rotary position embeddings, parallel attention/MLP",
    ),
    "gpt_neo_125m": FoundationSpec(
        model_id="EleutherAI/gpt-neo-125m",
        slug="gpt_neo_125m",
        architecture_family="gpt_neo",
        model_class_name="GPTNeoForCausalLM",
        target_modules=["q_proj", "v_proj"],
        epochs=2,
        notes="Local/Global windowed attention",
    ),
    "cerebras_111m": FoundationSpec(
        model_id="cerebras-archive/Cerebras-GPT-111M",
        slug="cerebras_111m",
        architecture_family="gpt2",
        model_class_name="GPT2LMHeadModel",
        target_modules=["c_attn"],
        fan_in_fan_out=True,
        epochs=2,
        notes="Classic GPT-2 multi-head attention",
    ),
    "mamba_130m": FoundationSpec(
        model_id="state-spaces/mamba-130m-hf",
        slug="mamba_130m",
        architecture_family="mamba",
        model_class_name="MambaForCausalLM",
        target_modules=["in_proj", "x_proj"],
        epochs=2,
        notes="Selective state-space SSM architecture without attention matrices",
    ),
}
