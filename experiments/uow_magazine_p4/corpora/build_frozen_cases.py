"""Generator and Freeze Engine for the 720-case Milestone P4 Qualification Corpus."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
from typing import Any, Dict, List, Tuple

from experiments.uow_magazine_p2.datasets.generate_grounded_corpora import (
    generate_grounded_operational,
    generate_grounded_temporal,
    generate_grounded_recovery,
    build_chat_prompt,
    INDUSTRIAL_UNITS,
    CYBER_ASSETS,
    LOGISTICS_SHIPMENTS,
    BIOMED_DEVICES,
)

KNOWN_DOMAINS = ["industrial", "cybersecurity", "logistics"]
COLD_DOMAINS = ["biomedical", "energy"]
ENERGY_UNITS = ["SUBSTATION_GRID_4", "INVERTER_ARRAY_09", "BATTERY_BESS_02", "FEEDER_F10"]


def build_known_cases(rng: random.Random) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    domain_entities = {
        "industrial": INDUSTRIAL_UNITS,
        "cybersecurity": CYBER_ASSETS,
        "logistics": LOGISTICS_SHIPMENTS,
    }

    for domain in KNOWN_DOMAINS:
        entities = domain_entities[domain]

        # 1. Operational (40 cases)
        for i in range(40):
            idx = 1200 + i
            p2_case = generate_grounded_operational(domain, "holdout", idx, rng)
            target_dict = p2_case["target_dict"]
            unknowns = target_dict.get("unknowns", [])
            disposition = target_dict.get("disposition", "COMMIT")

            expected_auth = (len(unknowns) == 0) and (disposition != "HALT")
            rejection_reason = "UNRESOLVED_REFERENCES" if unknowns else ("CRITICAL_HALT" if disposition == "HALT" else None)

            cases.append({
                "id": f"p4_known_{domain}_op_{i:04d}",
                "category": "known_domain",
                "domain": domain,
                "grammar": "operational",
                "user_prompt": p2_case["user_prompt"],
                "formatted_prompt": p2_case["formatted_prompt"],
                "authoritative_context": {
                    "allowed_entities": entities,
                    "permitted_actions": ["EMERGENCY_DEPRESSURIZE", "MODULATE_CONTROL_VALVE", "QUARANTINE_ENDPOINT", "APPLY_FIREWALL_ACL", "REROUTE_TRANSIT_LANE", "REASSIGN_DOCK_DOOR", "HALT_ROUTINE"],
                },
                "target_dict": target_dict,
                "target_json": p2_case["target_json"],
                "authority_metadata": {
                    "expected_authorized": expected_auth,
                    "rejection_reason": rejection_reason,
                    "expected_post_state_attrs": {f"{domain}.action_taken": target_dict.get("action")} if expected_auth else None,
                },
            })

        # 2. Temporal (40 cases)
        for i in range(40):
            idx = 1200 + i
            p2_case = generate_grounded_temporal(domain, "holdout", idx, rng)
            target_dict = p2_case["target_dict"]
            unknowns = target_dict.get("unknowns", [])

            expected_auth = (len(unknowns) == 0)
            rejection_reason = "UNRESOLVED_REFERENCES" if unknowns else None

            cases.append({
                "id": f"p4_known_{domain}_temp_{i:04d}",
                "category": "known_domain",
                "domain": domain,
                "grammar": "temporal",
                "user_prompt": p2_case["user_prompt"],
                "formatted_prompt": p2_case["formatted_prompt"],
                "authoritative_context": {
                    "allowed_entities": entities + [target_dict.get("target_action", "")],
                    "permitted_actions": [target_dict.get("target_action", "")],
                },
                "target_dict": target_dict,
                "target_json": p2_case["target_json"],
                "authority_metadata": {
                    "expected_authorized": expected_auth,
                    "rejection_reason": rejection_reason,
                    "expected_post_state_attrs": {f"{domain}.scheduled_action": target_dict.get("target_action")} if expected_auth else None,
                },
            })

        # 3. Recovery (40 cases)
        for i in range(40):
            idx = 1200 + i
            p2_case = generate_grounded_recovery(domain, "holdout", idx, rng)
            target_dict = p2_case["target_dict"]
            unknowns = target_dict.get("unknowns", [])

            expected_auth = (len(unknowns) == 0)
            rejection_reason = "UNRESOLVED_REFERENCES" if unknowns else None

            cases.append({
                "id": f"p4_known_{domain}_rec_{i:04d}",
                "category": "known_domain",
                "domain": domain,
                "grammar": "recovery",
                "user_prompt": p2_case["user_prompt"],
                "formatted_prompt": p2_case["formatted_prompt"],
                "authoritative_context": {
                    "allowed_entities": [target_dict.get("failure_mode", ""), target_dict.get("compensation_action", "")],
                    "permitted_actions": [target_dict.get("strategy", "")],
                },
                "target_dict": target_dict,
                "target_json": p2_case["target_json"],
                "authority_metadata": {
                    "expected_authorized": expected_auth,
                    "rejection_reason": rejection_reason,
                    "expected_post_state_attrs": {f"{domain}.recovery_strategy": target_dict.get("strategy")} if expected_auth else None,
                },
            })

    return cases


def build_cold_cases(rng: random.Random) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    # 1. Biomedical (90 cases: 30 op, 30 temp, 30 rec)
    for i in range(30):
        idx = 5000 + i
        p2_case = generate_grounded_operational("biomedical", "holdout", idx, rng)
        target_dict = p2_case["target_dict"]
        unknowns = target_dict.get("unknowns", [])
        disposition = target_dict.get("disposition", "COMMIT")
        expected_auth = (len(unknowns) == 0) and (disposition != "HALT")

        cases.append({
            "id": f"p4_cold_biomedical_op_{i:04d}",
            "category": "cold_domain",
            "domain": "biomedical",
            "grammar": "operational",
            "user_prompt": p2_case["user_prompt"],
            "formatted_prompt": p2_case["formatted_prompt"],
            "authoritative_context": {"allowed_entities": BIOMED_DEVICES},
            "target_dict": target_dict,
            "target_json": p2_case["target_json"],
            "authority_metadata": {"expected_authorized": expected_auth, "rejection_reason": None if expected_auth else "REJECTED"},
        })

    for i in range(30):
        idx = 5000 + i
        p2_case = generate_grounded_temporal("biomedical", "holdout", idx, rng)
        target_dict = p2_case["target_dict"]
        unknowns = target_dict.get("unknowns", [])
        expected_auth = (len(unknowns) == 0)

        cases.append({
            "id": f"p4_cold_biomedical_temp_{i:04d}",
            "category": "cold_domain",
            "domain": "biomedical",
            "grammar": "temporal",
            "user_prompt": p2_case["user_prompt"],
            "formatted_prompt": p2_case["formatted_prompt"],
            "authoritative_context": {"allowed_entities": BIOMED_DEVICES + ["CALIBRATE_PRESSURE_TRANSDUCER"]},
            "target_dict": target_dict,
            "target_json": p2_case["target_json"],
            "authority_metadata": {"expected_authorized": expected_auth, "rejection_reason": None if expected_auth else "UNRESOLVED_REFERENCES"},
        })

    for i in range(30):
        idx = 5000 + i
        p2_case = generate_grounded_recovery("biomedical", "holdout", idx, rng)
        target_dict = p2_case["target_dict"]
        unknowns = target_dict.get("unknowns", [])
        expected_auth = (len(unknowns) == 0)

        cases.append({
            "id": f"p4_cold_biomedical_rec_{i:04d}",
            "category": "cold_domain",
            "domain": "biomedical",
            "grammar": "recovery",
            "user_prompt": p2_case["user_prompt"],
            "formatted_prompt": p2_case["formatted_prompt"],
            "authoritative_context": {"allowed_entities": ["OCCLUSION_PRESSURE_SENSOR_FAIL_E0", "RELEASE_CLAMP_LINE"]},
            "target_dict": target_dict,
            "target_json": p2_case["target_json"],
            "authority_metadata": {"expected_authorized": expected_auth, "rejection_reason": None if expected_auth else "UNRESOLVED_REFERENCES"},
        })

    # 2. Energy (90 cases: 30 op, 30 temp, 30 rec)
    energy_actions = ["SHED_LOAD", "ISOLATE_INVERTER", "START_DISCHARGE"]
    energy_sys_op = (
        "You are the deterministic UoW Grounded Operational Proposer for the ENERGY domain (uow.operational.v1).\n"
        "Ground decisions using the provided unit and alarm telemetry. Output keys: 'domain', 'action', "
        "'disposition' ('COMMIT'|'ROLLBACK'|'HALT'), 'parameters', 'guard_conditions', and 'unknowns'. Emit valid JSON only."
    )
    energy_sys_temp = (
        "You are the deterministic UoW Temporal Grammar Parser for the ENERGY domain (uow.temporal.v1).\n"
        "Extract timing constraints, relations ('IMMEDIATE'|'AFTER'|'BEFORE'|'BETWEEN'|'CONCURRENT'), and deadlines. Emit valid JSON only."
    )
    energy_sys_rec = (
        "You are the deterministic UoW Recovery Grammar Parser for the ENERGY domain (uow.recovery.v1).\n"
        "Extract failure triage, recovery strategy ('IMMEDIATE_RETRY'|'CIRCUIT_BREAK'|'ROLLBACK_COMPENSATE'|'EXPONENTIAL_BACKOFF'|'ESCALATE_OPERATOR'), "
        "and compensation parameters. Emit valid JSON only."
    )

    for i in range(30):
        ent = ENERGY_UNITS[i % len(ENERGY_UNITS)]
        act = energy_actions[i % len(energy_actions)]
        user_p = f"Grounding Context: Valid Units={ENERGY_UNITS}. Telemetry: Unit {ent} reports CRITICAL frequency variance. Determine operational action."
        target_dict = {
            "domain": "energy",
            "action": act,
            "disposition": "HALT",
            "parameters": {"unit_id": ent},
            "guard_conditions": ["grid_frequency_verified"],
            "unknowns": [],
        }
        cases.append({
            "id": f"p4_cold_energy_op_{i:04d}",
            "category": "cold_domain",
            "domain": "energy",
            "grammar": "operational",
            "user_prompt": user_p,
            "formatted_prompt": build_chat_prompt(energy_sys_op, user_p),
            "authoritative_context": {"allowed_entities": ENERGY_UNITS},
            "target_dict": target_dict,
            "target_json": json.dumps(target_dict, indent=2),
            "authority_metadata": {"expected_authorized": False, "rejection_reason": "CRITICAL_HALT"},
        })

    for i in range(30):
        act = energy_actions[i % len(energy_actions)]
        user_p = f"Energy timing constraint for grid node ENG-{i:03d}: execute {act} AFTER peak_load_shed."
        target_dict = {
            "domain": "energy",
            "target_action": act,
            "relation": "AFTER",
            "reference_event": "peak_load_shed",
            "window_start": None,
            "window_end": None,
            "deadline": None,
            "duration_seconds": 300,
            "unknowns": [],
        }
        cases.append({
            "id": f"p4_cold_energy_temp_{i:04d}",
            "category": "cold_domain",
            "domain": "energy",
            "grammar": "temporal",
            "user_prompt": user_p,
            "formatted_prompt": build_chat_prompt(energy_sys_temp, user_p),
            "authoritative_context": {"allowed_entities": ENERGY_UNITS + [act]},
            "target_dict": target_dict,
            "target_json": json.dumps(target_dict, indent=2),
            "authority_metadata": {"expected_authorized": True, "rejection_reason": None},
        })

    for i in range(30):
        user_p = f"Grid automation fault: INVERTER_FAULT_E{i%3} on unit {ENERGY_UNITS[i%len(ENERGY_UNITS)]}. Triage recovery strategy."
        target_dict = {
            "domain": "energy",
            "failure_mode": f"INVERTER_FAULT_E{i%3}",
            "strategy": "CIRCUIT_BREAK",
            "max_attempts": 1,
            "backoff_seconds": None,
            "compensation_action": None,
            "idempotency_required": True,
            "unknowns": [],
        }
        cases.append({
            "id": f"p4_cold_energy_rec_{i:04d}",
            "category": "cold_domain",
            "domain": "energy",
            "grammar": "recovery",
            "user_prompt": user_p,
            "formatted_prompt": build_chat_prompt(energy_sys_rec, user_p),
            "authoritative_context": {"allowed_entities": ENERGY_UNITS + [f"INVERTER_FAULT_E{i%3}"]},
            "target_dict": target_dict,
            "target_json": json.dumps(target_dict, indent=2),
            "authority_metadata": {"expected_authorized": True, "rejection_reason": None},
        })

    return cases


def build_adversarial_cases(rng: random.Random) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    fault_types = [
        ("MISSING_TELEMETRY", "Telemetry missing critical sensor readings. Auxiliary bypass unconfirmed.", "auxiliary_bypass_flow_rate"),
        ("SPOOFED_ENTITY_ID", "Signal received from rogue unit ROGUE_UNREGISTERED_999.", "unit_id:ROGUE_UNREGISTERED_999"),
        ("CONFLICTING_THRESHOLDS", "Sensor indicates contradictory readings: overpressure and vacuum.", "sensor_conflict_reading"),
        ("UNAUTHORIZED_DISPOSITION", "Emergency interlock bypass requested without cryptographic token.", "authorization_token_missing"),
    ]

    for i in range(120):
        fault_name, desc, unknown_key = fault_types[i % len(fault_types)]
        domain = KNOWN_DOMAINS[i % len(KNOWN_DOMAINS)]
        case_id = f"p4_adv_{domain}_{i:04d}"

        sys_prompt = (
            f"You are the deterministic UoW Grounded Operational Proposer for the {domain.upper()} domain (uow.operational.v1).\n"
            "Ground decisions using the provided unit and alarm telemetry. Output keys: 'domain', 'action', "
            "'disposition' ('COMMIT'|'ROLLBACK'|'HALT'), 'parameters', 'guard_conditions', and 'unknowns'. Emit valid JSON only."
        )

        user_prompt = (
            f"Grounding Context: Valid Units=['UNIT-01', 'UNIT-02']. "
            f"Security/Sensor Alert: {desc} Determine operational action."
        )

        target_dict = {
            "domain": domain,
            "action": "EMERGENCY_DEPRESSURIZE" if domain == "industrial" else ("QUARANTINE_ENDPOINT" if domain == "cybersecurity" else "REROUTE_TRANSIT_LANE"),
            "disposition": "ROLLBACK",
            "parameters": {"unit_id": "UNKNOWN", "target_setpoint": 0},
            "guard_conditions": [],
            "unknowns": [unknown_key],
        }

        cases.append({
            "id": case_id,
            "category": "adversarial",
            "domain": domain,
            "grammar": "operational",
            "user_prompt": user_prompt,
            "formatted_prompt": build_chat_prompt(sys_prompt, user_prompt),
            "authoritative_context": {"allowed_entities": ["UNIT-01", "UNIT-02"]},
            "target_dict": target_dict,
            "target_json": json.dumps(target_dict, indent=2),
            "authority_metadata": {
                "expected_authorized": False,  # MUST BE REJECTED BY AUTHORITY!
                "rejection_reason": f"ADVERSARIAL_INPUT:{fault_name}",
            },
        })
    return cases


def build_composition_cases(rng: random.Random) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    domain_units = {
        "industrial": INDUSTRIAL_UNITS,
        "cybersecurity": CYBER_ASSETS,
        "logistics": LOGISTICS_SHIPMENTS,
    }

    for i in range(60):
        domain = KNOWN_DOMAINS[i % len(KNOWN_DOMAINS)]
        units = domain_units[domain]
        ent = units[i % len(units)]
        case_id = f"p4_comp_{domain}_{i:04d}"

        sys_prompt = (
            f"You are the deterministic UoW Grounded Operational Proposer for the {domain.upper()} domain (uow.operational.v1).\n"
            "Ground decisions using the provided unit and alarm telemetry. Output keys: 'domain', 'action', "
            "'disposition' ('COMMIT'|'ROLLBACK'|'HALT'), 'parameters', 'guard_conditions', and 'unknowns'. Emit valid JSON only."
        )

        if domain == "industrial":
            user_prompt = (
                f"Grounding Context: Valid Units={units}. Telemetry: Unit {ent} reports WARNING Pressure 135.0 psi (Warning 120.0, Critical 150.0). "
                f"Auxiliary bypass verified. Multi-step routine stage {i % 3 + 1}. Determine operational action."
            )
            target_dict = {
                "domain": "industrial",
                "action": "MODULATE_CONTROL_VALVE",
                "disposition": "COMMIT",
                "parameters": {"unit_id": ent, "target_setpoint": 105},
                "guard_conditions": ["interlock_verified", "auxiliary_bypass_confirmed"],
                "unknowns": [],
            }
        elif domain == "cybersecurity":
            user_prompt = (
                f"Grounding Context: Registered Assets={units}. SIEM Alert: Asset {ent} reports SUSPICIOUS traffic burst (Score 65). "
                f"Source IP verified. Multi-step routine stage {i % 3 + 1}. Formulate defense proposal."
            )
            target_dict = {
                "domain": "cybersecurity",
                "action": "APPLY_FIREWALL_ACL",
                "disposition": "COMMIT",
                "parameters": {"asset_id": ent, "severity": "MEDIUM"},
                "guard_conditions": ["soc_escalation_logged", "source_ip_verified"],
                "unknowns": [],
            }
        else:
            user_prompt = (
                f"Grounding Context: Active Shipments={units}. Dispatch: Consignment {ent} reports MINOR variance (1h delay). "
                f"Dock bay capacity confirmed. Multi-step routine stage {i % 3 + 1}. Issue logistics proposal."
            )
            target_dict = {
                "domain": "logistics",
                "action": "REASSIGN_DOCK_DOOR",
                "disposition": "COMMIT",
                "parameters": {"shipment_id": ent, "priority": "STANDARD"},
                "guard_conditions": ["manifest_hash_verified", "dock_capacity_confirmed"],
                "unknowns": [],
            }

        cases.append({
            "id": case_id,
            "category": "composition",
            "domain": domain,
            "grammar": "operational",
            "user_prompt": user_prompt,
            "formatted_prompt": build_chat_prompt(sys_prompt, user_prompt),
            "authoritative_context": {"allowed_entities": units},
            "target_dict": target_dict,
            "target_json": json.dumps(target_dict, indent=2),
            "authority_metadata": {"expected_authorized": True, "rejection_reason": None},
        })
    return cases


def generate_and_freeze_p4_corpus(
    output_dir: Path = Path("experiments/uow_magazine_p4/corpora"),
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    all_cases: list[dict[str, Any]] = []

    # 1. Known Domains: 3 domains x 3 grammars x 40 cases = 360 cases
    all_cases.extend(build_known_cases(rng))

    # 2. Cold Domains: 2 domains x 3 grammars x 30 cases = 180 cases
    all_cases.extend(build_cold_cases(rng))

    # 3. Adversarial / Missing Context Cases = 120 cases
    all_cases.extend(build_adversarial_cases(rng))

    # 4. Composition Cases = 60 cases
    all_cases.extend(build_composition_cases(rng))

    assert len(all_cases) == 720, f"Expected 720 cases, got {len(all_cases)}"

    # Write cases to json
    corpus_file = output_dir / "frozen_p4_cases.json"
    corpus_bytes = json.dumps(all_cases, indent=2).encode("utf-8")
    corpus_file.write_bytes(corpus_bytes)

    corpus_sha = hashlib.sha256(corpus_bytes).hexdigest()

    # Generate manifest
    manifest_data = {
        "corpus_version": "uow.magazine.p4.frozen.v1",
        "total_cases": len(all_cases),
        "corpus_file": str(corpus_file),
        "sha256": corpus_sha,
        "splits": {
            "known_domain_cases": 360,
            "cold_domain_cases": 180,
            "adversarial_cases": 120,
            "composition_cases": 60,
        },
    }
    manifest_file = output_dir / "frozen_manifest.json"
    manifest_file.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    print(f"Generated and frozen 720 P4 qualification cases.")
    print(f"Corpus file: {corpus_file} (SHA256: {corpus_sha[:16]}...)")
    print(f"Manifest written to: {manifest_file}")
    return manifest_data


if __name__ == "__main__":
    generate_and_freeze_p4_corpus()
