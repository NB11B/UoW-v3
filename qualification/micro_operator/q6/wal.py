"""Q6 Persistent Write-Ahead Log (WAL) with strict fsync and crash recovery."""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from uow.state import canonical_json

@dataclass(frozen=True)
class WALRecord:
    index: int
    timestamp_ns: int
    record_type: str  # INIT, PREPARE, COMMIT, ABORT, CHECKPOINT
    payload: Dict[str, Any]
    prev_hash: str
    record_hash: str = ""

    def calculate_hash(self) -> str:
        data = {
            "index": self.index,
            "timestamp_ns": self.timestamp_ns,
            "record_type": self.record_type,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
        }
        return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()

    def to_line(self) -> str:
        rec_dict = asdict(self)
        return canonical_json(rec_dict) + "\n"

    @classmethod
    def from_line(cls, line: str) -> WALRecord:
        data = json.loads(line)
        expected_hash = data.get("record_hash", "")
        rec = cls(
            index=data["index"],
            timestamp_ns=data["timestamp_ns"],
            record_type=data["record_type"],
            payload=data["payload"],
            prev_hash=data["prev_hash"],
            record_hash=expected_hash,
        )
        calculated = rec.calculate_hash()
        if expected_hash and expected_hash != calculated:
            raise ValueError(f"WAL record corruption detected at index {rec.index}")
        return rec

class PersistentWAL:
    """Crash-durable append-only Write-Ahead Log with fsync."""

    def __init__(self, wal_path: Path, *, auto_sync: bool = True) -> None:
        self.wal_path = Path(wal_path)
        self.wal_path.parent.mkdir(parents=True, exist_ok=True)
        self.auto_sync = auto_sync
        self._fd: Optional[int] = None
        self._last_index = 0
        self._last_hash = "0" * 64
        self._open_log()

    def _open_log(self) -> None:
        exists = self.wal_path.exists()
        if exists:
            # Verify and replay existing log to determine last index & hash
            records = self.read_all()
            if records:
                self._last_index = records[-1].index
                self._last_hash = records[-1].record_hash
        # Open in append binary mode
        self._fd = os.open(str(self.wal_path), os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, "O_BINARY", 0))

    def append(self, record_type: str, payload: Dict[str, Any]) -> WALRecord:
        idx = self._last_index + 1
        now_ns = time.time_ns()
        rec_temp = WALRecord(
            index=idx,
            timestamp_ns=now_ns,
            record_type=record_type,
            payload=payload,
            prev_hash=self._last_hash,
            record_hash="",
        )
        rec_hash = rec_temp.calculate_hash()
        rec = WALRecord(
            index=idx,
            timestamp_ns=now_ns,
            record_type=record_type,
            payload=payload,
            prev_hash=self._last_hash,
            record_hash=rec_hash,
        )
        data = rec.to_line().encode("utf-8")
        os.write(self._fd, data)
        if self.auto_sync:
            os.fsync(self._fd)
        self._last_index = idx
        self._last_hash = rec_hash
        return rec

    def read_all(self) -> List[WALRecord]:
        if not self.wal_path.exists():
            return []
        records = []
        prev = "0" * 64
        with open(self.wal_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                rec = WALRecord.from_line(line)
                if rec.prev_hash != prev:
                    raise ValueError(f"WAL broken hash chain at line {line_no}")
                prev = rec.record_hash
                records.append(rec)
        return records

    def sync(self) -> None:
        if self._fd is not None:
            os.fsync(self._fd)

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.fsync(self._fd)
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
