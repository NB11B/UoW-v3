import copy
import json
import pathlib
import sqlite3
import tempfile
import unittest
from integrations.omarchy_uow.service import Service

OBS = {"observation_id": "o1", "sensor_id": "sim-soil", "sensor_type": "ENVIRONMENTAL_PROBE", "causal_epoch": 1, "modality": "NUMERIC_GAUGE", "reading": {"value": 23, "unit": "percent"}, "confidence": 0.8}
TOKENS = {"sensor-secret": "sensor", "operator-secret": "operator"}
POLICY = {"sensor": ["observation.ingest"], "operator": ["observation.summarize"]}

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "state.db"
        self.s = Service(self.db, POLICY, TOKENS)
    def tearDown(self):
        self.s.close()
        self.tmp.cleanup()
    def req(self, rid="r1", token="sensor-secret", kind="observation.ingest", payload=None):
        return {"request_id": rid, "token": token, "kind": kind, "payload": copy.deepcopy(OBS if payload is None else payload)}
    def test_default_denial(self):
        self.s.close()
        self.s = Service(self.db, {}, TOKENS)
        self.assertEqual(self.s.handle(self.req())["decision"], "DENIED")
        self.assertEqual(self.s.state.sequence, 0)
    def test_credentials_and_unknown_capability(self):
        for i, token in enumerate(["", "operator", "wrong"]):
            self.assertEqual(self.s.handle(self.req(str(i), token))["decision"], "DENIED")
        self.assertEqual(self.s.handle(self.req("unknown", kind="shell.execute"))["decision"], "DENIED")
    def test_observation_then_summary_and_receipts(self):
        result = self.s.handle(self.req())
        self.assertEqual(result["decision"], "COMMITTED")
        self.assertNotIn("summary", self.s.state.attributes)
        summary = self.s.handle(self.req("r2", "operator-secret", "observation.summarize", {"observation_id": "o1"}))
        self.assertEqual(summary["decision"], "COMMITTED")
        self.assertEqual(self.s.state.get("summary")["value"], 23)
        self.assertTrue(self.s.ledger.verify_integrity())
        self.assertEqual(len(self.s.ledger.records), 2)
        self.assertEqual(summary["receipt"]["pre_state_hash"], result["receipt"]["post_state_hash"])
        self.assertNotIn("secret", self.db.read_bytes().decode(errors="ignore"))
    def test_injection_rejected(self):
        for i, field in enumerate(["authority", "mutations", "principal", "capabilities"]):
            obs = copy.deepcopy(OBS); obs[field] = "operator"
            self.assertEqual(self.s.handle(self.req(str(i), payload=obs))["decision"], "DENIED")
        self.assertEqual(self.s.state.sequence, 0)
    def test_invalid_observations_and_stale_epoch(self):
        for i, value in enumerate([True, float("nan"), float("inf"), "23"]):
            obs = copy.deepcopy(OBS); obs["reading"]["value"] = value
            self.assertEqual(self.s.handle(self.req(str(i), payload=obs))["decision"], "DENIED")
        self.s.handle(self.req())
        obs = copy.deepcopy(OBS); obs["observation_id"] = "o2"
        self.assertEqual(self.s.handle(self.req("stale", payload=obs))["decision"], "DENIED")
    def test_sensor_cannot_summarize_or_self_authorize(self):
        self.s.handle(self.req())
        req = self.req("r2", kind="observation.summarize", payload={"observation_id": "o1"})
        req["principal"] = "operator"
        self.assertEqual(self.s.handle(req)["decision"], "DENIED")
        self.assertEqual(self.s.state.sequence, 1)
    def test_duplicate_and_conflict(self):
        first = self.s.handle(self.req())
        self.assertEqual(self.s.handle(self.req()), first)
        obs = copy.deepcopy(OBS); obs["reading"]["value"] = 24
        self.assertEqual(self.s.handle(self.req(payload=obs))["reason"], "REQUEST_ID_CONFLICT")
        self.assertEqual(self.s.state.sequence, 1)
    def test_restart_and_revocation(self):
        first = self.s.handle(self.req()); state_hash = self.s.state.state_hash
        self.s.close(); self.s = Service(self.db, POLICY, TOKENS)
        self.assertEqual(self.s.state.state_hash, state_hash)
        self.assertEqual(self.s.handle(self.req()), first)
        self.s.close(); self.s = Service(self.db, {}, TOKENS)
        self.assertEqual(self.s.handle(self.req())["decision"], "DENIED")
    def test_receipt_corruption_fails_closed(self):
        self.s.handle(self.req()); self.s.close()
        with sqlite3.connect(self.db) as db:
            data = json.loads(db.execute("select response from journal").fetchone()[0])
            data["receipt"]["post_state_hash"] = "0" * 64
            db.execute("update journal set response=?", (json.dumps(data),))
        with self.assertRaises(ValueError):
            Service(self.db, POLICY, TOKENS)
    def test_forged_proposal_denied_by_upstream(self):
        from dataclasses import replace
        from uow.engine import propose, certify
        u = self.s.contract("observation.ingest", OBS, self.s.state)
        proposal = propose(u, self.s.state)
        forged = replace(proposal, proposed_state=proposal.proposed_state.with_attribute("authority", "admin"))
        self.assertFalse(certify(u, self.s.state, forged).is_valid)
    def test_hostile_numeric_and_unicode_input(self):
        self.assertEqual(self.s.handle(self.req(token="\ud800"))["decision"], "DENIED")
        obs = copy.deepcopy(OBS); obs["reading"]["value"] = 10**400
        self.assertEqual(self.s.handle(self.req(payload=obs))["decision"], "DENIED")
        obs = copy.deepcopy(OBS); obs["sensor_id"] = "\ud800"
        self.assertEqual(self.s.handle(self.req(payload=obs))["decision"], "DENIED")
        obs = copy.deepcopy(OBS); obs["extra"] = "\ud800"
        self.assertEqual(self.s.handle(self.req("extra", payload=obs))["decision"], "DENIED")
    def test_celsius_observation_summary(self):
        obs = copy.deepcopy(OBS)
        obs["reading"] = {"value": 51.25, "unit": "C"}
        self.assertEqual(self.s.handle(self.req(payload=obs))["decision"], "COMMITTED")
        result = self.s.handle(self.req("r2", "operator-secret", "observation.summarize", {"observation_id": "o1"}))
        self.assertEqual(result["decision"], "COMMITTED")
        self.assertEqual(self.s.state.get("summary")["unit"], "C")


class CrossoverServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = pathlib.Path(self.tmp.name) / "state.db"
        self.policy = {"operator": ["audio.stream.start", "audio.dsp.crossover.set"],
                       "audio_worker": ["audio.dsp.crossover.effect"]}
        self.tokens = {"operator-token": "operator", "worker-token": "audio_worker"}
        self.s = Service(self.db, self.policy, self.tokens)
        from integrations.omarchy_uow.service import AUDIO_PROFILE
        start = self.request("start", "operator-token", "audio.stream.start", {"session_id": "s1", **AUDIO_PROFILE})
        self.assertEqual(self.s.handle(start)["decision"], "COMMITTED")

    def tearDown(self):
        self.s.close()
        self.tmp.cleanup()

    @staticmethod
    def request(rid, token, kind, payload):
        return {"request_id": rid, "token": token, "kind": kind, "payload": payload}

    def intent(self, rid="cross-1", payload=None):
        return self.request(rid, "operator-token", "audio.dsp.crossover.set",
                            {"command_id": "cmd1", "session_id": "s1", "low_hz": 100.0, "high_hz": 2500.0} if payload is None else payload)

    def effect(self, rid="effect-1", outcome="REPORTED_MATCH", sequence=4):
        return self.request(rid, "worker-token", "audio.dsp.crossover.effect",
                            {"command_id": "cmd1", "outcome": outcome, "receiver_sequence": sequence})

    def test_intent_receipt_then_reported_match_replays(self):
        intent = self.s.handle(self.intent())
        self.assertEqual(intent["decision"], "COMMITTED")
        self.assertEqual(self.s.state.get("audio.crossover.cmd1")["outcome"], "UNCERTAIN")
        self.assertEqual(self.s.handle(self.effect())["decision"], "COMMITTED")
        self.assertEqual(self.s.state.get("audio.crossover.cmd1")["receiver_sequence"], 4)
        self.assertTrue(self.s.ledger.verify_integrity())
        state_hash = self.s.state.state_hash
        self.s.close(); self.s = Service(self.db, self.policy, self.tokens)
        self.assertEqual(self.s.state.state_hash, state_hash)
        self.assertEqual(self.s.handle(self.intent()), intent)

    def test_denial_and_invalid_pairs_never_create_intent(self):
        self.s.policy = {}
        self.assertEqual(self.s.handle(self.intent())["decision"], "DENIED")
        self.s.policy = self.policy
        base = self.intent()["payload"]
        for n, pair in enumerate([(0, 2500), (2500, 100), (100, 24000), (float("nan"), 2500),
                                  (True, 2500), (100, float("inf")), ("100", 2500), (10**400, 2500)]):
            payload = {**base, "low_hz": pair[0], "high_hz": pair[1]}
            self.assertEqual(self.s.handle(self.intent(f"bad-{n}", payload))["decision"], "DENIED")
        self.assertEqual(self.s.handle(self.intent("missing", {**base, "session_id": "other"}))["decision"], "DENIED")
        self.assertIsNone(self.s.state.get("audio.crossover.cmd1"))

    def test_duplicate_command_and_outcome_order(self):
        self.assertEqual(self.s.handle(self.effect())["decision"], "DENIED")
        self.assertEqual(self.s.handle(self.intent())["decision"], "COMMITTED")
        self.assertEqual(self.s.handle(self.intent("cross-2"))["decision"], "DENIED")
        self.assertEqual(self.s.handle(self.effect("wrong-token", sequence=5) | {"token": "operator-token"})["decision"], "DENIED")
        self.assertEqual(self.s.handle(self.effect("bad-timeout", "TIMEOUT", 3))["decision"], "DENIED")
        self.assertEqual(self.s.handle(self.effect("timeout", "TIMEOUT", None))["decision"], "COMMITTED")
        self.assertEqual(self.s.handle(self.effect("late-match"))["decision"], "DENIED")

if __name__ == "__main__":
    unittest.main(verbosity=2)
