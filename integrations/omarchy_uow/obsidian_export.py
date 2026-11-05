"""One-shot, read-only UoW to MAPEOGEOv2/Obsidian projection."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import uuid

from mapeogeo.psmsl.serialization import serialize_observation

from .mapeogeo_journal import snapshot_and_verify
from .mapeogeo_mapping import DecisionView, map_decision, map_observation


SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
SAFE_OBSERVATION_ID = re.compile(r"[A-Za-z0-9_-]{1,84}\Z")
SAFE_COMMIT = re.compile(r"[0-9a-f]{7,40}\Z")


@dataclass(frozen=True)
class ExportResult:
    observations: int
    decisions: int
    journal_sequence: int
    root: str
    vault: Path


def _escape(value: object) -> str:
    text = str(value)
    for char in ("\\", "`", "[", "]", "*", "<", ">", "|", "\n", "\r"):
        text = text.replace(char, "\\" + char if char not in ("\n", "\r") else " ")
    return text


def _observation_note(observation, commit: str) -> str:
    meta = observation.metadata
    lines = [
        f"# Observation {_escape(observation.observation_id)}",
        "",
        f"- Trust: **{_escape(meta['trust'])}**",
        "- Measurement timestamp: **unknown**",
        f"- Journal sequence: {meta['journal_sequence']}",
        f"- Journal hash: `{meta['journal_hash']}`",
        f"- UoW request: `{_escape(meta['uow_request_id'])}`",
        f"- Source kind: `{_escape(meta['source_kind'])}`",
        f"- MAPEOGEOv2 commit: `{commit}`",
    ]
    for key in ("sensor_id", "session_id", "causal_epoch", "receiver_sequence", "confidence"):
        if key in meta:
            lines.append(f"- {key.replace('_', ' ').title()}: {_escape(meta[key])}")
    lines.extend(["", "## Measurements", ""])
    for name, value, unit in zip(meta["measurement_names"], observation.values, meta["units"], strict=True):
        lines.append(f"- {_escape(name)}: **{value:g} {_escape(unit)}**")
    lines.extend(["", "This records a UoW claim; it does not verify the physical measurement.", ""])
    return "\n".join(lines)


def _decision_note(view: DecisionView) -> str:
    lines = [
        f"# UoW decision {_escape(view.request_id)}",
        "",
        f"- Kind: `{_escape(view.kind)}`",
        f"- Decision: **{_escape(view.decision)}**",
        f"- Reason: {_escape(view.reason)}",
        f"- Principal: `{_escape(view.principal)}`",
        f"- Journal sequence: {view.sequence}",
        f"- Journal hash: `{view.entry_hash}`",
    ]
    if view.session_id:
        lines.append(f"- Session: `{_escape(view.session_id)}`")
    if view.outcome:
        lines.append(f"- Effect status: **{_escape(view.outcome)}**")
    if view.pre_state_hash:
        lines.append(f"- Receipt pre-state hash: `{view.pre_state_hash}`")
    if view.post_state_hash:
        lines.append(f"- Receipt post-state hash: `{view.post_state_hash}`")
    return "\n".join([*lines, ""])


def _manifest_check(generated: Path) -> None:
    if not generated.exists():
        return
    if generated.is_symlink() or not generated.is_dir():
        raise ValueError("GENERATED_CONFLICT: invalid generated directory")
    manifest_path = generated / ".manifest.json"
    actual = {p.relative_to(generated).as_posix(): p for p in generated.rglob("*") if p.is_file() or p.is_symlink()}
    if not actual:
        return
    if ".manifest.json" not in actual or manifest_path.is_symlink():
        raise ValueError("GENERATED_CONFLICT: missing manifest")
    try:
        expected = json.loads(manifest_path.read_text())["files"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("GENERATED_CONFLICT: invalid manifest") from exc
    if not isinstance(expected, dict) or set(actual) != set(expected) | {".manifest.json"}:
        raise ValueError("GENERATED_CONFLICT: added or missing file")
    for name, digest in expected.items():
        path = actual[name]
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("GENERATED_CONFLICT: edited file " + name)


def _write_private(root: Path, name: str, data: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("x", encoding="utf-8") as output:
        output.write(data)
    path.chmod(0o600)


def _recover_backups(vault: Path) -> None:
    generated = vault / "Generated"
    backups = list(vault.glob(".mapeogeo-backup-*"))
    if not backups:
        return
    for backup in backups:
        _manifest_check(backup)
    if not generated.exists() and len(backups) == 1:
        backups[0].rename(generated)
        return
    if not generated.exists():
        raise ValueError("GENERATED_CONFLICT: ambiguous backup")
    history = vault / ".mapeogeo-history"
    if history.is_symlink():
        raise ValueError("GENERATED_CONFLICT: symlink history")
    history.mkdir(mode=0o700, exist_ok=True)
    for backup in backups:
        backup.rename(history / backup.name)


def _check_continuity(generated: Path, rows) -> None:
    if not generated.exists() or not (generated / "Index.md").exists():
        return
    index = (generated / "Index.md").read_text()
    sequence_match = re.search(r"^- Last verified journal sequence: (\d+)$", index, re.MULTILINE)
    root_match = re.search(r"^- Last verified journal root: `([0-9a-f]{64})`$", index, re.MULTILINE)
    if not sequence_match or not root_match:
        raise ValueError("GENERATED_CONFLICT: missing provenance")
    sequence = int(sequence_match.group(1))
    previous_root = root_match.group(1)
    if sequence > len(rows) or (rows[sequence - 1].entry_hash if sequence else "0" * 64) != previous_root:
        raise ValueError("JOURNAL_REGRESSION: published root is not a prefix")


def _refresh_locked(db: Path, vault: Path, mapeogeo_commit: str) -> ExportResult:
    generated = vault / "Generated"
    _recover_backups(vault)
    _manifest_check(generated)
    rows, root = snapshot_and_verify(db)
    _check_continuity(generated, rows)
    observations = []
    decisions = []
    for row in rows:
        observation = map_observation(row)
        decision = map_decision(row)
        if observation is not None:
            observations.append(observation)
        if decision is not None:
            decisions.append(decision)

    files = {}
    for observation in observations[-100:]:
        if not SAFE_OBSERVATION_ID.fullmatch(observation.observation_id):
            raise ValueError("INVALID_OBSERVATION_ID")
        base = f"Observations/{observation.observation_id}"
        files[base + ".md"] = _observation_note(observation, mapeogeo_commit)
        pinned = replace(observation, metadata={**observation.metadata, "mapeogeo_commit": mapeogeo_commit})
        files[base + ".json"] = serialize_observation(pinned)
    for decision in decisions[-100:]:
        if not SAFE_ID.fullmatch(decision.request_id):
            raise ValueError("INVALID_DECISION_ID")
        name = f"Decisions/{decision.sequence:08d}-{decision.request_id}.md"
        files[name] = _decision_note(decision)
    now = datetime.now(timezone.utc).isoformat()
    index = [
        "# MAPEOGEOv2 / UoW local view", "",
        "Generated from a verified local UoW journal. Obsidian edits do not change UoW state.", "",
        f"- Exported at: {now}",
        f"- Last verified journal sequence: {rows[-1].sequence if rows else 0}",
        f"- Last verified journal root: `{root}`",
        f"- MAPEOGEOv2 commit: `{mapeogeo_commit}`",
        f"- Total numeric observations: {len(observations)} (showing {min(len(observations), 100)})",
        f"- Total decisions and effect outcomes: {len(decisions)} (showing {min(len(decisions), 100)})",
        "", "## Observations", "",
    ]
    for observation in reversed(observations[-100:]):
        index.append(f"- [[Generated/Observations/{observation.observation_id}|{observation.observation_id}]]")
    index.extend(["", "## Decisions and effects", ""])
    for decision in reversed(decisions[-100:]):
        index.append(f"- [[Generated/Decisions/{decision.sequence:08d}-{decision.request_id}|{decision.sequence}: {_escape(decision.kind)} — {_escape(decision.decision)}]]")
    files["Index.md"] = "\n".join([*index, ""])

    stage = Path(tempfile.mkdtemp(prefix=".mapeogeo-stage-", dir=vault))
    backup = vault / (".mapeogeo-backup-" + uuid.uuid4().hex)
    try:
        manifest = {name: hashlib.sha256(data.encode()).hexdigest() for name, data in files.items()}
        for name, data in files.items():
            _write_private(stage, name, data)
        _write_private(stage, ".manifest.json", json.dumps({"files": manifest}, sort_keys=True) + "\n")
        _manifest_check(generated)
        if generated.exists():
            generated.rename(backup)
        try:
            stage.rename(generated)
        except Exception:
            if backup.exists():
                backup.rename(generated)
            raise
        if backup.exists():
            history = vault / ".mapeogeo-history"
            if history.is_symlink():
                raise ValueError("GENERATED_CONFLICT: symlink history")
            history.mkdir(mode=0o700, exist_ok=True)
            backup.rename(history / backup.name)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return ExportResult(len(observations), len(decisions), rows[-1].sequence if rows else 0, root, vault)


def refresh(db: Path, vault: Path, mapeogeo_commit: str) -> ExportResult:
    """Verify, map, and publish a bounded private vault snapshot."""
    if not SAFE_COMMIT.fullmatch(mapeogeo_commit):
        raise ValueError("INVALID_MAPEOGEO_COMMIT")
    vault = Path(vault)
    if vault.is_symlink() or (vault.exists() and not vault.is_dir()):
        raise ValueError("INVALID_VAULT")
    vault.mkdir(parents=True, exist_ok=True, mode=0o700)
    vault.chmod(0o700)
    lock_path = vault / ".mapeogeo-export.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        raise ValueError("INVALID_LOCK") from exc
    with os.fdopen(descriptor, "r+b") as lock:
        info = os.fstat(lock.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError("INVALID_LOCK")
        os.fchmod(lock.fileno(), 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _refresh_locked(db, vault, mapeogeo_commit)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--vault", required=True, type=Path)
    parser.add_argument("--mapeogeo-commit", required=True)
    args = parser.parse_args()
    result = refresh(args.db, args.vault, args.mapeogeo_commit)
    print(json.dumps({
        "observations": result.observations,
        "decisions": result.decisions,
        "journal_sequence": result.journal_sequence,
        "root": result.root,
        "vault": str(result.vault),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
