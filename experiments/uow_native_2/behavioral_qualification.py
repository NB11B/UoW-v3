"""Behavioral qualification suite (Gate B0) for UOW-NATIVE-2.

Evaluates frozen language model on three relational task families using
teacher-forced sequence log-likelihood scoring with strict prefix-boundary validation.

Gate B0 Qualification Criteria (per family):
  1. Holdout Accuracy >= 0.85
  2. Shifted-Template Accuracy >= 0.80
  3. Positional Accuracy Gap (|acc_order0 - acc_order1|) <= 0.10

Methodological Invariant:
  If all 3 families fail Gate B0, mechanistic search (Gates B1/B2) is halted immediately
  and recorded as BEHAVIORAL_COMPETENCE_NOT_ESTABLISHED.
"""

from dataclasses import asdict, dataclass
import json
import math
import os
import random
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from experiments.uow_native_2.datasets import Example, load_all_datasets


def validate_revision_sha(revision: str) -> str:
    """Validate 40-character hexadecimal model revision SHA."""
    if not revision or not isinstance(revision, str):
        raise ValueError("Specify immutable model revision SHA")
    rev = revision.strip().lower()
    if len(rev) != 40 or not all(c in "0123456789abcdef" for c in rev):
        raise ValueError("Specify 40-character hexadecimal model revision SHA")
    return rev


def score_sequence(
    model: torch.nn.Module,
    tokenizer: Any,
    prompt: str,
    candidate: str,
    device: str,
    separator: str = " ",
) -> Dict[str, Any]:
    """Teacher-forced sequence log-likelihood for prompt + candidate continuation.

    Calculates: L(candidate | prompt) = sum_{i=1}^m log p(c_i | prompt, c_1, ..., c_{i-1}).
    Enforces strict prefix-boundary validation to prevent token re-segmentation artifacts.
    """
    if not prompt:
        raise ValueError("Prompt cannot be empty")
    if candidate is None or candidate == "":
        raise ValueError("Candidate continuation cannot be empty")

    full_text = prompt + separator + candidate
    prompt_ids = tokenizer.encode(prompt, add_special_tokens=False)
    full_ids = tokenizer.encode(full_text, add_special_tokens=False)

    n = len(prompt_ids)
    L = len(full_ids)

    if n == 0:
        raise ValueError("Prompt encoded to 0 tokens")
    if L <= n:
        raise ValueError("Empty continuation: full sequence is not longer than prompt")
    if full_ids[:n] != prompt_ids:
        raise ValueError("Prefix-boundary mismatch: encoded prompt is not an exact prefix of full sequence")

    m = L - n  # continuation length
    continuation_tokens = full_ids[n:]

    input_ids = torch.tensor([full_ids], dtype=torch.long, device=device)
    with torch.inference_mode():
        outputs = model(input_ids)
        logits = outputs.logits if hasattr(outputs, "logits") else outputs

    if logits.dim() != 3 or logits.shape[1] != L:
        raise ValueError(f"Unexpected logits shape {logits.shape}, expected (1, {L}, vocab_size)")

    # Position n-1 predicts token n (first continuation token)
    # Position L-2 predicts token L-1 (last continuation token)
    logits_slice = logits[0, n - 1 : L - 1, :]
    target_tokens = input_ids[0, n:L]

    log_probs = torch.log_softmax(logits_slice, dim=-1)
    token_log_probs = log_probs.gather(dim=-1, index=target_tokens.unsqueeze(-1)).squeeze(-1)

    if not torch.isfinite(token_log_probs).all():
        raise ValueError("Nonfinite likelihood encountered")

    summed_ll = float(token_log_probs.sum().item())
    norm_ll = summed_ll / m

    return {
        "summed_log_likelihood": summed_ll,
        "normalized_log_likelihood": norm_ll,
        "continuation_tokens": continuation_tokens,
        "continuation_length": m,
    }


def compute_bootstrap_ci(
    values: List[float], n_bootstrap: int = 1000, ci: float = 0.95, seed: int = 42
) -> Tuple[float, float]:
    """Compute non-parametric bootstrap confidence interval."""
    if not values:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    arr = np.array(values)
    n = len(arr)
    boot_means = [rng.choice(arr, size=n, replace=True).mean() for _ in range(n_bootstrap)]
    lower = float(np.percentile(boot_means, (1.0 - ci) / 2.0 * 100))
    upper = float(np.percentile(boot_means, (1.0 + ci) / 2.0 * 100))
    return (lower, upper)


def evaluate_split(
    model: torch.nn.Module,
    tokenizer: Any,
    examples: List[Example],
    device: str,
    eval_shifted: bool = True,
) -> Dict[str, Any]:
    """Evaluate a dataset partition under canonical and shifted templates."""
    if not examples:
        raise ValueError("Cannot evaluate empty split")

    correct_list = []
    norm_correct_list = []
    margins = []
    norm_margins = []
    order_0_correct = []
    order_1_correct = []
    ties = 0

    example_results = {}

    for ex in examples:
        res_pos = score_sequence(model, tokenizer, ex.prompt, ex.positive, device)
        res_neg = score_sequence(model, tokenizer, ex.prompt, ex.negative, device)

        margin = res_pos["summed_log_likelihood"] - res_neg["summed_log_likelihood"]
        norm_margin = res_pos["normalized_log_likelihood"] - res_neg["normalized_log_likelihood"]

        if margin > 0:
            c = 1.0
        elif margin == 0.0:
            c = 0.5
            ties += 1
        else:
            c = 0.0

        norm_c = 1.0 if norm_margin > 0 else (0.5 if norm_margin == 0.0 else 0.0)

        correct_list.append(c)
        norm_correct_list.append(norm_c)
        margins.append(margin)
        norm_margins.append(norm_margin)

        if ex.order == 0:
            order_0_correct.append(c)
        elif ex.order == 1:
            order_1_correct.append(c)

        example_results[ex.id] = {
            "correct": c,
            "margin": margin,
            "norm_margin": norm_margin,
            "order": ex.order,
            "ground_truth_label": ex.ground_truth_label,
            "counterpart_id": ex.counterpart_id,
        }

    # Evaluate paired consistency
    paired_consistent = 0
    total_pairs = 0
    for ex in examples:
        if ex.order == 0 and ex.counterpart_id and ex.counterpart_id in example_results:
            total_pairs += 1
            c0 = example_results[ex.id]["correct"]
            c1 = example_results[ex.counterpart_id]["correct"]
            if c0 == 1.0 and c1 == 1.0:
                paired_consistent += 1

    paired_consistency_rate = (paired_consistent / total_pairs) if total_pairs > 0 else 0.0

    acc = float(np.mean(correct_list))
    acc_ci = compute_bootstrap_ci(correct_list)
    mean_margin = float(np.mean(margins))
    margin_ci = compute_bootstrap_ci(margins)

    acc_order_0 = float(np.mean(order_0_correct)) if order_0_correct else 0.0
    acc_order_1 = float(np.mean(order_1_correct)) if order_1_correct else 0.0
    positional_gap = abs(acc_order_0 - acc_order_1)

    # Affirmative bias evaluation for binary Yes/No tasks
    yes_correct = [example_results[ex.id]["correct"] for ex in examples if ex.ground_truth_label == "Yes"]
    no_correct = [example_results[ex.id]["correct"] for ex in examples if ex.ground_truth_label == "No"]
    acc_yes = float(np.mean(yes_correct)) if yes_correct else None
    acc_no = float(np.mean(no_correct)) if no_correct else None
    affirmative_bias_gap = abs(acc_yes - acc_no) if (acc_yes is not None and acc_no is not None) else None

    # Fraction of times candidate 'Yes' was chosen (margin > 0 when Yes is positive, margin < 0 when Yes is negative)
    yes_chosen_count = 0
    binary_total = 0
    for ex in examples:
        if ex.ground_truth_label in ("Yes", "No"):
            binary_total += 1
            m = example_results[ex.id]["margin"]
            if (ex.ground_truth_label == "Yes" and m > 0) or (ex.ground_truth_label == "No" and m < 0):
                yes_chosen_count += 1
    affirmative_response_rate = (yes_chosen_count / binary_total) if binary_total > 0 else None

    result = {
        "count": len(examples),
        "accuracy": acc,
        "accuracy_ci_95": list(acc_ci),
        "mean_margin": mean_margin,
        "margin_ci_95": list(margin_ci),
        "ties": ties,
        "order_0_accuracy": acc_order_0,
        "order_1_accuracy": acc_order_1,
        "positional_gap": positional_gap,
        "paired_consistency_rate": paired_consistency_rate,
        "yes_accuracy": acc_yes,
        "no_accuracy": acc_no,
        "affirmative_bias_gap": affirmative_bias_gap,
        "affirmative_response_rate": affirmative_response_rate,
        "normalized_accuracy": float(np.mean(norm_correct_list)),
        "normalized_mean_margin": float(np.mean(norm_margins)),
    }

    # Shifted templates evaluation
    if eval_shifted and len(examples) > 0 and len(examples[0].shifted_prompts) > 0:
        num_shifts = len(examples[0].shifted_prompts)
        shifted_accs = []
        shifted_margins = []
        for s_idx in range(num_shifts):
            s_correct = []
            s_margins = []
            for ex in examples:
                if s_idx < len(ex.shifted_prompts):
                    p_shift = ex.shifted_prompts[s_idx]
                    r_pos = score_sequence(model, tokenizer, p_shift, ex.positive, device)
                    r_neg = score_sequence(model, tokenizer, p_shift, ex.negative, device)
                    m = r_pos["summed_log_likelihood"] - r_neg["summed_log_likelihood"]
                    c = 1.0 if m > 0 else (0.5 if m == 0.0 else 0.0)
                    s_correct.append(c)
                    s_margins.append(m)
            s_acc = float(np.mean(s_correct))
            shifted_accs.append(s_acc)
            shifted_margins.append(float(np.mean(s_margins)))

        result["shifted_templates"] = {
            "accuracies": shifted_accs,
            "mean_shifted_accuracy": float(np.mean(shifted_accs)),
            "margins": shifted_margins,
            "mean_shifted_margin": float(np.mean(shifted_margins)),
        }

    return result


def run_behavioral_qualification(
    model_name: str = "HuggingFaceTB/SmolLM2-135M-Instruct",
    revision: str = "12fd25f77366fa6b3b4b768ec3050bf629380bac",
    device: Optional[str] = None,
    seed: int = 42,
    dataset_root_sha256: Optional[str] = None,
    output_path: Optional[str] = "artifacts/uow_native_2/behavioral_results.json",
) -> Dict[str, Any]:
    """Execute complete Gate B0 Behavioral Qualification across 3 task families."""
    rev = validate_revision_sha(revision)
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    start_time = time.time()
    tokenizer = AutoTokenizer.from_pretrained(model_name, revision=rev, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(model_name, revision=rev, trust_remote_code=False).to(device).eval()
    for param in model.parameters():
        param.requires_grad_(False)

    datasets = load_all_datasets(seed=seed)

    qualification_report = {
        "gate": "Gate B0: Behavioral Qualification",
        "model": model_name,
        "revision": rev,
        "device": device,
        "seed": seed,
        "dataset_root_sha256": dataset_root_sha256,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "criteria": {
            "min_holdout_accuracy": 0.85,
            "min_shifted_template_accuracy": 0.80,
            "max_positional_accuracy_gap": 0.10,
        },
        "families": {},
        "overall_status": "PENDING",
        "qualified_families": [],
        "halt_rule_triggered": False,
        "terminal_classification": None,
    }

    any_passed = False

    for fam_name, fam_splits in datasets.items():
        fam_report = {"splits": {}}
        for split_name, examples in fam_splits.items():
            # Evaluate canonical and shifted on holdout; canonical on dev/val
            eval_shifted = (split_name == "holdout")
            split_res = evaluate_split(model, tokenizer, examples, device, eval_shifted=eval_shifted)
            fam_report["splits"][split_name] = split_res

        # Gate B0 Criteria check on Holdout
        holdout_res = fam_report["splits"]["holdout"]
        holdout_acc = holdout_res["accuracy"]
        shifted_acc = holdout_res.get("shifted_templates", {}).get("mean_shifted_accuracy", 0.0)
        pos_gap = holdout_res["positional_gap"]

        acc_passed = holdout_acc >= 0.85
        shifted_passed = shifted_acc >= 0.80
        gap_passed = pos_gap <= 0.10

        fam_passed = acc_passed and shifted_passed and gap_passed
        fam_report["qualification"] = {
            "passed": fam_passed,
            "holdout_accuracy": holdout_acc,
            "holdout_accuracy_passed": acc_passed,
            "shifted_accuracy": shifted_acc,
            "shifted_accuracy_passed": shifted_passed,
            "positional_gap": pos_gap,
            "positional_gap_passed": gap_passed,
        }

        if fam_passed:
            qualification_report["qualified_families"].append(fam_name)
            any_passed = True

        qualification_report["families"][fam_name] = fam_report

    elapsed = time.time() - start_time
    qualification_report["elapsed_seconds"] = round(elapsed, 2)

    if any_passed:
        qualification_report["overall_status"] = "PASSED"
        qualification_report["terminal_classification"] = "BEHAVIORAL_COMPETENCE_QUALIFIED"
        qualification_report["halt_rule_triggered"] = False
    else:
        qualification_report["overall_status"] = "FAILED"
        qualification_report["terminal_classification"] = "BEHAVIORAL_COMPETENCE_NOT_ESTABLISHED"
        qualification_report["halt_rule_triggered"] = True

    if output_path:
        out_dir = os.path.dirname(os.path.abspath(output_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(qualification_report, f, indent=2)

    return qualification_report
