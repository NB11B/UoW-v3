# MAPEOGEOv2 on Omarchy with an Obsidian view

Date: 2026-11-05
Status: proposed; implementation awaits user approval

## Intent

Run the canonical MAPEOGEOv2 Python package on this Omarchy laptop and make locally recorded UoW observations and decisions easy to inspect in Obsidian. The user selected MAPEOGEOv2 as the runtime and Obsidian as a human-readable view. This milestone should demonstrate the connection with the existing audio and sensor UoW journal without granting notes or plugins authority to execute work.

## Baseline

- `NB11B/MAPEOGEOv2` is the canonical repository. The historical `NB11B/MAPEOGEO` repository remains an archive. An isolated HTTPS checkout at `work/MAPEOGEOv2` is clean at `1346330145ac37a991a22e159a6064cfa0856300`.
- Its `pyproject.toml` requires Python 3.11+ and has no runtime dependencies. On this laptop, a temporary Python 3.15.2 environment passed all 124 tests. System Python is 3.14.8. The package provides a kernel and PSMSL observation classes, but no resident service or Obsidian integration.
- Obsidian 1.14.4 is installed; no existing vault was found in the inspected user paths. The current Omarchy UoW gateway has a hash-linked SQLite journal at `~/.local/state/omarchy-uow-audio/uow.db`, with 2,256 rows at inspection. Its containing directory is mode 0700. The gateway was not queried or changed during this baseline because access to the user systemd bus was unavailable in the assessment environment.
- UoW's journal contains committed and denied requests, certified receipts, and state snapshots. Accepted sensor and audio telemetry values carry `UNVERIFIED_CLAIM`; a receipt proves the local UoW transition, not that a physical measurement was independently verified.

## Approaches

1. **Canonical MAPEOGEOv2 plus local Obsidian projection — selected.** Install the Python library in an isolated environment and use a small bridge to translate verified UoW records into MAPEOGEOv2 observations and generated Markdown. It is inspectable and keeps authority in the existing UoW gateway. The bridge needs explicit schema mapping and maintenance.
2. **MAPEOGEOv2 runtime without notes.** This is simpler to operate but does not provide the requested human review surface.
3. **Obsidian as a bidirectional control plane.** Notes could propose new work, but edits, sync, and plugins would become an additional unqualified authority path. That requires a separate proposal, review, and capability design.

## Scope and behavior

- Keep MAPEOGEOv2 in its separate clean checkout. Create a local virtual environment for this checkout; do not modify system Python, system packages, existing repositories, Omarchy privileges, or the audio plugin. Record the exact commit and Python interpreter in a baseline file.
- Put the bridge in `integrations/omarchy_uow/` of the existing UoW-v3 branch, with its own tests and a documented one-shot `refresh` command. No always-on service is required for the first milestone. A later opt-in user timer can refresh after the one-shot path is qualified.
- Read a consistent SQLite snapshot of the existing UoW journal. Verify the hash chain and UoW replay on a private copy using the existing service logic before producing output. Stop on any gap, hash mismatch, divergent receipt, malformed record, or unsupported schema. Never modify the live journal or invoke UoW capabilities as part of export.
- Map committed numeric `observation.ingest` and `audio.telemetry.ingest` records into MAPEOGEOv2 `psmsl.Observation` objects and deterministic serialized JSON. Use stable IDs derived from the UoW request/receipt. Preserve measurement names, units, sensor/session IDs, causal epoch or receiver sequence, trust status, source journal sequence/hash, and MAPEOGEOv2 commit. The journal has no trustworthy observation wall-clock timestamp; mark time as unknown rather than treating export time as measurement time. Do not infer a latent generator or claim that an observation is certified physical truth.
- Render bounded Markdown notes for the most recent 100 committed observations and 100 authority decisions/effect outcomes, plus an index containing counts, last verified journal sequence/root, and export time. Decisions and effect outcomes are UoW receipt views, not MAPEOGEOv2 observation objects. Show denials as denials and uncertain outcomes as uncertain. Never expose tokens, personal audio, unbounded raw payloads, or file paths outside the private workspace.
- Create a new, local-only vault under this workspace's `outputs/` directory. Write only within a dedicated `Generated/` subtree. The exporter owns that subtree and can replace its generated files atomically; it never deletes or rewrites notes elsewhere in the vault. The vault is owner-only and is not configured for cloud sync. Obsidian can open the folder as a vault; editing Markdown does not feed into UoW or MAPEOGEO state.
- The first deliverable is an on-demand refresh and a visible Obsidian vault. Automatic refresh and any agent-triggered MAPEOGEO planning remain out of scope until separately designed. This avoids creating an unobserved background reader of the journal.

## Failure and recovery

- A failed verification or mapping leaves the last successful export intact and returns a clear nonzero error. The index states the last successful journal root and export time, so stale notes are distinguishable from current state.
- If a note was manually edited in `Generated/`, the next refresh either refuses to overwrite it or rewrites only files whose stored generated hash matches the previous export; the user is shown the conflict. Manual notes outside `Generated/` are never touched.
- Re-running refresh against the same journal root must produce the same observation data and note content apart from an explicit export-time field in the index. A restart must not create duplicate observations or send any device command.

## Acceptance

- MAPEOGEOv2 imports from the isolated environment and its 124 tests still pass.
- Fixture tests show valid journal records become correctly typed MAPEOGEOv2 observations and linked notes; missing/invalid hashes, replay divergence, unsupported records, denied requests, unknown timestamps, and edited notes are handled as above.
- The real journal exports without exposing credentials, and the vault opens in Obsidian with an index plus linked recent observations and decisions. Validate actual counts and sample notes against the verified journal. No system privilege or streaming behavior changes.

## Builder choices left open

The bridge may use standard-library SQLite and atomic file replacement. It should choose stable, safe filenames and a manifest for detecting edited generated notes. The exact Markdown layout is a local presentation choice so long as provenance, trust, and uncertain status remain explicit.
