import struct
import unittest

from integrations.omarchy_uow.audio_worker import AudioWorker


def tm(seq, low=100.0, high=2500.0):
    b = bytearray(184)
    struct.pack_into("<IHHII", b, 0, 0x4D544352, 1, 184, seq, 100)
    struct.pack_into("<ff", b, 44, low, high)
    return bytes(b)


class FakeCapture:
    def __init__(self):
        self.closed = False
        self.frames = [bytes(1024)]
    def read(self):
        return self.frames.pop(0) if self.frames else None
    def close(self):
        self.closed = True


class FakeTransport:
    def __init__(self):
        self.sent = []
        self.received = []
        self.controls = []
    def send(self, data):
        self.sent.append(data)
    def receive(self):
        return self.received.pop(0) if self.received else None
    def send_control(self, data):
        self.controls.append(data)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.monitor = "speaker.monitor"
        self.capture = []
        self.transport = FakeTransport()
        self.requests = []
        def uow(kind, payload):
            self.requests.append((kind, payload))
            return {"decision": "COMMITTED", "receipt": {"id": len(self.requests)}}
        self.worker = AudioWorker(lambda: self.monitor, lambda name: self.open_capture(name), self.transport, uow)
    def open_capture(self, name):
        self.assertEqual(name, self.monitor)
        c = FakeCapture(); self.capture.append(c); return c
    def preflight(self):
        self.worker.heartbeat(0)
        self.worker.step(0)
        self.assertEqual(len(self.capture), 0)
        self.transport.received.append((tm(1), ("192.168.254.75", 4002)))
        self.worker.step(0.1)
        self.assertEqual(self.worker.status()["state"], "streaming")

    def test_never_capture_without_receipt_and_receiver(self):
        self.worker.heartbeat(0)
        self.worker.step(0)
        self.assertEqual(self.requests[0][0], "audio.stream.start")
        self.assertEqual(len(self.capture), 0)
        self.assertTrue(self.transport.sent)
        self.preflight()
        self.worker.step(0.2)
        self.assertGreater(len(self.transport.sent), 1)
        self.assertEqual(self.requests[-1][0], "audio.effect.record")

    def test_silent_preflight_is_bounded(self):
        self.worker.heartbeat(0)
        self.worker.step(0)
        self.assertEqual(len(self.transport.sent), 1)
        self.worker.step(0.001)
        self.assertEqual(len(self.transport.sent), 1)
        self.worker.step(0.1)
        self.assertEqual(len(self.transport.sent), 2)

    def test_queued_telemetry_cannot_skip_silent_preflight(self):
        self.transport.received.append((tm(1), ("192.168.254.75", 54321)))
        self.worker.heartbeat(0)
        self.worker.step(0)
        self.assertEqual(len(self.capture), 0)
        self.assertEqual(len(self.transport.sent), 1)
        self.assertEqual(self.worker.status()["state"], "preflight")
        self.transport.received.append((tm(2), ("192.168.254.75", 54321)))
        self.worker.step(0.1)
        self.assertEqual(len(self.capture), 1)

    def test_flooded_queue_cannot_bypass_silence_gate(self):
        self.transport.received.extend((tm(i), ("192.168.254.75", 54321)) for i in range(65))
        self.worker.heartbeat(0)
        self.worker.step(0)
        self.worker.step(0.01)
        self.assertEqual(len(self.capture), 0)
        self.assertGreaterEqual(len(self.transport.sent), 1)

    def test_off_stops_even_when_uow_unavailable(self):
        self.preflight()
        self.worker.uow = lambda *args: (_ for _ in ()).throw(ConnectionError())
        self.worker.off()
        self.assertTrue(self.capture[0].closed)
        self.assertEqual(self.worker.status()["state"], "off")

    def test_gateway_loss_during_stream_closes_capture(self):
        self.preflight()
        self.capture[0].frames = [bytes(1024)]
        self.transport.received.append((tm(2), ("192.168.254.75", 54321)))
        self.worker.uow = lambda *args: (_ for _ in ()).throw(ConnectionError())
        before = len(self.transport.sent)
        self.worker.heartbeat(1.2)
        self.worker.step(1.2)
        self.assertTrue(self.capture[0].closed)
        self.assertNotEqual(self.worker.status()["state"], "streaming")
        self.assertEqual(len(self.transport.sent), before)

    def test_stale_telemetry_and_heartbeat_stop_capture(self):
        self.preflight()
        self.worker.step(3.2)
        self.assertTrue(self.capture[0].closed)
        self.assertNotEqual(self.worker.status()["state"], "streaming")
        self.worker.step(4.0)
        self.assertEqual(self.worker.status()["state"], "off")

    def test_default_sink_switch_closes_old_capture(self):
        self.preflight()
        self.monitor = "headphones.monitor"
        self.worker.heartbeat(0.2)
        self.worker.step(0.2)
        self.assertTrue(self.capture[0].closed)
        self.assertNotEqual(self.worker.status()["state"], "streaming")

    def test_denied_start_fails_closed(self):
        self.worker.uow = lambda *args: {"decision": "DENIED"}
        self.worker.heartbeat(0)
        self.worker.step(0)
        self.assertEqual(self.worker.status()["state"], "denied")
        self.assertEqual(self.transport.sent, [])

    def test_receiver_observation_is_typed_and_bounded(self):
        self.preflight()
        self.worker.heartbeat(1.2)
        self.transport.received.append((tm(2), ("192.168.254.75", 4002)))
        self.worker.step(1.2)
        observations = [payload for kind, payload in self.requests if kind == "audio.telemetry.ingest"]
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["receiver_sequence"], 2)
        self.assertEqual(observations[0]["crossover_high_hz"], 2500.0)
        self.worker.heartbeat(2.2)
        self.worker.step(2.2)
        self.assertEqual(len([1 for kind, _ in self.requests if kind == "audio.telemetry.ingest"]), 1)

    def test_packets_are_paced_to_audio_frame_clock(self):
        self.preflight()
        self.capture[0].frames = [bytes(1024), bytes(1024)]
        count = len(self.transport.sent)
        self.worker.step(0.107)
        self.assertEqual(len(self.transport.sent), count + 1)
        self.worker.step(0.108)
        self.assertEqual(len(self.transport.sent), count + 1)
        self.worker.step(0.113)
        self.assertEqual(len(self.transport.sent), count + 2)

    def test_crossover_requires_authority_before_udp(self):
        self.preflight()
        self.worker.uow = lambda kind, payload: {"decision": "DENIED"}
        self.assertEqual(self.worker.set_crossover(100, 2500, 0.2)["state"], "denied")
        self.assertEqual(self.transport.controls, [])

    def test_crossover_confirms_only_newer_matching_telemetry(self):
        self.preflight()
        result = self.worker.set_crossover(120, 2200, 0.2)
        self.assertEqual(result["state"], "pending")
        self.assertEqual(self.transport.controls, [b"SET_CROSS_LOW:120.000\nSET_CROSS_HIGH:2200.000\n"])
        self.transport.received.append((tm(1), ("192.168.254.75", 4002)))
        self.worker.step(0.3)
        self.assertEqual(self.worker.status()["crossover_change"]["state"], "pending")
        self.transport.received.append((tm(2), ("192.168.254.75", 4002)))
        self.worker.step(0.4)
        self.assertEqual(self.worker.status()["crossover_change"]["state"], "pending")
        self.transport.received.append((tm(3, 120, 2200), ("192.168.254.75", 4002)))
        self.worker.step(0.5)
        self.assertEqual(self.worker.status(now=0.5)["crossover_change"]["state"], "receiver-reported")
        self.assertEqual(self.requests[-1][0], "audio.dsp.crossover.effect")
        self.assertEqual(self.requests[-1][1]["receiver_sequence"], 3)

    def test_queued_or_late_matching_telemetry_does_not_confirm(self):
        self.preflight()
        self.transport.received.append((tm(2, 120, 2200), ("192.168.254.75", 4002)))
        self.worker.set_crossover(120, 2200, 0.2)
        self.worker.step(0.3)
        self.assertEqual(self.worker.status()["crossover_change"]["state"], "pending")
        self.transport.received.append((tm(3, 120, 2200), ("192.168.254.75", 4002)))
        self.worker.heartbeat(2.3)
        self.worker.step(2.3)
        self.assertEqual(self.worker.status()["crossover_change"]["state"], "unconfirmed")

    def test_journal_uses_wire_rounded_crossover_values(self):
        self.preflight()
        self.worker.set_crossover(100.0004, 2500.0004, 0.2)
        payload = [p for kind, p in self.requests if kind == "audio.dsp.crossover.set"][-1]
        self.assertEqual((payload["low_hz"], payload["high_hz"]), (100.0, 2500.0))

    def test_crossover_timeout_and_stream_interruption(self):
        self.preflight()
        self.worker.set_crossover(120, 2200, 0.2)
        self.worker.heartbeat(2.3)
        self.worker.step(2.3)
        self.assertEqual(self.worker.status()["crossover_change"]["state"], "unconfirmed")
        self.assertEqual([p for k, p in self.requests if k == "audio.dsp.crossover.effect"][-1]["outcome"], "TIMEOUT")
        self.worker.set_crossover(130, 2300, 2.4)
        self.worker.off()
        self.assertEqual(self.worker.status()["crossover_change"]["state"], "interrupted")
        self.assertEqual([p for k, p in self.requests if k == "audio.dsp.crossover.effect"][-1]["outcome"], "INTERRUPTED")

    def test_off_closes_capture_before_recording_interrupted_crossover(self):
        self.preflight()
        self.worker.set_crossover(120, 2200, 0.2)
        original = self.worker.uow
        def uow(kind, payload):
            if kind == "audio.dsp.crossover.effect":
                self.assertTrue(self.capture[0].closed)
            return original(kind, payload)
        self.worker.uow = uow
        self.worker.off()


if __name__ == "__main__":
    unittest.main()
