"""P2 Grounding-Aware Corpus Generator.

Generates:
1. Strategy A corpora: 9 domain-grammar combinations with explicit grounding context,
   unresolved reference detection, and deterministic semantic features.
2. Strategy B corpora: 3 shared grammar corpora (shared.operational, shared.temporal, shared.recovery).
3. Cold-domain transfer holdout: Biomedical domain (unobserved in training).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
from typing import Any, Dict, List, Tuple


DOMAINS = ["industrial", "cybersecurity", "logistics"]
GRAMMARS = ["operational", "temporal", "recovery"]

# Domain Registries & Grounding Ontologies
INDUSTRIAL_UNITS = ["HC-401", "TB-202", "PZ-101", "CI-303"]
CYBER_ASSETS = ["GW-901", "RP-402", "KDC-104", "K8S-705"]
LOGISTICS_SHIPMENTS = ["SH-881", "SH-304", "SH-552", "SH-910"]
BIOMED_DEVICES = ["IP-101", "MV-202", "DM-303", "CM-404"]


def build_chat_prompt(system_prompt: str, user_text: str) -> str:
    return f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_text}<|im_end|>\n<|im_start|>assistant\n"


def generate_grounded_operational(
    domain: str,
    partition: str,
    index: int,
    rng: random.Random,
) -> dict[str, Any]:
    sys_prompt = (
        f"You are the deterministic UoW Grounded Operational Proposer for the {domain.upper()} domain (uow.operational.v1).\n"
        "Ground decisions using the provided unit and alarm telemetry. Output keys: 'domain', 'action', "
        "'disposition' ('COMMIT'|'ROLLBACK'|'HALT'), 'parameters', 'guard_conditions', and 'unknowns'. Emit valid JSON only."
    )

    case_type = index % 5
    # 0: CRITICAL -> Emergency Action, HALT
    # 1: WARNING (Auxiliary confirmed) -> Modulation/Normal Action, COMMIT
    # 2: WARNING (Auxiliary missing) -> Modulation/Normal Action, ROLLBACK, unknown auxiliary
    # 3: NORMAL -> Routine verification, COMMIT
    # 4: UNRESOLVED REFERENCE -> Unknown Unit ID, ROLLBACK, unknowns=[unit_id]

    if domain == "industrial":
        registered = INDUSTRIAL_UNITS
        if case_type == 4:
            unit_id = f"UNKNOWN_IND_{index:03d}"
            user_prompt = f"Grounding Context: Valid Units={registered}. Telemetry: Unit {unit_id} reports Pressure 185.0 psi (Limit 150.0). Determine operational action."
            proposal = {
                "domain": "industrial",
                "action": "EMERGENCY_DEPRESSURIZE",
                "disposition": "ROLLBACK",
                "parameters": {"unit_id": "UNKNOWN", "target_setpoint": 0},
                "guard_conditions": [],
                "unknowns": [f"unit_id:{unit_id}"],
            }
        elif case_type == 0:
            unit = registered[index % len(registered)]
            user_prompt = f"Grounding Context: Valid Units={registered}. Telemetry: Unit {unit} reports CRITICAL Pressure 182.5 psi (Critical Limit 150.0). Interlock armed. Determine operational action."
            proposal = {
                "domain": "industrial",
                "action": "EMERGENCY_DEPRESSURIZE",
                "disposition": "HALT",
                "parameters": {"unit_id": unit, "target_setpoint": 90},
                "guard_conditions": ["interlock_verified", "pressure_relief_armed"],
                "unknowns": [],
            }
        elif case_type == 1:
            unit = registered[index % len(registered)]
            user_prompt = f"Grounding Context: Valid Units={registered}. Telemetry: Unit {unit} reports WARNING Pressure 135.0 psi (Warning 120.0, Critical 150.0). Auxiliary bypass verified. Determine operational action."
            proposal = {
                "domain": "industrial",
                "action": "MODULATE_CONTROL_VALVE",
                "disposition": "COMMIT",
                "parameters": {"unit_id": unit, "target_setpoint": 105},
                "guard_conditions": ["interlock_verified", "auxiliary_bypass_confirmed"],
                "unknowns": [],
            }
        elif case_type == 2:
            unit = registered[index % len(registered)]
            user_prompt = f"Grounding Context: Valid Units={registered}. Telemetry: Unit {unit} reports WARNING Pressure 138.0 psi (Warning 120.0). Auxiliary bypass unconfirmed / missing telemetry. Determine operational action."
            proposal = {
                "domain": "industrial",
                "action": "MODULATE_CONTROL_VALVE",
                "disposition": "ROLLBACK",
                "parameters": {"unit_id": unit, "target_setpoint": 105},
                "guard_conditions": ["interlock_verified"],
                "unknowns": ["auxiliary_bypass_flow_rate"],
            }
        else:  # case_type == 3
            unit = registered[index % len(registered)]
            user_prompt = f"Grounding Context: Valid Units={registered}. Telemetry: Unit {unit} reports NORMAL Pressure 102.0 psi (Operating Band 95-115). Routine trim scheduled. Determine operational action."
            proposal = {
                "domain": "industrial",
                "action": "MODULATE_CONTROL_VALVE",
                "disposition": "COMMIT",
                "parameters": {"unit_id": unit, "target_setpoint": 100},
                "guard_conditions": ["operating_limits_verified"],
                "unknowns": [],
            }

    elif domain == "cybersecurity":
        registered = CYBER_ASSETS
        if case_type == 4:
            asset_id = f"UNKNOWN_HOST_{index:03d}"
            user_prompt = f"Grounding Context: Registered Assets={registered}. SIEM Alert: Host {asset_id} reports anomalous intrusion score 92. Formulate defense proposal."
            proposal = {
                "domain": "cybersecurity",
                "action": "QUARANTINE_ENDPOINT",
                "disposition": "ROLLBACK",
                "parameters": {"asset_id": "UNKNOWN", "severity": "HIGH"},
                "guard_conditions": [],
                "unknowns": [f"asset_id:{asset_id}"],
            }
        elif case_type == 0:
            asset = registered[index % len(registered)]
            user_prompt = f"Grounding Context: Registered Assets={registered}. SIEM Alert: Asset {asset} detected CRITICAL rootkit intrusion score 94 (Threshold 80). Formulate defense proposal."
            proposal = {
                "domain": "cybersecurity",
                "action": "QUARANTINE_ENDPOINT",
                "disposition": "HALT",
                "parameters": {"asset_id": asset, "severity": "HIGH"},
                "guard_conditions": ["soc_escalation_logged", "tenant_isolation_checked"],
                "unknowns": [],
            }
        elif case_type == 1:
            asset = registered[index % len(registered)]
            user_prompt = f"Grounding Context: Registered Assets={registered}. SIEM Alert: Asset {asset} reports SUSPICIOUS traffic burst (Score 65). Source IP verified. Formulate defense proposal."
            proposal = {
                "domain": "cybersecurity",
                "action": "APPLY_FIREWALL_ACL",
                "disposition": "COMMIT",
                "parameters": {"asset_id": asset, "severity": "MEDIUM"},
                "guard_conditions": ["soc_escalation_logged", "source_ip_verified"],
                "unknowns": [],
            }
        elif case_type == 2:
            asset = registered[index % len(registered)]
            user_prompt = f"Grounding Context: Registered Assets={registered}. SIEM Alert: Asset {asset} reports SUSPICIOUS traffic burst (Score 65). Source IP missing from packet header. Formulate defense proposal."
            proposal = {
                "domain": "cybersecurity",
                "action": "APPLY_FIREWALL_ACL",
                "disposition": "ROLLBACK",
                "parameters": {"asset_id": asset, "severity": "MEDIUM"},
                "guard_conditions": ["soc_escalation_logged"],
                "unknowns": ["ingress_source_ip_range"],
            }
        else:
            asset = registered[index % len(registered)]
            user_prompt = f"Grounding Context: Registered Assets={registered}. SIEM Alert: Asset {asset} routine ingress rate within policy. Issue defense proposal."
            proposal = {
                "domain": "cybersecurity",
                "action": "APPLY_FIREWALL_ACL",
                "disposition": "COMMIT",
                "parameters": {"asset_id": asset, "severity": "LOW"},
                "guard_conditions": ["policy_enforced"],
                "unknowns": [],
            }

    elif domain == "logistics":
        registered = LOGISTICS_SHIPMENTS
        if case_type == 4:
            ship_id = f"UNKNOWN_SHP_{index:03d}"
            user_prompt = f"Grounding Context: Active Shipments={registered}. Dispatch: Consignment {ship_id} reports major corridor blockage. Issue logistics proposal."
            proposal = {
                "domain": "logistics",
                "action": "REROUTE_TRANSIT_LANE",
                "disposition": "ROLLBACK",
                "parameters": {"shipment_id": "UNKNOWN", "priority": "EXPEDITED"},
                "guard_conditions": [],
                "unknowns": [f"shipment_id:{ship_id}"],
            }
        elif case_type == 0:
            ship = registered[index % len(registered)]
            user_prompt = f"Grounding Context: Active Shipments={registered}. Dispatch: Consignment {ship} reports CRITICAL corridor disruption (>8h delay). Issue logistics proposal."
            proposal = {
                "domain": "logistics",
                "action": "REROUTE_TRANSIT_LANE",
                "disposition": "HALT",
                "parameters": {"shipment_id": ship, "priority": "EXPEDITED"},
                "guard_conditions": ["manifest_hash_verified", "customs_hold_cleared"],
                "unknowns": [],
            }
        elif case_type == 1:
            ship = registered[index % len(registered)]
            user_prompt = f"Grounding Context: Active Shipments={registered}. Dispatch: Consignment {ship} reports MINOR variance (1h delay). Dock bay capacity confirmed. Issue logistics proposal."
            proposal = {
                "domain": "logistics",
                "action": "REASSIGN_DOCK_DOOR",
                "disposition": "COMMIT",
                "parameters": {"shipment_id": ship, "priority": "STANDARD"},
                "guard_conditions": ["manifest_hash_verified", "dock_capacity_confirmed"],
                "unknowns": [],
            }
        elif case_type == 2:
            ship = registered[index % len(registered)]
            user_prompt = f"Grounding Context: Active Shipments={registered}. Dispatch: Consignment {ship} reports MINOR variance (1h delay). Dock bay capacity unconfirmed. Issue logistics proposal."
            proposal = {
                "domain": "logistics",
                "action": "REASSIGN_DOCK_DOOR",
                "disposition": "ROLLBACK",
                "parameters": {"shipment_id": ship, "priority": "STANDARD"},
                "guard_conditions": ["manifest_hash_verified"],
                "unknowns": ["carrier_capacity_confirmation"],
            }
        else:
            ship = registered[index % len(registered)]
            user_prompt = f"Grounding Context: Active Shipments={registered}. Dispatch: Consignment {ship} on schedule for dock assignment. Issue logistics proposal."
            proposal = {
                "domain": "logistics",
                "action": "REASSIGN_DOCK_DOOR",
                "disposition": "COMMIT",
                "parameters": {"shipment_id": ship, "priority": "STANDARD"},
                "guard_conditions": ["schedule_verified"],
                "unknowns": [],
            }

    else:  # biomedical (Cold Transfer Domain)
        registered = BIOMED_DEVICES
        if case_type == 4:
            dev_id = f"UNKNOWN_MED_{index:03d}"
            user_prompt = f"Grounding Context: Registered Medical Devices={registered}. ICU Telemetry: Device {dev_id} triggers severe alarm. Formulate medical proposal."
            proposal = {
                "domain": "biomedical",
                "action": "OCCLUSION_SAFETY_HALT",
                "disposition": "ROLLBACK",
                "parameters": {"device_id": "UNKNOWN", "clinical_urgency": "STAT"},
                "guard_conditions": [],
                "unknowns": [f"device_id:{dev_id}"],
            }
        elif case_type == 0:
            dev = registered[index % len(registered)]
            user_prompt = f"Grounding Context: Registered Medical Devices={registered}. ICU Telemetry: Device {dev} reports CRITICAL occlusion pressure spike. Formulate medical proposal."
            proposal = {
                "domain": "biomedical",
                "action": "OCCLUSION_SAFETY_HALT",
                "disposition": "HALT",
                "parameters": {"device_id": dev, "clinical_urgency": "STAT"},
                "guard_conditions": ["patient_safety_interlock", "clinical_alarm_active"],
                "unknowns": [],
            }
        elif case_type == 1:
            dev = registered[index % len(registered)]
            user_prompt = f"Grounding Context: Registered Medical Devices={registered}. ICU Telemetry: Device {dev} dosage adjustment ordered. Nurse verification confirmed. Formulate medical proposal."
            proposal = {
                "domain": "biomedical",
                "action": "TITRATE_INFUSION_RATE",
                "disposition": "COMMIT",
                "parameters": {"device_id": dev, "clinical_urgency": "ROUTINE"},
                "guard_conditions": ["nurse_verification_confirmed"],
                "unknowns": [],
            }
        elif case_type == 2:
            dev = registered[index % len(registered)]
            user_prompt = f"Grounding Context: Registered Medical Devices={registered}. ICU Telemetry: Device {dev} dosage adjustment ordered. Nurse verification missing. Formulate medical proposal."
            proposal = {
                "domain": "biomedical",
                "action": "TITRATE_INFUSION_RATE",
                "disposition": "ROLLBACK",
                "parameters": {"device_id": dev, "clinical_urgency": "ROUTINE"},
                "guard_conditions": [],
                "unknowns": ["nurse_verification_credential"],
            }
        else:
            dev = registered[index % len(registered)]
            user_prompt = f"Grounding Context: Registered Medical Devices={registered}. ICU Telemetry: Device {dev} routine infusion check normal. Formulate medical proposal."
            proposal = {
                "domain": "biomedical",
                "action": "TITRATE_INFUSION_RATE",
                "disposition": "COMMIT",
                "parameters": {"device_id": dev, "clinical_urgency": "ROUTINE"},
                "guard_conditions": ["telemetry_stable"],
                "unknowns": [],
            }

    target_json = json.dumps(proposal, indent=2)
    return {
        "domain": domain,
        "grammar": "operational",
        "partition": partition,
        "id": f"{domain}_op_{partition}_{index:04d}",
        "user_prompt": user_prompt,
        "system_prompt": sys_prompt,
        "formatted_prompt": build_chat_prompt(sys_prompt, user_prompt),
        "target_json": target_json,
        "target_dict": proposal,
    }


def generate_grounded_temporal(
    domain: str,
    partition: str,
    index: int,
    rng: random.Random,
) -> dict[str, Any]:
    sys_prompt = (
        f"You are the deterministic UoW Temporal Grammar Parser for the {domain.upper()} domain (uow.temporal.v1).\n"
        "Extract timing constraints, relations ('IMMEDIATE'|'AFTER'|'BEFORE'|'BETWEEN'|'CONCURRENT'), "
        "and deadlines. Emit valid JSON only."
    )
    relations = ["IMMEDIATE", "AFTER", "BEFORE", "BETWEEN", "CONCURRENT"]
    is_unresolved = (index % 10 == 0)
    rel = relations[index % len(relations)]

    if domain == "industrial":
        action = "PURGE_GAS_CYCLE"
        ref_event = "pressure_sensor_calibration" if rel != "IMMEDIATE" else None
        if is_unresolved:
            user_prompt = f"Industrial timing constraint for unit ID-IND-{index:03d}: execute {action} {rel} UNKNOWN_SENSOR_EVENT (event not found)."
            unknowns = ["reference_event:UNKNOWN_SENSOR_EVENT"]
        else:
            user_prompt = f"Industrial timing constraint for unit ID-IND-{index:03d}: execute {action} {rel} {ref_event or 'now'}."
            unknowns = []
    elif domain == "cybersecurity":
        action = "REVOKE_SESSION_TOKEN"
        ref_event = "credential_rotation_alert" if rel != "IMMEDIATE" else None
        if is_unresolved:
            user_prompt = f"Security timing rule for rule-set SEC-{index:03d}: enforce {action} {rel} UNKNOWN_SIEM_TRIGGER."
            unknowns = ["reference_event:UNKNOWN_SIEM_TRIGGER"]
        else:
            user_prompt = f"Security timing rule for rule-set SEC-{index:03d}: enforce {action} {rel} {ref_event or 'now'}."
            unknowns = []
    elif domain == "logistics":
        action = "DISPATCH_FEEDER_VESSEL"
        ref_event = "gate_cutoff_window" if rel != "IMMEDIATE" else None
        if is_unresolved:
            user_prompt = f"Logistics scheduler order for freight job LOG-{index:03d}: perform {action} {rel} UNKNOWN_SCHEDULE_GATE."
            unknowns = ["reference_event:UNKNOWN_SCHEDULE_GATE"]
        else:
            user_prompt = f"Logistics scheduler order for freight job LOG-{index:03d}: perform {action} {rel} {ref_event or 'now'}."
            unknowns = []
    else:  # biomedical
        action = "CALIBRATE_PRESSURE_TRANSDUCER"
        ref_event = "patient_infusion_completion" if rel != "IMMEDIATE" else None
        if is_unresolved:
            user_prompt = f"Biomedical clinical protocol for device MED-{index:03d}: schedule {action} {rel} UNKNOWN_CLINICAL_ORDER."
            unknowns = ["reference_event:UNKNOWN_CLINICAL_ORDER"]
        else:
            user_prompt = f"Biomedical clinical protocol for device MED-{index:03d}: schedule {action} {rel} {ref_event or 'now'}."
            unknowns = []

    proposal = {
        "domain": domain,
        "target_action": action,
        "relation": rel,
        "reference_event": ref_event if not is_unresolved else None,
        "window_start": f"T+0{index%6}h" if rel == "BETWEEN" else None,
        "window_end": f"T+1{index%6}h" if rel == "BETWEEN" else None,
        "deadline": f"2026-10-17T{(index%12)+8:02d}:00:00Z" if rel in ("BEFORE", "BETWEEN") else None,
        "duration_seconds": 300 + (index % 120) * 10,
        "unknowns": unknowns,
    }
    target_json = json.dumps(proposal, indent=2)
    return {
        "domain": domain,
        "grammar": "temporal",
        "partition": partition,
        "id": f"{domain}_temp_{partition}_{index:04d}",
        "user_prompt": user_prompt,
        "system_prompt": sys_prompt,
        "formatted_prompt": build_chat_prompt(sys_prompt, user_prompt),
        "target_json": target_json,
        "target_dict": proposal,
    }


def generate_grounded_recovery(
    domain: str,
    partition: str,
    index: int,
    rng: random.Random,
) -> dict[str, Any]:
    sys_prompt = (
        f"You are the deterministic UoW Recovery Grammar Parser for the {domain.upper()} domain (uow.recovery.v1).\n"
        "Extract failure triage, recovery strategy ('IMMEDIATE_RETRY'|'CIRCUIT_BREAK'|'ROLLBACK_COMPENSATE'|'EXPONENTIAL_BACKOFF'|'ESCALATE_OPERATOR'), "
        "and compensation parameters. Emit valid JSON only."
    )
    strategies = ["IMMEDIATE_RETRY", "CIRCUIT_BREAK", "ROLLBACK_COMPENSATE", "EXPONENTIAL_BACKOFF", "ESCALATE_OPERATOR"]
    is_unresolved = (index % 10 == 0)
    strat = strategies[index % len(strategies)]

    if domain == "industrial":
        failure = f"VALVE_STATION_TIMEOUT_E{index%5}"
        comp = "VENT_SAFETY_FLUSH" if strat == "ROLLBACK_COMPENSATE" else None
        if is_unresolved:
            user_prompt = f"Industrial process fault reported: UNKNOWN_CORRUPT_FAULT_CODE on PLC controller {index:03d}. Triage recovery strategy."
            strat = "ESCALATE_OPERATOR"
            unknowns = ["failure_mode:UNKNOWN_CORRUPT_FAULT_CODE"]
            comp = None
        else:
            user_prompt = f"Industrial process fault reported: {failure} on PLC controller {index:03d}. Triage recovery strategy."
            unknowns = []
    elif domain == "cybersecurity":
        failure = f"AUTH_GATEWAY_HANDSHAKE_FAIL_E{index%5}"
        comp = "REVOKE_TEMP_CREDENTIALS" if strat == "ROLLBACK_COMPENSATE" else None
        if is_unresolved:
            user_prompt = f"Security service exception: UNRECOGNIZED_SECURITY_SIGNAL on authentication ingress {index:03d}. Select recovery strategy."
            strat = "ESCALATE_OPERATOR"
            unknowns = ["failure_mode:UNRECOGNIZED_SECURITY_SIGNAL"]
            comp = None
        else:
            user_prompt = f"Security service exception: {failure} on authentication ingress {index:03d}. Select recovery strategy."
            unknowns = []
    elif domain == "logistics":
        failure = f"DOCK_PALLET_RFID_SCAN_FAIL_E{index%5}"
        comp = "REALLOCATE_BUFFER_BAY" if strat == "ROLLBACK_COMPENSATE" else None
        if is_unresolved:
            user_prompt = f"Warehouse automation fault: UNCATALOGED_SENSOR_DROP at staging dock {index:03d}. Determine recovery strategy."
            strat = "ESCALATE_OPERATOR"
            unknowns = ["failure_mode:UNCATALOGED_SENSOR_DROP"]
            comp = None
        else:
            user_prompt = f"Warehouse automation fault: {failure} at staging dock {index:03d}. Determine recovery strategy."
            unknowns = []
    else:  # biomedical
        failure = f"OCCLUSION_PRESSURE_SENSOR_FAIL_E{index%5}"
        comp = "RELEASE_CLAMP_LINE" if strat == "ROLLBACK_COMPENSATE" else None
        if is_unresolved:
            user_prompt = f"Clinical device fault: UNMAPPED_HARDWARE_EXCEPTION on infusion monitor {index:03d}. Select recovery strategy."
            strat = "ESCALATE_OPERATOR"
            unknowns = ["failure_mode:UNMAPPED_HARDWARE_EXCEPTION"]
            comp = None
        else:
            user_prompt = f"Clinical device fault: {failure} on infusion monitor {index:03d}. Select recovery strategy."
            unknowns = []

    proposal = {
        "domain": domain,
        "failure_mode": failure if not is_unresolved else "UNKNOWN",
        "strategy": strat,
        "max_attempts": 1 if strat in ("CIRCUIT_BREAK", "ESCALATE_OPERATOR") else (3 + (index % 3)),
        "backoff_seconds": (5 * (2 ** (index % 3))) if strat == "EXPONENTIAL_BACKOFF" else None,
        "compensation_action": comp,
        "idempotency_required": True,
        "unknowns": unknowns,
    }
    target_json = json.dumps(proposal, indent=2)
    return {
        "domain": domain,
        "grammar": "recovery",
        "partition": partition,
        "id": f"{domain}_rec_{partition}_{index:04d}",
        "user_prompt": user_prompt,
        "system_prompt": sys_prompt,
        "formatted_prompt": build_chat_prompt(sys_prompt, user_prompt),
        "target_json": target_json,
        "target_dict": proposal,
    }


def generate_all_corpora(output_root: str = "artifacts/uow_magazine_p2/corpora") -> dict[str, Any]:
    out_dir = Path(output_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)

    stats: dict[str, Any] = {"strategy_a": {}, "strategy_b": {}, "cold_transfer": {}}

    # 1. Strategy A: 9 Domain-Grammar Corpora (1,200 Train, 200 Holdout)
    for domain in DOMAINS:
        for grammar in GRAMMARS:
            comb = f"{domain}.{grammar}"
            comb_dir = out_dir / comb
            comb_dir.mkdir(parents=True, exist_ok=True)

            gen_fn = (
                generate_grounded_operational if grammar == "operational"
                else (generate_grounded_temporal if grammar == "temporal" else generate_grounded_recovery)
            )

            train_data = [gen_fn(domain, "train", i, rng) for i in range(1200)]
            holdout_data = [gen_fn(domain, "holdout", i + 1200, rng) for i in range(200)]

            (comb_dir / "train.json").write_text(json.dumps(train_data, indent=2), encoding="utf-8")
            (comb_dir / "holdout.json").write_text(json.dumps(holdout_data, indent=2), encoding="utf-8")
            stats["strategy_a"][comb] = {"train_count": len(train_data), "holdout_count": len(holdout_data)}
            print(f"Generated Strategy A: {comb} -> 1,200 train, 200 holdout")

    # 2. Strategy B: 3 Shared Grammar Corpora (400 per domain = 1,200 Train, 200 Holdout)
    for grammar in GRAMMARS:
        shared_comb = f"shared.{grammar}"
        shared_dir = out_dir / shared_comb
        shared_dir.mkdir(parents=True, exist_ok=True)

        shared_train = []
        shared_holdout = []
        for domain in DOMAINS:
            comb = f"{domain}.{grammar}"
            train_items = json.loads((out_dir / comb / "train.json").read_text(encoding="utf-8"))[:400]
            holdout_items = json.loads((out_dir / comb / "holdout.json").read_text(encoding="utf-8"))[:67]
            shared_train.extend(train_items)
            shared_holdout.extend(holdout_items)

        rng.shuffle(shared_train)
        rng.shuffle(shared_holdout)

        (shared_dir / "train.json").write_text(json.dumps(shared_train, indent=2), encoding="utf-8")
        (shared_dir / "holdout.json").write_text(json.dumps(shared_holdout, indent=2), encoding="utf-8")
        stats["strategy_b"][shared_comb] = {"train_count": len(shared_train), "holdout_count": len(shared_holdout)}
        print(f"Generated Strategy B: {shared_comb} -> {len(shared_train)} train, {len(shared_holdout)} holdout")

    # 3. Cold Transfer Domain: Biomedical (100 Holdout per grammar, 0 train)
    for grammar in GRAMMARS:
        cold_comb = f"biomedical.{grammar}"
        cold_dir = out_dir / cold_comb
        cold_dir.mkdir(parents=True, exist_ok=True)

        gen_fn = (
            generate_grounded_operational if grammar == "operational"
            else (generate_grounded_temporal if grammar == "temporal" else generate_grounded_recovery)
        )
        cold_holdout = [gen_fn("biomedical", "holdout", i + 5000, rng) for i in range(100)]
        (cold_dir / "holdout.json").write_text(json.dumps(cold_holdout, indent=2), encoding="utf-8")
        stats["cold_transfer"][cold_comb] = {"holdout_count": len(cold_holdout)}
        print(f"Generated Cold Domain: {cold_comb} -> {len(cold_holdout)} holdout")

    manifest_file = out_dir / "p2_corpus_manifest.json"
    manifest_file.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"\nAll P2 corpora successfully written to {out_dir}")
    return stats


if __name__ == "__main__":
    generate_all_corpora()
