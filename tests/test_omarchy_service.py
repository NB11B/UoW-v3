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
    def test_celsius_observation_summary(self):
        obs = copy.deepcopy(OBS)
        obs["reading"] = {"value": 51.25, "unit": "C"}
        self.assertEqual(self.s.handle(self.req(payload=obs))["decision"], "COMMITTED")
        result = self.s.handle(self.req("r2", "operator-secret", "observation.summarize", {"observation_id": "o1"}))
        self.assertEqual(result["decision"], "COMMITTED")
        self.assertEqual(self.s.state.get("summary")["unit"], "C")
        obs = copy.deepcopy(OBS); obs["sensor_id"] = "\ud800"
        self.assertEqual(self.s.handle(self.req(payload=obs))["decision"], "DENIED")

if __name__ == "__main__":
    unittest.main(verbosity=2)
