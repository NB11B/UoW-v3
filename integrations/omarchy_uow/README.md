# Omarchy UoW local observation integration

This adapter runs on Python 3.10+ with no additional runtime packages. It uses
the existing UoW `WorldState`, guards, `propose`, `certify`, `commit`, and
`EvidenceRecord`. The `coretemp` adapter reads the Linux CPU package sensor
from `/sys/class/hwmon` and submits it as an `UNVERIFIED_CLAIM`.

The service is a foreground JSON-lines process over standard input/output.
`observation.ingest` and `observation.summarize` are its only capabilities.
The latter writes a bounded summary to local UoW state; it does not operate
hardware. Each committed request, state, and receipt is stored in one SQLite
transaction. Startup replays and verifies the hash-linked journal.

The optional Unix socket gateway accepts the same JSON-lines requests locally:

```sh
PYTHONPATH=src:. python -m integrations.omarchy_uow.gateway \
  --socket /path/to/private/uow.sock --db /path/to/state.db \
  --policy /path/to/policy.json --tokens /path/to/tokens.json
```

The socket is created with owner-only permissions and the gateway refuses an
occupied path. A bearer token still determines the principal and capabilities;
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

This proves authority at the service interface. Programs with the same OS
user identity can still access its configuration and database or bypass this
gateway. Bubblewrap works on the host and can hide the user's home from a
child process, but no real agent has been launched or qualified in such a
profile. Physical effects, sensor calibration, and OS-enforced isolation are
outside this integration's qualification scope.
