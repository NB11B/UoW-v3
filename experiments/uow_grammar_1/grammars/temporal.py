"""UoW Temporal Grammar (uow.temporal.v1) Schema, Codec, and Dataset Generator."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
import json
import random
import re
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = "uow.temporal.v1"

@dataclass(frozen=True)
class TemporalConstraint:
    target_action: str
    relation: str  # "IMMEDIATE", "AFTER", "BEFORE", "BETWEEN", "CONCURRENT"
    reference_event: Optional[str] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    deadline: Optional[str] = None
    duration_seconds: Optional[int] = None
    unknowns: Tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "target_action": self.target_action,
            "relation": self.relation,
        }
        if self.reference_event is not None:
            d["reference_event"] = self.reference_event
        if self.window_start is not None or self.window_end is not None:
            d["window"] = {"start": self.window_start, "end": self.window_end}
        if self.deadline is not None:
            d["deadline"] = self.deadline
        if self.duration_seconds is not None:
            d["duration_seconds"] = self.duration_seconds
        if self.unknowns:
            d["unknowns"] = list(self.unknowns)
        return d


class TemporalPromptBuilder:
    SYSTEM_PROMPT = (
        "You are the deterministic UoW Temporal Grammar Parser (uow.temporal.v1).\n"
        "Extract temporal constraints, execution order, time windows, and deadlines.\n"
        "Emit ONLY valid JSON with keys: 'target_action', 'relation' ('IMMEDIATE'|'AFTER'|'BEFORE'|'BETWEEN'|'CONCURRENT'), "
        "and optional 'reference_event', 'window', 'deadline', 'duration_seconds', or 'unknowns'."
    )

    def build_chat_messages(self, prompt_text: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": prompt_text.strip()}
        ]


class TemporalOutputParser:
    @classmethod
    def extract_json_text(cls, raw: str) -> str:
        cleaned = raw.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()
        return cleaned

    def parse(self, raw_text: str) -> Optional[TemporalConstraint]:
        try:
            text = self.extract_json_text(raw_text)
            data = json.loads(text)
            if not isinstance(data, dict):
                return None
            target = data.get("target_action")
            relation = data.get("relation")
            if not target or not relation:
                return None
            window = data.get("window", {})
            return TemporalConstraint(
                target_action=str(target),
                relation=str(relation).upper(),
                reference_event=data.get("reference_event"),
                window_start=window.get("start") if isinstance(window, dict) else None,
                window_end=window.get("end") if isinstance(window, dict) else None,
                deadline=data.get("deadline"),
                duration_seconds=int(data["duration_seconds"]) if "duration_seconds" in data and data["duration_seconds"] is not None else None,
                unknowns=tuple(data.get("unknowns", []))
            )
        except Exception:
            return None


def generate_synthetic_corpus(seed: int = 42) -> Tuple[List[dict], List[dict]]:
    """Generate family-disjoint train and holdout datasets for temporal grammar."""
    rng = random.Random(seed)
    
    actions = [
        "convey_sensors", "purge_buffer_cache", "dispatch_cells", "open_valve",
        "calibrate_manifold", "synchronize_clocks", "isolate_bay_4", "verify_telemetry",
        "archive_telemetry_logs", "transfer_power_bus", "reboot_auxiliary_core", "inspect_couplers"
    ]
    events = [
        "pump_shutdown", "depot_handshake", "reactor_cooling", "telemetry_ack",
        "pressure_stabilization", "network_rescan", "backup_completion", "door_lock"
    ]
    hours = ["08:00", "09:30", "11:00", "13:15", "14:00", "15:45", "16:00", "17:30", "18:00", "20:00"]
    durations = [15, 30, 45, 60, 90, 120, 300]

    train_data = []
    holdout_data = []

    # Holdout uses disjoint actions and templates
    holdout_actions = ["quarantine_node_7", "vent_chamber_3", "degauss_actuator", "flush_coolant_loop"]
    train_actions = [a for a in actions if a not in holdout_actions]

    # 1. AFTER templates (diverse relational phrasings)
    for a in train_actions:
        for e in events[:4]:
            target = TemporalConstraint(target_action=a, relation="AFTER", reference_event=e)
            train_data.append({"signal": f"After {e} completes, execute {a}.", "target": target.to_dict(), "family": "after_relational"})
            train_data.append({"signal": f"Following the completion of {e}, proceed with {a}.", "target": target.to_dict(), "family": "after_relational"})
            train_data.append({"signal": f"Once {e} has finished, initiate {a}.", "target": target.to_dict(), "family": "after_relational"})

    # 2. BEFORE templates (diverse relational phrasings)
    for a in train_actions:
        for e in events[4:]:
            target = TemporalConstraint(target_action=a, relation="BEFORE", reference_event=e)
            train_data.append({"signal": f"Ensure {a} is performed before {e}.", "target": target.to_dict(), "family": "before_relational"})
            train_data.append({"signal": f"Prior to {e}, finish {a}.", "target": target.to_dict(), "family": "before_relational"})
            train_data.append({"signal": f"Complete {a} ahead of {e}.", "target": target.to_dict(), "family": "before_relational"})

    # 3. WINDOW templates (diverse window phrasings)
    for i in range(len(hours) - 1):
        h1, h2 = hours[i], hours[i+1]
        for a in train_actions[:4]:
            target = TemporalConstraint(target_action=a, relation="BETWEEN", window_start=h1, window_end=h2)
            train_data.append({"signal": f"Between {h1} and {h2}, initiate {a}.", "target": target.to_dict(), "family": "window_constrained"})
            train_data.append({"signal": f"Within the time frame {h1} to {h2}, carry out {a}.", "target": target.to_dict(), "family": "window_constrained"})

    # 4. DEADLINE templates (diverse deadline phrasings)
    for h in hours:
        for a in train_actions[4:8]:
            target = TemporalConstraint(target_action=a, relation="BEFORE", deadline=h)
            train_data.append({"signal": f"Deliver {a} by {h} sharp.", "target": target.to_dict(), "family": "deadline_constrained"})
            train_data.append({"signal": f"Mandatory deadline: complete {a} no later than {h}.", "target": target.to_dict(), "family": "deadline_constrained"})

    # 5. IMMEDIATE templates (diverse immediate dispatch phrasings)
    for a in train_actions:
        target = TemporalConstraint(target_action=a, relation="IMMEDIATE")
        train_data.append({"signal": f"Execute {a} immediately without delay.", "target": target.to_dict(), "family": "immediate_dispatch"})
        train_data.append({"signal": f"Initiate {a} right now.", "target": target.to_dict(), "family": "immediate_dispatch"})
        train_data.append({"signal": f"Trigger {a} right away without waiting.", "target": target.to_dict(), "family": "immediate_dispatch"})

    # 6. UNKNOWN / AMBIGUOUS templates (diverse ambiguous timing phrasings)
    for a in train_actions:
        target = TemporalConstraint(target_action=a, relation="BETWEEN", unknowns=("window",))
        train_data.append({"signal": f"Schedule {a} for later sometime today.", "target": target.to_dict(), "family": "ambiguous_timing"})
        train_data.append({"signal": f"Perform {a} when convenient.", "target": target.to_dict(), "family": "ambiguous_timing"})
        train_data.append({"signal": f"Queue {a} with unspecified timing.", "target": target.to_dict(), "family": "ambiguous_timing"})

    # Build strictly disjoint holdout (24 cases across 6 families with holdout actions)
    for a in holdout_actions:
        # After
        e = events[rng.randint(0, len(events)-1)]
        holdout_data.append({
            "example_id": f"HO_temp_after_{a}",
            "signal": f"Following the completion of {e}, proceed with {a}.",
            "target": TemporalConstraint(target_action=a, relation="AFTER", reference_event=e).to_dict(),
            "family": "after_relational"
        })
        # Before
        e2 = events[rng.randint(0, len(events)-1)]
        holdout_data.append({
            "example_id": f"HO_temp_before_{a}",
            "signal": f"Prior to {e2}, finish {a}.",
            "target": TemporalConstraint(target_action=a, relation="BEFORE", reference_event=e2).to_dict(),
            "family": "before_relational"
        })
        # Window
        holdout_data.append({
            "example_id": f"HO_temp_window_{a}",
            "signal": f"Within the time frame 10:00 to 12:30, carry out {a}.",
            "target": TemporalConstraint(target_action=a, relation="BETWEEN", window_start="10:00", window_end="12:30").to_dict(),
            "family": "window_constrained"
        })
        # Deadline
        holdout_data.append({
            "example_id": f"HO_temp_deadline_{a}",
            "signal": f"Mandatory deadline: complete {a} no later than 19:00.",
            "target": TemporalConstraint(target_action=a, relation="BEFORE", deadline="19:00").to_dict(),
            "family": "deadline_constrained"
        })
        # Immediate
        holdout_data.append({
            "example_id": f"HO_temp_immediate_{a}",
            "signal": f"Initiate {a} right now.",
            "target": TemporalConstraint(target_action=a, relation="IMMEDIATE").to_dict(),
            "family": "immediate_dispatch"
        })
        # Ambiguous
        holdout_data.append({
            "example_id": f"HO_temp_ambig_{a}",
            "signal": f"Perform {a} when convenient.",
            "target": TemporalConstraint(target_action=a, relation="BETWEEN", unknowns=("window",)).to_dict(),
            "family": "ambiguous_timing"
        })

    rng.shuffle(train_data)
    return train_data, holdout_data


def generate_unseen_test_corpus(seed: int = 777) -> List[dict]:
    """Generate a separate, brand new 24-case unseen test suite with disjoint actions/events."""
    rng = random.Random(seed)
    unseen_actions = ["vent_silo_9", "purge_reaction_chamber", "isolate_subgrid_alpha", "sync_telemetry_beacon"]
    unseen_events = ["core_drain", "docking_seal", "sensor_sweep", "thermal_lock"]
    unseen_data = []

    for a in unseen_actions:
        e1 = unseen_events[rng.randint(0, len(unseen_events)-1)]
        unseen_data.append({
            "example_id": f"TEST_temp_after_{a}",
            "signal": f"Subsequent to {e1}, initiate {a}.",
            "target": TemporalConstraint(target_action=a, relation="AFTER", reference_event=e1).to_dict(),
            "family": "after_relational"
        })
        e2 = unseen_events[rng.randint(0, len(unseen_events)-1)]
        unseen_data.append({
            "example_id": f"TEST_temp_before_{a}",
            "signal": f"Finish {a} ahead of {e2}.",
            "target": TemporalConstraint(target_action=a, relation="BEFORE", reference_event=e2).to_dict(),
            "family": "before_relational"
        })
        unseen_data.append({
            "example_id": f"TEST_temp_window_{a}",
            "signal": f"Between 14:00 and 16:30, initiate {a}.",
            "target": TemporalConstraint(target_action=a, relation="BETWEEN", window_start="14:00", window_end="16:30").to_dict(),
            "family": "window_constrained"
        })
        unseen_data.append({
            "example_id": f"TEST_temp_deadline_{a}",
            "signal": f"Complete {a} no later than 21:00.",
            "target": TemporalConstraint(target_action=a, relation="BEFORE", deadline="21:00").to_dict(),
            "family": "deadline_constrained"
        })
        unseen_data.append({
            "example_id": f"TEST_temp_immediate_{a}",
            "signal": f"Trigger {a} immediately.",
            "target": TemporalConstraint(target_action=a, relation="IMMEDIATE").to_dict(),
            "family": "immediate_dispatch"
        })
        unseen_data.append({
            "example_id": f"TEST_temp_ambig_{a}",
            "signal": f"Queue {a} with unspecified timing.",
            "target": TemporalConstraint(target_action=a, relation="BETWEEN", unknowns=("window",)).to_dict(),
            "family": "ambiguous_timing"
        })

    return unseen_data


if __name__ == "__main__":
    train, hold = generate_synthetic_corpus()
    unseen = generate_unseen_test_corpus()
    print(f"Generated {len(train)} training, {len(hold)} holdout, and {len(unseen)} unseen test examples.")
