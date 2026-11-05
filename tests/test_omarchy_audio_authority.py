import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from integrations.omarchy_uow.service import Service


PROFILE = {"session_id": "s1", "source": "default-output-monitor", "destination": "192.168.254.75:4000", "sample_rate": 48000, "channels": 2, "sample_format": "s16le", "frames_per_packet": 256}


class AudioAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "uow.db"
        self.tokens = {"operator-token": "operator", "worker-token": "audio_worker", "agent-token": "agent"}
        self.policy = {"operator": ["audio.stream.start", "audio.stream.stop"], "audio_worker": ["audio.effect.record", "audio.telemetry.ingest"]}
        self.service = Service(self.db, self.policy, self.tokens)

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def ask(self, rid, kind, payload, token="operator-token"):
        return self.service.handle({"request_id": rid, "token": token, "kind": kind, "payload": payload})

    def test_default_denial_and_fixed_profile(self):
        self.assertEqual(self.ask("a", "audio.stream.start", PROFILE, "agent-token")["reason"], "CAPABILITY_DENIED")
        for i, change in enumerate(({"destination": "127.0.0.1:4000"}, {"source": "microphone"}, {"sample_rate": 44100}, {"extra": True})):
            self.assertEqual(self.ask(f"bad{i}", "audio.stream.start", PROFILE | change)["decision"], "DENIED")
        self.assertEqual(self.ask("cross", "audio.dsp.crossover.set", {"low": 100, "high": 2500})["reason"], "CAPABILITY_DENIED")

    def test_start_outcome_stop_and_restart_do_not_replay_effect(self):
        started = self.ask("start", "audio.stream.start", PROFILE)
        self.assertEqual(started["decision"], "COMMITTED")
        self.assertEqual(self.service.state.get("audio.session.s1")["outcome"], "UNCERTAIN")
        self.assertEqual(self.ask("start", "audio.stream.start", PROFILE), started)
        self.assertEqual(self.ask("outcome", "audio.effect.record", {"session_id": "s1", "outcome": "STARTED"}, "worker-token")["decision"], "COMMITTED")
        self.assertEqual(self.ask("stop", "audio.stream.stop", {"session_id": "s1"})["decision"], "COMMITTED")
        self.assertEqual(self.ask("stopped", "audio.effect.record", {"session_id": "s1", "outcome": "STOPPED"}, "worker-token")["decision"], "COMMITTED")
        state = self.service.state.to_dict()
        self.service.close()
        self.service = Service(self.db, self.policy, self.tokens)
        self.assertEqual(self.service.state.to_dict(), state)
        self.assertTrue(self.service.ledger.verify_integrity())

    def test_worker_only_outcome_and_typed_telemetry(self):
        self.ask("start", "audio.stream.start", PROFILE)
        self.assertEqual(self.ask("wrong", "audio.effect.record", {"session_id": "s1", "outcome": "STARTED"})["decision"], "DENIED")
        self.assertEqual(self.ask("unknown", "audio.effect.record", {"session_id": "s1", "outcome": "BOGUS"}, "worker-token")["decision"], "DENIED")
        sample = {"session_id": "s1", "receiver_sequence": 7, "packet_rate": 187.5, "drops": 0, "underruns": 0, "crossover_low_hz": 100.0, "crossover_high_hz": 2500.0}
        self.assertEqual(self.ask("telemetry", "audio.telemetry.ingest", sample, "worker-token")["decision"], "COMMITTED")
        self.assertEqual(self.service.state.get("audio.telemetry.s1")["trust"], "UNVERIFIED_CLAIM")
        self.assertEqual(self.ask("stale", "audio.telemetry.ingest", sample, "worker-token")["decision"], "DENIED")

    def test_unmodified_journal_does_not_replay_on_each_request(self):
        self.ask("start", "audio.stream.start", PROFILE)
        with patch.object(self.service, "_recover", side_effect=AssertionError("full replay during unchanged request")):
            result = self.ask("stop", "audio.stream.stop", {"session_id": "s1"})
        self.assertEqual(result["decision"], "COMMITTED")

    def test_external_journal_change_is_detected_before_next_request(self):
        self.ask("start", "audio.stream.start", PROFILE)
        with sqlite3.connect(self.db) as db:
            db.execute("update journal set entry_hash=? where n=1", ("0" * 64,))
        with self.assertRaises(ValueError):
            self.ask("stop", "audio.stream.stop", {"session_id": "s1"})

    def test_other_service_writer_is_seen_before_next_request(self):
        other = Service(self.db, self.policy, self.tokens)
        try:
            self.ask("start", "audio.stream.start", PROFILE)
            result = other.handle({"request_id": "stop-other", "token": "operator-token", "kind": "audio.stream.stop", "payload": {"session_id": "s1"}})
            self.assertEqual(result["decision"], "COMMITTED")
            self.assertEqual(self.service.handle({"request_id": "outcome-self", "token": "worker-token", "kind": "audio.effect.record", "payload": {"session_id": "s1", "outcome": "STOPPED"}})["decision"], "COMMITTED")
        finally:
            other.close()


if __name__ == "__main__":
    unittest.main()
