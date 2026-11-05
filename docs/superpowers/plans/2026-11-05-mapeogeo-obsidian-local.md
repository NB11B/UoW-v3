# MAPEOGEOv2 and Obsidian Local View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the canonical MAPEOGEOv2 library available on Omarchy and export verified local UoW observations and decisions to a private Obsidian vault.

**Architecture:** A one-shot bridge snapshots the live SQLite journal, replays it with the existing UoW service on a private copy, maps committed numeric observations into MAPEOGEOv2 PSMSL objects, then writes bounded generated Markdown and JSON. The bridge has no gateway credentials, sends no requests, and does not grant Obsidian execution authority.

**Tech Stack:** Python 3.14 virtual environment, stdlib SQLite/JSON/pathlib, installed editable MAPEOGEOv2, UoW-v3 runtime, pytest, Obsidian.

**Spec:** `docs/superpowers/specs/2026-11-05-mapeogeo-obsidian-local-design.md`

## Global Constraints

- Keep both repositories isolated; no system Python/package changes, privilege changes, or audio service changes.
- Verify hash chain and certified UoW replay on a private snapshot before export.
- Export only the most recent 100 committed numeric observations and 100 decisions/effect outcomes; preserve counts and last verified journal root.
- Generated files stay in `outputs/mapeogeo-obsidian-vault/Generated/`, owner-only, without cloud sync or a reverse import path.
- MAPEOGEOv2 observations are representations of UoW claims; receipt certification does not certify the physical measurement.

## Review Focus

- SQLite snapshot while gateway is writing: verify a consistent copied journal; test concurrent append against snapshot.
- Journal corruption: refuse publication and leave last successful notes intact; test broken hash or receipt.
- Unknown event shape: fail closed for committed observation kinds; test unknown schema.
- Edited generated notes: refuse overwrite; test hash conflict.
- No event wall clock: mark timestamp unknown; test that export time is not used as measurement time.

---

### Task 1: Isolated runtime and verified journal reader

**Files:** Create `integrations/omarchy_uow/mapeogeo_journal.py`; test `tests/test_omarchy_mapeogeo_journal.py`; record local runtime in `outputs/mapeogeo_baseline.md`.

**Interfaces:** `snapshot_and_verify(db: Path) -> tuple[list[JournalRow], str]`, where `JournalRow` contains sequence, request, response, and entry hash. Verification uses `Service` replay against the copied database with empty policy and token configuration; the returned root is the last row hash.

- [ ] Write tests for valid committed/denied rows, concurrent append snapshot, broken hash, divergent receipt, missing sequence, and unchanged live DB.
- [ ] Run `PYTHONPATH=src:. python -m pytest -q tests/test_omarchy_mapeogeo_journal.py`; confirm failure before code.
- [ ] Implement the snapshot reader with SQLite backup into an owner-only temporary directory and replay; inspect rows only after replay succeeds.
- [ ] Run focused tests and commit the reader with its tests.
- [ ] Create a venv under the MAPEOGEOv2 checkout, install editable MAPEOGEOv2 plus UoW-v3 without system packages, and record Python, commits, and import paths in the baseline file.

### Task 2: MAPEOGEOv2 observation mapping

**Files:** Create `integrations/omarchy_uow/mapeogeo_mapping.py`; test `tests/test_omarchy_mapeogeo_mapping.py`.

**Interfaces:** `map_observation(row: JournalRow) -> Observation | None`; `map_decision(row: JournalRow) -> DecisionView | None`. Numeric observations become PSMSL `Observation` values with source IDs, units, trust, causal sequence, and `timestamp=0.0` plus `timestamp_status=unknown`. Other committed/denied rows remain decision views only.

- [ ] Write tests for environmental gauge, audio telemetry, denial, unknown numeric schema, stable IDs and serialization, trust status, and unknown timestamp.
- [ ] Run focused tests and confirm failure before code.
- [ ] Implement narrow schema mappings, using MAPEOGEOv2 `Observation` and `serialize_observation` directly.
- [ ] Run focused tests and commit mapping plus tests.

### Task 3: Safe Obsidian export and real refresh

**Files:** Create `integrations/omarchy_uow/obsidian_export.py`; test `tests/test_omarchy_obsidian_export.py`; update `integrations/omarchy_uow/README.md`; create vault under workspace `outputs/mapeogeo-obsidian-vault/`.

**Interfaces:** `refresh(db: Path, vault: Path, mapeogeo_commit: str) -> ExportResult`; module CLI `python -m integrations.omarchy_uow.obsidian_export --db ... --vault ... --mapeogeo-commit ...`.

- [ ] Write tests for linked notes and index, bounded 100+100 output, deterministic retry, manual note preservation, edited generated file refusal, integrity failure retaining prior export, and private permissions.
- [ ] Run focused tests and confirm failure before code.
- [ ] Implement staging/manifest-based atomic export and CLI; no reverse import, gateway call, or device command.
- [ ] Run all focused bridge tests, the MAPEOGEOv2 124-test suite, and existing UoW Omarchy tests; commit code and README.
- [ ] Refresh the real journal into the private vault; verify counts, provenance, permissions, sample links, and Obsidian opening without modifying global app settings. Record exact commands, outcomes, and blockers.
