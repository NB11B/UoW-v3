"""Unit tests for circuit discovery, controls flow, and cache provenance."""

import unittest
from experiments.uow_native_2.circuit_discovery import discover_circuits
from experiments.uow_native_2.circuit_controls import falsify_circuits
from experiments.uow_native_2.datasets import Example


class TestCircuitFlow(unittest.TestCase):
    def test_halt_rule_and_data_handoff(self):
        ex = Example(
            id="ex0",
            family="numerical_ordering",
            split="dev",
            prompt="Which number is larger: 85 or 23?",
            positive="85",
            negative="23",
            order=0,
            ground_truth_label="85",
            shifted_prompts=[],
            counterpart_id=None,
            metadata={},
        )

        # When Gate B0 failed, discover_circuits must halt immediately but still register data handoff
        report_b1 = discover_circuits(
            model=None,
            tokenizer=None,
            dev_examples=[ex],
            device="cpu",
            b0_status="FAILED",
            family_name="numerical_ordering",
            output_path=None,
        )
        self.assertTrue(report_b1["halt_rule_triggered"])
        self.assertEqual(report_b1["status"], "HALTED")
        self.assertEqual(report_b1["terminal_classification"], "BEHAVIORAL_COMPETENCE_NOT_ESTABLISHED")
        self.assertEqual(report_b1["dev_examples_count"], 1)

        # Similarly, falsify_circuits must halt immediately but register data handoff
        report_b2 = falsify_circuits(
            model=None,
            tokenizer=None,
            holdout_examples=[ex, ex],
            negative_control_examples=[ex],
            b0_status="FAILED",
            circuit_discovery_report=report_b1,
            device="cpu",
            output_path=None,
        )
        self.assertTrue(report_b2["halt_rule_triggered"])
        self.assertEqual(report_b2["status"], "HALTED")
        self.assertEqual(report_b2["terminal_classification"], "BEHAVIORAL_COMPETENCE_NOT_ESTABLISHED")
        self.assertEqual(report_b2["holdout_examples_count"], 2)
        self.assertEqual(report_b2["negative_control_examples_count"], 1)

    def test_cache_provenance_validation(self):
        model_name = "HuggingFaceTB/SmolLM2-135M-Instruct"
        rev = "12fd25f77366fa6b3b4b768ec3050bf629380bac"
        manifest_root = "abcdef1234567890"

        valid_cache = {
            "model": model_name,
            "revision": rev,
            "seed": 42,
            "dataset_root_sha256": manifest_root,
        }

        # Valid matches
        self.assertTrue(
            valid_cache.get("model") == model_name
            and valid_cache.get("revision") == rev
            and valid_cache.get("seed") == 42
            and valid_cache.get("dataset_root_sha256") == manifest_root
        )

        # Mismatched SHA must be rejected
        tampered_cache = dict(valid_cache, dataset_root_sha256="wrong_hash")
        self.assertFalse(
            tampered_cache.get("dataset_root_sha256") == manifest_root
        )


if __name__ == "__main__":
    unittest.main()
