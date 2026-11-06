# Adaptive Audio Omarchy qualification — 2026-11-06

## Scope

Local Qt app, existing bar worker, and two-crossover control on the configured
Omarchy laptop. No firmware, stock Omarchy file, package, or system privilege
change. The Windows streamer was already stopped; the legacy Omarchy streamer
service remained disabled and inactive.

## Build and test evidence

| Command | Observed result |
| --- | --- |
| `PYTHONPATH=src:. .venv/bin/python -m pytest -q tests/test_omarchy_*.py` | 67 passed, 3 skipped |
| `bash apps/adaptive-audio/bin/test` | 7 Qt tests passed, including fragmented local socket response |
| `bash apps/adaptive-audio/bin/ui-smoke` | Exit 0; Qt window loaded offscreen |
| `omarchy plugin validate integrations/omarchy_uow/plugin` | Exit 0 |
| `desktop-file-validate ~/.local/share/applications/adaptive-audio.desktop` | Exit 0 |
| `git diff --check` | Exit 0 |

The full repository `pytest -q` did not collect because unrelated campaigns
need `numpy` and `openvino`, which are absent from this task's virtual
environment. The Omarchy integration suite above ran completely. `pytest`
itself was installed from the local `uv` cache into `.venv`; no network or
system package installation was used.

## Local installation

1. `python -m integrations.omarchy_uow.install_audio_plugin --check-upgrade`
   reported `ready`, 9 files, legacy policy. All 165 manifest-listed installed
   files matched their recorded hashes.
2. `bash apps/adaptive-audio/bin/install-local` installed the Qt binary,
   desktop entry, and icon in user-owned `.local` paths. The installed binary
   SHA-256 matched the build: `dfcb0f7207a8cf3289726b307b862c385aabfe9c7bce5dd540c323cdebecab6b`.
3. `omarchy plugin disable nb11b.adaptive-audio` stopped the bar-owned sender.
   `python -m integrations.omarchy_uow.install_audio_plugin --upgrade` replaced
   9 user-owned plugin/worker files and updated the local policy. The journal,
   token files, and enabled preference were preserved. Backup:
   `~/.local/state/omarchy-uow-audio/upgrade-backup-8cd11a7b2ae3499c8d44af52dad54c07`.
4. `systemctl --user restart omarchy-uow-audio-gateway.service` and
   `omarchy plugin enable nb11b.adaptive-audio` restored streaming. The
   gateway was active; the legacy service was disabled and inactive. One
   `omarchy-audio-worker serve` process was observed.
5. The old desktop launcher was copied to
   `~/.local/state/omarchy-uow-audio/legacy-omarchy-streamer.desktop.backup`
   and removed from the app menu. The old CLI and disabled user service remain
   available for recovery.

## Device observation

Immediately before the change, the worker reported streaming at 184.0
packets/s, receiver age 0.1 s, sequence 1245, and 100 / 2500 Hz.

| Command | Newer receiver telemetry | UoW journal |
| --- | --- | --- |
| `omarchy-audio-worker crossover 90 3100` | 90 / 3100 Hz, sequence 1347 in a later status read | Intent 454 and `REPORTED_MATCH` outcome 456, both committed with receipts |
| `omarchy-audio-worker crossover 100 2500` | 100 / 2500 Hz, sequence 1415 in a later status read | Intent 473 and `REPORTED_MATCH` outcome 475, both committed with receipts |

The restored stream reported 184.0 packets/s and receiver age 0.1 s. The
installed Qt window rendered the live stream and receiver settings, and a
second `adaptive-audio open` request returned 0 while the first instance ran.

Receiver telemetry is an unauthenticated device claim. It confirms what the
ESP32 reported over UDP, not acoustic output or which physical driver sounded.
No receiver-side serial or acoustic measurement was available for this test.
