"""Unit tests for circuit discovery and controls flow under Gate B0 conditions."""

import unittest
from experiments.uow_native_2.circuit_discovery import discover_circuits
from experiments.uow_native_2.circuit_controls import falsify_circuits
from experiments.uow_native_2.datasets import Example


class TestCircuitFlow(unittest.TestCase):
    def test_halt_rule_when_b0_failed(self):
        # When Gate B0 failed, discover_circuits must halt immediately
        report_b1 = discover_circuits(
            model=None,
            tokenizer=None,
            dev_examples=[],
            device="cpu",
            b0_status="FAILED",
            family_name="numerical_ordering",
            output_path=None,
        )
        self.assertTrue(report_b1["halt_rule_triggered"])
        self.assertEqual(report_b1["status"], "HALTED")
        self.assertEqual(report_b1["terminal_classification"], "BEHAVIORAL_COMPETENCE_NOT_ESTABLISHED")

        # Similarly, falsify_circuits must halt immediately
        report_b2 = falsify_circuits(
            model=None,
            tokenizer=None,
            holdout_examples=[],
            negative_control_examples=[],
            b0_status="FAILED",
            circuit_discovery_report=report_b1,
            device="cpu",
            output_path=None,
        )
        self.assertTrue(report_b2["halt_rule_triggered"])
        self.assertEqual(report_b2["status"], "HALTED")
        self.assertEqual(report_b2["terminal_classification"], "BEHAVIORAL_COMPETENCE_NOT_ESTABLISHED")


if __name__ == "__main__":
    unittest.main()
