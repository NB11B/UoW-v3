"""H3-N: Holdout Evaluation and Comparative Qualification Script.

Evaluates three model variants on the frozen 20 holdout cases:
1. Base M_0 (unadapted baseline, Delta W = 0)
2. Arm N-A (Fresh H3-native LoRA, M_0 -> M_H3)
3. Arm N-B (Grammar transfer LoRA, M_VG -> M_J2->H3)

Measures:
- S: valid serialization rate
- B: exact binding set rate
- D: exact disposition rate (UoW closure certificate matches expected)
- U: unsafe YES rate (false positive commitments)
- beta_D: deterministic overwrite / primacy violations
- Rates broken down by cardinality |F_P| in {1, 2, 3, 4}
- Rates broken down by behavior class: unique, composition, unknown, ambiguous
"""
from __future__ import annotations

import gc
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(PACKAGE_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT / "src"))
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from qualification.semantic.h3_native_corpus import H3NativeExample
from uow.semantic.adapters.codec import SemanticOutputParser, SemanticPromptBuilder
from uow.semantic.closure import SemanticClosureEngine
from uow.semantic.frontier import SemanticFrontierBuilder
from uow.semantic.schema import (
    BindingOrigin,
    CandidateSemanticBindings,
    ExternalSignal,
    MinimalSemanticContext,
    SemanticBinding,
    SemanticFrontierResult,
    SemanticRequirement,
    SemanticTranslationRequest,
)

MANIFEST_PATH = PACKAGE_ROOT / "qualification" / "artifacts" / "semantic_h3_native_corpus_manifest.json"
RESULTS_PATH = PACKAGE_ROOT / "qualification" / "artifacts" / "semantic_h3_native_holdout_results.json"
CHECKPOINTS_BASE = PACKAGE_ROOT / "checkpoints"

BASE_MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"
BASE_REVISION = "12fd25f77366fa6b3b4b768ec3050bf629380bac"


def evaluate_model_on_holdout(
    model_label: str,
    model: Any,
    tokenizer: Any,
    holdout_examples: list[H3NativeExample],
    device: str,
) -> dict[str, Any]:
    prompt_builder = SemanticPromptBuilder()
    output_parser = SemanticOutputParser()
    frontier_builder = SemanticFrontierBuilder()
    closure_engine = SemanticClosureEngine(frontier_builder)

    records: list[dict[str, Any]] = []

    cardinality_stats = {
        i: {"total": 0, "valid_json": 0, "exact_bindings": 0, "exact_disp": 0, "unsafe": 0}
        for i in (1, 2, 3, 4)
    }
    class_stats = {
        c: {"total": 0, "valid_json": 0, "exact_bindings": 0, "exact_disp": 0, "unsafe": 0}
        for c in ("A_unique", "B_composition", "C_unknown", "D_ambiguous")
    }

    total_cases = len(holdout_examples)
    total_valid_json = 0
    total_exact_bindings = 0
    total_exact_disp = 0
    total_unsafe_yes = 0
    total_beta_d_violations = 0
    total_frontier_violations = 0

    t0 = time.perf_counter()

    for idx, ex in enumerate(holdout_examples):
        req = ex.to_request()
        frontier_card = ex.frontier_cardinality
        b_class = ex.behavior_class

        # Generate prompt
        messages = prompt_builder.build_chat_messages(req)
        prompt_text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = tokenizer(prompt_text, return_tensors="pt").to(device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=128,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
            input_len = inputs["input_ids"].shape[1]
            raw_text = tokenizer.decode(outputs[0][input_len:], skip_special_tokens=True).strip()

        # Check serialization
        is_valid_json = False
        try:
            parsed_json = json.loads(output_parser.extract_json_text(raw_text))
            if isinstance(parsed_json, dict) and all(k in parsed_json for k in ("bindings", "alternatives", "unknowns")):
                is_valid_json = True
        except Exception:
            is_valid_json = False

        if is_valid_json:
            total_valid_json += 1

        # Strict parse via production parser (fail_closed for closure evaluation)
        cand_bindings = output_parser.parse(
            raw_text,
            req,
            evidence_ref=f"eval_{model_label}",
            fail_closed=True,
        )

        # Check frontier violation & deterministic overwrite
        frontier_names = set(ex.frontier)
        c_min_names = set(ex.context.keys())

        has_frontier_violation = any(
            b.terminal not in frontier_names for b in cand_bindings.candidate_bindings
        ) or any(u not in frontier_names for u in cand_bindings.unknowns)

        has_beta_d_overwrite = any(
            b.terminal in c_min_names for b in cand_bindings.candidate_bindings
        )

        if has_frontier_violation:
            total_frontier_violations += 1
        if has_beta_d_overwrite:
            total_beta_d_violations += 1

        # Check exact bindings
        exact_bindings = False
        if is_valid_json:
            target_b_map = {b["terminal"]: b["value"] for b in ex.target_bindings}
            actual_b_map = {b.terminal: b.value for b in cand_bindings.candidate_bindings}
            target_u_set = set(ex.target_unknowns)
            actual_u_set = set(cand_bindings.unknowns)

            if b_class in ("A_unique", "B_composition"):
                if target_b_map == actual_b_map and not cand_bindings.unknowns and not cand_bindings.alternatives:
                    exact_bindings = True
            elif b_class == "C_unknown":
                if target_u_set == actual_u_set and target_b_map == actual_b_map:
                    exact_bindings = True
            elif b_class == "D_ambiguous":
                if len(cand_bindings.alternatives) == len(ex.target_alternatives) and not cand_bindings.candidate_bindings:
                    exact_bindings = True

        if exact_bindings:
            total_exact_bindings += 1

        # Total transaction requirements = deterministic context requirements + unresolved frontier requirements
        all_reqs = tuple(SemanticRequirement(name=b.terminal) for b in req.minimal_context.bindings) + req.frontier
        init_frontier = frontier_builder.build(all_reqs, req.minimal_context)

        closure_outcome = closure_engine.close(
            signal=req.signal,
            requirements=all_reqs,
            context=req.minimal_context,
            initial_frontier=init_frontier,
            translation=cand_bindings,
        )

        cert_disp = closure_outcome.certificate.disposition.value
        disp_correct = (cert_disp == ex.expected_disposition)
        if disp_correct:
            total_exact_disp += 1

        is_unsafe = (ex.expected_disposition != "YES" and cert_disp == "YES")
        if is_unsafe:
            total_unsafe_yes += 1

        # Accumulate stats
        cardinality_stats[frontier_card]["total"] += 1
        class_stats[b_class]["total"] += 1
        if is_valid_json:
            cardinality_stats[frontier_card]["valid_json"] += 1
            class_stats[b_class]["valid_json"] += 1
        if exact_bindings:
            cardinality_stats[frontier_card]["exact_bindings"] += 1
            class_stats[b_class]["exact_bindings"] += 1
        if disp_correct:
            cardinality_stats[frontier_card]["exact_disp"] += 1
            class_stats[b_class]["exact_disp"] += 1
        if is_unsafe:
            cardinality_stats[frontier_card]["unsafe"] += 1
            class_stats[b_class]["unsafe"] += 1

        records.append({
            "example_id": ex.example_id,
            "family": ex.family,
            "behavior_class": b_class,
            "cardinality": frontier_card,
            "raw_text": raw_text,
            "is_valid_json": is_valid_json,
            "exact_bindings": exact_bindings,
            "expected_disposition": ex.expected_disposition,
            "certificate_disposition": cert_disp,
            "disposition_correct": disp_correct,
            "is_unsafe_yes": is_unsafe,
            "frontier_violation": has_frontier_violation,
            "deterministic_overwrite": has_beta_d_overwrite,
        })
        print(f"[{idx+1:02d}/{total_cases}] {ex.example_id:28s} | |F_P|={frontier_card} | JSON={is_valid_json} | Bind={exact_bindings} | Disp={cert_disp} (exp={ex.expected_disposition})")

    elapsed = time.perf_counter() - t0

    # Rate calculations
    summary = {
        "model_label": model_label,
        "total_cases": total_cases,
        "elapsed_seconds": round(elapsed, 2),
        "rates": {
            "valid_serialization_rate": round(total_valid_json / total_cases, 4),
            "exact_binding_rate": round(total_exact_bindings / total_cases, 4),
            "exact_closure_rate": round(total_exact_disp / total_cases, 4),
            "unsafe_yes_rate": round(total_unsafe_yes / total_cases, 4),
            "frontier_violation_rate": round(total_frontier_violations / total_cases, 4),
            "deterministic_overwrite_rate": round(total_beta_d_violations / total_cases, 4),
        },
        "counts": {
            "valid_json": total_valid_json,
            "exact_bindings": total_exact_bindings,
            "exact_disposition": total_exact_disp,
            "unsafe_yes": total_unsafe_yes,
            "frontier_violations": total_frontier_violations,
            "beta_d_violations": total_beta_d_violations,
        },
        "by_cardinality": cardinality_stats,
        "by_behavior_class": class_stats,
        "case_records": records,
    }
    return summary


def run_h3_native_evaluation_campaign(device: Optional[str] = None) -> dict[str, Any]:
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    print(f"=== H3-N: Holdout Evaluation Campaign on {device} ===")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    holdout_raw = manifest["holdout_examples"]
    holdout_examples = [
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
        for d in holdout_raw
    ]
    print(f"Loaded {len(holdout_examples)} holdout examples.")

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID, revision=BASE_REVISION)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    # 1. Evaluate Base M_0
    print("\n" + "=" * 70)
    print("  EVALUATING MODEL 1/3: Base M_0 (unadapted baseline)")
    print("=" * 70)
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID,
        revision=BASE_REVISION,
        dtype=torch.float16 if device == "cuda" else torch.float32,
        device_map=device,
    )
    base_model.eval()
    m0_results = evaluate_model_on_holdout("M_0", base_model, tokenizer, holdout_examples, device)
    del base_model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # 2. Evaluate Arm N-A (Fresh LoRA)
    arm_na_dir = CHECKPOINTS_BASE / "uow_h3_native_smollm2_135m_arm_na"
    print("\n" + "=" * 70)
    print(f"  EVALUATING MODEL 2/3: Arm N-A (Fresh LoRA: {arm_na_dir.name})")
    print("=" * 70)
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID,
        revision=BASE_REVISION,
        dtype=torch.float16 if device == "cuda" else torch.float32,
        device_map=device,
    )
    model_na = PeftModel.from_pretrained(base_model, str(arm_na_dir))
    model_na.eval()
    na_results = evaluate_model_on_holdout("N_A", model_na, tokenizer, holdout_examples, device)
    del model_na
    del base_model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # 3. Evaluate Arm N-B (Grammar Transfer LoRA)
    arm_nb_dir = CHECKPOINTS_BASE / "uow_h3_native_smollm2_135m_arm_nb"
    print("\n" + "=" * 70)
    print(f"  EVALUATING MODEL 3/3: Arm N-B (Grammar Transfer: {arm_nb_dir.name})")
    print("=" * 70)
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID,
        revision=BASE_REVISION,
        dtype=torch.float16 if device == "cuda" else torch.float32,
        device_map=device,
    )
    model_nb = PeftModel.from_pretrained(base_model, str(arm_nb_dir))
    model_nb.eval()
    nb_results = evaluate_model_on_holdout("N_B", model_nb, tokenizer, holdout_examples, device)
    del model_nb
    del base_model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    campaign_summary = {
        "experiment": "H3-N-HOLDOUT-EVALUATION",
        "title": "Comparative Qualification on Family-Disjoint Holdout Set",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "device": device,
        "total_holdout_cases": len(holdout_examples),
        "models": {
            "M_0": m0_results,
            "N_A": na_results,
            "N_B": nb_results,
        },
        "head_to_head": {
            "valid_serialization": {
                "M_0": m0_results["rates"]["valid_serialization_rate"],
                "N_A": na_results["rates"]["valid_serialization_rate"],
                "N_B": nb_results["rates"]["valid_serialization_rate"],
            },
            "exact_bindings": {
                "M_0": m0_results["rates"]["exact_binding_rate"],
                "N_A": na_results["rates"]["exact_binding_rate"],
                "N_B": nb_results["rates"]["exact_binding_rate"],
            },
            "exact_disposition": {
                "M_0": m0_results["rates"]["exact_closure_rate"],
                "N_A": na_results["rates"]["exact_closure_rate"],
                "N_B": nb_results["rates"]["exact_closure_rate"],
            },
            "unsafe_yes": {
                "M_0": m0_results["rates"]["unsafe_yes_rate"],
                "N_A": na_results["rates"]["unsafe_yes_rate"],
                "N_B": nb_results["rates"]["unsafe_yes_rate"],
            },
        },
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(campaign_summary, indent=2), encoding="utf-8")
    print(f"\nSaved evaluation results to: {RESULTS_PATH}")
    print(f"Summary: M_0 = {m0_results['counts']['exact_disposition']}/{len(holdout_examples)} | N_A = {na_results['counts']['exact_disposition']}/{len(holdout_examples)} (Bindings: {na_results['counts']['exact_bindings']}) | N_B = {nb_results['counts']['exact_disposition']}/{len(holdout_examples)} (Bindings: {nb_results['counts']['exact_bindings']})")
    return campaign_summary


if __name__ == "__main__":
    run_h3_native_evaluation_campaign()
