"""Architecture A: Resident multi-adapter model with dynamic dispatch and deterministic UoW composition."""
from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from experiments.uow_grammar_1.grammars.temporal import (
    TemporalPromptBuilder, TemporalOutputParser, TemporalConstraint
)
from experiments.uow_grammar_1.grammars.recovery import (
    RecoveryPromptBuilder, RecoveryOutputParser, RecoveryPlan
)
import sys

# Ensure UoW src is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from uow.compat.v2 import (
    DeterministicSequencer,
    EvidenceLedger,
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    Proposal,
    Route,
    Successor,
    WorldState,
    certify,
    commit,
    make_uow,
)
from uow.semantic import (
    BindingOrigin,
    CandidateSemanticBindings,
    ExternalSignal,
    IngressContext,
    MinimalSemanticContext,
    SemanticBinding,
    SemanticDisposition,
    SemanticFrontierBuilder,
    SemanticRequirement,
    SemanticTranslationRequest,
)
from uow.semantic.adapters.codec import SemanticOutputParser, SemanticPromptBuilder
from uow.semantic.closure import SemanticClosureEngine

BASE = "HuggingFaceTB/SmolLM2-135M-Instruct"
REV = "12fd25f77366fa6b3b4b768ec3050bf629380bac"


class MultiGrammarHarness:
    """Manages one frozen base model with resident switchable adapters."""

    def __init__(
        self,
        op_adapter_dir: str,
        temp_adapter_dir: str,
        rec_adapter_dir: str,
        device: str = "cuda"
    ):
        self.device = device
        self.tokenizer = AutoTokenizer.from_pretrained(BASE, revision=REV, trust_remote_code=False)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id

        print(f"Loading shared frozen base model: {BASE}")
        base_model = AutoModelForCausalLM.from_pretrained(BASE, revision=REV, trust_remote_code=False).to(device).eval()
        for p in base_model.parameters():
            p.requires_grad = False

        # Load primary adapter and attach additional resident adapters
        print(f"Attaching resident adapter: operational ({op_adapter_dir})")
        self.model = PeftModel.from_pretrained(base_model, op_adapter_dir, adapter_name="operational", is_trainable=False)
        
        print(f"Attaching resident adapter: temporal ({temp_adapter_dir})")
        self.model.load_adapter(temp_adapter_dir, adapter_name="temporal")
        
        print(f"Attaching resident adapter: recovery ({rec_adapter_dir})")
        self.model.load_adapter(rec_adapter_dir, adapter_name="recovery")
        
        self.model.eval().to(device)

        # Codecs
        self.temp_prompt = TemporalPromptBuilder()
        self.temp_parser = TemporalOutputParser()
        self.rec_prompt = RecoveryPromptBuilder()
        self.rec_parser = RecoveryOutputParser()
        self.op_prompt = SemanticPromptBuilder()
        self.op_parser = SemanticOutputParser()
        self.closure_engine = SemanticClosureEngine(SemanticFrontierBuilder())

    def switch_grammar(self, grammar_name: str) -> None:
        """Dynamic switch in microsecond dispatch without reloading weights."""
        self.model.set_adapter(grammar_name)

    def _generate(self, messages: list[dict[str, str]]) -> str:
        prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=128,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id
            )
            input_len = inputs["input_ids"].shape[1]
            return self.tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True).strip()

    def parse_temporal(self, signal: str) -> Optional[TemporalConstraint]:
        self.switch_grammar("temporal")
        messages = self.temp_prompt.build_chat_messages(signal)
        raw = self._generate(messages)
        return self.temp_parser.parse(raw)

    def parse_operational(self, request: SemanticTranslationRequest) -> CandidateSemanticBindings:
        self.switch_grammar("operational")
        messages = self.op_prompt.build_chat_messages(request)
        raw = self._generate(messages)
        return self.op_parser.parse(raw, request, evidence_ref="multi_grammar_harness", fail_closed=True)

    def parse_recovery(self, signal: str) -> Optional[RecoveryPlan]:
        self.switch_grammar("recovery")
        messages = self.rec_prompt.build_chat_messages(signal)
        raw = self._generate(messages)
        return self.rec_parser.parse(raw)
