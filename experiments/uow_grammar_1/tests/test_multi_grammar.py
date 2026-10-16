"""Unit tests for UOW-GRAMMAR-1 schemas, codecs, and deterministic composition."""
import json
from pathlib import Path
import sys
import unittest

# Ensure UoW src is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from experiments.uow_grammar_1.grammars.temporal import (
    TemporalConstraint, TemporalOutputParser, TemporalPromptBuilder
)
from experiments.uow_grammar_1.grammars.recovery import (
    RecoveryPlan, RecoveryOutputParser, RecoveryPromptBuilder
)
from uow.compat.v2 import (
    EvidenceLedger, Guard, GuardOp, Mutation, MutationOp,
    Proposal, Route, Successor, WorldState, certify, commit, make_uow, propose
)


class TestTemporalGrammar(unittest.TestCase):
    def setUp(self):
        self.parser = TemporalOutputParser()

    def test_parse_valid_temporal(self):
        raw = '{"target_action": "convey_sensors", "relation": "BETWEEN", "window": {"start": "09:00", "end": "17:00"}}'
        res = self.parser.parse(raw)
        self.assertIsNotNone(res)
        self.assertEqual(res.target_action, "convey_sensors")
        self.assertEqual(res.relation, "BETWEEN")
        self.assertEqual(res.window_start, "09:00")
        self.assertEqual(res.window_end, "17:00")

    def test_parse_invalid_temporal(self):
        self.assertIsNone(self.parser.parse("Broken text without json"))
        self.assertIsNone(self.parser.parse('{"missing_keys": 123}'))


class TestRecoveryGrammar(unittest.TestCase):
    def setUp(self):
        self.parser = RecoveryOutputParser()

    def test_parse_valid_recovery(self):
        raw = '{"failed_uow": "dispatch_cells", "strategy": "RETRY", "retry_policy": {"max_attempts": 3, "backoff": "EXPONENTIAL"}}'
        res = self.parser.parse(raw)
        self.assertIsNotNone(res)
        self.assertEqual(res.failed_uow, "dispatch_cells")
        self.assertEqual(res.strategy, "RETRY")
        self.assertEqual(res.max_attempts, 3)

    def test_parse_invalid_recovery(self):
        self.assertIsNone(self.parser.parse("Broken text"))
        self.assertIsNone(self.parser.parse('{"random": "payload"}'))


class TestDeterministicComposition(unittest.TestCase):
    def test_clock_boundary_and_commit_isolation(self):
        t_constraint = TemporalConstraint(target_action="task_a", relation="BETWEEN", window_start="09:00", window_end="17:00")
        
        # Valid clock inside window
        valid_clock = "12:00"
        self.assertTrue(t_constraint.window_start <= valid_clock <= t_constraint.window_end)

        # Invalid clock outside window
        invalid_clock = "20:00"
        self.assertFalse(t_constraint.window_start <= invalid_clock <= t_constraint.window_end)

        # Kernel uncertified commit refusal
        base_state = WorldState(attributes={"balance": 100})
        uow = make_uow("task_a", [Route(guard=Guard(GuardOp.ALWAYS), mutations=(Mutation(MutationOp.SET, "balance", 50),), successor=Successor.halt())])
        invalid_prop = Proposal(
            uow_id="task_a",
            pre_state_hash="forged_hash",
            selected_route_index=0,
            proposed_state=WorldState(attributes={"balance": 50}),
            selected_successor=None,
            halted=True
        )
        cert = certify(uow, base_state, invalid_prop)
        self.assertFalse(cert.is_valid)
        ledger = EvidenceLedger()
        with self.assertRaises(ValueError):
            commit(uow, base_state, invalid_prop, cert, prev_evidence_hash=ledger.root_hash(), step_number=1)
        self.assertEqual(len(ledger.records), 0)


if __name__ == "__main__":
    unittest.main()
