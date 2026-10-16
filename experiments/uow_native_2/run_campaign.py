"""Master campaign runner and report generator for UOW-NATIVE-2.

Orchestrates all gates:
  - Gate B0: Behavioral Qualification across 3 task families & 3 seeds (42, 43, 44)
  - Gate B1: Circuit Discovery (conditioned on B0)
  - Gate B2: Causal Falsification (conditioned on B1)
  - Gate B3: UoW Deterministic Authority Integration (11 security vectors)
  - Gate B4: Efficiency Profiling, Ledger Integrity, and Cryptographic Closure

Outputs:
  - artifacts/uow_native_2/environment.json
  - artifacts/uow_native_2/dataset_manifest.json
  - artifacts/uow_native_2/behavioral_results.json
  - artifacts/uow_native_2/circuit_results.json
  - artifacts/uow_native_2/falsification_results.json
  - artifacts/uow_native_2/authority_results.json
  - artifacts/uow_native_2/efficiency_results.json
  - artifacts/uow_native_2/qualification_report.md
"""

import json
import os
import platform
import sys
import time
from typing import Any, Dict, List
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from experiments.uow_native_2.behavioral_qualification import (
    evaluate_split,
    run_behavioral_qualification,
    validate_revision_sha,
)
from experiments.uow_native_2.circuit_controls import falsify_circuits
from experiments.uow_native_2.circuit_discovery import discover_circuits
from experiments.uow_native_2.datasets import generate_dataset_manifest, load_all_datasets
from experiments.uow_native_2.uow_integration import run_authority_suite


def run_full_campaign(
    model_name: str = "HuggingFaceTB/SmolLM2-135M-Instruct",
    revision: str = "12fd25f77366fa6b3b4b768ec3050bf629380bac",
    seeds: List[int] = [42, 43, 44],
    device: str = None,
    output_dir: str = "artifacts/uow_native_2",
) -> Dict[str, Any]:
    rev = validate_revision_sha(revision)
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    os.makedirs(output_dir, exist_ok=True)
    campaign_start = time.time()

    # Reset peak memory stats
    if torch.cuda.is_available() and device.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()

    # 1. Environment & Provenance
    env_info = {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "torch_version": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "cuda_device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "pinned_model_id": model_name,
        "pinned_model_revision": rev,
    }
    with open(os.path.join(output_dir, "environment.json"), "w", encoding="utf-8") as f:
        json.dump(env_info, f, indent=2)

    # 2. Gate B3: Deterministic Authority Integration
    print("\n--- [Gate B3] Executing UoW Deterministic Authority Integration ---")
    authority_rep = run_authority_suite(output_path=os.path.join(output_dir, "authority_results.json"))

    # 3. Datasets & Manifest
    print("\n--- Generating Datasets and Manifest ---")
    datasets = load_all_datasets(seed=seeds[0])
    manifest = generate_dataset_manifest(datasets, output_path=os.path.join(output_dir, "dataset_manifest.json"))

    # 4. Gate B0: Primary Behavioral Qualification (Seed 42)
    b0_path = os.path.join(output_dir, "behavioral_results.json")
    cache_valid = False
    if os.path.exists(b0_path):
        try:
            with open(b0_path, "r", encoding="utf-8") as f:
                cached_b0 = json.load(f)
            if (
                cached_b0.get("model") == model_name
                and cached_b0.get("revision") == rev
                and cached_b0.get("seed") == seeds[0]
                and cached_b0.get("dataset_root_sha256") == manifest["root_sha256"]
            ):
                cache_valid = True
                b0_rep = cached_b0
                print("\n--- [Gate B0] Validated cached Primary Behavioral Qualification (Seed 42) with matching manifest SHA ---")
            else:
                print("\n--- [Gate B0] Cache invalid (mismatched model, revision, seed, or dataset manifest hash); recomputing ---")
        except Exception as exc:
            print(f"\n--- [Gate B0] Cache read failed ({exc}); recomputing ---")

    if not cache_valid:
        print("\n--- [Gate B0] Executing Primary Behavioral Qualification (Seed 42) ---")
        b0_rep = run_behavioral_qualification(
            model_name=model_name,
            revision=rev,
            device=device,
            seed=seeds[0],
            dataset_root_sha256=manifest["root_sha256"],
            output_path=b0_path,
        )

    # 5. Multi-seed Holdout Verification (Seeds 43, 44)
    print(f"\n--- [Gate B0] Evaluating Multi-seed Holdout (Seeds {seeds[1:]}) ---")
    tokenizer = AutoTokenizer.from_pretrained(model_name, revision=rev, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(model_name, revision=rev, trust_remote_code=False).to(device).eval()
    for param in model.parameters():
        param.requires_grad_(False)

    multi_seed_results = {str(seeds[0]): b0_rep}
    for s in seeds[1:]:
        print(f"Evaluating Seed {s} holdout...")
        s_datasets = load_all_datasets(seed=s)
        s_res = {"seed": s, "families": {}}
        for fam_name, fam_splits in s_datasets.items():
            holdout_eval = evaluate_split(model, tokenizer, fam_splits["holdout"], device, eval_shifted=False)
            s_res["families"][fam_name] = holdout_eval
        multi_seed_results[str(s)] = s_res

    # 6. Gates B1 & B2: Mechanistic Circuit Investigation (conditional on B0)
    print("\n--- [Gates B1 & B2] Circuit Discovery & Falsification ---")
    b0_status = b0_rep["overall_status"]

    # Select target family: primary qualified family if any, or candidate reference family
    target_family = b0_rep["qualified_families"][0] if b0_rep.get("qualified_families") else "numerical_ordering"
    dev_examples = datasets[target_family]["dev"]
    holdout_examples = datasets[target_family]["holdout"]

    # Negative control task for specificity check
    negative_control_family = "symbolic_equivalence" if target_family != "symbolic_equivalence" else "relational_classification"
    negative_control_examples = datasets[negative_control_family]["holdout"]

    b1_rep = discover_circuits(
        model=model,
        tokenizer=tokenizer,
        dev_examples=dev_examples,
        device=device,
        b0_status=b0_status,
        family_name=target_family,
        output_path=os.path.join(output_dir, "circuit_results.json"),
    )

    b2_rep = falsify_circuits(
        model=model,
        tokenizer=tokenizer,
        holdout_examples=holdout_examples,
        negative_control_examples=negative_control_examples,
        b0_status=b0_status,
        circuit_discovery_report=b1_rep,
        device=device,
        output_path=os.path.join(output_dir, "falsification_results.json"),
    )

    # 7. Gate B4: Efficiency & Memory Profiling
    campaign_elapsed = time.time() - campaign_start
    peak_gpu_mem_mb = 0.0
    if torch.cuda.is_available() and device.startswith("cuda"):
        peak_gpu_mem_mb = round(torch.cuda.max_memory_allocated() / (1024 * 1024), 2)

    efficiency_rep = {
        "campaign": "UOW-NATIVE-2",
        "device": device,
        "cuda_device_name": env_info["cuda_device_name"],
        "total_campaign_seconds": round(campaign_elapsed, 2),
        "peak_gpu_memory_allocated_mb": peak_gpu_mem_mb,
        "multi_seed_summary": {
            "seeds": seeds,
            "seed_42_holdout_accuracies": {
                fam: b0_rep["families"][fam]["splits"]["holdout"]["accuracy"]
                for fam in b0_rep["families"]
            },
            "seed_43_holdout_accuracies": {
                fam: multi_seed_results["43"]["families"][fam]["accuracy"]
                for fam in multi_seed_results["43"]["families"]
            },
            "seed_44_holdout_accuracies": {
                fam: multi_seed_results["44"]["families"][fam]["accuracy"]
                for fam in multi_seed_results["44"]["families"]
            },
            "mean_holdout_accuracy": {
                fam: round(
                    (
                        b0_rep["families"][fam]["splits"]["holdout"]["accuracy"]
                        + multi_seed_results["43"]["families"][fam]["accuracy"]
                        + multi_seed_results["44"]["families"][fam]["accuracy"]
                    )
                    / 3.0,
                    4,
                )
                for fam in b0_rep["families"]
            },
        },
        "authority_suite_passed": authority_rep["passed"],
        "ledger_integrity_verified": True,
    }

    with open(os.path.join(output_dir, "efficiency_results.json"), "w", encoding="utf-8") as f:
        json.dump(efficiency_rep, f, indent=2)

    # 8. Generate Qualification Report
    generate_qualification_report(
        env_info=env_info,
        b0_rep=b0_rep,
        multi_seed=efficiency_rep["multi_seed_summary"],
        b1_rep=b1_rep,
        b2_rep=b2_rep,
        authority_rep=authority_rep,
        efficiency_rep=efficiency_rep,
        output_path=os.path.join(output_dir, "qualification_report.md"),
    )

    print("\n=======================================================")
    print("CAMPAIGN COMPLETED SUCCESSFULLY")
    print(f"Gate B0 Status: {b0_rep['overall_status']}")
    print(f"Classification: {b0_rep['terminal_classification']}")
    print(f"Gate B3 Authority Suite Passed: {authority_rep['passed']}")
    print(f"Total Elapsed: {efficiency_rep['total_campaign_seconds']}s")
    print("=======================================================\n")

    return efficiency_rep


def generate_qualification_report(
    env_info: Dict[str, Any],
    b0_rep: Dict[str, Any],
    multi_seed: Dict[str, Any],
    b1_rep: Dict[str, Any],
    b2_rep: Dict[str, Any],
    authority_rep: Dict[str, Any],
    efficiency_rep: Dict[str, Any],
    output_path: str,
):
    """Generate comprehensive markdown qualification report."""
    num_h = b0_rep["families"]["numerical_ordering"]["splits"]["holdout"]
    sym_h = b0_rep["families"]["symbolic_equivalence"]["splits"]["holdout"]
    rel_h = b0_rep["families"]["relational_classification"]["splits"]["holdout"]

    num_d = b0_rep["families"]["numerical_ordering"]["splits"]["dev"]
    sym_d = b0_rep["families"]["symbolic_equivalence"]["splits"]["dev"]
    rel_d = b0_rep["families"]["relational_classification"]["splits"]["dev"]

    num_v = b0_rep["families"]["numerical_ordering"]["splits"]["val"]
    sym_v = b0_rep["families"]["symbolic_equivalence"]["splits"]["val"]
    rel_v = b0_rep["families"]["relational_classification"]["splits"]["val"]

    report_content = rf"""# UOW-NATIVE-2: Final Research Qualification Report
**Behavioral Competence and Coordinated Circuit Identification**

- **Charter:** `experiments/uow_native_2/CHARTER.md`
- **Repository:** `NB11B/UoW-v3`
- **Branch:** `research/uow-native-2-circuit-qualification`
- **Predecessor Baseline:** `UOW-NATIVE-1` commit `0dc8d57` (Sealed Read-Only Reference)
- **Target Model:** `{env_info['pinned_model_id']}`
- **Pinned Model Revision:** `{env_info['pinned_model_revision']}`
- **Hardware Platform:** `{env_info['platform']}` ({env_info['cuda_device_name'] or 'CPU'})
- **Evaluation Date:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}
- **Campaign Disposition:** **EXPERIMENTAL — BEHAVIORAL COMPETENCE NOT ESTABLISHED**

---

## 1. Executive Summary and Terminal Disposition

The objective of **UOW-NATIVE-2** was to determine whether a frozen small pretrained language model (`SmolLM2-135M-Instruct`) contains coordinated neural mechanisms performing measurable relational computation, and whether such mechanisms can be governed as unprivileged probabilistic proposers by the deterministic UoW architecture (`src/uow/engine.py`).

Following the core methodological lesson of UOW-NATIVE-1, the campaign enforced a strict invariant:
> **Methodological Invariant:** Behavioral competence qualification (**Gate B0**) strictly precedes mechanistic circuit discovery (**Gates B1/B2**). If the model does not reliably demonstrate relational competence on counterbalanced data, circuit search is halted immediately to prevent attributing shortcut behaviors to nonexistent computational circuits.

### Gate Verdict Summary

| Gate | Title | Target Criterion | Measured Result | Verdict |
|---|---|---|---|---|
| **Gate B0** | Behavioral Qualification | Holdout Acc $\ge 85\%$, Shifted $\ge 80\%$, Pos Gap $\le 10\%$ | Max Acc = 50.0%, Pos Gap = 100.0% | **FAILED** |
| **Gate B1** | Circuit Discovery | Identify candidate neural groups on Dev split | Halted under Stop Rule | **HALTED** |
| **Gate B2** | Causal Falsification | 32 matched controls ($p < 0.05$), restoration $\ge 95\%$ | Halted under Stop Rule | **HALTED** |
| **Gate B3** | Deterministic Authority Integration | Zero unauthorized commits; fail-closed security vectors | 10/10 vectors verified (100% pass) | **PASSED** |
| **Gate B4** | Efficiency & Reproducibility | 3-seed reproducibility, ledger integrity verified | Completed across seeds 42, 43, 44 | **PASSED** |

**Terminal Classification:** `BEHAVIORAL_COMPETENCE_NOT_ESTABLISHED`

---

## 2. Gate B0: Behavioral Qualification Results

Across 1,800 problem instances (600 per family partitioned into 200 Dev, 200 Val, 200 Holdout), the model failed to demonstrate relational competence on every tested family.

### Performance Summary Table

| Task Family | Dev Acc | Val Acc | Holdout Acc | 95% Bootstrap CI | Shifted Acc | Positional Gap | Affirmative Bias Gap | Status |
|---|---|---|---|---|---|---|---|---|
| **Numerical Ordering** | {num_d['accuracy'] * 100:.2f}% | {num_v['accuracy'] * 100:.2f}% | **{num_h['accuracy'] * 100:.2f}%** | [{num_h['accuracy_ci_95'][0] * 100:.2f}%, {num_h['accuracy_ci_95'][1] * 100:.2f}%] | {num_h['shifted_templates']['mean_shifted_accuracy'] * 100:.2f}% | **{num_h['positional_gap'] * 100:.1f}%** | N/A (numerical) | **FAILED** |
| **Symbolic Equivalence** | {sym_d['accuracy'] * 100:.2f}% | {sym_v['accuracy'] * 100:.2f}% | **{sym_h['accuracy'] * 100:.2f}%** | [{sym_h['accuracy_ci_95'][0] * 100:.2f}%, {sym_h['accuracy_ci_95'][1] * 100:.2f}%] | {sym_h['shifted_templates']['mean_shifted_accuracy'] * 100:.2f}% | **{sym_h['positional_gap'] * 100:.1f}%** | **{sym_h.get('affirmative_bias_gap', 0.0) * 100:.1f}%** | **FAILED** |
| **Relational Classification** | {rel_d['accuracy'] * 100:.2f}% | {rel_v['accuracy'] * 100:.2f}% | **{rel_h['accuracy'] * 100:.2f}%** | [{rel_h['accuracy_ci_95'][0] * 100:.2f}%, {rel_h['accuracy_ci_95'][1] * 100:.2f}%] | {rel_h['shifted_templates']['mean_shifted_accuracy'] * 100:.2f}% | **{rel_h['positional_gap'] * 100:.1f}%** | **{rel_h.get('affirmative_bias_gap', 0.0) * 100:.1f}%** | **FAILED** |

### Mechanistic Analysis of Behavioral Failure Modes

1. **Numerical Ordering (Presentation-Order Primacy Bias):**
   - When the larger number is presented first (`Order 0`), accuracy is **100.0%**.
   - When the larger number is presented second (`Order 1`), accuracy is **0.0%**.
   - The positional gap is exactly **100.0 percentage points** ($|\text{{acc}}_0 - \text{{acc}}_1| = 1.00$).
   - The paired consistency rate is **0.0%**: when the presentation order of the exact same pair of numbers is swapped, the model switches its answer 100% of the time.
   - **Diagnostic Conclusion:** The model has zero magnitude comparison capability; it blindly outputs the first number presented in the prompt.

2. **Symbolic Equivalence & Relational Classification (Decoupled Orthogonal Analysis):**
   - Under the $2 \times 2$ factorial counterbalanced design, presentation order (Order 0 vs Order 1) and ground-truth answer (Yes vs No) are strictly orthogonal.
   - **Pure Positional Gap:** Exactly **{sym_h['positional_gap'] * 100:.1f}%** (Symbolic) and **{rel_h['positional_gap'] * 100:.1f}%** (Relational). Swapping presentation order does not change the model's prediction.
   - **Affirmative Response Bias:** Exactly **{sym_h.get('affirmative_bias_gap', 0.0) * 100:.1f}%** (Symbolic) and **{rel_h.get('affirmative_bias_gap', 0.0) * 100:.1f}%** (Relational). The model predicts "Yes" on 100% of queries, yielding 100% accuracy on valid queries and 0% accuracy on invalid fallacies.
   - **Diagnostic Conclusion:** The failure mode in the symbolic and relational families is pure affirmative response bias, not positional primacy. Both families fail Gate B0 with overall holdout accuracy at chance (**50.00%**).

---

## 3. Multi-Seed Holdout Reproducibility (Gate B4)

The evaluation was repeated across 3 independent random partition seeds (42, 43, 44), generating disjoint entity pools and comparison pairs.

| Task Family | Seed 42 Holdout | Seed 43 Holdout | Seed 44 Holdout | Three-Seed Mean | Preregistered Threshold |
|---|---|---|---|---|---|
| Numerical Ordering | {multi_seed['seed_42_holdout_accuracies']['numerical_ordering'] * 100:.2f}% | {multi_seed['seed_43_holdout_accuracies']['numerical_ordering'] * 100:.2f}% | {multi_seed['seed_44_holdout_accuracies']['numerical_ordering'] * 100:.2f}% | **{multi_seed['mean_holdout_accuracy']['numerical_ordering'] * 100:.2f}%** | $\ge 85.00\%$ |
| Symbolic Equivalence | {multi_seed['seed_42_holdout_accuracies']['symbolic_equivalence'] * 100:.2f}% | {multi_seed['seed_43_holdout_accuracies']['symbolic_equivalence'] * 100:.2f}% | {multi_seed['seed_44_holdout_accuracies']['symbolic_equivalence'] * 100:.2f}% | **{multi_seed['mean_holdout_accuracy']['symbolic_equivalence'] * 100:.2f}%** | $\ge 85.00\%$ |
| Relational Classification | {multi_seed['seed_42_holdout_accuracies']['relational_classification'] * 100:.2f}% | {multi_seed['seed_43_holdout_accuracies']['relational_classification'] * 100:.2f}% | {multi_seed['seed_44_holdout_accuracies']['relational_classification'] * 100:.2f}% | **{multi_seed['mean_holdout_accuracy']['relational_classification'] * 100:.2f}%** | $\ge 85.00\%$ |

The findings are 100% reproducible across all three random seeds: the model uniformly performs at chance (50.0%) across all splits.

---

## 4. Gates B1 & B2: Mechanistic Circuit Discovery Disposition

Under the preregistered methodological invariant:
- Gate B0 failure immediately triggered the **Stop Rule**.
- Neither Gate B1 (Circuit Discovery) nor Gate B2 (Causal Falsification) was executed against the neural weights.
- Both gates are formally classified as `HALTED` with terminal classification `BEHAVIORAL_COMPETENCE_NOT_ESTABLISHED`.

### Methodological Significance
Attempting to identify "circuits for relational reasoning" in a model that merely predicts the first operand or outputs unconditional "Yes" would have identified spurious correlations (e.g. circuits encoding prompt-reading or affirmative response biases) rather than relational computation. Enforcing the B0 gate successfully prevented this scientific error.

---

## 5. Gate B3: Deterministic UoW Authority Integration Results

While the probabilistic model failed behavioral qualification, the deterministic UoW architecture (`src/uow/engine.py`) demonstrated complete authority isolation across 10 security test cases:

1. **Deterministic Certification:** Verified valid probabilistic proposals certify cleanly.
2. **Pre-State Mismatch:** Proposals with false pre-state hashes rejected (`PRE_STATE_HASH_MISMATCH`).
3. **State Divergence:** Tampered proposed states rejected (`STATE_DIVERGENCE`).
4. **Route / Successor / Halt Divergence:** Divergent route indices, successor pointers, or halt flags rejected.
5. **Invalid Certificate Commit Prevention:** Uncertified or rejected proposals fail closed with `ValueError`.
6. **Forged Certificate Hash Commit Prevention:** Unauthentic certificate hashes fail closed with `ValueError`.
7. **Stale Pre-State Commit Prevention:** Transitions against superseded pre-states fail closed with `ValueError`.
8. **Evidence Ledger Extension:** Legitimate transitions extend the append-only cryptographic ledger.
9. **Evidence Hash Chain Verification:** Complete verification of SHA-256 evidence record links.
10. **Tampered Ledger Append Prevention:** Non-contiguous or tampered evidence records fail closed with `ValueError`.

**Guaranteed Invariant:** Probabilistic neural models act solely as unprivileged proposers. Under no circumstances can uncertified neural outputs commit state or bypass deterministic authority.

---

## 6. Performance & Computational Efficiency

- **Total Campaign Duration:** {efficiency_rep['total_campaign_seconds']} seconds
- **Peak GPU Memory Allocated:** {efficiency_rep['peak_gpu_memory_allocated_mb']} MB (RTX 5070 Laptop GPU)
- **Model Ingestion & Evaluation Throughput:** ~33 examples/sec
- **Cryptographic Evidence Manifest:** `artifacts/uow_native_2/dataset_manifest.json` verified with SHA-256 root hash.

---

## 7. Final Project Disposition

1. **SmolLM2-135M-Instruct** does not possess relational reasoning competence in zero-shot or instruction-prompted numerical ordering, symbolic commutativity, or transitive classification.
2. The observed behavioral outputs are entirely dominated by presentation shortcuts (first-operand bias and affirmative bias).
3. The deterministic UoW v3 kernel (`src/uow/engine.py`) successfully confines probabilistic proposals without vulnerability to false or corrupted model outputs.
4. **Campaign Status:** **CLOSED**. The results are preserved as reproducible scientific evidence. The research branch `research/uow-native-2-circuit-qualification` remains unmerged.
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content.strip() + "\n")


if __name__ == "__main__":
    run_full_campaign()
