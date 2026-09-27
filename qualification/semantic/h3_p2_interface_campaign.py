"""H3-P2: Paired Negative Control Campaign across 45 Frozen Cases.

Evaluates unadapted base SmolLM2-135M (M_0, Delta W = 0) under two interfaces:
- Arm C0-J2: original J2 prompt & J2 parsing + deterministic lowering bridge.
- Arm C0-H3: new H3 IR prompt & native H3 parser.

Measures the interface/serialization migration cost versus semantic capacity.
"""
from __future__ import annotations

import gc
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

# Ensure canonical package root
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(PACKAGE_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT / "src"))
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from qualification.semantic.legacy_j2_bridge import J2SemanticCodec, J2ToH3Bridge
from uow.semantic.adapters.codec import SemanticOutputParser, SemanticPromptBuilder
from uow.semantic.closure import SemanticClosureEngine
from uow.semantic.frontier import SemanticFrontierBuilder
from uow.semantic.schema import (
    BindingOrigin,
    CandidateSemanticBindings,
    ExternalSignal,
    MinimalSemanticContext,
    SemanticBinding,
    SemanticDisposition,
    SemanticFrontierResult,
    SemanticRequirement,
    SemanticTranslationRequest,
)

FROZEN_CAMPAIGN_PATH = PACKAGE_ROOT / "qualification" / "semantic" / "frozen_campaign_45.json"
RESULTS_ARTIFACT_PATH = PACKAGE_ROOT / "qualification" / "artifacts" / "semantic_h3_p2_interface_results.json"

BASE_MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"
BASE_REVISION = "12fd25f77366fa6b3b4b768ec3050bf629380bac"
CANDIDATE_ADAPTER_PATH = r"C:\Users\nateb\OneDrive\Documents\jevtest\checkpoints\peft_cvc_mcv"


def run_h3_p2_campaign(
    device: Optional[str] = None,
    output_path: Optional[Path] = None,
) -> dict[str, Any]:
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    out_file = output_path or RESULTS_ARTIFACT_PATH
    out_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"=== H3-P2 Campaign: Paired Negative Control (M_0) on {device} ===")
    cases_raw = json.loads(FROZEN_CAMPAIGN_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(cases_raw)} frozen campaign cases.")

    print(f"Loading base model {BASE_MODEL_ID} (rev={BASE_REVISION[:8]})...")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID, revision=BASE_REVISION)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID,
        revision=BASE_REVISION,
        dtype=torch.float16 if device == "cuda" else torch.float32,
        device_map=device,
    )

    # Initialize components
    frontier_builder = SemanticFrontierBuilder()
    closure_engine = SemanticClosureEngine(frontier_builder)
    j2_codec = J2SemanticCodec()
    j2_bridge = J2ToH3Bridge()
    h3_builder = SemanticPromptBuilder()
    h3_parser = SemanticOutputParser()

    case_records: list[dict[str, Any]] = []

    c0_j2_yes = 0
    c0_j2_clarify = 0
    c0_j2_no = 0
    c0_j2_exact = 0
    c0_j2_beta_d = 0
    c0_j2_unsafe = 0

    c0_h3_yes = 0
    c0_h3_clarify = 0
    c0_h3_no = 0
    c0_h3_exact = 0
    c0_h3_beta_d = 0
    c0_h3_unsafe = 0

    t_start = time.perf_counter()

    for idx, c in enumerate(cases_raw):
        case_id = c["case_id"]
        signal_text = c["surface_utterance"]
        expected_disp = c["disposition"]
        expected_gold = c.get("gold_bindings", {})
        partition = c["partition"]
        difficulty = c["difficulty"]

        sig = ExternalSignal(raw=signal_text, signal_id=case_id)
        reqs = tuple(SemanticRequirement(name=r["req_id"]) for r in c["requirements"])
        ctx = MinimalSemanticContext(state_hash="0" * 64, state_sequence=1, bindings=())
        init_frontier = SemanticFrontierResult(resolved=(), frontier=reqs, deterministic_evidence=())
        req = SemanticTranslationRequest(signal=sig, minimal_context=ctx, frontier=reqs)

        # -------------------------------------------------------------
        # ARM 1: C0-J2 (Legacy J2 Prompt + Deterministic Bridge)
        # -------------------------------------------------------------
        j2_prompt = j2_codec.build_prompt(req)
        j2_inputs = tokenizer(j2_prompt, return_tensors="pt").to(device)

        with torch.no_grad():
            j2_out = base_model.generate(
                **j2_inputs,
                max_new_tokens=256,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
            j2_raw_text = tokenizer.decode(
                j2_out[0][j2_inputs["input_ids"].shape[1]:],
                skip_special_tokens=True,
            )

        j2_legacy_resp = j2_codec.parse(j2_raw_text, req)
        j2_candidate_bindings = j2_bridge.lower(j2_legacy_resp, req, evidence_ref="c0_j2_m0")
        j2_outcome = closure_engine.close(
            signal=sig,
            requirements=reqs,
            context=ctx,
            initial_frontier=init_frontier,
            translation=j2_candidate_bindings,
        )

        j2_disp = j2_outcome.certificate.disposition.value
        if j2_disp == "YES":
            c0_j2_yes += 1
        elif j2_disp == "CLARIFY":
            c0_j2_clarify += 1
        elif j2_disp == "NO":
            c0_j2_no += 1

        # Check safety invariants
        if "DETERMINISTIC_PRIMACY_VIOLATION" in j2_outcome.certificate.reason_codes:
            c0_j2_beta_d += 1
        if expected_disp != "YES" and j2_disp == "YES":
            c0_j2_unsafe += 1

        # Check exact closure:
        # For YES-cases: all required terminals closed with YES
        # For CLARIFY/NO cases: safe abstention matching expected disposition
        j2_exact_closed = (j2_disp == expected_disp)
        if j2_exact_closed:
            c0_j2_exact += 1

        # -------------------------------------------------------------
        # ARM 2: C0-H3 (H3 Direct Prompt + Native H3 Parser)
        # -------------------------------------------------------------
        h3_user_prompt = h3_builder.build_user_prompt(req)
        h3_messages = [
            {"role": "system", "content": h3_builder.system_prompt},
            {"role": "user", "content": h3_user_prompt},
        ]
        if hasattr(tokenizer, "apply_chat_template") and getattr(tokenizer, "chat_template", None):
            try:
                h3_formatted = tokenizer.apply_chat_template(h3_messages, tokenize=False, add_generation_prompt=True)
            except Exception:
                h3_formatted = f"{h3_builder.system_prompt}\n\n{h3_user_prompt}\n"
        else:
            h3_formatted = f"{h3_builder.system_prompt}\n\n{h3_user_prompt}\n"

        h3_inputs = tokenizer(h3_formatted, return_tensors="pt").to(device)

        with torch.no_grad():
            h3_out = base_model.generate(
                **h3_inputs,
                max_new_tokens=256,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
            h3_raw_text = tokenizer.decode(
                h3_out[0][h3_inputs["input_ids"].shape[1]:],
                skip_special_tokens=True,
            )

        h3_candidate_bindings = h3_parser.parse(h3_raw_text, req, evidence_ref="c0_h3_m0", fail_closed=True)
        h3_outcome = closure_engine.close(
            signal=sig,
            requirements=reqs,
            context=ctx,
            initial_frontier=init_frontier,
            translation=h3_candidate_bindings,
        )

        h3_disp = h3_outcome.certificate.disposition.value
        if h3_disp == "YES":
            c0_h3_yes += 1
        elif h3_disp == "CLARIFY":
            c0_h3_clarify += 1
        elif h3_disp == "NO":
            c0_h3_no += 1

        if "DETERMINISTIC_PRIMACY_VIOLATION" in h3_outcome.certificate.reason_codes:
            c0_h3_beta_d += 1
        if expected_disp != "YES" and h3_disp == "YES":
            c0_h3_unsafe += 1

        h3_exact_closed = (h3_disp == expected_disp)
        if h3_exact_closed:
            c0_h3_exact += 1

        record = {
            "case_id": case_id,
            "partition": partition,
            "difficulty": difficulty,
            "signal": signal_text,
            "expected_disposition": expected_disp,
            "expected_gold": expected_gold,
            "c0_j2": {
                "raw_text": j2_raw_text.strip(),
                "proposals_count": len(j2_legacy_resp.proposals),
                "syntactically_valid": j2_legacy_resp.is_syntactically_valid,
                "disposition": j2_disp,
                "reason_codes": list(j2_outcome.certificate.reason_codes),
                "exact_closed": j2_exact_closed,
            },
            "c0_h3": {
                "raw_text": h3_raw_text.strip(),
                "candidate_bindings_count": len(h3_candidate_bindings.candidate_bindings),
                "unknowns_count": len(h3_candidate_bindings.unknowns),
                "disposition": h3_disp,
                "reason_codes": list(h3_outcome.certificate.reason_codes),
                "exact_closed": h3_exact_closed,
            },
        }
        case_records.append(record)
        print(f"[{idx+1:02d}/45] {case_id:36s} | Expected: {expected_disp:7s} | C0-J2: {j2_disp:7s} (ok={j2_exact_closed}) | C0-H3: {h3_disp:7s} (ok={h3_exact_closed})")

    t_elapsed = time.perf_counter() - t_start
    total_cases = len(cases_raw)

    summary = {
        "experiment": "H3-P2",
        "title": "Paired Negative Control (M_0) Interface Campaign",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_model_id": BASE_MODEL_ID,
        "base_model_revision": BASE_REVISION,
        "device": device,
        "total_cases": total_cases,
        "elapsed_seconds": round(t_elapsed, 2),
        "arms": {
            "C0_J2": {
                "description": "Base model (M_0, Delta W=0) + Legacy J2 Prompt + Deterministic Lowering Bridge",
                "exact_closures": c0_j2_exact,
                "closure_rate": round(c0_j2_exact / total_cases, 4),
                "yes_count": c0_j2_yes,
                "clarify_count": c0_j2_clarify,
                "no_count": c0_j2_no,
                "beta_D": c0_j2_beta_d,
                "epsilon_unsafe": c0_j2_unsafe,
            },
            "C0_H3": {
                "description": "Base model (M_0, Delta W=0) + New H3 IR Prompt + Native Output Parser",
                "exact_closures": c0_h3_exact,
                "closure_rate": round(c0_h3_exact / total_cases, 4),
                "yes_count": c0_h3_yes,
                "clarify_count": c0_h3_clarify,
                "no_count": c0_h3_no,
                "beta_D": c0_h3_beta_d,
                "epsilon_unsafe": c0_h3_unsafe,
            },
        },
        "interface_migration_effect": {
            "exact_closures_delta": c0_j2_exact - c0_h3_exact,
            "rate_delta": round((c0_j2_exact - c0_h3_exact) / total_cases, 4),
            "interpretation": "Measures output grammar/interface serialization burden on base model without weight changes.",
        },
        "all_invariants_preserved": (c0_j2_beta_d == 0 and c0_j2_unsafe == 0 and c0_h3_beta_d == 0 and c0_h3_unsafe == 0),
        "case_details": case_records,
    }

    out_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSaved H3-P2 results to {out_file}")
    print(f"Summary: C0-J2 = {c0_j2_exact}/{total_cases} ({c0_j2_exact/total_cases:.1%}) | C0-H3 = {c0_h3_exact}/{total_cases} ({c0_h3_exact/total_cases:.1%})")
    print(f"Invariants: beta_D={c0_j2_beta_d + c0_h3_beta_d}, eps_unsafe={c0_j2_unsafe + c0_h3_unsafe}")

    # Clean up
    del base_model
    del tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return summary


if __name__ == "__main__":
    run_h3_p2_campaign()
