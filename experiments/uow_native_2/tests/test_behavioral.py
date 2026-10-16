"""Unit tests for behavioral_qualification.py."""

import unittest
from unittest.mock import MagicMock
import torch

from experiments.uow_native_2.behavioral_qualification import (
    compute_bootstrap_ci,
    evaluate_split,
    score_sequence,
    validate_revision_sha,
)
from experiments.uow_native_2.datasets import Example


class MockTokenizer:
    def __init__(self):
        self.vocab = {"Which": 1, "number": 2, "is": 3, "larger:": 4, "85": 5, "or": 6, "23?": 7, "Yes": 8, "No": 9}

    def encode(self, text, add_special_tokens=False):
        tokens = text.strip().split()
        return [self.vocab.get(t, 100) for t in tokens]


class MockModel(torch.nn.Module):
    def __init__(self, vocab_size=200):
        super().__init__()
        self.vocab_size = vocab_size

    def forward(self, input_ids):
        batch_size, seq_len = input_ids.shape
        # Create deterministic logits
        logits = torch.zeros((batch_size, seq_len, self.vocab_size), dtype=torch.float32)
        # Give higher logit to token 5 (positive) than token 7 (negative)
        logits[:, :, 5] = 5.0
        logits[:, :, 7] = 1.0
        logits[:, :, 8] = 4.0
        logits[:, :, 9] = 2.0
        return MagicMock(logits=logits)


class TestBehavioralQualification(unittest.TestCase):
    def test_validate_revision_sha(self):
        valid = "12fd25f77366fa6b3b4b768ec3050bf629380bac"
        self.assertEqual(validate_revision_sha(valid), valid)
        with self.assertRaises(ValueError):
            validate_revision_sha("short")
        with self.assertRaises(ValueError):
            validate_revision_sha("12fd25f77366fa6b3b4b768ec3050bf629380bzz")  # non-hex

    def test_compute_bootstrap_ci(self):
        values = [1.0] * 50 + [0.0] * 50
        low, high = compute_bootstrap_ci(values, n_bootstrap=500, ci=0.95)
        self.assertAlmostEqual(low, 0.4, delta=0.1)
        self.assertAlmostEqual(high, 0.6, delta=0.1)
        self.assertLessEqual(low, high)

    def test_score_sequence_prefix_validation(self):
        model = MockModel()
        tokenizer = MockTokenizer()
        device = "cpu"

        # Valid prompt + continuation
        res = score_sequence(model, tokenizer, "Which number is", "larger:", device)
        self.assertIn("summed_log_likelihood", res)
        self.assertIn("normalized_log_likelihood", res)
        self.assertEqual(res["continuation_length"], 1)

        # Empty prompt error
        with self.assertRaises(ValueError):
            score_sequence(model, tokenizer, "", "Yes", device)

        # Empty continuation error
        with self.assertRaises(ValueError):
            score_sequence(model, tokenizer, "Which number", "", device)

    def test_evaluate_split(self):
        model = MockModel()
        tokenizer = MockTokenizer()
        device = "cpu"

        ex0 = Example(
            id="ex0",
            family="numerical_ordering",
            split="dev",
            prompt="Which number is",
            positive="larger:",
            negative="23?",
            order=0,
            ground_truth_label="larger:",
            shifted_prompts=["Which number is"],
            counterpart_id="ex1",
            metadata={},
        )
        ex1 = Example(
            id="ex1",
            family="numerical_ordering",
            split="dev",
            prompt="Which number is",
            positive="larger:",
            negative="23?",
            order=1,
            ground_truth_label="larger:",
            shifted_prompts=["Which number is"],
            counterpart_id="ex0",
            metadata={},
        )

        res = evaluate_split(model, tokenizer, [ex0, ex1], device)
        self.assertEqual(res["count"], 2)
        self.assertIn("accuracy", res)
        self.assertIn("positional_gap", res)
        self.assertIn("shifted_templates", res)


if __name__ == "__main__":
    unittest.main()
