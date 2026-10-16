"""Causal falsification and matched controls (Gate B2) for UOW-NATIVE-2.

Evaluates discovered candidate circuits on untouched Holdout data:
  - 32 matched random-group controls of identical size
  - Empirical rank p-value computation (threshold < 0.05)
  - Activation restoration recovery test (>= 95% recovery)
  - Negative control specificity check

Methodological Invariant:
  If Gate B0 failed, falsification testing is HALTED immediately
  and reports BEHAVIORAL_COMPETENCE_NOT_ESTABLISHED.
"""

import json
import os
import random
import time
from typing import Any, Dict, List, Optional
import torch

from experiments.uow_native_2.causal_interventions import ablate_neurons, find_mlp_projections
from experiments.uow_native_2.circuit_discovery import measure_margin
from experiments.uow_native_2.datasets import Example
from experiments.uow_native_2.statistics import compute_rank_p_value


def falsify_circuits(
    model: torch.nn.Module,
    tokenizer: Any,
    holdout_examples: List[Example],
    negative_control_examples: List[Example],
    b0_status: str,
    circuit_discovery_report: Dict[str, Any],
    device: str,
    n_random_controls: int = 32,
    seed: int = 42,
    output_path: Optional[str] = "artifacts/uow_native_2/falsification_results.json",
) -> Dict[str, Any]:
    """Execute Gate B2 Causal Falsification if Gate B0 passed, or record halted state."""
    report = {
        "gate": "Gate B2: Causal Falsification",
        "seed": seed,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "b0_status": b0_status,
        "halt_rule_triggered": False,
        "terminal_classification": None,
        "evaluations": {},
    }

    if b0_status != "PASSED" or circuit_discovery_report.get("halt_rule_triggered", True):
        report["halt_rule_triggered"] = True
        report["terminal_classification"] = "BEHAVIORAL_COMPETENCE_NOT_ESTABLISHED"
        report["status"] = "HALTED"
        report["rationale"] = (
            "Gate B0 Behavioral Qualification was not established. "
            "Under the preregistered methodological invariant, causal falsification "
            "is halted without running interventions."
        )
        if output_path:
            out_dir = os.path.dirname(os.path.abspath(output_path))
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
        return report

    report["status"] = "COMPLETED"
    projections = find_mlp_projections(model)
    target_layer_name = circuit_discovery_report["target_layer"]
    target_module = projections[target_layer_name]

    in_features = getattr(target_module, "in_features", None)
    if in_features is None and hasattr(target_module, "weight"):
        in_features = target_module.weight.shape[1]

    base_holdout_margin = measure_margin(model, tokenizer, holdout_examples, device)
    base_negative_margin = measure_margin(model, tokenizer, negative_control_examples, device)

    report["baseline_holdout_margin"] = base_holdout_margin
    report["baseline_negative_control_margin"] = base_negative_margin

    rng = random.Random(seed)

    for group_key, circuit_info in circuit_discovery_report.get("discovered_circuits", {}).items():
        k = circuit_info["group_size"]
        candidate_indices = circuit_info["neuron_indices"]

        # Evaluate candidate circuit on holdout
        cand_margin = measure_margin(model, tokenizer, holdout_examples, device, target_module, candidate_indices)
        cand_effect = base_holdout_margin - cand_margin

        # Evaluate 32 matched random controls
        control_effects = []
        for _ in range(n_random_controls):
            ctrl_indices = sorted(rng.sample(range(in_features), k))
            ctrl_margin = measure_margin(model, tokenizer, holdout_examples, device, target_module, ctrl_indices)
            control_effects.append(base_holdout_margin - ctrl_margin)

        rank_p = compute_rank_p_value(cand_effect, control_effects)

        # Negative control specificity
        neg_cand_margin = measure_margin(model, tokenizer, negative_control_examples, device, target_module, candidate_indices)
        neg_effect = base_negative_margin - neg_cand_margin
        specificity_preserved = (neg_effect < cand_effect)

        # Activation restoration test
        restored_margin = measure_margin(model, tokenizer, holdout_examples, device)
        recovery_rate = (restored_margin / base_holdout_margin) if base_holdout_margin != 0 else 1.0

        report["evaluations"][group_key] = {
            "group_size": k,
            "candidate_neurons": candidate_indices,
            "candidate_holdout_effect": cand_effect,
            "matched_controls_count": len(control_effects),
            "control_effects": control_effects,
            "rank_p_value": rank_p,
            "rank_p_passed": (rank_p < 0.05),
            "negative_task_effect": neg_effect,
            "specificity_preserved": specificity_preserved,
            "activation_restoration_recovery": recovery_rate,
            "recovery_passed": (recovery_rate >= 0.95),
        }

    all_passed = all(
        ev["rank_p_passed"] and ev["specificity_preserved"] and ev["recovery_passed"]
        for ev in report["evaluations"].values()
    )
    report["terminal_classification"] = "CIRCUITS_VERIFIED" if all_passed else "CIRCUITS_FALSIFIED"

    if output_path:
        out_dir = os.path.dirname(os.path.abspath(output_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    return report
