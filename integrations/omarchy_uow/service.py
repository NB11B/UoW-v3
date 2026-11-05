"""Bounded JSON-lines UoW integration. No shell, network or actuator capability."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import hmac
import json
import math
from pathlib import Path
import re
import sqlite3
import sys

from uow import WorldState
from uow.contracts import Guard, GuardOp, Mutation, MutationOp, Route, Successor, make_uow
from uow.engine import EvidenceLedger, propose, certify, commit
from uow.state import canonical_json

ID = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
KINDS = {"observation.ingest", "observation.summarize"}

def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()

def valid_id(value):
    return isinstance(value, str) and ID.fullmatch(value) is not None

def validate_observation(obs):
    fields = {"observation_id", "sensor_id", "sensor_type", "causal_epoch", "modality", "reading", "confidence"}
    if not isinstance(obs, dict) or set(obs) != fields:
        raise ValueError("OBSERVATION_SCHEMA")
    if not valid_id(obs["observation_id"]) or not valid_id(obs["sensor_id"]):
        raise ValueError("OBSERVATION_ID")
    if obs["sensor_type"] != "ENVIRONMENTAL_PROBE" or obs["modality"] != "NUMERIC_GAUGE":
        raise ValueError("UNSUPPORTED_SENSOR_PROFILE")
    if type(obs["causal_epoch"]) is not int or obs["causal_epoch"] < 0:
        raise ValueError("EPOCH")
    reading = obs["reading"]
    if not isinstance(reading, dict) or set(reading) != {"value", "unit"} or reading["unit"] not in {"percent", "C"}:
        raise ValueError("READING_SCHEMA")
    lower, upper = (0, 100) if reading["unit"] == "percent" else (-40, 125)
    for value, lower, upper in [(reading["value"], lower, upper), (obs["confidence"], 0, 1)]:
        if type(value) not in (int, float) or not lower <= value <= upper or not math.isfinite(value):
            raise ValueError("READING_RANGE")

class Service:
    def __init__(self, db, policy, tokens):
        if not isinstance(policy, dict) or not isinstance(tokens, dict):
            raise ValueError("CONFIG_SCHEMA")
        if any(not isinstance(k, str) or not k or not isinstance(v, str) or not v for k, v in tokens.items()):
            raise ValueError("TOKEN_CONFIG")
        if any(not isinstance(v, list) or any(c not in KINDS for c in v) for v in policy.values()):
            raise ValueError("POLICY_CONFIG")
        self.policy, self.tokens = policy, tokens
        self.db = sqlite3.connect(db, isolation_level=None)
        try:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("CREATE TABLE IF NOT EXISTS journal (n INTEGER PRIMARY KEY, request_id TEXT UNIQUE, request TEXT, response TEXT, prev_hash TEXT, entry_hash TEXT)")
            self._recover()
        except Exception:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    @staticmethod
    def contract(kind, payload, state):
        if kind == "observation.ingest":
            validate_observation(payload)
            key = "obs." + payload["observation_id"]
            epoch_key = "epoch." + payload["sensor_id"]
            if payload["causal_epoch"] <= state.get(epoch_key, -1):
                raise ValueError("STALE_EPOCH")
            guard = Guard(GuardOp.NOT_EXISTS, key)
            mutations = (Mutation(MutationOp.SET, key, {**payload, "trust": "UNVERIFIED_CLAIM"}),
                         Mutation(MutationOp.SET, epoch_key, payload["causal_epoch"]))
        elif kind == "observation.summarize":
            if not isinstance(payload, dict) or set(payload) != {"observation_id"} or not valid_id(payload["observation_id"]):
                raise ValueError("SUMMARY_SCHEMA")
            key = "obs." + payload["observation_id"]
            obs = state.get(key)
            if obs is None:
                raise ValueError("OBSERVATION_MISSING")
            guard = Guard(GuardOp.EXISTS, key)
            mutations = (Mutation(MutationOp.SET, "summary", {"observation_id": payload["observation_id"], "value": obs["reading"]["value"], "unit": obs["reading"]["unit"], "trust": "UNVERIFIED_CLAIM"}),)
        else:
            raise ValueError("UNKNOWN_CAPABILITY")
        return make_uow(kind, [Route(guard, mutations, Successor.preserve())])

    def _transition(self, req):
        u = self.contract(req["kind"], req["payload"], self.state)
        p = propose(u, self.state)
        c = certify(u, self.state, p)
        state, evidence = commit(u, self.state, p, c, prev_evidence_hash=self.ledger.root_hash(), step_number=len(self.ledger.records) + 1)
        return state, evidence

    def _recover(self):
        self.state, self.ledger, self.root = WorldState(), EvidenceLedger(), "0" * 64
        for expected_n, row in enumerate(self.db.execute("SELECT n, request, response, prev_hash, entry_hash FROM journal ORDER BY n"), 1):
            n, raw_req, raw_res, prev, entry_hash = row
            req, res = json.loads(raw_req), json.loads(raw_res)
            if n != expected_n or prev != self.root or digest({"n": n, "request": req, "response": res, "prev_hash": prev}) != entry_hash:
                raise ValueError("JOURNAL_INTEGRITY")
            if res["decision"] == "COMMITTED":
                state, evidence = self._transition(req)
                if state.to_dict() != res["state"] or asdict(evidence) != res["receipt"]:
                    raise ValueError("REPLAY_DIVERGENCE")
                self.state = state
                self.ledger.append(evidence)
            elif res["decision"] != "DENIED":
                raise ValueError("INVALID_DECISION")
            self.root = entry_hash

    def handle(self, request):
        denied = lambda reason: {"decision": "DENIED", "reason": reason, "receipt": None}
        if not isinstance(request, dict) or set(request) != {"request_id", "token", "kind", "payload"} or not valid_id(request.get("request_id")):
            return denied("REQUEST_SCHEMA")
        token = request["token"]
        try:
            token_bytes = token.encode() if isinstance(token, str) else b""
        except UnicodeEncodeError:
            return denied("UNAUTHENTICATED")
        principal = next((p for t, p in self.tokens.items() if hmac.compare_digest(t.encode(), token_bytes)), None)
        if principal is None:
            return denied("UNAUTHENTICATED")
        kind = request["kind"]
        if not isinstance(kind, str) or kind not in KINDS or kind not in self.policy.get(principal, []):
            reason = "CAPABILITY_DENIED"
        else:
            reason = None
        req = {k: request[k] for k in ("request_id", "kind", "payload")}
        req["principal"] = principal
        try:
            raw_req = canonical_json(req)
            raw_req.encode("utf-8")
        except (TypeError, ValueError, OverflowError, UnicodeError):
            return denied("NONCANONICAL_INPUT")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self._recover()  # Includes other writers; stale state is never authoritative.
            old = self.db.execute("SELECT request,response FROM journal WHERE request_id=?", (request["request_id"],)).fetchone()
            if old:
                self.db.execute("ROLLBACK")
                if reason:
                    return denied(reason)
                return json.loads(old[1]) if old[0] == raw_req else denied("REQUEST_ID_CONFLICT")
            state, evidence = None, None
            if not reason:
                try:
                    state, evidence = self._transition(req)
                except (ValueError, TypeError, KeyError, RuntimeError) as exc:
                    reason = str(exc)
            res = denied(reason) if reason else {"decision": "COMMITTED", "reason": "CERTIFIED", "receipt": asdict(evidence), "state": state.to_dict()}
            n = self.db.execute("SELECT count(*) FROM journal").fetchone()[0] + 1
            entry_hash = digest({"n": n, "request": req, "response": res, "prev_hash": self.root})
            self.db.execute("INSERT INTO journal VALUES (?,?,?,?,?,?)", (n, req["request_id"], raw_req, canonical_json(res), self.root, entry_hash))
            self.db.execute("COMMIT")
            if state:
                self.state = state; self.ledger.append(evidence)
            self.root = entry_hash
            return res
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--tokens", type=Path, required=True)
    args = parser.parse_args()
    if args.tokens.stat().st_mode & 0o077:
        parser.error("token file must have mode 0600")
    import os
    os.umask(0o077)
    service = Service(args.db, json.loads(args.policy.read_text()), json.loads(args.tokens.read_text()))
    try:
        while line := sys.stdin.buffer.readline(65538):
            if len(line) > 65536:
                raise ValueError("INPUT_TOO_LARGE")
            try:
                request = json.loads(line)
                response = service.handle(request)
            except (json.JSONDecodeError, UnicodeDecodeError):
                response = {"decision": "DENIED", "reason": "INVALID_JSON", "receipt": None}
            print(canonical_json(response), flush=True)
    finally:
        service.close()

if __name__ == "__main__":
    main()
