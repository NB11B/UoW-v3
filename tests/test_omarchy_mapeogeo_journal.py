import json
import sqlite3
import threading

import pytest

from integrations.omarchy_uow.mapeogeo_journal import snapshot_and_verify
from integrations.omarchy_uow.service import Service, digest


OBS = {"observation_id": "obs1", "sensor_id": "soil", "sensor_type": "ENVIRONMENTAL_PROBE", "causal_epoch": 1, "modality": "NUMERIC_GAUGE", "reading": {"value": 21, "unit": "C"}, "confidence": 0.8}


def make_service(db):
    return Service(db, {"sensor": ["observation.ingest"]}, {"secret": "sensor"})


def request(number, payload=OBS, token="secret"):
    return {"request_id": f"r{number}", "token": token, "kind": "observation.ingest", "payload": payload}


def denied_request(number):
    return {"request_id": f"r{number}", "token": "secret", "kind": "observation.summarize", "payload": {"observation_id": "obs1"}}


def test_snapshot_valid_committed_and_denied_leaves_live_database_unchanged(tmp_path):
    db = tmp_path / "uow.db"
    service = make_service(db)
    assert service.handle(request(1))["decision"] == "COMMITTED"
    assert service.handle(denied_request(2))["decision"] == "DENIED"
    service.close()
    before = db.read_bytes()
    rows, root = snapshot_and_verify(db)
    assert [row.sequence for row in rows] == [1, 2]
    assert [row.response["decision"] for row in rows] == ["COMMITTED", "DENIED"]
    assert root == rows[-1].entry_hash
    assert db.read_bytes() == before


def test_snapshot_fails_on_broken_hash(tmp_path):
    db = tmp_path / "uow.db"
    service = make_service(db)
    service.handle(request(1))
    service.close()
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE journal SET entry_hash=?", ("0" * 64,))
    with pytest.raises(ValueError, match="JOURNAL_INTEGRITY"):
        snapshot_and_verify(db)


def test_snapshot_fails_on_divergent_receipt_even_with_rehashed_row(tmp_path):
    db = tmp_path / "uow.db"
    service = make_service(db)
    service.handle(request(1))
    service.close()
    with sqlite3.connect(db) as connection:
        n, raw_request, raw_response, prev = connection.execute("SELECT n,request,response,prev_hash FROM journal").fetchone()
        response = json.loads(raw_response)
        response["receipt"]["post_state_hash"] = "0" * 64
        entry_hash = digest({"n": n, "request": json.loads(raw_request), "response": response, "prev_hash": prev})
        connection.execute("UPDATE journal SET response=?,entry_hash=?", (json.dumps(response), entry_hash))
    with pytest.raises(ValueError, match="REPLAY_DIVERGENCE"):
        snapshot_and_verify(db)


def test_snapshot_fails_on_missing_sequence(tmp_path):
    db = tmp_path / "uow.db"
    service = make_service(db)
    service.handle(request(1))
    service.handle(denied_request(2))
    service.close()
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE journal SET n=3 WHERE n=2")
    with pytest.raises(ValueError, match="JOURNAL_INTEGRITY"):
        snapshot_and_verify(db)


def test_snapshot_is_consistent_during_append(tmp_path):
    db = tmp_path / "uow.db"
    service = make_service(db)
    service.handle(request(1))
    service.close()
    go = threading.Event()

    def writer():
        go.wait()
        writer_service = make_service(db)
        try:
            for number in range(2, 30):
                writer_service.handle(denied_request(number))
        finally:
            writer_service.close()

    thread = threading.Thread(target=writer)
    thread.start()
    go.set()
    rows, root = snapshot_and_verify(db)
    thread.join()
    assert len(rows) >= 1
    assert root == rows[-1].entry_hash
    assert [row.sequence for row in rows] == list(range(1, len(rows) + 1))
