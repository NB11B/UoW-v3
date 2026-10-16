"""Regression guards for dataset leakage and control-rank reporting."""
import unittest
from pretrained_probe import independent_splits, rank_p_value


class TestStage2Controls(unittest.TestCase):
    def test_disjoint_pair_partitions(self):
        for seed in (42, 43, 44, 101, 202):
            partitions = independent_splits(seed)
            pair_sets = []
            for partition in partitions:
                self.assertEqual(len(partition), len(set(x[0] for x in partition)))
                pairs = set()
                for prompt, larger, smaller in partition:
                    self.assertGreater(int(larger), int(smaller))
                    self.assertIn(larger, prompt)
                    self.assertIn(smaller, prompt)
                    pairs.add((smaller, larger))
                pair_sets.append(pairs)
            for i in range(len(pair_sets)):
                for j in range(i+1, len(pair_sets)):
                    self.assertFalse(pair_sets[i] & pair_sets[j])

    def test_reproducible_splits(self):
        self.assertEqual(independent_splits(42), independent_splits(42))
        self.assertNotEqual(independent_splits(42), independent_splits(43))

    def test_rank_ties_and_minimum_resolution(self):
        self.assertEqual(rank_p_value(2.0,[1.0]*31),1/32)
        self.assertEqual(rank_p_value(1.0,[1.0]*31),1)
        self.assertEqual(rank_p_value(0.0,[1.0]*31),1)
        with self.assertRaises(ValueError): rank_p_value(2.0,[])

    def test_reject_oversubscribed_universe(self):
        with self.assertRaises(ValueError): independent_splits(42,(4000,))

if __name__ == "__main__":
    unittest.main()
