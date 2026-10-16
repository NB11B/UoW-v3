"""Replaceable Model Backend Abstraction."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional
import time


class ModelBackend(ABC):
    """Abstract interface for foundation model and adapter execution engines."""

    @abstractmethod
    def load_foundation(self, model_name: str, device: str = "cuda") -> None:
        """Loads and initializes the frozen foundation model."""
        pass

    @abstractmethod
    def load_adapter(self, adapter_id: str, adapter_path: Path) -> None:
        """Loads a PEFT adapter into memory."""
        pass

    @abstractmethod
    def switch_adapter(self, adapter_id: str) -> float:
        """Switches active adapter. Returns switch latency in milliseconds."""
        pass

    @abstractmethod
    def unload_adapter(self, adapter_id: str) -> None:
        """Unloads an adapter from memory."""
        pass

    @abstractmethod
    def generate(self, prompt: str, max_tokens: int = 140) -> str:
        """Executes autoregressive generation on the active adapter."""
        pass


class PyTorchPeftBackend(ModelBackend):
    """Production backend executing PyTorch + PEFT on CUDA / CPU."""

    def __init__(self) -> None:
        self.tokenizer = None
        self.base_model = None
        self.peft_model = None
        self.device = "cuda"
        self.active_adapter_id: Optional[str] = None

    def load_foundation(self, model_name: str, device: str = "cuda") -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.device = device
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id or 0

        self.base_model = AutoModelForCausalLM.from_pretrained(
            model_name,
            trust_remote_code=True,
            dtype=torch.float32,
        ).to(device)
        self.base_model.eval()

    def load_adapter(self, adapter_id: str, adapter_path: Path) -> None:
        from peft import PeftModel

        sanitized_name = adapter_id.replace(".", "_")
        if self.peft_model is None:
            self.peft_model = PeftModel.from_pretrained(
                self.base_model,
                str(adapter_path),
                adapter_name=sanitized_name,
                is_trainable=False,
            )
            self.peft_model.to(self.device).eval()
            self.active_adapter_id = adapter_id
        else:
            self.peft_model.load_adapter(str(adapter_path), adapter_name=sanitized_name)

    def switch_adapter(self, adapter_id: str) -> float:
        import torch

        if self.peft_model is None:
            raise RuntimeError("PEFT model not initialized")

        sanitized_name = adapter_id.replace(".", "_")
        if torch.cuda.is_available() and self.device.startswith("cuda"):
            start_event = torch.cuda.Event(enable_timing=True)
            end_event = torch.cuda.Event(enable_timing=True)
            start_event.record()
            self.peft_model.set_adapter(sanitized_name)
            end_event.record()
            torch.cuda.synchronize()
            latency_ms = start_event.elapsed_time(end_event)
        else:
            t0 = time.perf_counter_ns()
            self.peft_model.set_adapter(sanitized_name)
            latency_ms = (time.perf_counter_ns() - t0) / 1_000_000.0

        self.active_adapter_id = adapter_id
        return latency_ms

    def unload_adapter(self, adapter_id: str) -> None:
        sanitized_name = adapter_id.replace(".", "_")
        if self.peft_model and hasattr(self.peft_model, "delete_adapter"):
            try:
                self.peft_model.delete_adapter(sanitized_name)
            except Exception:
                pass

    def generate(self, prompt: str, max_tokens: int = 140) -> str:
        import torch

        if self.peft_model is None or self.tokenizer is None:
            raise RuntimeError("Backend not initialized for generation")

        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        with torch.no_grad():
            output_tokens = self.peft_model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )
        gen_tokens = output_tokens[0][inputs["input_ids"].shape[1]:]
        return self.tokenizer.decode(gen_tokens, skip_special_tokens=True)


class MockModelBackend(ModelBackend):
    """Deterministic mock backend for rapid conformance testing and CI without CUDA."""

    def __init__(self, response_templates: Optional[dict[str, str]] = None) -> None:
        self.response_templates = response_templates or {}
        self.loaded_adapters: set[str] = set()
        self.active_adapter: Optional[str] = None

    def load_foundation(self, model_name: str, device: str = "cpu") -> None:
        pass

    def load_adapter(self, adapter_id: str, adapter_path: Path) -> None:
        self.loaded_adapters.add(adapter_id)
        if self.active_adapter is None:
            self.active_adapter = adapter_id

    def switch_adapter(self, adapter_id: str) -> float:
        if adapter_id not in self.loaded_adapters:
            raise KeyError(f"Adapter '{adapter_id}' not loaded in mock backend")
        t0 = time.perf_counter_ns()
        self.active_adapter = adapter_id
        return (time.perf_counter_ns() - t0) / 1_000_000.0

    def unload_adapter(self, adapter_id: str) -> None:
        self.loaded_adapters.discard(adapter_id)
        if self.active_adapter == adapter_id:
            self.active_adapter = None

    def generate(self, prompt: str, max_tokens: int = 140) -> str:
        if self.active_adapter and self.active_adapter in self.response_templates:
            return self.response_templates[self.active_adapter]
        # Default mock operational proposal
        return (
            '{"domain": "industrial", "action": "EMERGENCY_DEPRESSURIZE", '
            '"disposition": "COMMIT", "parameters": {"unit_id": "P-101"}, '
            '"guard_conditions": ["interlock_verified"], "unknowns": []}'
        )
