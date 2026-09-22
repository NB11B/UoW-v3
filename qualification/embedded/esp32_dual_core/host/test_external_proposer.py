from __future__ import annotations

import hashlib
import json
import unittest

from external_proposer import (
    Candidate,
    ExternalAuthorityClient,
    ReferenceBackend,
    Snapshot,
    state_hash_fields,
)
from interrogator import Interrogator


ZERO = "0" * 64


class ExternalFakeDevice:
    def __init__(self):
        self.r0 = 10
        self.r1 = 0
        self.pc = 0
        self.sequence = 0
        self.halted = False
        self.root = ZERO
        self.request_id = 1
        self.queue: list[str] = []

    def snapshot(self):
        return Snapshot(
            self.r0,
            self.r1,
            self.pc,
            self.sequence,
            self.halted,
            state_hash_fields(self.r0, self.r1, self.pc, self.sequence, self.halted),
            self.root,
        )

    def expected(self):
        return ReferenceBackend().propose(self.snapshot())

    def commit_expected(self, candidate: Candidate):
        pre = self.snapshot()
        expected = self.expected()
        if candidate.pre_state_hash != pre.state_hash:
            return False, "STALE_PRE_STATE"
        proposed_fields = (
            candidate.r0, candidate.r1, candidate.pc,
            candidate.sequence, candidate.halted,
        )
        expected_fields = (
            expected.r0, expected.r1, expected.pc,
            expected.sequence, expected.halted,
        )
        if proposed_fields != expected_fields:
            return False, "STATE_DIVERGENCE"
        if candidate.selected_pc != expected.selected_pc:
            return False, "ROUTE_DIVERGENCE"
        rebuilt = Candidate.build(
            pre_state_hash=candidate.pre_state_hash,
            r0=candidate.r0,
            r1=candidate.r1,
            pc=candidate.pc,
            sequence=candidate.sequence,
            halted=candidate.halted,
            selected_pc=candidate.selected_pc,
        )
        if candidate.proposal_hash != rebuilt.proposal_hash:
            return False, "PROPOSAL_HASH_DIVERGENCE"

        self.r0 = candidate.r0
        self.r1 = candidate.r1
        self.pc = candidate.pc
        self.sequence = candidate.sequence
        self.halted = candidate.halted
        post_hash = self.snapshot().state_hash
        self.root = hashlib.sha256(
            f"{self.root}:{pre.state_hash}:{post_hash}:{candidate.proposal_hash}".encode()
        ).hexdigest()
        return True, "NONE"

    def internal_step(self):
        return self.commit_expected(self.expected())

    def status_event(self, event, rid):
        snap = self.snapshot()
        return {
            "event": event,
            "request_id": rid,
            "proposer_core": 0,
            "authority_core": 1,
            "r0": snap.r0,
            "r1": snap.r1,
            "pc": snap.pc,
            "sequence": snap.sequence,
            "halted": snap.halted,
            "state_hash": snap.state_hash,
            "evidence_root": snap.evidence_root,
            "evidence_steps": snap.sequence,
        }

    def handle(self, line: str):
        rid = self.request_id
        self.request_id += 1
        parts = line.split()
        op = parts[0]
        events = []

        if op == "PERSIST":
            events.append(self.status_event("persist", rid))
        elif op == "RESET":
            self.r0, self.r1 = int(parts[1]), int(parts[2])
            self.pc = self.sequence = 0
            self.halted = False
            self.root = ZERO
            events.append(self.status_event("reset", rid))
        elif op == "STATUS":
            events.append(self.status_event("status", rid))
        elif op == "SNAPSHOT":
            events.append(self.status_event("snapshot", rid))
        elif op == "STEP":
            committed, reason = self.internal_step()
            events.append({
                "event": "decision",
                "request_id": rid,
                "origin": "internal",
                "committed": committed,
                "reason": reason,
                "evidence_root": self.root,
            })
        elif op == "RUN":
            budget = int(parts[1])
            attempts = 0
            while not self.halted and attempts < budget:
                committed, _ = self.internal_step()
                if not committed:
                    break
                attempts += 1
            events.append(self.status_event("run_complete", rid))
        elif op == "EXT_PROPOSE":
            c = Candidate(
                pre_state_hash=parts[1],
                r0=int(parts[2]),
                r1=int(parts[3]),
                pc=int(parts[4]),
                sequence=int(parts[5]),
                halted=parts[6] == "1",
                selected_pc=int(parts[7]),
                proposal_hash=parts[8],
            )
            committed, reason = self.commit_expected(c)
            events.append({
                "event": "decision",
                "request_id": rid,
                "origin": "external",
                "committed": committed,
                "reason": reason,
                "evidence_root": self.root,
            })
        else:
            events.append({"event": "error", "request_id": rid, "reason": "unknown"})

        self.queue.extend(json.dumps(x) for x in events)


class FakeTransport:
    def __init__(self):
        self.device = ExternalFakeDevice()
        self.closed = False

    def write_line(self, text: str):
        if self.closed:
            raise RuntimeError("closed")
        self.device.handle(text)

    def read_line(self, timeout: float):
        if self.closed:
            return None
        return self.device.queue.pop(0) if self.device.queue else None

    def close(self):
        self.closed = True

    def reconnect(self, timeout: float = 15.0):
        self.closed = False


class AlwaysBadBackend:
    name = "always-bad"

    def propose(self, snapshot: Snapshot) -> Candidate:
        good = ReferenceBackend().propose(snapshot)
        return Candidate(
            good.pre_state_hash,
            good.r0,
            good.r1 + 999,
            good.pc,
            good.sequence,
            good.halted,
            good.selected_pc,
            good.proposal_hash,
        )


class ExternalProposerTests(unittest.TestCase):
    def make_client(self):
        return ExternalAuthorityClient(Interrogator(FakeTransport(), echo=False))

    def test_reference_external_run_matches_internal_baseline(self):
        client = self.make_client()
        client.iq.reset(50, 25)
        baseline = client.iq.run(1000).terminal
        report = client.run_external(ReferenceBackend(), initial_r0=50, initial_r1=25)
        self.assertTrue(report.halted)
        self.assertEqual(report.final_state_hash, baseline["state_hash"])
        self.assertEqual(report.final_evidence_root, baseline["evidence_root"])

    def test_capability_gate_reference_passes(self):
        report = self.make_client().capability(ReferenceBackend())
        self.assertTrue(report.passed)
        self.assertTrue(report.halted)
        self.assertTrue(report.state_parity)
        self.assertTrue(report.evidence_parity)

    def test_capability_gate_bad_backend_fails_without_wrong_commit(self):
        report = self.make_client().capability(AlwaysBadBackend())
        self.assertFalse(report.passed)
        self.assertGreater(report.rejections, 0)

    def test_full_external_qualification_reference_backend(self):
        report = self.make_client().qualify(ReferenceBackend(), backend_trials=10)
        self.assertTrue(report.passed)
        self.assertEqual(report.wrong_authoritative_commits, 0)
        self.assertEqual(report.backend_rejects, 0)

    def test_bad_backend_is_contained(self):
        report = self.make_client().qualify(AlwaysBadBackend(), backend_trials=10)
        self.assertTrue(report.passed)
        self.assertEqual(report.backend_accepts, 0)
        self.assertEqual(report.backend_rejects, 10)
        self.assertEqual(report.wrong_authoritative_commits, 0)

    def test_intel_npu_adapter_step(self):
        try:
            import numpy
            import openvino
            from intel_npu_adapter import propose
        except Exception:
            self.skipTest("intel_npu_adapter dependencies not available")

        snapshot = {
            "r0": 50,
            "r1": 25,
            "pc": 0,
            "sequence": 0,
            "halted": False,
            "state_hash": "dummy",
            "evidence_root": ZERO,
        }
        res = propose(snapshot)
        self.assertEqual(res["r0"], 49)
        self.assertEqual(res["r1"], 25)
        self.assertEqual(res["pc"], 1)
        self.assertEqual(res["sequence"], 1)
        self.assertFalse(res["halted"])


if __name__ == "__main__":
    unittest.main()
