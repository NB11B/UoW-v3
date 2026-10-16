"""Frozen causal-LM neuron ablation test; sequence-level scoring; UOW-NATIVE-1."""
import argparse
from contextlib import contextmanager
import json
import math
import os
import platform
import random
import sys
import time
import torch

TEMPLATES = [
    "Which number is larger: {a} or {b}? Answer with the number only.",
    "Select the maximum of {a} and {b}. Reply with its numeral.",
    "A comparison of {a} versus {b}: give only the greater value.",
]


def rows(seed, count, template):
    rng = random.Random(seed)
    seen, result = set(), []
    while len(result) < count:
        lo, hi = sorted(rng.sample(range(10, 95), 2))
        a, b = (hi, lo) if len(result) % 2 == 0 else (lo, hi)
        if (a, b) in seen:
            continue
        seen.add((a, b))
        result.append((TEMPLATES[template].format(a=a, b=b), str(hi), str(lo)))
    return result


def independent_splits(seed, sizes=(24, 48, 48)):
    """Disjoint unordered numeric pairs, even across prompt-template shifts."""
    rng = random.Random(seed)
    universe = [(a, b) for a in range(10, 95) for b in range(a + 1, 95)]
    if sum(sizes) > len(universe):
        raise ValueError("Requested more distinct pairs than available")
    rng.shuffle(universe)
    out = []
    offset = 0
    for template, count in enumerate(sizes):
        partition = []
        for j, (lo, hi) in enumerate(universe[offset:offset + count]):
            a, b = (hi, lo) if j % 2 == 0 else (lo, hi)
            partition.append((TEMPLATES[template].format(a=a, b=b), str(hi), str(lo)))
        out.append(partition)
        offset += count
    return tuple(out)


def rank_p_value(effect, controls):
    if not controls:
        raise ValueError("At least one control is required")
    return (1 + sum(value >= effect for value in controls)) / (1 + len(controls))


def projections(model):
    return [(n, m) for n, m in model.named_modules() if n.endswith("mlp.down_proj") and hasattr(m, "in_features")]


@contextmanager
def ablate(module, index):
    def hook(_, args):
        x = args[0].clone()
        x[..., index] = 0
        return (x, *args[1:])
    handle = module.register_forward_pre_hook(hook)
    try:
        yield
    finally:
        handle.remove()


def validate_revision_sha(revision: str) -> str:
    if not revision or not isinstance(revision, str):
        raise ValueError("Specify immutable model revision SHA")
    rev = revision.strip().lower()
    if len(rev) != 40 or not all(c in "0123456789abcdef" for c in rev):
        raise ValueError("Specify 40-character hexadecimal model revision SHA")
    return rev


def score_sequence(model, tokenizer, prompt: str, candidate: str, device, separator: str = " ") -> dict:
    """Teacher-forced sequence log-likelihood for prompt + candidate continuation.

    Calculates: L(candidate | prompt) = sum_{i=1}^m log p(a_i | prompt, a_1, ..., a_{i-1}).
    """
    if not prompt:
        raise ValueError("Prompt cannot be empty")
    if candidate is None or candidate == "":
        raise ValueError("Candidate answer cannot be empty")

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

    # Logits at position i predict token at position i+1.
    # Position n-1 (last prompt token) predicts token n (first continuation token).
    # Position L-2 predicts token L-1 (last continuation token).
    logits_slice = logits[0, n - 1:L - 1, :]
    target_tokens = input_ids[0, n:L]

    log_probs = torch.log_softmax(logits_slice, dim=-1)
    token_log_probs = log_probs.gather(dim=-1, index=target_tokens.unsqueeze(-1)).squeeze(-1)

    if not torch.isfinite(token_log_probs).all():
        raise ValueError("Nonfinite likelihood encountered")

    summed_ll = float(token_log_probs.sum().item())
    norm_ll = float(token_log_probs.mean().item())

    if not math.isfinite(summed_ll) or not math.isfinite(norm_ll):
        raise ValueError("Nonfinite likelihood encountered")

    return {
        "summed_log_likelihood": summed_ll,
        "normalized_log_likelihood": norm_ll,
        "continuation_tokens": continuation_tokens,
        "continuation_length": m,
    }


def measure(model, tokenizer, prompts, device, layer=None, neuron=None, separator: str = " "):
    if not prompts:
        raise ValueError("Prompts list cannot be empty")

    correct = 0.0
    norm_correct = 0.0
    total_margin = 0.0
    total_norm_margin = 0.0
    margins = []
    norm_margins = []
    ties = 0

    for prompt, positive, negative in prompts:
        if layer is not None and neuron is not None:
            with ablate(layer, neuron):
                res_pos = score_sequence(model, tokenizer, prompt, positive, device, separator)
                res_neg = score_sequence(model, tokenizer, prompt, negative, device, separator)
        else:
            res_pos = score_sequence(model, tokenizer, prompt, positive, device, separator)
            res_neg = score_sequence(model, tokenizer, prompt, negative, device, separator)

        margin = res_pos["summed_log_likelihood"] - res_neg["summed_log_likelihood"]
        norm_margin = res_pos["normalized_log_likelihood"] - res_neg["normalized_log_likelihood"]

        if not math.isfinite(margin) or not math.isfinite(norm_margin):
            raise ValueError("Nonfinite margin encountered")

        if margin > 0:
            correct += 1.0
        elif margin == 0.0:
            ties += 1
            correct += 0.5
        else:
            correct += 0.0

        if norm_margin > 0:
            norm_correct += 1.0
        elif norm_margin == 0.0:
            norm_correct += 0.5
        else:
            norm_correct += 0.0

        total_margin += margin
        total_norm_margin += norm_margin
        margins.append(margin)
        norm_margins.append(norm_margin)

    n = len(prompts)
    return {
        "accuracy": correct / n,
        "margin": total_margin / n,
        "normalized_accuracy": norm_correct / n,
        "normalized_margin": total_norm_margin / n,
        "margins": margins,
        "normalized_margins": norm_margins,
        "ties": ties,
    }


def run_probe(
    model_name: str,
    revision: str,
    seed: int,
    sizes=(24, 48, 48),
    candidate_count: int = 32,
    device: str = None,
):
    rev = validate_revision_sha(revision)
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    from transformers import AutoModelForCausalLM, AutoTokenizer

    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    start_time = time.time()
    tokenizer = AutoTokenizer.from_pretrained(model_name, revision=rev, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(model_name, revision=rev, trust_remote_code=False).to(device).eval()
    for param in model.parameters():
        param.requires_grad_(False)

    layers = projections(model)
    if not layers:
        raise ValueError("Model has no supported mlp.down_proj")
    name, layer = layers[-1]

    selection, holdout, shifted = independent_splits(seed, tuple(sizes))
    rng = random.Random(seed + 31337)
    candidates = sorted(rng.sample(range(layer.in_features), min(candidate_count, layer.in_features)))
    if len(candidates) < 2:
        raise ValueError("Need at least two sampled neurons")

    train_base = measure(model, tokenizer, selection, device)
    deltas = [(abs(train_base["margin"] - measure(model, tokenizer, selection, device, layer, i)["margin"]), i) for i in candidates]
    selected = max(deltas, key=lambda t: (t[0], -t[1]))[1]

    baseline = measure(model, tokenizer, holdout, device)
    intervention = measure(model, tokenizer, holdout, device, layer, selected)
    shift_base = measure(model, tokenizer, shifted, device)
    shift_intervention = measure(model, tokenizer, shifted, device, layer, selected)

    # Signed effect: baseline margin minus intervention margin (positive means ablation degraded accuracy/margin)
    signed_effect = float(baseline["margin"] - intervention["margin"])
    absolute_effect = abs(signed_effect)

    control_signed_effects = []
    control_absolute_effects = []
    for i in candidates:
        if i != selected:
            c_res = measure(model, tokenizer, holdout, device, layer, i)
            c_signed = float(baseline["margin"] - c_res["margin"])
            control_signed_effects.append(c_signed)
            control_absolute_effects.append(abs(c_signed))

    control_rank_p = rank_p_value(absolute_effect, control_absolute_effects)
    signed_control_rank_p = rank_p_value(signed_effect, control_signed_effects)

    norm_signed_effect = float(baseline["normalized_margin"] - intervention["normalized_margin"])
    norm_absolute_effect = abs(norm_signed_effect)

    elapsed = time.time() - start_time

    report = {
        "campaign": "UOW-NATIVE-1 Stage 2",
        "model": model_name,
        "revision": rev,
        "seed": seed,
        "sizes": list(sizes),
        "layer": name,
        "neuron": selected,
        "candidates": len(candidates),
        "candidate_neurons": candidates,
        "selection_train_only": True,
        "baseline": baseline,
        "intervention": intervention,
        "shift_baseline": shift_base,
        "shift_intervention": shift_intervention,
        "holdout_margin_effect": absolute_effect,
        "signed_effect": signed_effect,
        "absolute_effect": absolute_effect,
        "random_control_margin_effects": control_absolute_effects,
        "control_signed_effects": control_signed_effects,
        "control_absolute_effects": control_absolute_effects,
        "control_rank_p": control_rank_p,
        "descriptive_control_rank_fraction": control_rank_p,
        "signed_control_rank_p": signed_control_rank_p,
        "exploratory_control_rank_below_0_05": control_rank_p < 0.05,
        "sensitivity_normalized": {
            "baseline_normalized_margin": baseline["normalized_margin"],
            "baseline_normalized_accuracy": baseline["normalized_accuracy"],
            "intervention_normalized_margin": intervention["normalized_margin"],
            "intervention_normalized_accuracy": intervention["normalized_accuracy"],
            "normalized_signed_effect": norm_signed_effect,
            "normalized_absolute_effect": norm_absolute_effect,
            "shift_baseline_normalized_margin": shift_base["normalized_margin"],
            "shift_intervention_normalized_margin": shift_intervention["normalized_margin"],
        },
        "elapsed_seconds": round(elapsed, 2),
        "hardware": {
            "platform": platform.platform(),
            "device": device,
            "cuda_device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() and device.startswith("cuda") else None,
        },
        "statistical_warning": "Selected and comparison neurons are not exchangeable; rank is descriptive, not a valid confirmatory p-value.",
        "limitations": "Neural intervention only; not UoW conformance or isolated capability.",
    }
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="HuggingFaceTB/SmolLM2-135M-Instruct")
    p.add_argument("--revision", required=True)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--sizes", type=int, nargs=3, default=(24, 48, 48))
    p.add_argument("--candidates", type=int, default=32)
    p.add_argument("--device", default=None)
    p.add_argument("--output", default="pretrained_report.json")
    args = p.parse_args()

    report = run_probe(
        model_name=args.model,
        revision=args.revision,
        seed=args.seed,
        sizes=tuple(args.sizes),
        candidate_count=args.candidates,
        device=args.device,
    )
    result = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        out_dir = os.path.dirname(os.path.abspath(args.output))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(args.output, "w", encoding="utf8") as file:
            file.write(result + "\n")
    print(result)


if __name__ == "__main__":
    main()
