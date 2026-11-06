# Adaptive Audio for Omarchy

A small native Qt window for the existing UoW-governed Omarchy playback
stream. The current bar widget still owns the Python sender and its heartbeat;
the app talks to the same local worker socket. Disabling the bar stops the
stream. Closing the window does not stop it.

Build and test locally:

```sh
bash bin/build
bash bin/test
bash bin/ui-smoke
python -m unittest discover -s tests -p 'test_install.py' -q
```

Install the window to user-owned bin, applications, and icon paths with
`bash bin/install-local`. The existing bar icon's **Open Adaptive Audio**
action launches this window; the app launcher does too. The UoW audio worker
upgrade is described in `../../integrations/omarchy_uow/README.md`.

The first version exposes the current two crossover frequencies only. Apply
requires a fresh receiver report and a local UoW intent receipt. A sent
control datagram is shown as pending until newer receiver telemetry reports
both requested values. There are no automatic crossover changes on launch.
