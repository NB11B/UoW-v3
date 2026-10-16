"""Deterministic unit and regression tests for pretrained_probe.py.

Exercises all 12 required regression contracts without requiring network or SmolLM2 weights.
"""
import math
import unittest
import torch
from torch import nn

from pretrained_probe import (
    TEMPLATES,
    ablate,
    independent_splits,
    measure,
    projections,
    rank_p_value,
    rows,
    score_sequence,
    validate_revision_sha,
)


class Tiny(nn.Module):
    def __init__(self):
        super().__init__()
        self.mlp = nn.Module()
        self.mlp.down_proj = nn.Linear(4, 2, bias=False)

    def forward(self, x):
        return self.mlp.down_proj(x)


class MockTokenizer:
    def __init__(self, mapping, prefix_mismatch_key=None):
        self.mapping = dict(mapping)
        self.prefix_mismatch_key = prefix_mismatch_key

    def encode(self, text, add_special_tokens=False):
        if self.prefix_mismatch_key and text == self.prefix_mismatch_key:
            return [999, 998, 997]
        if text in self.mapping:
            return list(self.mapping[text])
        raise KeyError(f"MockTokenizer text not mapped: {text!r}")


class MockCausalLM(nn.Module):
    def __init__(self, vocab_size=50, hidden_dim=4, fixed_logits=None):
        super().__init__()
        self.vocab_size = vocab_size
        self.mlp = nn.Module()
        self.mlp.down_proj = nn.Linear(hidden_dim, hidden_dim, bias=False)
        with torch.no_grad():
            self.mlp.down_proj.weight.copy_(torch.eye(hidden_dim))
        self.fixed_logits = fixed_logits

    def forward(self, input_ids):
        # input_ids: (batch_size, seq_len)
        b, L = input_ids.shape
        if self.fixed_logits is not None:
            return self.fixed_logits.clone()
        # Default: produce hidden state, ablate affects down_proj
        x = torch.ones((b, L, self.mlp.down_proj.in_features), dtype=torch.float32)
        h = self.mlp.down_proj(x)
        # Create distinct logits across vocab
        logits = torch.zeros((b, L, self.vocab_size), dtype=torch.float32)
        for i in range(min(self.mlp.down_proj.in_features, self.vocab_size)):
            logits[:, :, i] = h[:, :, i] * 2.0
        return logits


class TestPretrainedProbeRegression(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(42)

    # 1. Single-token numerical answer: Correct likelihood calculation
    def test_single_token_likelihood_calculation(self):
        prompt = "Which is larger: 1 or 2?"
        cand = "2"
        # Prompt: tokens [10, 11]. Cand: [20]. Full: [10, 11, 20] (length 3, continuation length 1)
        tok = MockTokenizer({
            prompt: [10, 11],
            prompt + " " + cand: [10, 11, 20],
        })
        vocab_size = 30
        logits = torch.zeros((1, 3, vocab_size))
        # At position 1 (last prompt token, index n-1=1), model predicts token 20
        # Let's set logits[0, 1, 20] = 3.0 and logits[0, 1, 0] = 1.0, others 0
        logits[0, 1, 20] = 3.0
        logits[0, 1, 0] = 1.0
        model = MockCausalLM(vocab_size=vocab_size, fixed_logits=logits)

        res = score_sequence(model, tok, prompt, cand, device="cpu")
        self.assertEqual(res["continuation_tokens"], [20])
        self.assertEqual(res["continuation_length"], 1)

        # Expected log likelihood: log_softmax of logits[0, 1, :] at index 20
        expected_log_p = float(torch.log_softmax(logits[0, 1, :], dim=-1)[20].item())
        self.assertAlmostEqual(res["summed_log_likelihood"], expected_log_p, places=5)
        self.assertAlmostEqual(res["normalized_log_likelihood"], expected_log_p, places=5)

    # 2. Multi-token numerical answer: Correct likelihood calculation
    def test_multi_token_likelihood_calculation(self):
        prompt = "Which is larger: 15 or 82?"
        cand = "82"
        # Prompt: [10, 11]. Cand: [21, 22]. Full: [10, 11, 21, 22] (length 4, continuation 2)
        tok = MockTokenizer({
            prompt: [10, 11],
            prompt + " " + cand: [10, 11, 21, 22],
        })
        vocab_size = 30
        logits = torch.randn((1, 4, vocab_size))
        model = MockCausalLM(vocab_size=vocab_size, fixed_logits=logits)

        res = score_sequence(model, tok, prompt, cand, device="cpu")
        self.assertEqual(res["continuation_tokens"], [21, 22])
        self.assertEqual(res["continuation_length"], 2)

        # Logit at index 1 predicts token 21; logit at index 2 predicts token 22
        lp1 = float(torch.log_softmax(logits[0, 1, :], dim=-1)[21].item())
        lp2 = float(torch.log_softmax(logits[0, 2, :], dim=-1)[22].item())
        expected_sum = lp1 + lp2
        expected_mean = expected_sum / 2.0

        self.assertAlmostEqual(res["summed_log_likelihood"], expected_sum, places=5)
        self.assertAlmostEqual(res["normalized_log_likelihood"], expected_mean, places=5)

    # 3. Two candidates of different token lengths: Valid comparison
    def test_candidates_of_different_token_lengths(self):
        prompt = "Which is larger: 5 or 100?"
        pos = "100"  # 2 tokens [21, 22]
        neg = "5"    # 1 token [25]
        tok = MockTokenizer({
            prompt: [10, 11],
            prompt + " " + pos: [10, 11, 21, 22],
            prompt + " " + neg: [10, 11, 25],
        })
        model = MockCausalLM(vocab_size=30)
        out = measure(model, tok, [(prompt, pos, neg)], device="cpu")
        self.assertEqual(len(out["margins"]), 1)
        self.assertEqual(len(out["normalized_margins"]), 1)
        self.assertTrue(math.isfinite(out["margin"]))
        self.assertTrue(math.isfinite(out["normalized_margin"]))

    # 4. Prefix-boundary mismatch: Explicit rejection
    def test_prefix_boundary_mismatch_rejection(self):
        prompt = "Which is larger: 15 or 82?"
        cand = "82"
        tok = MockTokenizer(
            {prompt: [10, 11], prompt + " " + cand: [999, 998, 997]},
            prefix_mismatch_key=prompt + " " + cand,
        )
        model = MockCausalLM(vocab_size=30)
        with self.assertRaises(ValueError) as ctx:
            score_sequence(model, tok, prompt, cand, device="cpu")
        self.assertIn("Prefix-boundary mismatch", str(ctx.exception))

    # 5. Empty continuation: Explicit rejection
    def test_empty_continuation_rejection(self):
        prompt = "Which is larger: 15 or 82?"
        cand = ""
        tok = MockTokenizer({prompt: [10, 11]})
        model = MockCausalLM(vocab_size=30)
        with self.assertRaises(ValueError):
            score_sequence(model, tok, prompt, cand, device="cpu")

        # Also test if full text tokenizes to identical length as prompt
        tok2 = MockTokenizer({
            prompt: [10, 11],
            prompt + " none": [10, 11],
        })
        with self.assertRaises(ValueError) as ctx:
            score_sequence(model, tok2, prompt, "none", device="cpu")
        self.assertIn("Empty continuation", str(ctx.exception))

    # 6. Equal candidate scores: Correct tie handling
    def test_equal_candidate_scores_tie_handling(self):
        prompt = "Compare 10 and 10"
        pos = "10"
        neg = "10"
        tok = MockTokenizer({
            prompt: [10, 11],
            prompt + " " + pos: [10, 11, 20],
        })
        # Mock model produces identical logits
        model = MockCausalLM(vocab_size=30)
        out = measure(model, tok, [(prompt, pos, neg)], device="cpu")
        self.assertEqual(out["margin"], 0.0)
        self.assertEqual(out["normalized_margin"], 0.0)
        self.assertEqual(out["ties"], 1)
        self.assertEqual(out["accuracy"], 0.5)
        self.assertEqual(out["normalized_accuracy"], 0.5)

    # 7. Ablation changes the intended activation: Demonstrated
    def test_ablation_changes_activation(self):
        model = Tiny()
        x = torch.ones((2, 4))
        expected = model(x)
        with ablate(model.mlp.down_proj, 0):
            actual = model(x)
            self.assertFalse(torch.equal(actual, expected))
        self.assertTrue(torch.equal(model(x), expected))

    # 8. Ablation cleanup after exception: No leaked hooks
    def test_ablation_cleanup_after_exception(self):
        model = Tiny()
        with self.assertRaises(RuntimeError):
            with ablate(model.mlp.down_proj, 0):
                raise RuntimeError("controlled failure")
        self.assertEqual(len(model.mlp.down_proj._forward_pre_hooks), 0)

    # 9. Distinct selection/holdout pairs: Zero overlap
    def test_distinct_pair_partitions(self):
        partitions = independent_splits(42, (10, 20, 20))
        pair_sets = []
        for partition in partitions:
            pairs = set()
            for prompt, hi, lo in partition:
                self.assertGreater(int(hi), int(lo))
                pairs.add((int(lo), int(hi)))
            pair_sets.append(pairs)
        self.assertEqual(len(pair_sets[0] & pair_sets[1]), 0)
        self.assertEqual(len(pair_sets[0] & pair_sets[2]), 0)
        self.assertEqual(len(pair_sets[1] & pair_sets[2]), 0)

    # 10. Repeat with identical seed: Reproducible result
    def test_repeat_with_identical_seed_reproducible(self):
        s1 = independent_splits(42, (10, 10, 10))
        s2 = independent_splits(42, (10, 10, 10))
        self.assertEqual(s1, s2)
        s3 = independent_splits(43, (10, 10, 10))
        self.assertNotEqual(s1, s3)

    # 11. Missing or invalid model revision: Fail closed
    def test_revision_validation_fails_closed(self):
        valid_sha = "12fd25f77366fa6b3b4b768ec3050bf629380bac"
        self.assertEqual(validate_revision_sha(valid_sha), valid_sha)
        self.assertEqual(validate_revision_sha(valid_sha.upper()), valid_sha)
        with self.assertRaises(ValueError):
            validate_revision_sha("")
        with self.assertRaises(ValueError):
            validate_revision_sha(None)
        with self.assertRaises(ValueError):
            validate_revision_sha("short_sha")
        with self.assertRaises(ValueError):
            validate_revision_sha("z" * 40)  # non-hex

    # 12. Nonfinite likelihood or margin: Explicit rejection
    def test_nonfinite_likelihood_rejection(self):
        prompt = "Which is larger: 1 or 2?"
        cand = "2"
        tok = MockTokenizer({
            prompt: [10, 11],
            prompt + " " + cand: [10, 11, 20],
        })
        # Inject NaN into logits
        logits = torch.zeros((1, 3, 30))
        logits[0, 1, 20] = float("nan")
        model = MockCausalLM(vocab_size=30, fixed_logits=logits)
        with self.assertRaises(ValueError) as ctx:
            score_sequence(model, tok, prompt, cand, device="cpu")
        self.assertIn("Nonfinite likelihood", str(ctx.exception))

        # Inject Inf into logits
        logits[0, 1, 20] = float("inf")
        with self.assertRaises(ValueError) as ctx2:
            score_sequence(model, tok, prompt, cand, device="cpu")
        self.assertIn("Nonfinite likelihood", str(ctx2.exception))


if __name__ == "__main__":
    unittest.main()
