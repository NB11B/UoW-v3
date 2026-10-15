import unittest
from experiment import execute_proposal, run_seed


class TestNativePilot(unittest.TestCase):
    def test_fail_closed(self):
        for p in (0, 1):
            for authority, epoch in ((False, 1), (True, 0)):
                self.assertFalse(execute_proposal(p, authority, 1, epoch))
        self.assertTrue(execute_proposal(1, True, 1, 1))
        self.assertFalse(execute_proposal(0, True, 1, 1))

    def test_probe_reproducible_and_causal(self):
        a = run_seed(0)
        b = run_seed(0)
        self.assertEqual(a, b)
        self.assertEqual(a.denial_violations, 0)
        self.assertGreater(a.baseline_accuracy, 0.90)
        self.assertGreater(a.selected_unit_ablation_drop, a.median_control_drop)
        self.assertGreater(a.prediction_change_rate, 0)


if __name__ == '__main__':
    unittest.main()
