"""Gate Q1: Full Semantic and Authority Evaluation Runner for Milestone P4."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch

from src.uow.contracts import make_uow, Route, Guard, GuardOp, Mutation, MutationOp, Successor, SuccessorKind
from src.uow.state import WorldState
from src.uow.engine import EvidenceLedger
from src.uow.inference.gateway import InferenceGateway
from src.uow.inference.model_backend import PyTorchPeftBackend
from src.uow.inference.request_context import CapabilityTarget, InferenceRequest, StateReference
from src.uow.magazine.manager import MagazineManager
from src.uow.magazine.schema import CapabilityManifest
from experiments.uow_magazine_p4.scoring.full_record_oracle import FullRecordOracle, SemanticEvaluationResult
from experiments.uow_magazine_p4.scoring.authorization_oracle import AuthorizationOracle, AuthorityAuditRecord

CANDIDATES = {
    "cerebras_111m": {
        "model_id": "cerebras-archive/Cerebras-GPT-111M",
        "arch": "GPT2LMHeadModel",
        "checkpoint_slug": "cerebras_111m",
    },
    "smollm2_135m": {
        "model_id": "HuggingFaceTB/SmolLM2-135M-Instruct",
        "arch": "LlamaForCausalLM",
        "checkpoint_slug": "smollm2_135m",
    },
}

GRAMMARS = ["operational", "temporal", "recovery"]


def build_uow_for_case(case: dict[str, Any]) -> tuple[Any, WorldState]:
    domain = case.get("domain", "industrial")
    target_dict = case.get("target_dict", {})
    action = target_dict.get("action") or target_dict.get("target_action") or "DEFAULT_ACTION"
    expected_auth = case.get("authority_metadata", {}).get("expected_authorized", True)

    interlock_val = 1 if expected_auth else 0
    pre_state = WorldState(attributes={f"{domain}.interlock_armed": interlock_val, f"{domain}.active": 1})

    uow = make_uow(
        f"uow_{case['id']}",
        [
            Route(
                guard=Guard(GuardOp.EQ, f"{domain}.interlock_armed", 1),
                mutations=(
                    Mutation(MutationOp.SET, f"{domain}.action_taken", str(action)),
                ),
                successor=Successor(kind=SuccessorKind.STATIC, value="committed"),
            )
        ]
    )
    return uow, pre_state


def run_q1_evaluation(
    corpus_path: Path = Path("experiments/uow_magazine_p4/corpora/frozen_p4_cases.json"),
    output_path: Path = Path("artifacts/uow_magazine_p4/q1_semantics.json"),
    failure_ledger_path: Path = Path("artifacts/uow_magazine_p4/failure_ledger.jsonl"),
    checkpoints_base: Path = Path("checkpoints/uow_magazine_p3"),
    device: str = "cuda" if torch.cuda.is_available() else "cpu",
    limit_per_category: Optional[int] = None,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    all_cases: list[dict[str, Any]] = json.loads(corpus_path.read_text(encoding="utf-8"))

    if limit_per_category is not None:
        cat_counts: dict[str, int] = {}
        filtered = []
        for c in all_cases:
            cat = c["category"]
            if cat_counts.get(cat, 0) < limit_per_category:
                filtered.append(c)
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
        all_cases = filtered

    results: dict[str, Any] = {
        "milestone": "P4",
        "gate": "Q1",
        "timestamp": time.time(),
        "device": device,
        "total_corpus_cases": len(all_cases),
        "candidates": {},
    }

    print(f"\n=======================================================")
    print(f"Executing Gate Q1: Full Semantic and Authority Evaluation")
    print(f"Total frozen test cases: {len(all_cases)} on {device.upper()}")
    print(f"=======================================================")

    for cand_name, cand_info in CANDIDATES.items():
        print(f"\n--- Evaluating Candidate: {cand_name} ({cand_info['model_id']}) ---")
        backend = PyTorchPeftBackend()
        backend.load_foundation(cand_info["model_id"], device=device)

        mgr = MagazineManager(
            foundation_id=cand_info["model_id"],
            foundation_revision="main",
            foundation_architecture=cand_info["arch"],
            device=device,
            max_resident_slots=4,
            backend_loader=backend.load_adapter,
            backend_switcher=backend.switch_adapter,
            backend_unloader=backend.unload_adapter,
        )

        # Load the 3 Strategy B shared grammar adapters
        for g in GRAMMARS:
            ad_dir = checkpoints_base / cand_info["checkpoint_slug"] / f"shared.{g}"
            if not ad_dir.exists():
                raise FileNotFoundError(f"Missing adapter {ad_dir}")
            weight_f = ad_dir / "adapter_model.safetensors"
            import hashlib
            sha = hashlib.sha256(weight_f.read_bytes()).hexdigest()
            manifest = CapabilityManifest(
                adapter_id=f"shared.{g}",
                domain="shared",
                grammar=g,
                version="1.0.0",
                foundation_model=cand_info["model_id"],
                adapter_sha256=sha,
                weight_size_bytes=weight_f.stat().st_size,
            )
            mgr.register_manifest(manifest, ad_dir, auto_verify=True)
            mgr.load_adapter(f"shared.{g}")

        gateway = InferenceGateway(magazine_manager=mgr, model_backend=backend)
        ledger = EvidenceLedger()

        cand_results = {
            "known_domain": {"total": 0, "schema_valid": 0, "complete_semantic_match": 0, "grounding_valid": 0, "uncertainty_valid": 0, "numeric_precision": 0},
            "cold_domain": {"total": 0, "schema_valid": 0, "complete_semantic_match": 0, "grounding_valid": 0, "recovery_correct": 0},
            "adversarial": {"total": 0, "schema_valid": 0, "correctly_rejected": 0, "unexpected_commits": 0, "unexpected_denials": 0},
            "composition": {"total": 0, "schema_valid": 0, "complete_semantic_match": 0},
            "authority_audit": {"total_evaluated": 0, "actual_authorized": 0, "actual_denied": 0, "unexpected_commits": 0, "unexpected_denials": 0, "ledger_integrity": True},
        }

        # Progress tracking
        t0 = time.time()
        for idx, case in enumerate(all_cases):
            cat = case["category"]
            grammar = case["grammar"]
            domain = case["domain"]

            req = InferenceRequest(
                request_id=f"q1_{cand_name}_{idx:04d}",
                state=StateReference(state_hash="state_p4", sequence=idx + 1),
                capability=CapabilityTarget(domain=domain, grammar=grammar),
                prompt_text=case["formatted_prompt"],
            )
            resp = gateway.process_request(req)

            proposal_dict = resp.result.payload if (resp.status == "OK" and resp.result) else None
            sem_res: SemanticEvaluationResult = FullRecordOracle.evaluate(
                proposal_dict=proposal_dict,
                ground_truth=case["target_dict"],
                authoritative_context=case.get("authoritative_context"),
                grammar=grammar,
            )

            # Authority evaluation using actual model proposal
            uow, pre_state = build_uow_for_case(case)
            auth_record: AuthorityAuditRecord = AuthorizationOracle.audit_transaction(
                case=case,
                inference_resp=resp,
                uow=uow,
                pre_state=pre_state,
                ledger=ledger,
            )

            # Record stats
            if cat == "known_domain":
                cand_results["known_domain"]["total"] += 1
                if sem_res.schema_valid: cand_results["known_domain"]["schema_valid"] += 1
                if sem_res.complete_semantic_match: cand_results["known_domain"]["complete_semantic_match"] += 1
                if sem_res.grounding_valid: cand_results["known_domain"]["grounding_valid"] += 1
                if sem_res.uncertainty_valid: cand_results["known_domain"]["uncertainty_valid"] += 1
                if sem_res.numeric_precision: cand_results["known_domain"]["numeric_precision"] += 1

            elif cat == "cold_domain":
                cand_results["cold_domain"]["total"] += 1
                if sem_res.schema_valid: cand_results["cold_domain"]["schema_valid"] += 1
                if sem_res.complete_semantic_match: cand_results["cold_domain"]["complete_semantic_match"] += 1
                if sem_res.grounding_valid: cand_results["cold_domain"]["grounding_valid"] += 1
                if grammar == "recovery" and sem_res.recovery_correctness: cand_results["cold_domain"]["recovery_correct"] += 1

            elif cat == "adversarial":
                cand_results["adversarial"]["total"] += 1
                if sem_res.schema_valid: cand_results["adversarial"]["schema_valid"] += 1
                if not auth_record.actual_authorized: cand_results["adversarial"]["correctly_rejected"] += 1
                if auth_record.is_unexpected_commit: cand_results["adversarial"]["unexpected_commits"] += 1
                if auth_record.is_unexpected_denial: cand_results["adversarial"]["unexpected_denials"] += 1

            elif cat == "composition":
                cand_results["composition"]["total"] += 1
                if sem_res.schema_valid: cand_results["composition"]["schema_valid"] += 1
                if sem_res.complete_semantic_match: cand_results["composition"]["complete_semantic_match"] += 1

            # Global authority counters
            cand_results["authority_audit"]["total_evaluated"] += 1
            if auth_record.actual_authorized: cand_results["authority_audit"]["actual_authorized"] += 1
            else: cand_results["authority_audit"]["actual_denied"] += 1
            if auth_record.is_unexpected_commit: cand_results["authority_audit"]["unexpected_commits"] += 1
            if auth_record.is_unexpected_denial: cand_results["authority_audit"]["unexpected_denials"] += 1

            # Log any unexpected safety failures to failure ledger
            if auth_record.is_unexpected_commit or not sem_res.grounding_valid:
                fail_entry = {
                    "timestamp": time.time(),
                    "candidate": cand_name,
                    "case_id": case["id"],
                    "category": cat,
                    "unexpected_commit": auth_record.is_unexpected_commit,
                    "grounding_violations": sem_res.grounding_violations,
                    "failure_reasons": sem_res.failure_reasons,
                }
                with failure_ledger_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(fail_entry) + "\n")

            if (idx + 1) % 180 == 0:
                print(f"[{cand_name}] Evaluated {idx + 1}/{len(all_cases)} cases ({time.time() - t0:.1f}s)...", flush=True)

        cand_results["authority_audit"]["ledger_integrity"] = ledger.verify_integrity()

        # Compute summary percentages
        kd = cand_results["known_domain"]
        kd_total = max(1, kd["total"])
        kd["complete_semantic_pct"] = round(kd["complete_semantic_match"] / kd_total * 100.0, 2)
        kd["grounding_pct"] = round(kd["grounding_valid"] / kd_total * 100.0, 2)
        kd["uncertainty_pct"] = round(kd["uncertainty_valid"] / kd_total * 100.0, 2)
        kd["numeric_precision_pct"] = round(kd["numeric_precision"] / kd_total * 100.0, 2)

        results["candidates"][cand_name] = cand_results

        print(f"[{cand_name}] Known Domain Complete Semantic Match: {kd['complete_semantic_pct']}% | Grounding: {kd['grounding_pct']}%")
        print(f"[{cand_name}] Adversarial Unexpected Commits: {cand_results['adversarial']['unexpected_commits']} (Target: 0)")
        print(f"[{cand_name}] Ledger Integrity Verified: {cand_results['authority_audit']['ledger_integrity']}")

        del gateway
        del mgr
        del backend
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nGate Q1 Evaluation Complete! Results written to: {output_path}")
    return results


if __name__ == "__main__":
    run_q1_evaluation()
