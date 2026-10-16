"""UoW Recovery Grammar (uow.recovery.v1) Schema, Codec, and Dataset Generator."""
from __future__ import annotations
from dataclasses import dataclass, field
import json
import random
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = "uow.recovery.v1"

@dataclass(frozen=True)
class RecoveryPlan:
    failed_uow: str
    strategy: str  # "RETRY", "COMPENSATE", "FALLBACK", "ESCALATE"
    max_attempts: Optional[int] = None
    backoff: Optional[str] = None  # "EXPONENTIAL", "LINEAR", "FIXED"
    compensation_uow: Optional[str] = None
    fallback_uow: Optional[str] = None
    unknowns: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "failed_uow": self.failed_uow,
            "strategy": self.strategy,
        }
        if self.max_attempts is not None or self.backoff is not None:
            d["retry_policy"] = {
                "max_attempts": self.max_attempts or 3,
                "backoff": self.backoff or "FIXED"
            }
        if self.compensation_uow is not None:
            d["compensation_uow"] = self.compensation_uow
        if self.fallback_uow is not None:
            d["fallback_uow"] = self.fallback_uow
        if self.unknowns:
            d["unknowns"] = list(self.unknowns)
        return d


class RecoveryPromptBuilder:
    SYSTEM_PROMPT = (
        "You are the deterministic UoW Recovery Grammar Parser (uow.recovery.v1).\n"
        "Analyze failure symptoms, error codes, and operational state to propose a recovery strategy.\n"
        "Emit ONLY valid JSON with keys: 'failed_uow', 'strategy' ('RETRY'|'COMPENSATE'|'FALLBACK'|'ESCALATE'), "
        "and optional 'retry_policy' (with 'max_attempts', 'backoff'), 'compensation_uow', 'fallback_uow', or 'unknowns'."
    )

    def build_chat_messages(self, prompt_text: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": prompt_text.strip()}
        ]


class RecoveryOutputParser:
    @classmethod
    def extract_json_text(cls, raw: str) -> str:
        cleaned = raw.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()
        return cleaned

    def parse(self, raw_text: str) -> Optional[RecoveryPlan]:
        try:
            text = self.extract_json_text(raw_text)
            data = json.loads(text)
            if not isinstance(data, dict):
                return None
            failed = data.get("failed_uow")
            strat = data.get("strategy")
            if not failed or not strat:
                return None
            policy = data.get("retry_policy", {})
            return RecoveryPlan(
                failed_uow=str(failed),
                strategy=str(strat).upper(),
                max_attempts=policy.get("max_attempts") if isinstance(policy, dict) else None,
                backoff=policy.get("backoff") if isinstance(policy, dict) else None,
                compensation_uow=data.get("compensation_uow"),
                fallback_uow=data.get("fallback_uow"),
                unknowns=tuple(data.get("unknowns", []))
            )
        except Exception:
            return None


def generate_synthetic_corpus(seed: int = 101) -> Tuple[List[dict], List[dict]]:
    """Generate family-disjoint train and holdout datasets for recovery grammar."""
    rng = random.Random(seed)

    tasks = [
        "dispatch_cells", "convey_sensors", "debit_account", "transfer_payload",
        "lock_valve", "purge_pipeline", "flash_firmware", "allocate_bandwidth",
        "calibrate_gyro", "vent_tank", "synchronize_clocks", "isolate_circuit",
        "index_catalog", "refresh_session", "mount_storage", "rotate_keys"
    ]
    holdout_tasks = [
        "write_telemetry_block", "authorize_reactor_flow", "synchronize_database",
        "eject_capsule", "power_down_sensor_array", "drain_coolant_reservoir"
    ]
    train_tasks = [t for t in tasks if t not in holdout_tasks]

    train_data = []
    holdout_data = []

    # 1. RETRY patterns (transient timeout, network jitter, busy lock)
    errors_retry = ["ETIMEDOUT", "LOCK_BUSY", "NETWORK_JITTER", "CONNECTION_RESET", "SERVICE_UNAVAILABLE"]
    for t in train_tasks:
        for err in errors_retry[:2]:  # balanced subset so retry does not dominate
            target = RecoveryPlan(failed_uow=t, strategy="RETRY", max_attempts=3, backoff="EXPONENTIAL")
            train_data.append({"signal": f"Task {t} failed with error {err}. Transient condition detected.", "target": target.to_dict(), "family": "retry_transient"})
            train_data.append({"signal": f"Transient failure during {t}: {err}. Immediate re-execution allowed.", "target": target.to_dict(), "family": "retry_transient"})
            train_data.append({"signal": f"Execution of {t} dropped packet with {err}. Remote port momentarily unresponsive.", "target": target.to_dict(), "family": "retry_transient"})

    # 2. COMPENSATE patterns (semantic failure, balance deficit, partial write rollback)
    compensations = {
        "dispatch_cells": "recall_cells",
        "convey_sensors": "retrieve_sensors",
        "debit_account": "credit_account",
        "transfer_payload": "rollback_payload",
        "lock_valve": "unlock_valve",
        "purge_pipeline": "restore_pipeline_state",
        "flash_firmware": "restore_firmware_backup",
        "allocate_bandwidth": "release_bandwidth",
        "calibrate_gyro": "reset_gyro_offsets",
        "vent_tank": "reseal_tank_valves",
        "synchronize_clocks": "revert_clock_drift",
        "isolate_circuit": "reconnect_circuit_breakers",
        "index_catalog": "purge_index_diff",
        "refresh_session": "invalidate_session_tokens",
        "mount_storage": "unmount_storage_volume",
        "rotate_keys": "restore_previous_keyring"
    }
    for t in train_tasks:
        comp = compensations[t]
        target = RecoveryPlan(failed_uow=t, strategy="COMPENSATE", compensation_uow=comp)
        train_data.append({"signal": f"Task {t} encountered unrecoverable semantic validation error. Reversal required.", "target": target.to_dict(), "family": "compensate_semantic"})
        train_data.append({"signal": f"Transaction abort in {t}. Invoke compensation routine {comp}.", "target": target.to_dict(), "family": "compensate_semantic"})
        train_data.append({"signal": f"State invariant violated in {t}. Rollback to previous checkpoint needed immediately.", "target": target.to_dict(), "family": "compensate_semantic"})
        train_data.append({"signal": f"Semantic integrity check failed during {t}. Execute compensating transaction {comp}.", "target": target.to_dict(), "family": "compensate_semantic"})

    # 3. FALLBACK patterns (secondary route / alternative channel)
    fallbacks = {
        "dispatch_cells": "dispatch_cells_secondary_hub",
        "convey_sensors": "convey_sensors_ground_courier",
        "debit_account": "charge_reserve_escrow",
        "transfer_payload": "route_payload_via_satellite",
        "lock_valve": "engage_mechanical_lock",
        "purge_pipeline": "divert_pipeline_to_tank_b",
        "flash_firmware": "boot_read_only_image",
        "allocate_bandwidth": "switch_to_narrowband_mesh",
        "calibrate_gyro": "load_factory_gyro_profile",
        "vent_tank": "divert_vent_to_scrubber",
        "synchronize_clocks": "poll_ntp_peer_pool",
        "isolate_circuit": "trip_upstream_substation",
        "index_catalog": "query_replica_catalog",
        "refresh_session": "prompt_user_reauthentication",
        "mount_storage": "mount_ephemeral_ramdisk",
        "rotate_keys": "request_hsm_key_derivation"
    }
    for t in train_tasks:
        fb = fallbacks[t]
        target = RecoveryPlan(failed_uow=t, strategy="FALLBACK", fallback_uow=fb)
        train_data.append({"signal": f"Task {t} failed due to hardware channel breakdown. Alternative route available.", "target": target.to_dict(), "family": "fallback_routing"})
        train_data.append({"signal": f"Primary interface down during {t}. Switch to auxiliary backup apparatus.", "target": target.to_dict(), "family": "fallback_routing"})
        train_data.append({"signal": f"Hardware channel lost in {t}. Divert execution to fallback routine {fb}.", "target": target.to_dict(), "family": "fallback_routing"})
        train_data.append({"signal": f"Secondary dispatch route available for {t} after primary link failure: {fb}.", "target": target.to_dict(), "family": "fallback_routing"})

    # 4. ESCALATE / AMBIGUOUS patterns (unknown critical fault)
    for t in train_tasks:
        target = RecoveryPlan(failed_uow=t, strategy="ESCALATE", unknowns=("recovery_path",))
        train_data.append({"signal": f"Task {t} halted with unknown fatal corruption 0xDEADBEEF.", "target": target.to_dict(), "family": "escalate_ambiguous"})
        train_data.append({"signal": f"Unrecognized hardware anomaly detected during {t}. No automated resolution policy.", "target": target.to_dict(), "family": "escalate_ambiguous"})
        train_data.append({"signal": f"Critical unclassified failure in {t}. Escalate to system supervisor.", "target": target.to_dict(), "family": "escalate_ambiguous"})
        train_data.append({"signal": f"Fatal execution exception in {t} without recovery handler.", "target": target.to_dict(), "family": "escalate_ambiguous"})

    # Holdout cases (24 strictly disjoint holdouts across 6 holdout tasks)
    holdout_compensations = {
        "write_telemetry_block": "invalidate_telemetry_index",
        "authorize_reactor_flow": "clamp_emergency_scram_valves",
        "synchronize_database": "revert_wal_checkpoint",
        "eject_capsule": "retract_ejection_latches",
        "power_down_sensor_array": "restore_sensor_power_grid",
        "drain_coolant_reservoir": "refill_coolant_lines"
    }
    holdout_fallbacks = {
        "write_telemetry_block": "spool_telemetry_to_local_nvme",
        "authorize_reactor_flow": "route_coolant_auxiliary_bypass",
        "synchronize_database": "queue_offline_delta_log",
        "eject_capsule": "seal_capsule_in_containment_bay",
        "power_down_sensor_array": "isolate_sensor_bus_optically",
        "drain_coolant_reservoir": "pump_coolant_to_reserve_sump"
    }

    for t in holdout_tasks:
        # Retry
        holdout_data.append({
            "example_id": f"HO_rec_retry_{t}",
            "signal": f"Execution of {t} dropped packet with ETIMEDOUT. Remote port momentarily unresponsive.",
            "target": RecoveryPlan(failed_uow=t, strategy="RETRY", max_attempts=5, backoff="EXPONENTIAL").to_dict(),
            "family": "retry_transient"
        })
        # Compensate
        comp = holdout_compensations[t]
        holdout_data.append({
            "example_id": f"HO_rec_comp_{t}",
            "signal": f"State invariant violated in {t}. Rollback to previous checkpoint needed immediately.",
            "target": RecoveryPlan(failed_uow=t, strategy="COMPENSATE", compensation_uow=comp).to_dict(),
            "family": "compensate_semantic"
        })
        # Fallback
        fb = holdout_fallbacks[t]
        holdout_data.append({
            "example_id": f"HO_rec_fb_{t}",
            "signal": f"Primary interface down during {t}. Switch to auxiliary backup apparatus.",
            "target": RecoveryPlan(failed_uow=t, strategy="FALLBACK", fallback_uow=fb).to_dict(),
            "family": "fallback_routing"
        })
        # Escalate
        holdout_data.append({
            "example_id": f"HO_rec_esc_{t}",
            "signal": f"Unrecognized hardware anomaly detected during {t}. No automated resolution policy.",
            "target": RecoveryPlan(failed_uow=t, strategy="ESCALATE", unknowns=("recovery_path",)).to_dict(),
            "family": "escalate_ambiguous"
        })

    rng.shuffle(train_data)
    return train_data, holdout_data


def generate_unseen_test_corpus(seed: int = 888) -> List[dict]:
    """Generate a separate, brand new 24-case unseen test suite with disjoint tasks."""
    rng = random.Random(seed)
    unseen_tasks = [
        "ignite_thruster_array", "recalibrate_star_tracker",
        "pressurize_fuel_cell", "recharge_ion_battery",
        "purge_nitrogen_tank", "deploy_solar_mast"
    ]
    unseen_compensations = {
        "ignite_thruster_array": "cutoff_fuel_valves",
        "recalibrate_star_tracker": "load_inertial_gyro_frame",
        "pressurize_fuel_cell": "vent_overpressure_manifold",
        "recharge_ion_battery": "disconnect_solar_array",
        "purge_nitrogen_tank": "reseal_nitrogen_valves",
        "deploy_solar_mast": "retract_mast_gimbal"
    }
    unseen_fallbacks = {
        "ignite_thruster_array": "fire_cold_gas_thrusters",
        "recalibrate_star_tracker": "align_optical_horizon_sensor",
        "pressurize_fuel_cell": "draw_from_auxiliary_battery",
        "recharge_ion_battery": "switch_to_fuel_cell_bus",
        "purge_nitrogen_tank": "divert_to_auxiliary_scrubber",
        "deploy_solar_mast": "lock_mast_at_partial_angle"
    }
    unseen_data = []

    for t in unseen_tasks:
        # 1. Retry
        unseen_data.append({
            "example_id": f"TEST_rec_retry_{t}",
            "signal": f"Execution of {t} dropped packet with ETIMEDOUT. Remote port momentarily unresponsive.",
            "target": RecoveryPlan(failed_uow=t, strategy="RETRY", max_attempts=3, backoff="EXPONENTIAL").to_dict(),
            "family": "retry_transient"
        })
        # 2. Compensate (explicit compensation in signal)
        comp = unseen_compensations[t]
        unseen_data.append({
            "example_id": f"TEST_rec_comp_{t}",
            "signal": f"Transaction abort in {t}. Invoke compensation routine {comp}.",
            "target": RecoveryPlan(failed_uow=t, strategy="COMPENSATE", compensation_uow=comp).to_dict(),
            "family": "compensate_semantic"
        })
        # 3. Fallback (explicit fallback in signal)
        fb = unseen_fallbacks[t]
        unseen_data.append({
            "example_id": f"TEST_rec_fb_{t}",
            "signal": f"Hardware channel lost in {t}. Divert execution to fallback routine {fb}.",
            "target": RecoveryPlan(failed_uow=t, strategy="FALLBACK", fallback_uow=fb).to_dict(),
            "family": "fallback_routing"
        })
        # 4. Escalate
        unseen_data.append({
            "example_id": f"TEST_rec_esc_{t}",
            "signal": f"Critical unclassified failure in {t}. Escalate to system supervisor.",
            "target": RecoveryPlan(failed_uow=t, strategy="ESCALATE", unknowns=("recovery_path",)).to_dict(),
            "family": "escalate_ambiguous"
        })

    return unseen_data


if __name__ == "__main__":
    train, hold = generate_synthetic_corpus()
    unseen = generate_unseen_test_corpus()
    print(f"Generated {len(train)} training, {len(hold)} holdout, and {len(unseen)} unseen test examples.")
