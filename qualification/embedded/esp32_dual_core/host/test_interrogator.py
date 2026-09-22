from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from interrogator import CampaignReport, Interrogator, Transcript, compare_reports


class FakeDevice:
    def __init__(self, proposer_core=0, authority_core=1):
        self.p = proposer_core
        self.a = authority_core
        self.r0 = 10
        self.r1 = 0
        self.pc = 0
        self.sequence = 0
        self.halted = False
        self.request_id = 1
        self.queue: list[str] = []
        self.persistence_enabled = False
        self.recovered_on_boot = False
        self.reboot_after = 0
        self.stall_ms = 0
        self.timeout_ms = 5000

    def _root(self):
        return f"root-{self.r0}-{self.r1}-{self.pc}-{self.sequence}-{int(self.halted)}"

    def _state_hash(self):
        return f"state-{self.r0}-{self.r1}-{self.pc}-{self.sequence}-{int(self.halted)}"

    def _status(self, event, rid, note=None):
        out = {
            "event": event,
            "request_id": rid,
            "proposer_core": self.p,
            "authority_core": self.a,
            "r0": self.r0,
            "r1": self.r1,
            "pc": self.pc,
            "sequence": self.sequence,
            "halted": self.halted,
            "state_hash": self._state_hash(),
            "evidence_root": self._root(),
            "evidence_steps": self.sequence,
            "persistence_enabled": self.persistence_enabled,
            "recovered_on_boot": self.recovered_on_boot,
            "proposer_stall_ms": self.stall_ms,
            "proposal_timeout_ms": self.timeout_ms,
            "work_queue_depth": 0,
            "proposal_queue_depth": 0,
            "control_queue_depth": 0,
        }
        if note is not None:
            out["note"] = note
        return out

    def _step_once(self):
        if self.halted:
            return
        if self.pc == 0:
            self.sequence += 1
            if self.r0 == 0:
                self.pc = 2
            else:
                self.r0 -= 1
                self.pc = 1
        elif self.pc == 1:
            self.sequence += 1
            self.r1 += 1
            self.pc = 0
        elif self.pc == 2:
            self.sequence += 1
            self.halted = True

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
            self.pc = 0
            self.sequence = 0
            self.halted = False
            self.recovered_on_boot = False
            events.append(self._status("reset", rid))
        elif op == "CLOCKS":
            events.append(self._status("clocks", rid))
        elif op == "FREEZE":
            events.append(self._status("freeze", rid))
        elif op == "PERSIST":
            self.persistence_enabled = parts[1] == "1"
            if not self.persistence_enabled:
                self.recovered_on_boot = False
            events.append(self._status("persist", rid))
        elif op == "REBOOT_AFTER":
            self.reboot_after = int(parts[1])
            events.append(self._status("reboot_after", rid))
        elif op == "STALL":
            self.stall_ms = int(parts[1])
            events.append(self._status("stall", rid))
        elif op == "TIMEOUT":
            self.timeout_ms = int(parts[1])
            events.append(self._status("timeout", rid))
        elif op == "BURST":
            requested = int(parts[1])
            enqueued = min(requested, 4)
            committed = 0
            if enqueued and not self.halted:
                self._step_once()
                committed = 1
            rejected = max(0, enqueued - committed)
            events.append({
                "event": "burst_complete",
                "request_id": rid,
                "requested": requested,
                "enqueued": enqueued,
                "committed": committed,
                "rejected": rejected,
                "state_hash": self._state_hash(),
                "evidence_root": self._root(),
            })
        elif op == "STEP":
            fault = parts[1] if len(parts) > 1 else "NONE"
            if self.stall_ms > self.timeout_ms:
                events.append(self._status("error", rid, "proposal timeout"))
            else:
                reason = {
                    "TAMPER_STATE": "STATE_DIVERGENCE",
                    "TAMPER_PREHASH": "STALE_PRE_STATE",
                    "TAMPER_ROUTE": "ROUTE_DIVERGENCE",
                }.get(fault)
                if reason:
                    events.append({
                        "event": "decision",
                        "request_id": rid,
                        "committed": False,
                        "reason": reason,
                    })
                else:
                    self._step_once()
                    events.append({
                        "event": "decision",
                        "request_id": rid,
                        "committed": True,
                        "reason": "NONE",
                    })
        elif op == "RUN":
            budget = int(parts[1])
            attempted = 0
            while not self.halted and attempted < budget:
                self._step_once()
                attempted += 1
                if self.reboot_after > 0:
                    self.reboot_after -= 1
                    if self.reboot_after == 0:
                        self.recovered_on_boot = self.persistence_enabled
                        events.append(self._status("rebooting", rid, "scheduled reboot after commit"))
                        break
            else:
                events.append(self._status("run_complete", rid))
        elif op == "REBOOT":
            self.recovered_on_boot = self.persistence_enabled
            events.append(self._status("rebooting", rid, "operator requested reboot"))
        else:
            events.append({"event": "error", "request_id": rid, "reason": "unknown"})

        self.queue.extend(json.dumps(x) for x in events)


class FakeTransport:
    def __init__(self, device: FakeDevice):
        self.device = device
        self.closed = False

    def write_line(self, text: str):
        if self.closed:
            raise RuntimeError("fake transport closed")
        self.device.handle(text)

    def read_line(self, timeout: float):
        if self.closed:
            return None
        return self.device.queue.pop(0) if self.device.queue else None

    def close(self):
        self.closed = True

    def reconnect(self, timeout: float = 15.0):
        self.closed = False
        # Match SerialTransport.reconnect(): stale pre-disconnect USB input is discarded.
        self.device.queue.clear()


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

    def test_stress_campaign(self):
        iq = Interrogator(FakeTransport(FakeDevice()), echo=False)
        report = iq.stress(trials=8, seed=12345)
        self.assertTrue(report.passed)
        self.assertEqual(report.trials_completed, 8)
        self.assertTrue(all(t.passed for t in report.trials))

    def test_fault_matrix(self):
        iq = Interrogator(FakeTransport(FakeDevice()), echo=False)
        report = iq.fault_matrix()
        self.assertTrue(report.passed)
        self.assertEqual(len(report.cases), 6)
        self.assertTrue(all(case.passed for case in report.cases))

    def test_soak_campaign(self):
        iq = Interrogator(FakeTransport(FakeDevice()), echo=False)
        report = iq.soak(rounds=3, trials_per_round=4, seed=900)
        self.assertTrue(report.passed)
        self.assertEqual(report.rounds_completed, 3)
        self.assertTrue(iq.transcript.verify())

    def test_resilience_campaign(self):
        iq = Interrogator(FakeTransport(FakeDevice()), echo=False)
        report = iq.resilience()
        self.assertTrue(report.passed)
        self.assertTrue(all(report.checks.values()))

    def test_full_qualification(self):
        iq = Interrogator(FakeTransport(FakeDevice()), echo=False)
        report = iq.qualify_all(stress_trials=3, seed=777)
        self.assertTrue(report.passed)
        self.assertTrue(report.resilience_passed)
        self.assertTrue(report.transcript_audit_passed)

    def test_transcript_hash_chain_roundtrip_and_tamper_detection(self):
        iq = Interrogator(FakeTransport(FakeDevice()), echo=False)
        iq.status()
        iq.reset(3, 4)
        iq.run(20)
        self.assertTrue(iq.transcript.verify())
        audit = iq.transcript.audit()
        self.assertTrue(audit.passed)
        self.assertGreater(audit.event_count, 0)

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "transcript.jsonl"
            iq.transcript.save_jsonl(p)
            loaded = Transcript.load_jsonl(p)
            self.assertTrue(loaded.verify())
            self.assertEqual(loaded.root_hash, iq.transcript.root_hash)

            lines = p.read_text(encoding="utf-8").splitlines()
            first = json.loads(lines[0])
            first["payload"] = "STATUS_TAMPERED"
            lines[0] = json.dumps(first, sort_keys=True)
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
            tampered = Transcript.load_jsonl(p)
            self.assertFalse(tampered.verify())


if __name__ == "__main__":
    unittest.main()
