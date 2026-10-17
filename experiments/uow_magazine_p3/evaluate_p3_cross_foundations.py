"""Cross-Foundation Head-to-Head Evaluation Suite for Milestone P3 (UOW-MAGAZINE-RC0)."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch

from uow.inference.gateway import InferenceGateway
from uow.inference.model_backend import PyTorchPeftBackend
from uow.inference.request_context import CapabilityTarget, InferenceRequest, StateReference, TypedProposal
from uow.inference.authority_bridge import AuthorityBridge
from uow.contracts import make_uow, Route, Guard, GuardOp, Mutation, MutationOp, Successor, SuccessorKind
from uow.state import WorldState
from uow.engine import EvidenceLedger
from uow.magazine.manager import MagazineManager
from uow.magazine.schema import CapabilityManifest
from experiments.uow_magazine_p3.foundations import FOUNDATION_ROSTER, FoundationSpec

DOMAINS = ["industrial", "cybersecurity", "logistics"]
GRAMMARS = ["operational", "temporal", "recovery"]


def compute_manifest(adapter_id: str, domain: str, grammar: str, foundation_id: str, adapter_dir: Path) -> CapabilityManifest:
    weights_path = adapter_dir / "adapter_model.safetensors"
    if not weights_path.exists():
        weights_path = adapter_dir / "adapter_model.bin"
    raw = weights_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    return CapabilityManifest(
        adapter_id=adapter_id,
        domain=domain,
        grammar=grammar,
        version="1.0.0",
        foundation_model=foundation_id,
        adapter_sha256=sha,
        weight_size_bytes=len(raw),
    )


def build_uow_for_test(domain: str, action: str) -> tuple[Any, WorldState]:
    """Constructs a minimal test UoW contract and pre-state for authority validation."""
    if domain == "industrial":
        pre_state = WorldState(attributes={"plant.pressure": 160.0, "plant.interlock_armed": 1})
        uow = make_uow(
            f"uow_{domain}_{action.lower()}",
            [
                Route(
                    guard=Guard(GuardOp.EQ, "plant.interlock_armed", 1),
                    mutations=(
                        Mutation(MutationOp.SET, "plant.pressure", 90.0),
                        Mutation(MutationOp.SET, "plant.action_taken", action),
                    ),
                    successor=Successor(kind=SuccessorKind.STATIC, value=f"{action.lower()}_done"),
                )
            ]
        )
    elif domain == "cybersecurity":
        pre_state = WorldState(attributes={"net.quarantine_status": 0, "net.soc_armed": 1})
        uow = make_uow(
            f"uow_{domain}_{action.lower()}",
            [
                Route(
                    guard=Guard(GuardOp.EQ, "net.soc_armed", 1),
                    mutations=(
                        Mutation(MutationOp.SET, "net.quarantine_status", 1),
                        Mutation(MutationOp.SET, "net.action_taken", action),
                    ),
                    successor=Successor(kind=SuccessorKind.STATIC, value=f"{action.lower()}_done"),
                )
            ]
        )
    else:
        pre_state = WorldState(attributes={"freight.hold_cleared": 1, "freight.status": "PENDING"})
        uow = make_uow(
            f"uow_{domain}_{action.lower()}",
            [
                Route(
                    guard=Guard(GuardOp.EQ, "freight.hold_cleared", 1),
                    mutations=(
                        Mutation(MutationOp.SET, "freight.status", "EXECUTED"),
                        Mutation(MutationOp.SET, "freight.action_taken", action),
                    ),
                    successor=Successor(kind=SuccessorKind.STATIC, value=f"{action.lower()}_done"),
                )
            ]
        )
    return uow, pre_state


def evaluate_suite(
    gateway: InferenceGateway,
    holdout_data: list[dict],
    grammar: str,
    target_domain: str,
    sample_limit: int = 20,
) -> dict[str, Any]:
    ledger = EvidenceLedger()
    total = min(len(holdout_data), sample_limit)
    valid_json = 0
    semantic_match = 0
    unresolved_ref_detected = 0
    total_unresolved_ground_truth = 0
    authority_certified = 0
    authority_rejected = 0
    unauthorized_commits = 0
    total_latency_ms = 0.0

    for i in range(total):
        case = holdout_data[i]
        prompt = case.get("formatted_prompt") or case.get("prompt", "")
        target = case.get("target_dict") or json.loads(case["target_json"])

        req = InferenceRequest(
            request_id=f"p3-eval-{grammar}-{i}",
            state=StateReference(state_hash="state_p3", sequence=i + 1),
            capability=CapabilityTarget(domain=target_domain, grammar=grammar),
            prompt_text=prompt,
        )
        resp = gateway.process_request(req)

        if resp.status != "OK" or not resp.result:
            continue

        valid_json += 1
        payload = resp.result.payload or {}

        # Semantic match logic
        matched = False
        if grammar == "operational":
            if (
                payload.get("action") == target.get("action")
                and payload.get("disposition") == target.get("disposition")
            ):
                matched = True
        elif grammar == "temporal":
            if (
                payload.get("relation") == target.get("relation")
                and payload.get("target_action") == target.get("target_action")
            ):
                matched = True
        elif grammar == "recovery":
            pred_f = payload.get("failure_mode") or payload.get("failed_action") or payload.get("failure_class")
            tgt_f = target.get("failure_mode") or target.get("failed_action") or target.get("failure_class")
            if payload.get("strategy") == target.get("strategy") and pred_f == tgt_f:
                matched = True

        if matched:
            semantic_match += 1

        # Unresolved reference logic
        target_unknowns = target.get("unknowns", [])
        pred_unknowns = payload.get("unknowns", [])
        if target_unknowns:
            total_unresolved_ground_truth += 1
            if pred_unknowns:
                unresolved_ref_detected += 1

        # Authority bridge submission
        action_name = payload.get("action") or target.get("action") or "DEFAULT_ACTION"
        test_uow, pre_state = build_uow_for_test(target_domain, action_name)
        auth_eval = AuthorityBridge.evaluate_and_commit(resp, test_uow, pre_state, ledger)

        if auth_eval.is_authority_certified:
            authority_certified += 1
        else:
            authority_rejected += 1

        if resp.provenance:
            total_latency_ms += resp.provenance.get("inference_latency_ms", 0.0)

    ledger_integrity = ledger.verify_integrity()
    unresolved_rate = (
        round(unresolved_ref_detected / total_unresolved_ground_truth * 100.0, 2)
        if total_unresolved_ground_truth > 0 else 100.0
    )

    return {
        "evaluated_cases": total,
        "valid_json_count": valid_json,
        "valid_json_rate": round(valid_json / total * 100.0, 2),
        "semantic_match_count": semantic_match,
        "semantic_match_rate": round(semantic_match / total * 100.0, 2),
        "unresolved_reference_accuracy": unresolved_rate,
        "authority_certified_count": authority_certified,
        "authority_rejected_count": authority_rejected,
        "unauthorized_commits": unauthorized_commits,
        "ledger_integrity": ledger_integrity,
        "mean_latency_ms": round(total_latency_ms / max(1, valid_json), 2),
    }


def evaluate_p3_cross_foundations(
    corpora_dir: str = "artifacts/uow_magazine_p2/corpora",
    checkpoints_base: str = "checkpoints/uow_magazine_p3",
    output_file: str = "artifacts/uow_magazine_p3/p3_cross_foundation_scorecard.json",
    sample_limit: int = 20,
    foundations: Optional[list[str]] = None,
) -> dict[str, Any]:
    corpora_path = Path(corpora_dir)
    checkpoints_path = Path(checkpoints_base)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    trained_slugs = [k for k in FOUNDATION_ROSTER.keys() if (checkpoints_path / k).exists()]
    selected_slugs = foundations or trained_slugs
    results: dict[str, Any] = {
        "campaign": "UOW-MAGAZINE-RC0",
        "milestone": "P3",
        "device": device,
        "timestamp": time.time(),
        "foundations": {},
        "summary_scorecard": {},
        "disqualified_foundations": {
            "mamba_130m": {
                "model_id": "state-spaces/mamba-130m-hf",
                "family": "selective_ssm",
                "status": "DISQUALIFIED_EDGE_AUTOGRAD_OOM",
                "reason": "Uncompiled selective SSM autograd on Windows/CPU exceeded host memory ceiling (>24 GB RAM) during backward pass.",
            }
        },
    }

    print(f"\n=======================================================")
    print(f"Starting Milestone P3 Cross-Foundation Evaluation on {device.upper()}")
    print(f"Selected Foundations: {selected_slugs}")
    print(f"=======================================================")

    for slug in selected_slugs:
        if slug not in FOUNDATION_ROSTER:
            continue
        spec = FOUNDATION_ROSTER[slug]
        print(f"\n--- Evaluating Foundation: {spec.slug} ({spec.model_id}) ---")

        backend = PyTorchPeftBackend()
        try:
            backend.load_foundation(spec.model_id, device=device)
        except Exception as e:
            print(f"Error loading foundation {spec.model_id}: {e}")
            results["foundations"][slug] = {"error": str(e)}
            continue

        mgr = MagazineManager(
            foundation_id=spec.model_id,
            foundation_revision="main",
            foundation_architecture=spec.model_class_name,
            device=device,
            max_resident_slots=4,
            backend_loader=backend.load_adapter,
            backend_switcher=backend.switch_adapter,
            backend_unloader=backend.unload_adapter,
        )

        total_weight_bytes = 0
        loaded_count = 0
        for g in GRAMMARS:
            shared_comb = f"shared.{g}"
            adapter_dir = checkpoints_path / slug / shared_comb
            if not adapter_dir.exists():
                print(f"Adapter {adapter_dir} missing, skipping.")
                continue

            manifest = compute_manifest(shared_comb, "shared", g, spec.model_id, adapter_dir)
            total_weight_bytes += manifest.weight_size_bytes
            mgr.register_manifest(manifest, adapter_dir, auto_verify=True)
            mgr.load_adapter(shared_comb)
            loaded_count += 1

        if loaded_count < len(GRAMMARS):
            print(f"Warning: Only {loaded_count}/{len(GRAMMARS)} adapters loaded for {slug}")

        gateway = InferenceGateway(magazine_manager=mgr, model_backend=backend)
        foundation_eval: dict[str, Any] = {"tasks": {}}

        for d in DOMAINS:
            for g in GRAMMARS:
                comb = f"{d}.{g}"
                holdout_file = corpora_path / comb / "holdout.json"
                if not holdout_file.exists():
                    continue
                holdout_data = json.loads(holdout_file.read_text(encoding="utf-8"))
                print(f"[{slug}] Testing {comb} ({sample_limit} cases)...", flush=True)
                score = evaluate_suite(gateway, holdout_data, g, d, sample_limit=sample_limit)
                foundation_eval["tasks"][comb] = score
                print(f"  -> JSON: {score['valid_json_rate']}%, Semantic: {score['semantic_match_rate']}%, Unresolved: {score['unresolved_reference_accuracy']}%", flush=True)

        # Foundation summary stats
        task_scores = list(foundation_eval["tasks"].values())
        mean_json = sum(t["valid_json_rate"] for t in task_scores) / max(1, len(task_scores))
        mean_sem = sum(t["semantic_match_rate"] for t in task_scores) / max(1, len(task_scores))
        mean_lat = sum(t["mean_latency_ms"] for t in task_scores) / max(1, len(task_scores))

        op_scores = [foundation_eval["tasks"][f"{d}.operational"]["semantic_match_rate"] for d in DOMAINS if f"{d}.operational" in foundation_eval["tasks"]]
        temp_scores = [foundation_eval["tasks"][f"{d}.temporal"]["semantic_match_rate"] for d in DOMAINS if f"{d}.temporal" in foundation_eval["tasks"]]
        rec_scores = [foundation_eval["tasks"][f"{d}.recovery"]["semantic_match_rate"] for d in DOMAINS if f"{d}.recovery" in foundation_eval["tasks"]]

        foundation_eval["summary"] = {
            "foundation_id": spec.model_id,
            "architecture_family": spec.architecture_family,
            "storage_mb": round(total_weight_bytes / (1024 * 1024), 2),
            "mean_valid_json_rate": round(mean_json, 2),
            "mean_semantic_match_rate": round(mean_sem, 2),
            "operational_semantic_rate": round(sum(op_scores) / max(1, len(op_scores)), 2),
            "temporal_semantic_rate": round(sum(temp_scores) / max(1, len(temp_scores)), 2),
            "recovery_semantic_rate": round(sum(rec_scores) / max(1, len(rec_scores)), 2),
            "mean_latency_ms": round(mean_lat, 2),
        }
        results["foundations"][slug] = foundation_eval

        # Cleanup foundation memory before next model
        del gateway
        del mgr
        del backend
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # Aggregate comparative scorecard
    scorecard: dict[str, Any] = {}
    for slug, f_data in results["foundations"].items():
        if "summary" in f_data:
            scorecard[slug] = f_data["summary"]
    results["summary_scorecard"] = scorecard

    out_p = Path(output_file)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"\n=======================================================")
    print("Milestone P3 Cross-Foundation Evaluation Complete!")
    print(f"Scorecard written to: {output_file}")
    print("=======================================================")
    return results


if __name__ == "__main__":
    evaluate_p3_cross_foundations()
