"""One-shot, read-only UoW to MAPEOGEOv2/Obsidian projection."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from mapeogeo.psmsl.serialization import serialize_observation

from .mapeogeo_journal import snapshot_and_verify
from .mapeogeo_mapping import DecisionView, map_decision, map_observation


SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
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


def refresh(db: Path, vault: Path, mapeogeo_commit: str) -> ExportResult:
    """Verify, map, and publish a bounded private vault snapshot."""
    if not SAFE_COMMIT.fullmatch(mapeogeo_commit):
        raise ValueError("INVALID_MAPEOGEO_COMMIT")
    rows, root = snapshot_and_verify(db)
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
        if not SAFE_ID.fullmatch(observation.observation_id):
            raise ValueError("INVALID_OBSERVATION_ID")
        base = f"Observations/{observation.observation_id}"
        files[base + ".md"] = _observation_note(observation, mapeogeo_commit)
        files[base + ".json"] = serialize_observation(observation)
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

    vault = Path(vault)
    if vault.is_symlink() or (vault.exists() and not vault.is_dir()):
        raise ValueError("INVALID_VAULT")
    vault.mkdir(parents=True, exist_ok=True, mode=0o700)
    vault.chmod(0o700)
    generated = vault / "Generated"
    lock_path = vault / ".mapeogeo-export.lock"
    with lock_path.open("a+b") as lock:
        lock_path.chmod(0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        backups = list(vault.glob(".mapeogeo-backup-*"))
        if not generated.exists() and len(backups) == 1:
            backups[0].rename(generated)
        elif backups:
            raise ValueError("GENERATED_CONFLICT: unresolved backup")
        _manifest_check(generated)
        stage = Path(tempfile.mkdtemp(prefix=".mapeogeo-stage-", dir=vault))
        backup = vault / (".mapeogeo-backup-" + uuid.uuid4().hex)
        try:
            manifest = {name: hashlib.sha256(data.encode()).hexdigest() for name, data in files.items()}
            for name, data in files.items():
                _write_private(stage, name, data)
            _write_private(stage, ".manifest.json", json.dumps({"files": manifest}, sort_keys=True) + "\n")
            if generated.exists():
                generated.rename(backup)
            try:
                stage.rename(generated)
            except Exception:
                if backup.exists():
                    backup.rename(generated)
                raise
            if backup.exists():
                shutil.rmtree(backup)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return ExportResult(len(observations), len(decisions), rows[-1].sequence if rows else 0, root, vault)


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
