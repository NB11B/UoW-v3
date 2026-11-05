import json
import os
import sqlite3

import pytest

from integrations.omarchy_uow.obsidian_export import refresh
from integrations.omarchy_uow.service import Service


def make_journal(db, observations=1, denials=1):
    service = Service(db, {"sensor": ["observation.ingest"]}, {"secret": "sensor"})
    for number in range(observations):
        payload = {"observation_id": f"o{number}", "sensor_id": "probe", "sensor_type": "ENVIRONMENTAL_PROBE", "causal_epoch": number + 1, "modality": "NUMERIC_GAUGE", "reading": {"value": number % 100, "unit": "percent"}, "confidence": 0.8}
        assert service.handle({"request_id": f"obs{number}", "token": "secret", "kind": "observation.ingest", "payload": payload})["decision"] == "COMMITTED"
    for number in range(denials):
        assert service.handle({"request_id": f"deny{number}", "token": "secret", "kind": "observation.summarize", "payload": {"observation_id": "o0"}})["decision"] == "DENIED"
    service.close()


def test_export_creates_linked_private_vault_with_no_reverse_input(tmp_path):
    db, vault = tmp_path / "uow.db", tmp_path / "vault"
    make_journal(db)
    result = refresh(db, vault, "1346330")
    assert result.observations == 1
    assert result.decisions == 1
    index = (vault / "Generated" / "Index.md").read_text()
    assert "[[Generated/Observations/uow-obs0|" in index
    assert "[[Generated/Decisions/" in index
    note = (vault / "Generated" / "Observations" / "uow-obs0.md").read_text()
    assert "UNVERIFIED_CLAIM" in note
    assert "unknown" in note
    assert "journal sequence" in note.lower()
    sidecar = json.loads((vault / "Generated" / "Observations" / "uow-obs0.json").read_text())
    assert sidecar["schema"] == "mapeogeo.psmsl.observation"
    assert "token" not in index.lower() + note.lower()
    assert os.stat(vault).st_mode & 0o777 == 0o700
    assert os.stat(vault / "Generated" / "Index.md").st_mode & 0o777 == 0o600


def test_export_bounds_recent_notes_and_preserves_manual_notes(tmp_path):
    db, vault = tmp_path / "uow.db", tmp_path / "vault"
    make_journal(db, observations=101, denials=101)
    vault.mkdir()
    manual = vault / "My notes.md"
    manual.write_text("leave me alone")
    result = refresh(db, vault, "1346330")
    assert result.observations == 101
    assert result.decisions == 101
    assert len(list((vault / "Generated" / "Observations").glob("*.md"))) == 100
    assert len(list((vault / "Generated" / "Decisions").glob("*.md"))) == 100
    assert manual.read_text() == "leave me alone"


def test_retry_is_stable_except_index_export_time(tmp_path):
    db, vault = tmp_path / "uow.db", tmp_path / "vault"
    make_journal(db)
    first = refresh(db, vault, "1346330")
    note = (vault / "Generated" / "Observations" / "uow-obs0.md").read_bytes()
    second = refresh(db, vault, "1346330")
    assert first.root == second.root
    assert (vault / "Generated" / "Observations" / "uow-obs0.md").read_bytes() == note


def test_manual_edit_to_generated_note_refuses_overwrite(tmp_path):
    db, vault = tmp_path / "uow.db", tmp_path / "vault"
    make_journal(db)
    refresh(db, vault, "1346330")
    note = vault / "Generated" / "Observations" / "uow-obs0.md"
    note.write_text(note.read_text() + "\nmy edit\n")
    with pytest.raises(ValueError, match="GENERATED_CONFLICT"):
        refresh(db, vault, "1346330")
    assert "my edit" in note.read_text()


def test_corrupt_journal_leaves_previous_export_untouched(tmp_path):
    db, vault = tmp_path / "uow.db", tmp_path / "vault"
    make_journal(db)
    refresh(db, vault, "1346330")
    before = (vault / "Generated" / "Index.md").read_bytes()
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE journal SET entry_hash=? WHERE n=1", ("0" * 64,))
    with pytest.raises(ValueError, match="JOURNAL_INTEGRITY"):
        refresh(db, vault, "1346330")
    assert (vault / "Generated" / "Index.md").read_bytes() == before
