"""Narrow mapping from verified UoW records to PSMSL observations and views."""

from __future__ import annotations

from dataclasses import dataclass
import math

from mapeogeo.psmsl.latent import Observation

from .mapeogeo_journal import JournalRow
from .service import validate_observation


AUDIO_FIELDS = (
    "packet_rate", "drops", "underruns", "crossover_low_hz", "crossover_high_hz"
)
AUDIO_UNITS = ("packets/s", "count", "count", "Hz", "Hz")


@dataclass(frozen=True)
class DecisionView:
    sequence: int
    entry_hash: str
    request_id: str
    kind: str
    decision: str
    reason: str
    principal: str
    session_id: str | None
    outcome: str | None
    pre_state_hash: str | None
    post_state_hash: str | None


def _trusted_state(row: JournalRow, key: str) -> None:
    attributes = row.response.get("state", {}).get("attributes", {})
    value = attributes.get(key)
    if not isinstance(value, dict) or value.get("trust") != "UNVERIFIED_CLAIM":
        raise ValueError("OBSERVATION_MAPPING: missing unverified claim")


def map_observation(row: JournalRow) -> Observation | None:
    if row.response.get("decision") != "COMMITTED":
        return None
    kind = row.request.get("kind")
    if kind not in {"observation.ingest", "audio.telemetry.ingest"}:
        return None
    payload = row.request.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("OBSERVATION_MAPPING: payload")
    metadata = {
        "timestamp_status": "unknown",
        "trust": "UNVERIFIED_CLAIM",
        "source_kind": kind,
        "uow_request_id": row.request["request_id"],
        "journal_sequence": row.sequence,
        "journal_hash": row.entry_hash,
    }
    try:
        if kind == "observation.ingest":
            validate_observation(payload)
            _trusted_state(row, "obs." + payload["observation_id"])
            values = (float(payload["reading"]["value"]),)
            metadata.update({
                "source_observation_id": payload["observation_id"],
                "sensor_id": payload["sensor_id"],
                "causal_epoch": payload["causal_epoch"],
                "confidence": payload["confidence"],
                "measurement_names": ["value"],
                "units": [payload["reading"]["unit"]],
            })
        else:
            required = {"session_id", "receiver_sequence", *AUDIO_FIELDS}
            if set(payload) != required or not isinstance(payload["session_id"], str):
                raise ValueError("audio schema")
            if type(payload["receiver_sequence"]) is not int or payload["receiver_sequence"] < 0:
                raise ValueError("receiver sequence")
            if any(type(payload[name]) not in (int, float) or not math.isfinite(payload[name]) for name in AUDIO_FIELDS):
                raise ValueError("audio value")
            _trusted_state(row, "audio.telemetry." + payload["session_id"])
            values = tuple(float(payload[name]) for name in AUDIO_FIELDS)
            metadata.update({
                "session_id": payload["session_id"],
                "receiver_sequence": payload["receiver_sequence"],
                "measurement_names": list(AUDIO_FIELDS),
                "units": list(AUDIO_UNITS),
            })
        return Observation(
            observation_id="uow-" + row.request["request_id"],
            values=values,
            timestamp=0.0,
            metadata=metadata,
        )
    except (TypeError, KeyError, ValueError) as exc:
        raise ValueError("OBSERVATION_MAPPING: unsupported verified record") from exc


def map_decision(row: JournalRow) -> DecisionView | None:
    kind = row.request.get("kind")
    decision = row.response.get("decision")
    if decision == "COMMITTED" and kind in {"observation.ingest", "audio.telemetry.ingest"}:
        return None
    if decision not in {"COMMITTED", "DENIED"}:
        raise ValueError("DECISION_MAPPING")
    payload = row.request.get("payload")
    session_id = payload.get("session_id") if isinstance(payload, dict) else None
    outcome = None
    if decision == "COMMITTED":
        if kind in {"audio.stream.start", "audio.stream.stop"}:
            outcome = "UNCERTAIN"
        elif kind == "audio.effect.record" and isinstance(payload, dict):
            outcome = payload.get("outcome")
    receipt = row.response.get("receipt")
    receipt = receipt if isinstance(receipt, dict) else {}
    return DecisionView(
        sequence=row.sequence,
        entry_hash=row.entry_hash,
        request_id=str(row.request.get("request_id", "")),
        kind=str(kind),
        decision=decision,
        reason=str(row.response.get("reason", "")),
        principal=str(row.request.get("principal", "")),
        session_id=session_id if isinstance(session_id, str) else None,
        outcome=outcome if isinstance(outcome, str) else None,
        pre_state_hash=receipt.get("pre_state_hash"),
        post_state_hash=receipt.get("post_state_hash"),
    )
