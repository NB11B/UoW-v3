"""Bounded audio worker core; the widget owns its short heartbeat lease."""
from __future__ import annotations

import time
import uuid

from .audio_protocol import AUDIO_PORT, TARGET, ReceiverEpoch, default_monitor, encode_audio, parse_telemetry
from .service import AUDIO_PROFILE


class AudioWorker:
    def __init__(self, monitor=default_monitor, capture=None, transport=None, uow=None):
        self.monitor, self.capture_factory, self.transport, self.uow = monitor, capture, transport, uow
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
        self.mode = "waiting"
        self.retry_after = 0.0
        self.last_observation = None
        self.last_observed_sequence = None

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

    def _close(self, outcome, stop_intent=False):
        if self.capture is not None:
            self.capture.close()
            self.capture = None
        if self.session_id is not None:
            if stop_intent:
                self._request("audio.stream.stop", {"session_id": self.session_id})
            self._request("audio.effect.record", {"session_id": self.session_id, "outcome": outcome})
        self.session_id = None
        self.source = None
        self.telemetry = None
        self.last_telemetry = None
        self.receiver_epoch.reset()
        self.packet_rate = 0.0
        self.last_observed_sequence = None

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
            try:
                source = self.monitor()
            except (OSError, ValueError, TimeoutError):
                self.mode = "no-monitor"
                self.retry_after = now + 1
                return
            session_id = uuid.uuid4().hex
            if not self._request("audio.stream.start", {"session_id": session_id, **AUDIO_PROFILE}):
                self.mode = "denied"
                self.retry_after = now + 1
                return
            self.session_id, self.source = session_id, source
            self.rate_start, self.packets = now, 0
            self.last_observation = now
            self.next_preflight = now
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
        received = self.transport.receive()
        if received is not None:
            telemetry = parse_telemetry(received[0], received[1], self.receiver_epoch)
            if telemetry is not None:
                self.telemetry, self.last_telemetry = telemetry, now
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
        if self.telemetry is not None and self.telemetry.sequence != self.last_observed_sequence and now - self.last_observation >= 1:
            tm = self.telemetry
            if self._request("audio.telemetry.ingest", {"session_id": self.session_id, "receiver_sequence": tm.sequence, "packet_rate": self.packet_rate, "drops": tm.drops, "underruns": tm.underruns, "crossover_low_hz": tm.low_hz, "crossover_high_hz": tm.high_hz}):
                self.last_observed_sequence = tm.sequence
            self.last_observation = now

    def status(self):
        tm = self.telemetry
        age = max(0, time.monotonic() - self.last_telemetry) if self.last_telemetry is not None else None
        return {"state": self.mode, "source": self.source, "destination": f"{TARGET}:{AUDIO_PORT}", "packet_rate": round(self.packet_rate, 1), "receiver_age_s": round(age, 1) if age is not None else None, "receiver_sequence": tm.sequence if tm else None, "crossover_low_hz": tm.low_hz if tm else None, "crossover_high_hz": tm.high_hz if tm else None, "drops": tm.drops if tm else None, "underruns": tm.underruns if tm else None}
