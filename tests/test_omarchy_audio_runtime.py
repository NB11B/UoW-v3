import pathlib
import socket
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import uuid

from integrations.omarchy_uow.audio_runtime import ParecCapture, PendingSessions, PendingCommands, SocketUoW, dispatch_control, load_preference, save_preference, read_control, serve_connection
from integrations.omarchy_uow.audio_worker import AudioWorker
from integrations.omarchy_uow.gateway import Gateway
from integrations.omarchy_uow.service import AUDIO_PROFILE, Service


class RuntimeTests(unittest.TestCase):
    def test_control_waits_for_complete_line_and_rejects_trailing_data(self):
        left, right = socket.socketpair()
        try:
            left.settimeout(0.05)
            right.sendall(b"crossover 100 2500")
            with self.assertRaises(socket.timeout):
                read_control(left)
            right.sendall(b"\nextra")
            with self.assertRaises(ValueError):
                read_control(left)
        finally:
            left.close(); right.close()

    def test_disconnected_control_client_does_not_stop_worker(self):
        left, right = socket.socketpair()
        worker = Mock()
        worker.status.return_value = {"state": "streaming"}
        worker.desired = True
        try:
            right.sendall(b"status\n")
            right.close()
            serve_connection(left, worker, pathlib.Path("/unused"))
            worker.off.assert_not_called()
        finally:
            left.close()
    def test_crossover_control_parser_rejects_malformed_input(self):
        with tempfile.TemporaryDirectory() as td:
            worker = Mock()
            worker.status.return_value = {"state": "streaming", "crossover_change": {"state": "idle"}}
            worker.set_crossover.return_value = {"state": "pending"}
            preference = pathlib.Path(td) / "enabled.json"
            self.assertEqual(dispatch_control("crossover 120 2200", worker, preference)["state"], "pending")
            worker.set_crossover.assert_called_once_with(120.0, 2200.0)
            for command in ("crossover NaN 2200", "crossover 2200 120", "crossover 120", "crossover 120 2200 extra", "x" * 129):
                with self.assertRaises(ValueError):
                    dispatch_control(command, worker, preference)
            self.assertEqual(worker.set_crossover.call_count, 1)

    def test_pending_command_reconciles_without_resending(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            store = PendingCommands(root / "commands.json")
            service = Service(root / "uow.db", {"operator": ["audio.stream.start", "audio.dsp.crossover.set"],
                                                  "audio_worker": ["audio.dsp.crossover.effect"]},
                              {"operator-token": "operator", "worker-token": "audio_worker"})
            def uow(kind, payload):
                token = "worker-token" if kind == "audio.dsp.crossover.effect" else "operator-token"
                return service.handle({"request_id": SocketUoW.request_id(kind, payload), "token": token,
                                       "kind": kind, "payload": payload})
            self.assertEqual(uow("audio.stream.start", {"session_id": "s1", **AUDIO_PROFILE})["decision"], "COMMITTED")
            self.assertEqual(uow("audio.dsp.crossover.set", {"command_id": "cmd1", "session_id": "s1", "low_hz": 120, "high_hz": 2200})["decision"], "COMMITTED")
            store.add("cmd1")
            self.assertTrue(store.reconcile(uow))
            self.assertEqual(store.pending(), [])
            self.assertEqual(service.state.get("audio.crossover.cmd1")["outcome"], "INTERRUPTED")
            service.close()
    def test_restart_reconciles_unfinished_session_before_new_start(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            store = PendingSessions(root / "sessions.json")
            service = Service(root / "uow.db", {"operator": ["audio.stream.start", "audio.stream.stop"], "audio_worker": ["audio.effect.record"]}, {"operator-token": "operator", "worker-token": "audio_worker"})
            def uow(kind, payload):
                token = "worker-token" if kind == "audio.effect.record" else "operator-token"
                return service.handle({"request_id": uuid.uuid4().hex, "token": token, "kind": kind, "payload": payload})
            class Transport:
                def __init__(self): self.received = []
                def send(self, packet): pass
                def receive(self): return self.received.pop(0) if self.received else None
            net = Transport()
            first = AudioWorker(lambda: "speaker.monitor", lambda _: Mock(read=lambda: None), net, uow, store)
            first.heartbeat(0); first.step(0)
            old_session = first.session_id
            self.assertIn(old_session, store.pending())
            second = AudioWorker(lambda: "speaker.monitor", lambda _: Mock(read=lambda: None), Transport(), uow, store)
            second.heartbeat(1); second.step(1)
            self.assertEqual(service.state.get("audio.session." + old_session)["outcome"], "INTERRUPTED")
            self.assertNotIn(old_session, store.pending())
            service.close()

    def test_lost_reconciliation_response_reuses_receipts(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            service = Service(root / "uow.db", {"operator": ["audio.stream.start", "audio.stream.stop"], "audio_worker": ["audio.effect.record"]}, {"operator-token": "operator", "worker-token": "audio_worker"})
            store = PendingSessions(root / "sessions.json")
            store.add("s1")
            lost = [True]
            def uow(kind, payload):
                token = "worker-token" if kind == "audio.effect.record" else "operator-token"
                response = service.handle({"request_id": SocketUoW.request_id(kind, payload), "token": token, "kind": kind, "payload": payload})
                if kind == "audio.effect.record" and lost[0]:
                    lost[0] = False
                    raise ConnectionError("response lost after commit")
                return response
            uow("audio.stream.start", {"session_id": "s1", **AUDIO_PROFILE})
            self.assertFalse(store.reconcile(uow))
            self.assertEqual(store.pending(), ["s1"])
            self.assertTrue(store.reconcile(uow))
            self.assertEqual(store.pending(), [])
            self.assertEqual(sqlite3.connect(root / "uow.db").execute("select count(*) from journal").fetchone()[0], 3)
            service.close()

    def test_capture_never_accumulates_unbounded_audio(self):
        capture = ParecCapture.__new__(ParecCapture)
        capture.process = Mock()
        capture.process.poll.return_value = None
        capture.process.stdout.fileno.return_value = 1
        capture.buffer = bytearray()
        with patch("integrations.omarchy_uow.audio_runtime.os.read", return_value=b"x" * 32768):
            self.assertEqual(len(capture.read()), 1024)
        self.assertLessEqual(len(capture.buffer), 8192)

    def test_capture_drains_existing_frames_before_reading_more(self):
        capture = ParecCapture.__new__(ParecCapture)
        capture.process = Mock()
        capture.process.poll.return_value = None
        capture.process.stdout.fileno.return_value = 1
        capture.buffer = bytearray(b"a" * 8192)
        with patch("integrations.omarchy_uow.audio_runtime.os.read", return_value=b"b" * 8192) as reader:
            self.assertEqual(capture.read(), b"a" * 1024)
        reader.assert_not_called()
        self.assertEqual(len(capture.buffer), 7168)

    def test_gateway_client_and_persisted_off_preference(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            gateway = Gateway(root / "gateway.sock", root / "uow.db", {"operator": ["audio.stream.start"], "audio_worker": ["audio.effect.record"]}, {"operator-token": "operator", "worker-token": "audio_worker"})
            thread = threading.Thread(target=gateway.serve_forever, daemon=True)
            thread.start()
            client = SocketUoW(root / "gateway.sock", "operator-token", "worker-token")
            result = client("audio.stream.start", {"session_id": "s1", **AUDIO_PROFILE})
            self.assertEqual(result["decision"], "COMMITTED")
            self.assertIsNotNone(result["receipt"])
            pref = root / "enabled.json"
            self.assertTrue(load_preference(pref))
            save_preference(pref, False)
            self.assertFalse(load_preference(pref))
            gateway.shutdown(); gateway.server_close(); thread.join(timeout=2)

    def test_gateway_client_reuses_request_id_for_session_phase_retry(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            gateway = Gateway(root / "gateway.sock", root / "uow.db", {"operator": ["audio.stream.start", "audio.stream.stop"]}, {"operator-token": "operator"})
            thread = threading.Thread(target=gateway.serve_forever, daemon=True)
            thread.start()
            try:
                client = SocketUoW(root / "gateway.sock", "operator-token", "worker-token")
                client("audio.stream.start", {"session_id": "s1", **AUDIO_PROFILE})
                first = client("audio.stream.stop", {"session_id": "s1"})
                self.assertEqual(client("audio.stream.stop", {"session_id": "s1"}), first)
                self.assertEqual(sqlite3.connect(root / "uow.db").execute("select count(*) from journal").fetchone()[0], 2)
            finally:
                gateway.shutdown(); gateway.server_close(); thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
