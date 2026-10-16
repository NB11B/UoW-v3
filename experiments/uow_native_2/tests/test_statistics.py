"""Unit tests for statistics.py in UOW-NATIVE-2."""

import unittest
from experiments.uow_native_2.statistics import (
    compute_bootstrap_ci,
    compute_rank_p_value,
    paired_difference_sign_test,
)


class TestStatistics(unittest.TestCase):
    def test_bootstrap_ci_coverage(self):
        data = [10.0] * 50 + [20.0] * 50
        lower, upper = compute_bootstrap_ci(data, n_bootstrap=1000, ci=0.95, seed=42)
        self.assertLess(lower, 15.0)
        self.assertGreater(upper, 15.0)
        self.assertLess(lower, upper)

    def test_bootstrap_empty(self):
        lower, upper = compute_bootstrap_ci([])
        self.assertEqual((lower, upper), (0.0, 0.0))

    def test_rank_p_value(self):
        controls = [1.0, 2.0, 3.0, 4.0, 5.0]
        # Effect is strictly larger than all controls -> (1 + 0) / (1 + 5) = 1/6
        p1 = compute_rank_p_value(6.0, controls)
        self.assertAlmostEqual(p1, 1.0 / 6.0)

        # Effect is equal to 3 controls -> (1 + 3) / (1 + 5) = 4/6
        p2 = compute_rank_p_value(3.0, controls)
        self.assertAlmostEqual(p2, 4.0 / 6.0)

        # Empty controls raises ValueError
        with self.assertRaises(ValueError):
            compute_rank_p_value(1.0, [])

    def test_paired_difference_sign_test(self):
        diffs = [1.5, -0.5, 0.0, 2.3, -1.0, 0.0, 3.1]
        pos, neg, zero = paired_difference_sign_test(diffs)
        self.assertEqual(pos, 3)
        self.assertEqual(neg, 2)
        self.assertEqual(zero, 2)


if __name__ == "__main__":
    unittest.main()
