# Adaptive Audio: one Omarchy app for streaming and crossover control

## Intent

Make the working Omarchy-to-ESP32 audio path usable from one small native Qt
window. The user can see stream and receiver state, turn streaming on or off,
and set the two crossover frequencies. The existing bar icon remains a quick
control and opens the same app. This first build keeps the current Python
capture and telemetry worker, UDP audio format, and ESP32 firmware unchanged.

## Approaches

1. **Selected: Qt window over the existing UoW audio worker.** Add a narrow
   crossover command to the worker's local socket; share its state with the
   bar and window. This changes the control surface while preserving the
   qualified sender and its receiver preflight.
2. **Replace the sender with a new Qt audio engine.** This would place all
   code in one process, but changes capture timing, restart behavior, and
   packet transport that already work. It is outside this build.
3. **Expand the ESP32 into a per-output miniDSP-like processor.** This could
   expose routing, per-output filters, and slopes, but needs firmware and
   hardware qualification. It is a later project.

## User experience

- One Omarchy-themed Qt Quick window, launched from the app menu or the
  existing Adaptive Audio bar icon. The existing panel may retain a status
  summary and on/off switch; it offers an **Open Adaptive Audio** action.
- Top: stream state, current default output, receiver freshness, packet rate,
  and a single on/off control. Opening or closing the window does not change
  playback or the stream.
- Middle: a simple low / mid / high band diagram with two movable split
  markers. Numeric fields allow exact low and high values in Hz. The diagram
  shows division points, not a measured or modeled filter response.
- Bottom: **Apply**, **Revert edits**, and a result line. Show the receiver's
  current low/high values separately from unsent edits. Applying is explicit;
  moving a marker does not transmit. A successful result says **Receiver
  reports X / Y Hz**. Timeout says **Sent; receiver confirmation missing**.
- When telemetry is stale or absent, current values are shown as unavailable
  and Apply is disabled. The app does not silently use the legacy streamer's
  100 / 2500 Hz defaults or resend settings on launch.
- First version has no routing matrix, per-driver output controls, gain, test
  tone, or presets. These would imply device features or add state that this
  protocol has not qualified.

## Control and authority

- Keep the existing `omarchy-audio-worker` as the sole local PCM sender and
  UDP-4002 telemetry listener. The Qt app and bar both use its owner-only Unix
  control socket. No second worker or legacy streamer is launched by the app.
- Add one bounded local `crossover.set` command with two finite numeric
  values. Structural validity is `0 < low < high < 24000` Hz for the 48 kHz
  stream. There are no fixed speaker-model ranges; the user selects values
  for their connected drivers. The app does not label any setting "safe".
- The UoW gateway's `audio.dsp.crossover.set` contract remains deny-by-default
  unless its explicit operator policy grants it. On acceptance it records an
  intent before a device command is sent. The worker sends a bounded control
  datagram to the fixed ESP32 address and port 4001, then watches *newer*
  telemetry for both requested values with float tolerance. A send is not
  reported as applied. The journal records the eventual reported match,
  timeout, or interruption as a separate outcome. A restart never replays an
  old command.
- The receiver telemetry is an unauthenticated device claim. The UI says
  what the receiver reports; it does not claim that sound came from the
  correct driver or that the filters are physically safe.
- The bar's heartbeat, streaming on/off behavior, automatic following of the
  default output monitor, and fail-closed receiver preflight stay as they are.
  Crossover edits do not restart streaming. For this first build, the bar
  continues to own the worker lifecycle: disabling the bar stops the sender,
  and a desktop app opened while the bar is disabled shows that streaming is
  unavailable until the bar is re-enabled. This is the least disruptive
  interpretation of the user's request; a standalone background service can
  be considered after this version is qualified.

## Packaging and migration

- Keep source in a dedicated app project under this workspace, with the
  existing UoW integration source as its backend dependency. Build the GUI
  as C++/Qt Quick with `qmake6`, matching the user's Jitsi and Workbench
  preference for a real app window. An unpublished bar plugin remains the
  quick control. No Omarchy stock files or system privileges change.
- Stage and test a replacement of the existing user-owned plugin files and
  copied Python worker with backup and rollback. Preserve its state database,
  tokens, current stream preference, and current device values. The old
  `omarchy-streamer` launcher and user service are not used; after the new
  app passes host checks, disable the legacy service if active and remove the
  old launcher only after checking its ownership and contents.
- No firmware update, package update, public plugin release, or automatic
  change to crossover settings is part of this milestone.

## Verification

1. Unit tests: invalid values and missing authority send nothing; a valid
   accepted request gets an intent receipt before transmission; only newer
   matching telemetry completes it; timeout/restart leave a truthful outcome.
2. Regression tests: stream startup, default-output following, stale receiver
   shutdown, heartbeat lease, and deny-by-default still work.
3. Local integration: build the Qt window, run UI tests offscreen, validate
   the unpublished bar plugin, and confirm the app and bar read the same
   worker state. Test window open/close without disturbing streaming.
4. Device check: use the existing ESP32 and low playback level to apply one
   user-chosen crossover pair supplied specifically for the test, observe
   newer matching telemetry, then restore the prior receiver-reported pair.
   Never invent a physical crossover pair for this test. If the user has not
   supplied a pair or receiver telemetry is unavailable, stop at simulated
   tests and report that device confirmation is pending.

## Remaining builder decisions

Choose the app name and icon, exact Qt layout, float comparison tolerance,
command timeout, and the safest upgrade path for the current installer after
inspecting installed file hashes. Keep each choice observable in tests or
in the app's status text.
