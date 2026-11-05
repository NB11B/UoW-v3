"""Consistent, verified read of the local UoW journal."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import tempfile
from typing import Any

from .service import Service


@dataclass(frozen=True)
class JournalRow:
    sequence: int
    request: dict[str, Any]
    response: dict[str, Any]
    entry_hash: str


def snapshot_and_verify(db: Path) -> tuple[list[JournalRow], str]:
    """Return rows only after a consistent copy passes full service replay."""
    try:
        db = Path(db).resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError("JOURNAL_SCHEMA: missing database") from exc
    with tempfile.TemporaryDirectory(prefix="uow-mapeogeo-") as directory:
        copied = Path(directory) / "journal.db"
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as source:
            with sqlite3.connect(copied) as destination:
                source.backup(destination)
        with sqlite3.connect(copied) as snapshot:
            table = snapshot.execute("SELECT type FROM sqlite_master WHERE name='journal'").fetchone()
            columns = {row[1] for row in snapshot.execute("PRAGMA table_info(journal)")}
            if table != ("table",) or columns != {"n", "request_id", "request", "response", "prev_hash", "entry_hash"}:
                raise ValueError("JOURNAL_SCHEMA: expected UoW journal")
        service = Service(copied, {}, {})
        try:
            root = service.root
            with sqlite3.connect(copied) as snapshot:
                rows = [
                    JournalRow(n, json.loads(raw_request), json.loads(raw_response), entry_hash)
                    for n, raw_request, raw_response, entry_hash in snapshot.execute(
                        "SELECT n,request,response,entry_hash FROM journal ORDER BY n"
                    )
                ]
            if rows and rows[-1].entry_hash != root:
                raise ValueError("JOURNAL_INTEGRITY")
            return rows, root
        finally:
            service.close()
