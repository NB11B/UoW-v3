import json
from pathlib import Path
import tempfile

import pytest

from integrations.omarchy_uow.coretemp import sample_coretemp, ingest_coretemp
from integrations.omarchy_uow.service import Service


def fixture(tmp_path, value="51250"):
    hw = tmp_path / "hwmon0"
    hw.mkdir()
    (hw / "name").write_text("coretemp\n")
    (hw / "temp1_label").write_text("Package id 0\n")
    (hw / "temp1_input").write_text(value + "\n")
    return hw


def test_sample_has_source_and_causal_epoch(tmp_path):
    fixture(tmp_path)
    obs = sample_coretemp(tmp_path, 7)
    assert obs["sensor_id"] == "host-coretemp-package"
    assert obs["causal_epoch"] == 7
    assert obs["reading"] == {"value": 51.25, "unit": "C"}
    assert obs["confidence"] == 0.5


def test_missing_or_invalid_sensor_fails_closed(tmp_path):
    with pytest.raises(ValueError):
        sample_coretemp(tmp_path, 1)
    hw = fixture(tmp_path, "not-a-number")
    with pytest.raises(ValueError):
        sample_coretemp(tmp_path, 1)
    (hw / "temp1_input").write_text("200000\n")
    with pytest.raises(ValueError):
        sample_coretemp(tmp_path, 1)


def test_real_source_through_authority_receipt_and_restart(tmp_path):
    fixture(tmp_path)
    db = tmp_path / "state.db"
    policy = {"sensor": ["observation.ingest"], "operator": ["observation.summarize"]}
    tokens = {"sensor-secret": "sensor", "operator-secret": "operator"}
    service = Service(db, policy, tokens)
    first = ingest_coretemp(service, tmp_path, "sensor-secret")
    assert first["decision"] == "COMMITTED"
    assert service.state.get("obs.host-coretemp-package-1")["reading"]["value"] == 51.25
    summary = service.handle({"request_id": "summary-1", "token": "operator-secret", "kind": "observation.summarize", "payload": {"observation_id": "host-coretemp-package-1"}})
    assert summary["decision"] == "COMMITTED"
    assert summary["receipt"]["pre_state_hash"] == first["receipt"]["post_state_hash"]
    service.close()
    recovered = Service(db, policy, tokens)
    assert recovered.state.get("summary")["unit"] == "C"
    recovered.close()


def test_source_does_not_grant_authority(tmp_path):
    fixture(tmp_path)
    service = Service(tmp_path / "state.db", {}, {"sensor-secret": "sensor"})
    try:
        assert ingest_coretemp(service, tmp_path, "sensor-secret")["decision"] == "DENIED"
        assert service.state.sequence == 0
    finally:
        service.close()
