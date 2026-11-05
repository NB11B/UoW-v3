import json

import pytest

from integrations.omarchy_uow.mapeogeo_journal import JournalRow
from integrations.omarchy_uow.mapeogeo_mapping import map_decision, map_observation
from mapeogeo.psmsl.serialization import serialize_observation


def row(kind, payload, decision="COMMITTED", sequence=7, reason="CERTIFIED", state=None):
    return JournalRow(
        sequence,
        {"request_id": "request7", "principal": "sensor", "kind": kind, "payload": payload},
        {"decision": decision, "reason": reason, "receipt": {} if decision == "COMMITTED" else None, "state": state or {"attributes": {}}},
        "a" * 64,
    )


def test_environmental_observation_preserves_source_units_trust_and_unknown_time():
    payload = {"observation_id": "soil7", "sensor_id": "soil", "sensor_type": "ENVIRONMENTAL_PROBE", "causal_epoch": 4, "modality": "NUMERIC_GAUGE", "reading": {"value": 22.5, "unit": "C"}, "confidence": 0.8}
    item = row("observation.ingest", payload, state={"attributes": {"obs.soil7": {**payload, "trust": "UNVERIFIED_CLAIM"}}})
    observation = map_observation(item)
    assert observation.values == (22.5,)
    assert observation.observation_id == "uow-request7"
    assert observation.timestamp == 0.0
    assert observation.metadata["timestamp_status"] == "unknown"
    assert observation.metadata["units"] == ["C"]
    assert observation.metadata["trust"] == "UNVERIFIED_CLAIM"
    assert observation.metadata["causal_epoch"] == 4
    assert observation.metadata["journal_sequence"] == 7
    assert observation.metadata["journal_hash"] == "a" * 64
    serialized = json.loads(serialize_observation(observation))
    assert serialized["schema"] == "mapeogeo.psmsl.observation"
    assert serialized["values"] == [22.5]
    assert map_decision(item) is None


def test_audio_telemetry_maps_fixed_order_and_receiver_sequence():
    payload = {"session_id": "s1", "receiver_sequence": 8, "packet_rate": 187.5, "drops": 2, "underruns": 1, "crossover_low_hz": 100.0, "crossover_high_hz": 2500.0}
    item = row("audio.telemetry.ingest", payload, state={"attributes": {"audio.telemetry.s1": {**payload, "trust": "UNVERIFIED_CLAIM"}}})
    observation = map_observation(item)
    assert observation.values == (187.5, 2.0, 1.0, 100.0, 2500.0)
    assert observation.metadata["measurement_names"] == ["packet_rate", "drops", "underruns", "crossover_low_hz", "crossover_high_hz"]
    assert observation.metadata["units"] == ["packets/s", "count", "count", "Hz", "Hz"]
    assert observation.metadata["receiver_sequence"] == 8
    assert observation.metadata["session_id"] == "s1"


def test_denial_is_decision_not_observation():
    item = row("audio.telemetry.ingest", {}, decision="DENIED", reason="CAPABILITY_DENIED")
    assert map_observation(item) is None
    decision = map_decision(item)
    assert decision.decision == "DENIED"
    assert decision.reason == "CAPABILITY_DENIED"
    assert decision.outcome is None


def test_committed_unknown_numeric_schema_fails_closed():
    item = row("observation.ingest", {"observation_id": "bad", "reading": "x"})
    with pytest.raises(ValueError, match="OBSERVATION_MAPPING"):
        map_observation(item)


def test_stable_ids_and_uncertain_audio_intent():
    item = row("audio.stream.start", {"session_id": "s1"})
    first = map_decision(item)
    assert first == map_decision(item)
    assert first.outcome == "UNCERTAIN"
    assert first.request_id == "request7"
    assert map_observation(item) is None


def test_unexpected_trust_state_fails_closed():
    payload = {"observation_id": "o", "sensor_id": "s", "sensor_type": "ENVIRONMENTAL_PROBE", "causal_epoch": 1, "modality": "NUMERIC_GAUGE", "reading": {"value": 3, "unit": "C"}, "confidence": 0.5}
    item = row("observation.ingest", payload)
    with pytest.raises(ValueError, match="OBSERVATION_MAPPING"):
        map_observation(item)
