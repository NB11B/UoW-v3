from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from interrogator import CampaignReport, Interrogator, compare_reports


class FakeDevice:
    def __init__(self, proposer_core=0, authority_core=1):
        self.p = proposer_core
        self.a = authority_core
        self.r0 = 10
        self.r1 = 0
        self.sequence = 0
        self.halted = False
        self.request_id = 1
        self.queue: list[str] = []

    def _root(self):
        return f"root-{self.r0}-{self.r1}-{self.sequence}-{int(self.halted)}"

    def _status(self, event, rid):
        return {
            "event": event,
            "request_id": rid,
            "proposer_core": self.p,
            "authority_core": self.a,
            "r0": self.r0,
            "r1": self.r1,
            "sequence": self.sequence,
            "halted": self.halted,
            "state_hash": f"state-{self.r0}-{self.r1}-{self.sequence}-{int(self.halted)}",
            "evidence_root": self._root(),
        }

    def handle(self, line: str):
        rid = self.request_id
        self.request_id += 1
        parts = line.split()
        op = parts[0]
        events = []
        if op == "STATUS":
            events.append(self._status("status", rid))
        elif op == "RESET":
            self.r0, self.r1 = int(parts[1]), int(parts[2])
            self.sequence = 0
            self.halted = False
            events.append(self._status("reset", rid))
        elif op == "CLOCKS":
            events.append(self._status("clocks", rid))
        elif op == "FREEZE":
            events.append(self._status("freeze", rid))
        elif op == "STEP":
            fault = parts[1] if len(parts) > 1 else "NONE"
            reason = {
                "TAMPER_STATE": "STATE_DIVERGENCE",
                "TAMPER_PREHASH": "STALE_PRE_STATE",
                "TAMPER_ROUTE": "ROUTE_DIVERGENCE",
            }.get(fault)
            if reason:
                events.append({"event": "decision", "request_id": rid, "committed": False, "reason": reason})
            else:
                events.append({"event": "decision", "request_id": rid, "committed": True, "reason": "NONE"})
        elif op == "RUN":
            initial_total = self.r0 + self.r1
            self.sequence += 2 * self.r0 + 2
            self.r0 = 0
            self.r1 = initial_total
            self.halted = True
            events.append(self._status("run_complete", rid))
        else:
            events.append({"event": "error", "request_id": rid, "reason": "unknown"})
        self.queue.extend(json.dumps(x) for x in events)


class FakeTransport:
    def __init__(self, device: FakeDevice):
        self.device = device

    def write_line(self, text: str):
        self.device.handle(text)

    def read_line(self, timeout: float):
        return self.device.queue.pop(0) if self.device.queue else None

    def close(self):
        pass


class InterrogatorTests(unittest.TestCase):
    def test_campaign_and_report(self):
        iq = Interrogator(FakeTransport(FakeDevice()), echo=False)
        report = iq.campaign()
        self.assertTrue(report.passed)
        self.assertEqual((report.final_r0, report.final_r1, report.final_sequence), (0, 75, 102))
        self.assertGreater(len(iq.transcript.events), 10)

    def test_core_inversion_compare(self):
        left = Interrogator(FakeTransport(FakeDevice(0, 1)), echo=False).campaign()
        right = Interrogator(FakeTransport(FakeDevice(1, 0)), echo=False).campaign()
        result = compare_reports(left, right)
        self.assertTrue(all(result.values()))

    def test_report_roundtrip(self):
        report = Interrogator(FakeTransport(FakeDevice()), echo=False).campaign()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "r.json"
            report.save(p)
            loaded = CampaignReport.load(p)
            self.assertEqual(report, loaded)


if __name__ == "__main__":
    unittest.main()
