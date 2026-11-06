"""Bounded audio worker core; the widget owns its short heartbeat lease."""
from __future__ import annotations

import time
import uuid

from .audio_protocol import AUDIO_PORT, TARGET, ReceiverEpoch, default_monitor, encode_audio, encode_crossover, parse_telemetry
from .service import AUDIO_PROFILE


class AudioWorker:
    def __init__(self, monitor=default_monitor, capture=None, transport=None, uow=None, session_store=None, command_store=None):
        self.monitor, self.capture_factory, self.transport, self.uow = monitor, capture, transport, uow
        self.session_store = session_store
        self.command_store = command_store
        self.desired = True
        self.last_heartbeat = None
        self.session_id = None
        self.capture = None
        self.source = None
        self.last_telemetry = None
        self.telemetry = None
        self.receiver_epoch = ReceiverEpoch()
        self.sequence = 0
        self.packets = 0
        self.rate_start = None
        self.packet_rate = 0.0
        self.next_send = 0.0
        self.next_preflight = 0.0
        self.probe_sent = False
        self.mode = "waiting"
        self.retry_after = 0.0
        self.last_observation = None
        self.last_observed_sequence = None
        self.pending_crossover = None
        self.crossover_change = {"state": "idle"}

    def heartbeat(self, now=None):
        self.last_heartbeat = time.monotonic() if now is None else now

    def on(self):
        self.desired = True
        self.mode = "waiting"

    def off(self):
        self.desired = False
        self._close("STOPPED", stop_intent=True)
        self.mode = "off"

    def _request(self, kind, payload):
        try:
            return self.uow(kind, payload).get("decision") == "COMMITTED"
        except (OSError, ValueError, ConnectionError, TimeoutError):
            return False

    def set_crossover(self, low_hz, high_hz, now=None):
        now = time.monotonic() if now is None else now
        wire = encode_crossover(low_hz, high_hz)
        if self.mode != "streaming" or self.telemetry is None or self.last_telemetry is None or now - self.last_telemetry > 3:
            return {"state": "receiver-unavailable"}
        if self.pending_crossover is not None:
            return {"state": "busy"}
        if self.command_store is not None and self.command_store.pending():
            return {"state": "reconciliation-pending"}
        command_id = uuid.uuid4().hex
        if self.command_store is not None:
            self.command_store.add(command_id)
        payload = {"command_id": command_id, "session_id": self.session_id, "low_hz": low_hz, "high_hz": high_hz}
        if not self._request("audio.dsp.crossover.set", payload):
            if self.command_store is not None:
                self.command_store.reconcile(self.uow)
            self.crossover_change = {"state": "denied"}
            return self.crossover_change.copy()
        self.pending_crossover = {"command_id": command_id, "low_hz": low_hz, "high_hz": high_hz,
                                  "baseline_sequence": self.telemetry.sequence, "deadline": now + 2}
        self.crossover_change = {"state": "pending", "low_hz": low_hz, "high_hz": high_hz}
        try:
            self.transport.send_control(wire)
        except OSError:
            self._finish_crossover("INTERRUPTED")
        return self.crossover_change.copy()

    def _finish_crossover(self, outcome, sequence=None):
        pending = self.pending_crossover
        if pending is None:
            return
        recorded = self._request("audio.dsp.crossover.effect", {"command_id": pending["command_id"],
                                 "outcome": outcome, "receiver_sequence": sequence})
        if recorded and self.command_store is not None:
            self.command_store.remove(pending["command_id"])
        state = {"REPORTED_MATCH": "receiver-reported", "TIMEOUT": "unconfirmed", "INTERRUPTED": "interrupted"}[outcome]
        self.crossover_change = {"state": state if recorded else "unconfirmed",
                                 "low_hz": pending["low_hz"], "high_hz": pending["high_hz"]}
        self.pending_crossover = None

    def _close(self, outcome, stop_intent=False):
        if self.capture is not None:
            self.capture.close()
            self.capture = None
        self._finish_crossover("INTERRUPTED")
        if self.session_id is not None:
            if stop_intent:
                self._request("audio.stream.stop", {"session_id": self.session_id})
            recorded = self._request("audio.effect.record", {"session_id": self.session_id, "outcome": outcome})
            if recorded and self.session_store is not None:
                self.session_store.remove(self.session_id)
        self.session_id = None
        self.source = None
        self.telemetry = None
        self.last_telemetry = None
        self.receiver_epoch.reset()
        self.packet_rate = 0.0
        self.last_observed_sequence = None
        self.probe_sent = False

    def _send(self, pcm):
        self.transport.send(encode_audio(self.sequence, time.monotonic_ns(), pcm))
        self.sequence += 1

    def step(self, now=None):
        now = time.monotonic() if now is None else now
        if not self.desired or self.last_heartbeat is None or now - self.last_heartbeat > 3:
            if self.session_id is not None:
                self._close("INTERRUPTED", stop_intent=True)
            self.mode = "off"
            return
        if now < self.retry_after:
            return
        if self.session_id is None:
            if self.command_store is not None and not self.command_store.reconcile(self.uow):
                self.mode = "gateway-wait"
                self.retry_after = now + 1
                return
            if self.session_store is not None and not self.session_store.reconcile(self.uow):
                self.mode = "gateway-wait"
                self.retry_after = now + 1
                return
            try:
                source = self.monitor()
            except (OSError, ValueError, TimeoutError):
                self.mode = "no-monitor"
                self.retry_after = now + 1
                return
            session_id = uuid.uuid4().hex
            if self.session_store is not None:
                try:
                    self.session_store.add(session_id)
                except (OSError, ValueError):
                    self.mode = "state-error"
                    return
            if not self._request("audio.stream.start", {"session_id": session_id, **AUDIO_PROFILE}):
                self.mode = "denied"
                self.retry_after = now + 1
                return
            self.session_id, self.source = session_id, source
            self.rate_start, self.packets = now, 0
            self.last_observation = now
            self.next_preflight = now
            self.probe_sent = False
            self.mode = "preflight"
        elif self.capture is not None:
            try:
                source = self.monitor()
            except (OSError, ValueError, TimeoutError):
                source = None
            if source != self.source:
                self._close("INTERRUPTED", stop_intent=True)
                self.mode = "waiting"
                return
        if not self.probe_sent:
            # Drain stale datagrams over as many loops as needed. A flooded
            # queue must never let capture open before this session sends.
            for _ in range(64):
                if self.transport.receive() is None:
                    self._send(bytes(1024))
                    self.probe_sent = True
                    self.next_preflight = now + 0.1
                    return
            return
        received = self.transport.receive()
        if received is not None:
            telemetry = parse_telemetry(received[0], received[1], self.receiver_epoch)
            if telemetry is not None:
                self.telemetry, self.last_telemetry = telemetry, now
                pending = self.pending_crossover
                if (pending is not None and telemetry.sequence > pending["baseline_sequence"]
                        and abs(telemetry.low_hz - pending["low_hz"]) <= 0.05
                        and abs(telemetry.high_hz - pending["high_hz"]) <= 0.05):
                    self._finish_crossover("REPORTED_MATCH", telemetry.sequence)
        if self.pending_crossover is not None and now >= self.pending_crossover["deadline"]:
            self._finish_crossover("TIMEOUT")
        if self.capture is None:
            if self.telemetry is None:
                if now >= self.next_preflight:
                    self._send(bytes(1024))
                    self.next_preflight = now + 0.1
                if now - self.rate_start > 3:
                    self._close("FAILED_PREFLIGHT")
                    self.mode = "receiver-wait"
                    self.retry_after = now + 1
                return
            try:
                capture = self.capture_factory(self.source)
            except (OSError, ValueError):
                self._close("INTERRUPTED")
                self.mode = "capture-error"
                self.retry_after = now + 1
                return
            if not self._request("audio.effect.record", {"session_id": self.session_id, "outcome": "STARTED"}):
                capture.close()
                self._close("INTERRUPTED")
                self.mode = "denied"
                return
            self.capture = capture
            self.mode = "streaming"
            self.rate_start, self.packets = now, 0
            self.next_send = now
        if now - self.last_telemetry > 3:
            self._close("TELEMETRY_LOST", stop_intent=True)
            self.mode = "receiver-wait"
            self.retry_after = now + 1
            return
        if self.telemetry is not None and self.telemetry.sequence != self.last_observed_sequence and now - self.last_observation >= 1:
            tm = self.telemetry
            if not self._request("audio.telemetry.ingest", {"session_id": self.session_id, "receiver_sequence": tm.sequence, "packet_rate": self.packet_rate, "drops": tm.drops, "underruns": tm.underruns, "crossover_low_hz": tm.low_hz, "crossover_high_hz": tm.high_hz}):
                self._close("INTERRUPTED", stop_intent=True)
                self.mode = "gateway-wait"
                self.retry_after = now + 1
                return
            self.last_observed_sequence = tm.sequence
            self.last_observation = now
        pcm = self.capture.read() if now >= self.next_send else None
        if pcm is not None:
            if len(pcm) != 1024:
                self._close("INTERRUPTED", stop_intent=True)
                self.mode = "capture-error"
                return
            self._send(pcm)
            self.next_send += 256 / 48000
            if self.next_send < now - 256 / 48000:
                self.next_send = now + 256 / 48000
            self.packets += 1
            if now - self.rate_start >= 1:
                self.packet_rate = self.packets / (now - self.rate_start)
                self.rate_start, self.packets = now, 0

    def status(self):
        tm = self.telemetry
        age = max(0, time.monotonic() - self.last_telemetry) if self.last_telemetry is not None else None
        return {"state": self.mode, "source": self.source, "destination": f"{TARGET}:{AUDIO_PORT}", "packet_rate": round(self.packet_rate, 1), "receiver_age_s": round(age, 1) if age is not None else None, "receiver_sequence": tm.sequence if tm else None, "crossover_low_hz": tm.low_hz if tm else None, "crossover_high_hz": tm.high_hz if tm else None, "drops": tm.drops if tm else None, "underruns": tm.underruns if tm else None, "crossover_change": self.crossover_change.copy()}
