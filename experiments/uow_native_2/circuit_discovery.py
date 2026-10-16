"""Circuit discovery (Gate B1) for UOW-NATIVE-2.

Conditioned on Gate B0 Behavioral Qualification.
Searches exclusively on the Development (dev) partition for candidate cooperating
neural groups (group sizes 4, 8, 16) within MLP down-projections.

Methodological Invariant:
  If Gate B0 failed, mechanistic circuit discovery is HALTED immediately
  and reports BEHAVIORAL_COMPETENCE_NOT_ESTABLISHED without running interventions.
"""

import json
import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple
import torch

from experiments.uow_native_2.causal_interventions import ablate_neurons, find_mlp_projections
from experiments.uow_native_2.datasets import Example
from experiments.uow_native_2.behavioral_qualification import score_sequence


def measure_margin(
    model: torch.nn.Module,
    tokenizer: Any,
    examples: List[Example],
    device: str,
    module: Optional[torch.nn.Module] = None,
    indices: Optional[List[int]] = None,
) -> float:
    """Measure mean margin across a set of examples, optionally with ablation."""
    total_margin = 0.0
    for ex in examples:
        if module is not None and indices:
            with ablate_neurons(module, indices):
                r_pos = score_sequence(model, tokenizer, ex.prompt, ex.positive, device)
                r_neg = score_sequence(model, tokenizer, ex.prompt, ex.negative, device)
        else:
            r_pos = score_sequence(model, tokenizer, ex.prompt, ex.positive, device)
            r_neg = score_sequence(model, tokenizer, ex.prompt, ex.negative, device)
        total_margin += (r_pos["summed_log_likelihood"] - r_neg["summed_log_likelihood"])
    return total_margin / len(examples)


def discover_circuits(
    model: torch.nn.Module,
    tokenizer: Any,
    dev_examples: List[Example],
    device: str,
    b0_status: str,
    family_name: str,
    group_sizes: Tuple[int, ...] = (4, 8, 16),
    candidate_pool_size: int = 32,
    seed: int = 42,
    output_path: Optional[str] = "artifacts/uow_native_2/circuit_results.json",
) -> Dict[str, Any]:
    """Execute Gate B1 Circuit Discovery if Gate B0 passed, or record halted state."""
    report = {
        "gate": "Gate B1: Circuit Discovery",
        "family": family_name,
        "seed": seed,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "b0_status": b0_status,
        "halt_rule_triggered": False,
        "terminal_classification": None,
        "discovered_circuits": {},
    }

    if b0_status != "PASSED":
        report["halt_rule_triggered"] = True
        report["terminal_classification"] = "BEHAVIORAL_COMPETENCE_NOT_ESTABLISHED"
        report["status"] = "HALTED"
        report["rationale"] = (
            "Gate B0 Behavioral Qualification was not established. "
            "Under the preregistered methodological invariant, mechanistic circuit discovery "
            "is halted to prevent searching for spurious circuits on tasks the model cannot reliably perform."
        )
        if output_path:
            out_dir = os.path.dirname(os.path.abspath(output_path))
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
        return report

    report["status"] = "COMPLETED"
    report["terminal_classification"] = "CIRCUITS_DISCOVERED"
    projections = find_mlp_projections(model)
    down_projs = [(k, v) for k, v in projections.items() if "down_proj" in k]
    if not down_projs:
        raise ValueError("No mlp.down_proj layers found in model")

    # Select target layer (last down_proj layer)
    target_name, target_module = down_projs[-1]
    in_features = getattr(target_module, "in_features", None)
    if in_features is None and hasattr(target_module, "weight"):
        in_features = target_module.weight.shape[1]

    rng = random.Random(seed)
    sampled_pool = sorted(rng.sample(range(in_features), min(candidate_pool_size, in_features)))

    base_dev_margin = measure_margin(model, tokenizer, dev_examples, device)
    report["baseline_dev_margin"] = base_dev_margin
    report["target_layer"] = target_name

    # Single-neuron impact scan on dev
    neuron_impacts = []
    for n_idx in sampled_pool:
        m_abl = measure_margin(model, tokenizer, dev_examples, device, target_module, [n_idx])
        drop = base_dev_margin - m_abl
        neuron_impacts.append((drop, n_idx))

    neuron_impacts.sort(reverse=True, key=lambda t: t[0])

    for k in group_sizes:
        top_k_indices = [idx for _, idx in neuron_impacts[:k]]
        abl_margin = measure_margin(model, tokenizer, dev_examples, device, target_module, top_k_indices)
        causal_drop = base_dev_margin - abl_margin
        report["discovered_circuits"][f"group_{k}"] = {
            "group_size": k,
            "neuron_indices": top_k_indices,
            "ablated_dev_margin": abl_margin,
            "causal_margin_drop": causal_drop,
        }

    if output_path:
        out_dir = os.path.dirname(os.path.abspath(output_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    return report
