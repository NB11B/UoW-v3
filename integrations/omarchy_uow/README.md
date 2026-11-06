# Omarchy UoW local observation integration

This adapter runs on Python 3.10+ with no additional runtime packages. It uses
the existing UoW `WorldState`, guards, `propose`, `certify`, `commit`, and
`EvidenceRecord`. The `coretemp` adapter reads the Linux CPU package sensor
from `/sys/class/hwmon` and submits it as an `UNVERIFIED_CLAIM`.

The service is a foreground JSON-lines process over standard input/output.
It supports environmental observations and fixed-profile audio intents,
worker outcomes, and typed receiver telemetry. The audio crossover capability
accepts an explicit operator-selected pair with structural validation and a
separate receiver-reported outcome. It does not certify driver safety.
The latter writes a bounded summary to local UoW state; it does not operate
hardware. Each committed request, state, and receipt is stored in one SQLite
transaction. Startup replays and verifies the hash-linked journal.

The optional Unix socket gateway accepts the same JSON-lines requests locally:

```sh
PYTHONPATH=src:. python -m integrations.omarchy_uow.gateway \
  --socket /path/to/private/uow.sock --db /path/to/state.db \
  --policy /path/to/policy.json --tokens /path/to/tokens.json
```

The socket is created with owner-only permissions and the gateway refuses a
live occupied path; an owned stale socket is removed during recovery. A bearer token still determines the principal and capabilities;
the socket itself does not authorize an operation. Keep the socket directory
private. The gateway serves one request at a time to preserve SQLite's
single-threaded state and receipt sequence.

To run from the repository root:

```sh
PYTHONPATH=src:. python -m pytest -q tests/test_omarchy_service.py tests/test_omarchy_process.py tests/test_omarchy_coretemp.py
PYTHONPATH=src:. python -m integrations.omarchy_uow.coretemp --db /path/to/state.db --policy /path/to/policy.json --tokens /path/to/tokens.json
```

The token file must have mode `0600`. It maps random secret tokens to
principal names, for example `{"<random-token>":"sensor"}`. Policy maps
principals to capability lists, for example
`{"sensor":["observation.ingest"]}`. Empty policy denies all operations.
The one-shot `coretemp` command requires exactly one configured token whose
principal has `observation.ingest`. It reads a real temperature and prints a
receipt. Keep token values private; they are not written to the journal.

This proves authority at the service interface. An opt-in host test launches
a Bubblewrap client with only the gateway socket mounted; it confirms the
client can commit a scoped observation while the user's home and service
database are absent. An unrestricted same-user process can still access the
database or bypass this gateway. No real agent has been launched or qualified
in the restricted profile. Physical effects, sensor calibration, and full
agent isolation are outside this integration's qualification scope.

Run the host containment check only on a machine with working Bubblewrap and
Unix socket support:

```sh
UOW_RUN_HOST_SANDBOX_TEST=1 PYTHONPATH=src:. python -m pytest -q tests/test_omarchy_containment.py
```

## Unpublished Adaptive Audio bar widget

The approved local-only audio integration lives in `plugin/`, `audio_protocol.py`,
`audio_worker.py`, and `audio_runtime.py`. The widget starts a separate worker
and sends a one-second heartbeat. If the widget or shell exits, capture stops
within three seconds. The worker follows the current default PipeWire output
monitor. It never falls back to a microphone. It sends fixed 48 kHz stereo
`s16le` packets to `192.168.254.75:4000` and requires fresh valid receiver
telemetry from UDP 4002 before opening playback capture. The physical sound
output is not verified by telemetry.

Installation stages files only in the user's plugin, bin, state, share, and
systemd user directories, and refuses conflicting paths:

```sh
PYTHONPATH=src:. python -m integrations.omarchy_uow.install_audio_plugin
omarchy plugin validate ~/.config/omarchy/plugins/nb11b.adaptive-audio
/usr/lib/qt6/bin/qmllint -I /usr/share/omarchy/shell \
  ~/.config/omarchy/plugins/nb11b.adaptive-audio/{BarWidget,Panel}.qml
```

Before activation, stop the Windows streamer. The ESP32 wire protocol has no
sender ownership. Then enable the local gateway and widget:

```sh
systemctl --user daemon-reload
systemctl --user enable --now omarchy-uow-audio-gateway.service
omarchy plugin enable nb11b.adaptive-audio
omarchy-audio-worker status
```

The worker wrapper accepts `on`, `off`, `status`, and `heartbeat`. The widget
supplies the heartbeat and a visible on/off control. `off` stops local capture
even if the UoW gateway is down. An agent principal is absent from the live
start/stop policy. This remains a same-user audit boundary, not independent
OS-enforced governance against processes running as the desktop user.

The Adaptive Audio Qt window in `apps/adaptive-audio/` also uses this worker.
`omarchy-audio-worker crossover LOW HIGH` requests a UoW intent before sending
the fixed UDP-4001 control datagram. It accepts finite `0 < LOW < HIGH < 24000`
Hz and reports success only after a newer telemetry packet reports both
requested values. The app does not change settings at startup. Keep the bar
enabled to keep its heartbeat lease; disabling the bar stops streaming.

For an existing unmodified local installation, check the recorded file hashes
before upgrading. The upgrade preserves the journal, tokens, and on/off
preference, and leaves a backup of replaced user-owned files:

```sh
PYTHONPATH=src:. python -m integrations.omarchy_uow.install_audio_plugin --check-upgrade
omarchy plugin disable nb11b.adaptive-audio
PYTHONPATH=src:. python -m integrations.omarchy_uow.install_audio_plugin --upgrade
systemctl --user restart omarchy-uow-audio-gateway.service
omarchy plugin enable nb11b.adaptive-audio
```

Build and install the Qt window with `bash apps/adaptive-audio/bin/install-local`.
The legacy `omarchy-streamer` user service should remain disabled so it cannot
become a second sender. A live crossover change needs a pair chosen for the
attached drivers; simulated tests do not need one.

If the user-owned upgrade needs to be reversed, disable the bar, run
`python -m integrations.omarchy_uow.install_audio_plugin --rollback BACKUP_PATH`
from the same source revision, restart the gateway, and re-enable the bar.
Rollback refuses to overwrite installed files that changed after the upgrade.
If the journal contains a committed crossover command, rollback retains the
newer service replay code and restores the legacy policy so older worker files
cannot issue another crossover command. The receipt database is never removed.

The installer writes hashes of its own files to a private inventory. To remove
the plugin and gateway after qualification, run
`PYTHONPATH=src:. python -m integrations.omarchy_uow.install_audio_plugin --uninstall`.
It stops the widget and gateway, refuses to delete edited files, and retains
the UoW receipt database and credentials in the state directory for review.

## MAPEOGEOv2 and Obsidian local view

The optional, one-shot exporter in `mapeogeo_journal.py`,
`mapeogeo_mapping.py`, and `obsidian_export.py` reads a consistent copy of the
existing UoW SQLite journal and replays every row before publishing notes.
It uses the canonical `mapeogeo.psmsl.Observation` type for committed numeric
sensor and audio telemetry claims. Authority decisions and effect outcomes are
rendered separately. An accepted UoW receipt does not prove a physical sensor
reading; exported observations retain `UNVERIFIED_CLAIM` and unknown measurement
time. The exporter has no token, gateway request, or hardware capability.

From this repository root, with MAPEOGEOv2 installed or available to the
chosen Python interpreter:

```sh
python -m integrations.omarchy_uow.obsidian_export \
  --db /path/to/private/uow.db \
  --vault /path/to/private/mapeogeo-obsidian-vault \
  --mapeogeo-commit <exact-40-character-v2-commit>
```

The vault contains `Generated/Index.md`, up to 100 recent observation notes
and JSON sidecars, and up to 100 recent decision/effect notes. A manifest
detects edits or added files under `Generated/` and refuses to overwrite them.
Personal notes outside `Generated/` are untouched. The vault and generated
files are owner-only. Older generated trees are retained under the private
`.mapeogeo-history/` folder, so an edit racing with refresh is not discarded;
periodic pruning is not automatic. A refresh rejects a journal whose previous
published root is not a prefix of the current verified journal. Open the vault
folder in Obsidian using its **Open folder
as vault** action. Markdown edits are never imported into UoW or MAPEOGEOv2.
There is no background refresh or cloud synchronization configured by this
integration.

The MAPEOGEOv2-dependent tests skip when that private package is unavailable,
so the core UoW CI job does not need cross-repository credentials. Run them
locally with the pinned MAPEOGEOv2 checkout in the Python environment:

```sh
python -m pytest -q tests/test_omarchy_mapeogeo_mapping.py tests/test_omarchy_obsidian_export.py
```
