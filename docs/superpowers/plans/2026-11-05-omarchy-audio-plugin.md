# Omarchy audio plugin implementation plan

**Goal:** Ship an unpublished bar widget and bounded Python worker for default-output audio to the ESP32, with UoW intent/outcome receipts and recoverable telemetry status.

**Architecture:** Extend the existing UoW service for fixed-profile audio intents and outcomes. A separate worker controls PipeWire capture and UDP transport; QML only issues fixed local controls and displays JSON status. The worker must have a live widget heartbeat and fresh receiver telemetry before capture.

**Tech stack:** Python 3 standard library, UoW-v3, Quickshell/QML, PipeWire `parec`, UDP, unittest.

**Spec:** `docs/superpowers/specs/2026-11-05-omarchy-audio-plugin-design.md`.

**Global constraints:** Keep the existing installed streamer and stock Omarchy files intact. No privilege changes. Fixed target and audio profile. Windows sender off before host activation. Agent principals denied. Do not claim physical playback from UDP telemetry.

**Review focus:** (1) microphone fallback; (2) stale/spoofed telemetry; (3) old receipt replaying an effect; (4) widget removal leaving hidden capture; (5) concurrent senders or workers.

## Task 1: UoW audio authority

**Files:** `integrations/omarchy_uow/service.py`, `tests/test_omarchy_audio_authority.py`.

**Interface:** `audio.stream.start/stop` fixed payloads; `audio.effect.record` worker-only outcome; `audio.telemetry.ingest` typed bounded observation. `audio.dsp.crossover.set` remains denied until safe limits exist.

1. Write tests for default denial, exact fixed profile, intent receipt, duplicate/restart, unresolved intent, authorized outcome, invalid outcome, typed telemetry. Run test and observe failure.
2. Add schema validation and UoW contracts. Store intent and outcome separately; never execute effects from replay. Run tests and existing Omarchy suite.
3. Commit authority code and tests.

## Task 2: Audio protocol and capture selection

**Files:** `integrations/omarchy_uow/audio_protocol.py`, `tests/test_omarchy_audio_protocol.py`.

**Interface:** `encode_audio`, `parse_telemetry`, `ReceiverEpoch`, `default_monitor`.

1. Write failing tests for 22-byte header, 256-frame payload, 184-byte RCTM layout, source/sequence rejection, board reboot reset, default sink monitor and no mic fallback.
2. Implement bounded parser and monitor resolution using `pactl` output. Run tests.
3. Commit.

## Task 3: Worker, local control, and recovery

**Files:** `integrations/omarchy_uow/audio_worker.py`, `tests/test_omarchy_audio_worker.py`.

**Interface:** JSON status/control over user-owned Unix socket; `on/off/status/heartbeat` only. UoW gateway client handles intents/outcomes. Process lock and heartbeat lease; capture only after preflight. Atomic preference and status files.

1. Write failing tests with fake capture/UDP for preflight, telemetry loss, sink switch, off without gateway, heartbeat expiry, restart reconciliation, and packet rate.
2. Implement minimal worker and CLI. Run focused and existing Omarchy tests.
3. Commit.

## Task 4: Unpublished Omarchy widget and host qualification

**Files:** `integrations/omarchy_uow/plugin/manifest.json`, `BarWidget.qml`, `Panel.qml`, `integrations/omarchy_uow/install_audio_plugin.py`, `tests/test_omarchy_audio_install.py`, `integrations/omarchy_uow/README.md`.

**Interface:** Widget starts/heartbeats worker; panel displays status and on/off; installer refuses conflicting files and installs only user-owned files.

1. Test manifest/installer conflict and clean uninstall; observe failure.
2. Implement widget, installer, docs. Validate with `omarchy plugin validate`, `qmllint`, and tests.
3. Qualify on host only after checking the Windows sender is stopped. Record sender/receiver telemetry and limitations. Commit; obtain whole-branch review and fix important findings.
