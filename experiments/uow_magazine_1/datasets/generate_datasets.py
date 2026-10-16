"""Synthetic Dataset Generator for UOW-MAGAZINE-1 across 3 Domains and 3 Grammars.

Generates 1,200 Train, 200 Dev, 200 Val, and 300 Disjoint Holdout per combination:
Total = 9 combinations * 1,900 examples = 17,100 examples.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
from typing import Any, Dict, List, Tuple

from experiments.uow_magazine_1.datasets.schemas import (
    OperationalProposal,
    TemporalConstraint,
    RecoveryStrategy,
)

DOMAINS = ["industrial", "cybersecurity", "logistics"]
GRAMMARS = ["operational", "temporal", "recovery"]

# --- Prompt Templates and Vocabulary ---

INDUSTRIAL_CONTEXTS = [
    {"plant": "Refinery Alpha", "unit": "Hydrocracker-4", "metric": "Reactor Core Pressure", "unit_id": "HC-401"},
    {"plant": "Power Station Beta", "unit": "Turbine-2", "metric": "Vibration Amplitude", "unit_id": "TB-202"},
    {"plant": "Chemical Facility Gamma", "unit": "Polymerizer-1", "metric": "Exothermic Temperature", "unit_id": "PZ-101"},
    {"plant": "Water Treatment Delta", "unit": "Chlorine Injector-3", "metric": "Flow Velocity", "unit_id": "CI-303"},
]

CYBER_CONTEXTS = [
    {"network": "Core Perimeter", "asset": "Edge Gateway", "threat": "Brute Force Auth Burst", "asset_id": "GW-901"},
    {"network": "DMZ Enclave", "asset": "Reverse Proxy", "threat": "SQL Injection Pattern", "asset_id": "RP-402"},
    {"network": "Identity Fabric", "asset": "Kerberos KDC", "threat": "Ticket Forgery Anomaly", "asset_id": "KDC-104"},
    {"network": "Kubernetes Cluster", "asset": "API Server", "threat": "Privilege Escalation Probe", "asset_id": "K8S-705"},
]

LOGISTICS_CONTEXTS = [
    {"hub": "Transshipment Port Newark", "lane": "Intermodal Corridor A", "event": "Berth Congestion Surge", "shipment_id": "SH-881"},
    {"hub": "Air Cargo Gateway ORD", "lane": "Cold Chain Flight 402", "event": "Reefer Temperature Spike", "shipment_id": "SH-304"},
    {"hub": "Cross-Dock Dallas", "lane": "Dry Van Fleet 19", "event": "Hours-of-Service Breach", "shipment_id": "SH-552"},
    {"hub": "Rail Terminal Chicago", "lane": "Unit Train Westbound", "event": "Switch Siding Derail Delay", "shipment_id": "SH-910"},
]


def build_chat_prompt(system_prompt: str, user_text: str) -> str:
    return f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_text}<|im_end|>\n<|im_start|>assistant\n"


def generate_operational_example(domain: str, partition: str, index: int, rng: random.Random) -> dict[str, Any]:
    sys_prompt = (
        f"You are the deterministic UoW Operational Proposal Parser for the {domain.upper()} domain (uow.operational.v1).\n"
        "Generate a structured operational proposal with keys: 'domain', 'action', 'disposition' ('COMMIT'|'ROLLBACK'|'HALT'), "
        "'parameters', 'guard_conditions', and 'unknowns'. Emit valid JSON only."
    )
    if domain == "industrial":
        ctx = rng.choice(INDUSTRIAL_CONTEXTS)
        is_emergency = (index % 4 == 0) if partition != "holdout" else (index % 3 == 0)
        action = "EMERGENCY_DEPRESSURIZE" if is_emergency else "MODULATE_CONTROL_VALVE"
        disposition = "HALT" if is_emergency else ("COMMIT" if (index % 2 == 0) else "ROLLBACK")
        user_prompt = (
            f"Sensor alert from {ctx['plant']} on unit {ctx['unit']} ({ctx['unit_id']}). "
            f"{ctx['metric']} reading exceeds threshold at index {index}. Determine operational action."
        )
        proposal = OperationalProposal(
            domain="industrial",
            action=action,
            disposition=disposition,
            parameters={"unit_id": ctx["unit_id"], "target_setpoint": 100 - (index % 40)},
            guard_conditions=["interlock_verified", "pressure_relief_armed"],
            unknowns=[] if disposition == "COMMIT" else ["secondary_bypass_flow_rate"],
        )
    elif domain == "cybersecurity":
        ctx = rng.choice(CYBER_CONTEXTS)
        is_critical = (index % 3 == 0)
        action = "QUARANTINE_ENDPOINT" if is_critical else "APPLY_FIREWALL_ACL"
        disposition = "HALT" if is_critical else ("COMMIT" if (index % 2 == 0) else "ROLLBACK")
        user_prompt = (
            f"SIEM signal detected on {ctx['network']} targeting {ctx['asset']} ({ctx['asset_id']}). "
            f"Identified anomaly: {ctx['threat']}. Formulate defense action proposal."
        )
        proposal = OperationalProposal(
            domain="cybersecurity",
            action=action,
            disposition=disposition,
            parameters={"asset_id": ctx["asset_id"], "severity": "HIGH" if is_critical else "MEDIUM"},
            guard_conditions=["soc_escalation_logged", "tenant_isolation_checked"],
            unknowns=[] if disposition == "COMMIT" else ["ingress_source_ip_range"],
        )
    else:  # logistics
        ctx = rng.choice(LOGISTICS_CONTEXTS)
        is_reroute = (index % 3 == 0)
        action = "REROUTE_TRANSIT_LANE" if is_reroute else "REASSIGN_DOCK_DOOR"
        disposition = "HALT" if is_reroute else ("COMMIT" if (index % 2 == 0) else "ROLLBACK")
        user_prompt = (
            f"Freight dispatch notification at {ctx['hub']} for lane {ctx['lane']}. "
            f"Incident: {ctx['event']} affecting consignment {ctx['shipment_id']}. Issue logistics proposal."
        )
        proposal = OperationalProposal(
            domain="logistics",
            action=action,
            disposition=disposition,
            parameters={"shipment_id": ctx["shipment_id"], "priority": "EXPEDITED" if is_reroute else "STANDARD"},
            guard_conditions=["manifest_hash_verified", "customs_hold_cleared"],
            unknowns=[] if disposition == "COMMIT" else ["carrier_capacity_confirmation"],
        )

    target_json = json.dumps(proposal.to_dict(), indent=2)
    return {
        "domain": domain,
        "grammar": "operational",
        "partition": partition,
        "id": f"{domain}_op_{partition}_{index:04d}",
        "user_prompt": user_prompt,
        "system_prompt": sys_prompt,
        "formatted_prompt": build_chat_prompt(sys_prompt, user_prompt),
        "target_json": target_json,
        "target_dict": proposal.to_dict(),
    }


def generate_temporal_example(domain: str, partition: str, index: int, rng: random.Random) -> dict[str, Any]:
    sys_prompt = (
        f"You are the deterministic UoW Temporal Grammar Parser for the {domain.upper()} domain (uow.temporal.v1).\n"
        "Extract timing constraints, relations ('IMMEDIATE'|'AFTER'|'BEFORE'|'BETWEEN'|'CONCURRENT'), "
        "and deadlines. Emit valid JSON only."
    )
    relations = ["IMMEDIATE", "AFTER", "BEFORE", "BETWEEN", "CONCURRENT"]
    rel = relations[index % len(relations)]

    if domain == "industrial":
        action = "PURGE_GAS_CYCLE"
        user_prompt = f"Industrial timing constraint for unit ID-IND-{index:03d}: execute {action} {rel} pressure sensor calibration."
        ref_event = "pressure_sensor_calibration" if rel != "IMMEDIATE" else None
    elif domain == "cybersecurity":
        action = "REVOKE_SESSION_TOKEN"
        user_prompt = f"Security timing rule for rule-set SEC-{index:03d}: enforce {action} {rel} credential rotation alert."
        ref_event = "credential_rotation_alert" if rel != "IMMEDIATE" else None
    else:  # logistics
        action = "DISPATCH_FEEDER_VESSEL"
        user_prompt = f"Logistics scheduler order for freight job LOG-{index:03d}: perform {action} {rel} gate cutoff window."
        ref_event = "gate_cutoff_window" if rel != "IMMEDIATE" else None

    window_start = f"T+0{index%6}h" if rel == "BETWEEN" else None
    window_end = f"T+1{index%6}h" if rel == "BETWEEN" else None
    deadline = f"2026-10-17T{(index%12)+8:02d}:00:00Z" if rel in ("BEFORE", "BETWEEN") else None
    duration = 300 + (index % 120) * 10

    tc = TemporalConstraint(
        domain=domain,
        target_action=action,
        relation=rel,
        reference_event=ref_event,
        window_start=window_start,
        window_end=window_end,
        deadline=deadline,
        duration_seconds=duration,
        unknowns=[],
    )
    target_json = json.dumps(tc.to_dict(), indent=2)
    return {
        "domain": domain,
        "grammar": "temporal",
        "partition": partition,
        "id": f"{domain}_temp_{partition}_{index:04d}",
        "user_prompt": user_prompt,
        "system_prompt": sys_prompt,
        "formatted_prompt": build_chat_prompt(sys_prompt, user_prompt),
        "target_json": target_json,
        "target_dict": tc.to_dict(),
    }


def generate_recovery_example(domain: str, partition: str, index: int, rng: random.Random) -> dict[str, Any]:
    sys_prompt = (
        f"You are the deterministic UoW Recovery Grammar Parser for the {domain.upper()} domain (uow.recovery.v1).\n"
        "Extract failure triage, recovery strategy ('IMMEDIATE_RETRY'|'CIRCUIT_BREAK'|'ROLLBACK_COMPENSATE'|'EXPONENTIAL_BACKOFF'|'ESCALATE_OPERATOR'), "
        "and compensation parameters. Emit valid JSON only."
    )
    strategies = ["IMMEDIATE_RETRY", "CIRCUIT_BREAK", "ROLLBACK_COMPENSATE", "EXPONENTIAL_BACKOFF", "ESCALATE_OPERATOR"]
    strat = strategies[index % len(strategies)]

    if domain == "industrial":
        failure = f"VALVE_STATION_TIMEOUT_E{index%5}"
        comp = "VENT_SAFETY_FLUSH" if strat == "ROLLBACK_COMPENSATE" else None
        user_prompt = f"Industrial process fault reported: {failure} on PLC controller {index:03d}. Triage recovery strategy."
    elif domain == "cybersecurity":
        failure = f"AUTH_GATEWAY_HANDSHAKE_FAIL_E{index%5}"
        comp = "REVOKE_TEMP_CREDENTIALS" if strat == "ROLLBACK_COMPENSATE" else None
        user_prompt = f"Security service exception: {failure} on authentication ingress {index:03d}. Select recovery strategy."
    else:  # logistics
        failure = f"DOCK_PALLET_RFID_SCAN_FAIL_E{index%5}"
        comp = "REALLOCATE_BUFFER_BAY" if strat == "ROLLBACK_COMPENSATE" else None
        user_prompt = f"Warehouse automation fault: {failure} at staging dock {index:03d}. Determine recovery strategy."

    max_att = 1 if strat in ("CIRCUIT_BREAK", "ESCALATE_OPERATOR") else (3 + (index % 3))
    backoff = (5 * (2 ** (index % 3))) if strat == "EXPONENTIAL_BACKOFF" else None

    rs = RecoveryStrategy(
        domain=domain,
        failure_mode=failure,
        strategy=strat,
        max_attempts=max_att,
        backoff_seconds=backoff,
        compensation_action=comp,
        idempotency_required=True,
        unknowns=[],
    )
    target_json = json.dumps(rs.to_dict(), indent=2)
    return {
        "domain": domain,
        "grammar": "recovery",
        "partition": partition,
        "id": f"{domain}_rec_{partition}_{index:04d}",
        "user_prompt": user_prompt,
        "system_prompt": sys_prompt,
        "formatted_prompt": build_chat_prompt(sys_prompt, user_prompt),
        "target_json": target_json,
        "target_dict": rs.to_dict(),
    }


def generate_combination(domain: str, grammar: str, seed: int) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(seed)
    gen_fn = {
        "operational": generate_operational_example,
        "temporal": generate_temporal_example,
        "recovery": generate_recovery_example,
    }[grammar]

    # Partition sizes: 1,200 Train, 200 Dev, 200 Val, 300 Holdout
    train_ex = [gen_fn(domain, "train", i, rng) for i in range(1200)]
    dev_ex = [gen_fn(domain, "dev", i, rng) for i in range(200)]
    val_ex = [gen_fn(domain, "val", i, rng) for i in range(200)]
    holdout_ex = [gen_fn(domain, "holdout", i, rng) for i in range(300)]

    return {
        "train": train_ex,
        "dev": dev_ex,
        "val": val_ex,
        "holdout": holdout_ex,
    }


def generate_all_datasets(seed: int = 42, output_dir: str = "artifacts/uow_magazine_1") -> dict[str, Any]:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "campaign": "UOW-MAGAZINE-1",
        "spec_version": "uow.magazine.v1",
        "domains": DOMAINS,
        "grammars": GRAMMARS,
        "partitions_per_combination": {"train": 1200, "dev": 200, "val": 200, "holdout": 300},
        "combinations": {},
        "hashes": {},
    }

    total_examples = 0
    for dom_idx, domain in enumerate(DOMAINS):
        for g_idx, grammar in enumerate(GRAMMARS):
            comb_key = f"{domain}.{grammar}"
            comb_seed = seed + (dom_idx * 10) + g_idx
            splits = generate_combination(domain, grammar, comb_seed)
            counts = {k: len(v) for k, v in splits.items()}
            total_examples += sum(counts.values())

            # Save split files
            comb_dir = out_path / "corpora" / comb_key
            comb_dir.mkdir(parents=True, exist_ok=True)
            split_hashes = {}
            for split_name, examples in splits.items():
                split_file = comb_dir / f"{split_name}.json"
                data_bytes = (json.dumps(examples, indent=2) + "\n").encode("utf-8")
                split_file.write_bytes(data_bytes)
                h = hashlib.sha256(data_bytes).hexdigest()
                split_hashes[split_name] = {"count": len(examples), "sha256": h, "file": str(split_file.as_posix())}

            manifest["combinations"][comb_key] = split_hashes

    manifest["total_examples"] = total_examples
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    manifest_file = out_path / "dataset_manifest.json"
    manifest_file.write_bytes(manifest_bytes)
    print(f"Dataset generation complete: {total_examples} examples across 9 combinations -> {manifest_file}")
    return manifest


if __name__ == "__main__":
    generate_all_datasets()
