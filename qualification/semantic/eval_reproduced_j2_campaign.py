"""Evaluate reproduced J2.10 M_VG adapter checkpoint on the frozen 45-case campaign.

Executes:
1. Gate 1: Pure J2 evaluation comparing M_0 vs M_VG_repro.
   Target phenotype: M_0 = 30/45, M_VG_repro = 42/45.
2. Gate 2: Causal A/B/A/B toggle test on identical base weights:
   M_0 -> M_VG_repro -> M_0 -> M_VG_repro
   Target phenotype: 30 -> 42 -> 30 -> 42 with determinism_error == 0.0.
3. Case-by-case transition audit (already closed, newly recovered, safe abstentions).
"""
from __future__ import annotations

import gc
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Tuple

from peft import PeftModel
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# Import jevtest
JEVTEST_DIR = Path(r"C:\Users\nateb\OneDrive\Documents\jevtest")
if str(JEVTEST_DIR) not in sys.path:
    sys.path.insert(0, str(JEVTEST_DIR))

# Import UoW-v2
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(PACKAGE_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT / "src"))
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from jevl.adaptation.adapters import J2SpecializedAdapter
from jevl.adaptation.corpus import AdaptationCondition
from jevl.semantic.hidden_campaign import HiddenCampaignGenerator
from jevl.semantic.j2_schema import J2FrontierItem, J2Request
from jevl.semantic.prompt_codec import SYSTEM_PROMPT, format_j2_prompt, parse_j2_response

from qualification.semantic.legacy_j2_bridge import J2SemanticCodec, J2ToH3Bridge
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

FROZEN_CAMPAIGN_FILE = PACKAGE_ROOT / "qualification" / "semantic" / "frozen_campaign_45.json"
REPRODUCED_CHECKPOINT_DIR = JEVTEST_DIR / "checkpoints" / "reproduced_j2_10_mvg_135m"
SPEC_FILE = PACKAGE_ROOT / "qualification" / "semantic" / "j2_10_mvg_reproduction_spec.json"


def evaluate_j2_case(
    model: Any,
    tokenizer: Any,
    case_dict: dict[str, Any],
    device: str,
    max_new_tokens: int = 256,
) -> dict[str, Any]:
    """Evaluates a single campaign case through the physical model with the canonical J2 prompt."""
    req_items = tuple(
        J2FrontierItem(req_id=r["req_id"], description=r.get("description", ""))
        for r in case_dict["requirements"]
    )
    j2_req = J2Request(
        case_id=case_dict["case_id"],
        signal=case_dict["surface_utterance"],
        minimal_context={},
        frontier=req_items,
    )

    prompt_body = format_j2_prompt(j2_req)
    raw_prompt = f"{SYSTEM_PROMPT}\n\n{prompt_body}\n\nJSON Output:\n"
    inputs = tokenizer(raw_prompt, return_tensors="pt").to(device)

    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
        raw_text = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

    resp, is_valid = parse_j2_response(raw_text, j2_req, model_id="physical_135m")

    # J2 evaluation criterion
    p_targets = {p.target_requirement for p in resp.proposals if not p.proposed_binding.is_unknown}
    req_targets = {r["req_id"] for r in case_dict["requirements"]}
    has_unknown = any(p.proposed_binding.is_unknown for p in resp.proposals)
    closed = req_targets.issubset(p_targets) and not has_unknown

    # Also evaluate via UoW-v2 SemanticClosureEngine with J2ToH3Bridge
    sig = ExternalSignal(raw=case_dict["surface_utterance"], signal_id=case_dict["case_id"])
    reqs = tuple(SemanticRequirement(name=r["req_id"]) for r in case_dict["requirements"])
    ctx = MinimalSemanticContext(state_hash="0" * 64, state_sequence=1, bindings=())
    init_frontier = SemanticFrontierResult(resolved=(), frontier=reqs, deterministic_evidence=())
    trans_req = SemanticTranslationRequest(signal=sig, minimal_context=ctx, frontier=reqs)

    j2_codec = J2SemanticCodec()
    j2_bridge = J2ToH3Bridge()
    legacy_resp = j2_codec.parse(raw_text, trans_req)
    cand_bindings = j2_bridge.lower(legacy_resp, trans_req)

    engine = SemanticClosureEngine(SemanticFrontierBuilder())
    closure_outcome = engine.close(
        signal=sig,
        requirements=reqs,
        context=ctx,
        initial_frontier=init_frontier,
        translation=cand_bindings,
    )

    return {
        "case_id": case_dict["case_id"],
        "is_valid_json": is_valid,
        "raw_text": raw_text.strip(),
        "j2_closed": closed,
        "proposals": [(p.target_requirement, p.proposed_binding.value, p.proposed_binding.is_unknown) for p in resp.proposals],
        "uow_disposition": closure_outcome.certificate.disposition.value,
        "uow_reason_codes": list(closure_outcome.certificate.reason_codes),
        "uow_resolved_count": len(closure_outcome.certificate.resolved_bindings),
        "uow_unresolved_count": len(closure_outcome.certificate.unresolved),
    }


def run_reproduced_j2_eval(device: str | None = None) -> dict[str, Any]:
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    print("=" * 80)
    print("  EVALUATING REPRODUCED J2.10 M_VG ADAPTER ON 45 FROZEN CASES")
    print("=" * 80)

    cases = json.loads(FROZEN_CAMPAIGN_FILE.read_text(encoding="utf-8"))
    spec = json.loads(SPEC_FILE.read_text(encoding="utf-8"))
    base_model_id = spec["base_model"]
    base_revision = spec["revision"]

    print(f"Loading base model {base_model_id} on {device}...")
    tokenizer = AutoTokenizer.from_pretrained(base_model_id, revision=base_revision)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        revision=base_revision,
        dtype=torch.float16 if device == "cuda" else torch.float32,
        device_map=device,
    )
    print(f"Loading reproduced adapter from {REPRODUCED_CHECKPOINT_DIR}...")
    peft_model = PeftModel.from_pretrained(base_model, str(REPRODUCED_CHECKPOINT_DIR))
    print("Models loaded successfully.")

    # -------------------------------------------------------------------------
    # CAUSAL A/B/A/B TOGGLE TEST: M_0 -> M_VG -> M_0 -> M_VG
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("  STARTING CAUSAL A/B/A/B TOGGLE TEST (IDENTICAL BASE WEIGHTS)")
    print("=" * 80)

    steps = [
        ("Step 1 (M_0 base)", False),
        ("Step 2 (M_VG reproduced)", True),
        ("Step 3 (M_0 base)", False),
        ("Step 4 (M_VG reproduced)", True),
    ]

    toggle_results = []
    step_case_details = {}

    for step_name, enable_adapter in steps:
        print(f"\n--- Running {step_name} (adapter_enabled={enable_adapter}) ---")
        t0 = time.perf_counter()
        closures = 0
        details = []

        for idx, c in enumerate(cases):
            with torch.no_grad():
                if enable_adapter:
                    # LoRA active
                    res = evaluate_j2_case(peft_model, tokenizer, c, device)
                else:
                    # LoRA disabled
                    with peft_model.disable_adapter():
                        res = evaluate_j2_case(peft_model, tokenizer, c, device)

            if res["j2_closed"]:
                closures += 1
            details.append(res)
            print(f"  [{idx+1:02d}/45] {c['case_id']:34s} | j2_closed={str(res['j2_closed']):5s} | uow={res['uow_disposition']:7s} | valid_json={res['is_valid_json']}")

        elapsed = time.perf_counter() - t0
        rate = closures / len(cases)
        toggle_results.append({
            "step": step_name,
            "adapter_enabled": enable_adapter,
            "closures": closures,
            "total": len(cases),
            "rate": round(rate, 4),
            "elapsed_s": round(elapsed, 2),
        })
        step_case_details[step_name] = details
        print(f"  --> {step_name} Total: {closures}/{len(cases)} ({rate:.1%}) in {elapsed:.2f}s")

    # Compute causal metrics
    r1 = toggle_results[0]["rate"]
    r2 = toggle_results[1]["rate"]
    r3 = toggle_results[2]["rate"]
    r4 = toggle_results[3]["rate"]

    delta_enable_1 = r2 - r1
    delta_disable = r3 - r2
    delta_enable_2 = r4 - r3
    determinism_error = abs(r1 - r3) + abs(r2 - r4)

    c1 = toggle_results[0]["closures"]
    c2 = toggle_results[1]["closures"]
    c3 = toggle_results[2]["closures"]
    c4 = toggle_results[3]["closures"]

    causal_pass = (
        (c1 == c3 and c2 == c4)
        and determinism_error == 0.0
        and (c2 > c1)
    )

    print("\n" + "=" * 80)
    print("  CAUSAL A/B/A/B TEST SUMMARY")
    print("=" * 80)
    print(f"  Step 1: M_0 Base           -> {c1}/{len(cases)} ({r1:.1%})")
    print(f"  Step 2: M_VG Reproduced    -> {c2}/{len(cases)} ({r2:.1%}) | Delta: {delta_enable_1:+.1%}")
    print(f"  Step 3: M_0 Base           -> {c3}/{len(cases)} ({r3:.1%}) | Delta: {delta_disable:+.1%}")
    print(f"  Step 4: M_VG Reproduced    -> {c4}/{len(cases)} ({r4:.1%}) | Delta: {delta_enable_2:+.1%}")
    print(f"  Determinism Error:            {determinism_error:.6f}")
    print(f"  Causal Identity Verified:     {causal_pass}")

    # -------------------------------------------------------------------------
    # CASE-BY-CASE AUDIT BETWEEN BASE (Step 1) AND TUNED (Step 2)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("  CASE-BY-CASE RECOVERY & TRANSITION AUDIT")
    print("=" * 80)

    base_cases = step_case_details["Step 1 (M_0 base)"]
    tuned_cases = step_case_details["Step 2 (M_VG reproduced)"]

    already_closed = []
    newly_recovered = []
    safe_unclosed = []
    regressions = []

    for b, t, c in zip(base_cases, tuned_cases, cases):
        cid = c["case_id"]
        b_closed = b["j2_closed"]
        t_closed = t["j2_closed"]

        if b_closed and t_closed:
            already_closed.append(cid)
        elif not b_closed and t_closed:
            newly_recovered.append(cid)
        elif not t_closed:
            safe_unclosed.append(cid)
        else:
            regressions.append(cid)

    print(f"  Already closed (Base & Tuned): {len(already_closed)} cases")
    print(f"  Newly recovered (Tuned only):  {len(newly_recovered)} cases")
    print(f"  Persistent unclosed / abstain: {len(safe_unclosed)} cases")
    print(f"  Regressions:                   {len(regressions)} cases")

    print("\n  Newly recovered cases:")
    for cid in newly_recovered:
        print(f"    - {cid}")

    print("\n  Persistent unclosed cases:")
    for cid in safe_unclosed:
        print(f"    - {cid}")

    # Clean up
    del peft_model
    del base_model
    del tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    artifact_path = PACKAGE_ROOT / "qualification" / "artifacts" / "semantic_h3_p3_weight_toggle_results.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    summary_data = {
        "experiment": "H3-P3-REPRODUCTION",
        "title": "Causal A/B/A/B Toggle and Recovery Audit of Reproduced M_VG",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checkpoint": str(REPRODUCED_CHECKPOINT_DIR),
        "causal_pass": causal_pass,
        "determinism_error": determinism_error,
        "toggle_results": toggle_results,
        "recovery_breakdown": {
            "already_closed_count": len(already_closed),
            "newly_recovered_count": len(newly_recovered),
            "safe_unclosed_count": len(safe_unclosed),
            "regressions_count": len(regressions),
            "newly_recovered": newly_recovered,
            "safe_unclosed": safe_unclosed,
        },
        "case_details": step_case_details,
    }
    artifact_path.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")
    print(f"\nArtifact saved to: {artifact_path}")

    return summary_data


if __name__ == "__main__":
    run_reproduced_j2_eval()
