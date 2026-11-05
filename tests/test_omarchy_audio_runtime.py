import pathlib
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from integrations.omarchy_uow.audio_runtime import ParecCapture, SocketUoW, load_preference, save_preference
from integrations.omarchy_uow.gateway import Gateway
from integrations.omarchy_uow.service import AUDIO_PROFILE


class RuntimeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
