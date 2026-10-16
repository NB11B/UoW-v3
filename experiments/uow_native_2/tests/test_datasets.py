"""Unit tests for datasets.py in UOW-NATIVE-2."""

import os
import unittest
from experiments.uow_native_2.datasets import (
    compute_sha256,
    generate_dataset_manifest,
    generate_numerical_ordering,
    generate_relational_classification,
    generate_symbolic_equivalence,
    load_all_datasets,
)


class TestDatasets(unittest.TestCase):
    def test_numerical_ordering_counts_and_balance(self):
        splits = generate_numerical_ordering(seed=42)
        self.assertEqual(set(splits.keys()), {"dev", "val", "holdout"})

        for split_name, examples in splits.items():
            self.assertEqual(len(examples), 200, f"Split {split_name} should have 200 examples")
            order_0 = sum(1 for e in examples if e.order == 0)
            order_1 = sum(1 for e in examples if e.order == 1)
            self.assertEqual(order_0, 100, f"Split {split_name} order 0 must be 100")
            self.assertEqual(order_1, 100, f"Split {split_name} order 1 must be 100")

            # Check counterpart reciprocity
            by_id = {e.id: e for e in examples}
            for e in examples:
                self.assertIsNotNone(e.counterpart_id)
                self.assertIn(e.counterpart_id, by_id)
                counter = by_id[e.counterpart_id]
                self.assertEqual(counter.counterpart_id, e.id)
                self.assertEqual(e.order + counter.order, 1)

    def test_numerical_ordering_disjoint_partitions(self):
        splits = generate_numerical_ordering(seed=42)
        dev_pairs = {tuple(sorted((e.metadata["hi"], e.metadata["lo"]))) for e in splits["dev"]}
        val_pairs = {tuple(sorted((e.metadata["hi"], e.metadata["lo"]))) for e in splits["val"]}
        holdout_pairs = {tuple(sorted((e.metadata["hi"], e.metadata["lo"]))) for e in splits["holdout"]}

        self.assertEqual(len(dev_pairs), 100)
        self.assertEqual(len(val_pairs), 100)
        self.assertEqual(len(holdout_pairs), 100)

        self.assertTrue(dev_pairs.isdisjoint(val_pairs), "Dev and Val pairs must be disjoint")
        self.assertTrue(dev_pairs.isdisjoint(holdout_pairs), "Dev and Holdout pairs must be disjoint")
        self.assertTrue(val_pairs.isdisjoint(holdout_pairs), "Val and Holdout pairs must be disjoint")

    def test_symbolic_equivalence_orthogonal_factorial_design(self):
        splits = generate_symbolic_equivalence(seed=43)
        self.assertEqual(set(splits.keys()), {"dev", "val", "holdout"})

        for split_name, examples in splits.items():
            self.assertEqual(len(examples), 200, f"Split {split_name} should have 200 examples")
            yes_count = sum(1 for e in examples if e.ground_truth_label == "Yes")
            no_count = sum(1 for e in examples if e.ground_truth_label == "No")
            order_0 = sum(1 for e in examples if e.order == 0)
            order_1 = sum(1 for e in examples if e.order == 1)

            self.assertEqual(yes_count, 100, f"Split {split_name} Yes count must be 100")
            self.assertEqual(no_count, 100, f"Split {split_name} No count must be 100")
            self.assertEqual(order_0, 100, f"Split {split_name} order 0 must be 100")
            self.assertEqual(order_1, 100, f"Split {split_name} order 1 must be 100")

            # Check exact 2x2 orthogonality: 50 in each cell
            ord0_yes = sum(1 for e in examples if e.order == 0 and e.ground_truth_label == "Yes")
            ord0_no = sum(1 for e in examples if e.order == 0 and e.ground_truth_label == "No")
            ord1_yes = sum(1 for e in examples if e.order == 1 and e.ground_truth_label == "Yes")
            ord1_no = sum(1 for e in examples if e.order == 1 and e.ground_truth_label == "No")

            self.assertEqual(ord0_yes, 50)
            self.assertEqual(ord0_no, 50)
            self.assertEqual(ord1_yes, 50)
            self.assertEqual(ord1_no, 50)

            # Check counterpart reciprocity
            by_id = {e.id: e for e in examples}
            for e in examples:
                self.assertIsNotNone(e.counterpart_id)
                self.assertIn(e.counterpart_id, by_id)
                counter = by_id[e.counterpart_id]
                self.assertEqual(counter.counterpart_id, e.id)
                self.assertEqual(e.order + counter.order, 1)
                self.assertEqual(e.ground_truth_label, counter.ground_truth_label)

    def test_relational_classification_orthogonal_factorial_design(self):
        splits = generate_relational_classification(seed=44)
        self.assertEqual(set(splits.keys()), {"dev", "val", "holdout"})

        for split_name, examples in splits.items():
            self.assertEqual(len(examples), 200, f"Split {split_name} should have 200 examples")
            yes_count = sum(1 for e in examples if e.ground_truth_label == "Yes")
            no_count = sum(1 for e in examples if e.ground_truth_label == "No")
            order_0 = sum(1 for e in examples if e.order == 0)
            order_1 = sum(1 for e in examples if e.order == 1)

            self.assertEqual(yes_count, 100, f"Split {split_name} Yes count must be 100")
            self.assertEqual(no_count, 100, f"Split {split_name} No count must be 100")
            self.assertEqual(order_0, 100, f"Split {split_name} order 0 must be 100")
            self.assertEqual(order_1, 100, f"Split {split_name} order 1 must be 100")

            # Check exact 2x2 orthogonality: 50 in each cell
            ord0_yes = sum(1 for e in examples if e.order == 0 and e.ground_truth_label == "Yes")
            ord0_no = sum(1 for e in examples if e.order == 0 and e.ground_truth_label == "No")
            ord1_yes = sum(1 for e in examples if e.order == 1 and e.ground_truth_label == "Yes")
            ord1_no = sum(1 for e in examples if e.order == 1 and e.ground_truth_label == "No")

            self.assertEqual(ord0_yes, 50)
            self.assertEqual(ord0_no, 50)
            self.assertEqual(ord1_yes, 50)
            self.assertEqual(ord1_no, 50)

            # Check counterpart reciprocity
            by_id = {e.id: e for e in examples}
            for e in examples:
                self.assertIsNotNone(e.counterpart_id)
                self.assertIn(e.counterpart_id, by_id)
                counter = by_id[e.counterpart_id]
                self.assertEqual(counter.counterpart_id, e.id)
                self.assertEqual(e.order + counter.order, 1)
                self.assertEqual(e.ground_truth_label, counter.ground_truth_label)

    def test_determinism_and_hash_integrity(self):
        d1 = load_all_datasets(seed=42)
        d2 = load_all_datasets(seed=42)

        m1 = generate_dataset_manifest(d1)
        m2 = generate_dataset_manifest(d2)

        self.assertEqual(m1["root_sha256"], m2["root_sha256"])
        self.assertEqual(m1["total_examples"], 1800)

    def test_manifest_export(self):
        datasets = load_all_datasets(seed=42)
        out_path = "artifacts/uow_native_2/dataset_manifest.json"
        manifest = generate_dataset_manifest(datasets, output_path=out_path)

        self.assertTrue(os.path.exists(out_path))
        self.assertEqual(manifest["total_examples"], 1800)
        self.assertEqual(len(manifest["families"]), 3)
        for fam_info in manifest["families"].values():
            self.assertEqual(fam_info["total_examples"], 600)
            for split_info in fam_info["splits"].values():
                self.assertEqual(split_info["count"], 200)
                self.assertEqual(split_info["counterbalanced_order_ratio"], 0.5)
                self.assertEqual(split_info["factorial_cells"]["order_0_yes"] + split_info["factorial_cells"]["order_1_yes"], split_info["yes_count"])


if __name__ == "__main__":
    unittest.main()
