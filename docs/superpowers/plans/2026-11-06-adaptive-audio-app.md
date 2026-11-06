# Adaptive Audio App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship one local Qt window for the existing Omarchy audio stream and its two ESP32 crossover values.

**Architecture:** Keep the current Python audio worker as the sole sender and telemetry listener. Extend its UoW authority and local control interfaces for explicit crossover changes, then build a Qt Quick window that talks only to that worker. Keep the bar as worker owner and quick control.

**Tech Stack:** Python 3.10+, existing UoW-v3 runtime, Qt 6 C++/QML with qmake6, Omarchy Quickshell plugin.

**Spec:** `docs/superpowers/specs/2026-11-06-adaptive-audio-app-design.md`

## Global Constraints

- Fixed device `192.168.254.75`, audio UDP 4000, control UDP 4001, telemetry UDP 4002, 48 kHz stereo s16le, 256 frames per packet.
- Keep current PipeWire capture, telemetry preflight, on/off preference, and bar heartbeat lease.
- No firmware update, universal driver ranges, routing controls, automatic crossover change, or second audio sender.
- A control datagram is only *sent*; only newer matching telemetry may be described as *receiver-reported*.
- No physical crossover values may be invented for device tests; preserve user state and restore the prior pair after a user-selected live test.
- Install only to user-owned paths, preserve existing UoW journal/tokens/preferences, and leave stock Omarchy files and system privileges alone.

## File map

- `integrations/omarchy_uow/service.py`: crossover intent and outcome contracts; deny-by-default authority.
- `integrations/omarchy_uow/audio_protocol.py`: fixed ASCII crossover control encoding and pair validation.
- `integrations/omarchy_uow/audio_worker.py`: one pending command, newer telemetry comparison, timeout, restart reconciliation.
- `integrations/omarchy_uow/audio_runtime.py`: worker socket command and UDP transport extension.
- `integrations/omarchy_uow/plugin/{BarWidget,Panel}.qml`: open the app from the existing bar panel.
- `apps/adaptive-audio/`: dedicated qmake6 project, C++ socket backend, Qt Quick window, tests, desktop file, and local installer.
- `tests/test_omarchy_{service,audio_protocol,audio_worker,audio_runtime}.py`: boundary and regression tests.

## Review Focus

1. A malformed or non-finite frequency must never reach UDP or the UoW journal; test in protocol and socket layers.
2. A denied or unavailable UoW gateway must never send a crossover datagram; test worker with fake transport.
3. Old, mismatched, or stale telemetry must not say *receiver reports requested values*; test worker sequence and timeout.
4. A worker restart during a pending change must not replay it or claim success; test recovery state.
5. Qt opening/closing while streaming must leave the sender running; test app status and bar heartbeat integration.

---

### Task 1: Governed crossover intent and outcome

**Files:** Modify `integrations/omarchy_uow/service.py`; tests in `tests/test_omarchy_service.py`.

**Interfaces:** `audio.dsp.crossover.set` consumes `{command_id, session_id, low_hz, high_hz}` and creates an `UNCERTAIN` intent; `audio.dsp.crossover.effect` consumes `{command_id, outcome, receiver_sequence}` with outcome `REPORTED_MATCH`, `TIMEOUT`, or `INTERRUPTED`. Both use existing `Service.handle` journaling and policy. `receiver_sequence` is a nonnegative integer for a match, `null` otherwise.

- [ ] Write failing tests for invalid values, duplicate IDs, missing session, empty policy, accepted receipt before effect, outcome order, and replay of intent/outcome.
- [ ] Run `PYTHONPATH=src:. python -m pytest -q tests/test_omarchy_service.py` and confirm the new tests fail for the expected missing contract.
- [ ] Implement strict schema and structural `0 < low < high < 24000` validation; add the effect kind and state transition without changing stream contracts.
- [ ] Run the same tests and confirm pass; commit this task.

### Task 2: Worker control and receiver confirmation

**Files:** Modify `integrations/omarchy_uow/{audio_protocol,audio_worker,audio_runtime}.py`; tests in `tests/test_omarchy_{audio_protocol,audio_worker,audio_runtime}.py`.

**Interfaces:** `encode_crossover(low_hz: float, high_hz: float) -> bytes` returns the existing `SET_CROSS_LOW` and `SET_CROSS_HIGH` ASCII datagram after validation. `AudioWorker.set_crossover(low_hz, high_hz, now=None) -> dict` requests the UoW intent before `transport.send_control(payload)`. `AudioWorker.status()` adds a bounded `crossover_change` state. CLI `omarchy-audio-worker crossover LOW HIGH` sends the command to the same local worker socket; socket input stays bounded.

- [ ] Write failing protocol tests for exact datagram bytes and non-finite, unordered, and out-of-range pairs.
- [ ] Write failing worker tests for no effect on denial, one send after commit, newer matching telemetry, mismatch/timeout, and interruption/restart without resend.
- [ ] Write failing socket tests for malformed commands, bound lengths, and status visibility.
- [ ] Run the three named test files and confirm expected failures; implement the protocol, worker, transport, and socket pieces.
- [ ] Run named tests plus existing audio regressions; commit this task.

### Task 3: Native window and bar entry

**Files:** Create `apps/adaptive-audio/{adaptive-audio.pro,src/*,tests/*,bin/*,desktop/*,README.md}`; modify `integrations/omarchy_uow/plugin/{BarWidget,Panel}.qml`.

**Interfaces:** C++ `AudioBackend` reads bounded JSON from the existing worker socket and exposes `state`, `source`, `receiverAge`, `currentLow`, `currentHigh`, `editLow`, `editHigh`, and `changeState` to QML. `Q_INVOKABLE` methods `refresh()`, `setStreaming(bool)`, `apply()`, and `revertEdits()` use fixed local commands; `apply()` never sends on field change. Bar `Open Adaptive Audio` launches one app instance.

- [ ] Write failing Qt backend tests against a fake Unix socket for parsing, on/off/apply commands, stale telemetry disabling Apply, and opening/closing without an off command.
- [ ] Build the smallest C++ backend and QML layout: status, output, three-band split diagram, two numeric fields, Apply/Revert, receiver-reported result.
- [ ] Add app icon, desktop entry, theme/language support, build and offscreen UI smoke scripts; update bar action without changing its worker ownership.
- [ ] Run app tests, `qmake6` build, QML/offscreen smoke, plugin validation and `qmllint`; commit this task.

### Task 4: Safe local upgrade and qualification

**Files:** Modify `integrations/omarchy_uow/install_audio_plugin.py`; create `apps/adaptive-audio/bin/install-local` and integration checks; update both READMEs.

**Interfaces:** Upgrade checks hashes of installed files against the current manifest, backs up existing plugin and worker files, stages replacements atomically, preserves DB/tokens/preferences, and can roll back. App installer refuses conflicting launcher/binary paths. No package or privilege changes.

- [ ] Write installer tests for conflict refusal, unmodified-file upgrade, preserved state, and rollback after an injected failure.
- [ ] Implement installer and read-only preflight; run installer tests.
- [ ] Run full Python and Qt verification, then install the app and upgrade user-owned worker/plugin files if preflight passes.
- [ ] Verify bar and app show the same receiver state, existing stream start/stop behavior, service restart recovery, and no second sender; record commands/results.
- [ ] Use a user-selected low/high pair for a live change and restore prior values, or report device change test pending if no pair is supplied. Commit docs and final corrections.
