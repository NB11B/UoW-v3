"""Unit tests for causal_interventions.py."""

import unittest
import torch
import torch.nn as nn
from experiments.uow_native_2.causal_interventions import (
    ablate_neurons,
    find_mlp_projections,
    restore_activations,
)


class DummyMLP(nn.Module):
    def __init__(self):
        super().__init__()
        self.down_proj = nn.Linear(16, 8, bias=False)


class DummyModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.mlp = DummyMLP()

    def forward(self, x):
        return self.mlp.down_proj(x)


class TestInterventions(unittest.TestCase):
    def test_find_mlp_projections(self):
        model = DummyModel()
        projs = find_mlp_projections(model)
        self.assertIn("mlp.down_proj", projs)

    def test_ablate_neurons(self):
        linear = nn.Linear(8, 4, bias=False)
        linear.weight.data.fill_(1.0)
        x = torch.ones((1, 8))

        # Unablated output should be 8 * 1 = 8.0 for all 4 features
        out_normal = linear(x)
        self.assertTrue(torch.allclose(out_normal, torch.tensor([8.0] * 4)))

        # Ablate indices 0, 1, 2 (3 neurons) -> remaining 5 * 1 = 5.0
        with ablate_neurons(linear, [0, 1, 2]):
            out_ablated = linear(x)
            self.assertTrue(torch.allclose(out_ablated, torch.tensor([5.0] * 4)))

        # After context exit, hook removed
        out_restored = linear(x)
        self.assertTrue(torch.allclose(out_restored, torch.tensor([8.0] * 4)))

    def test_restore_activations(self):
        linear = nn.Linear(4, 2, bias=False)
        linear.weight.data.fill_(1.0)
        original_x = torch.tensor([[10.0, 10.0, 10.0, 10.0]])
        corrupted_x = torch.zeros((1, 4))

        with restore_activations(linear, original_x, [0, 1]):
            # Features 0 and 1 are restored from original_x (10 + 10 = 20), features 2 and 3 remain 0
            out = linear(corrupted_x)
            self.assertTrue(torch.allclose(out, torch.tensor([20.0, 20.0])))


if __name__ == "__main__":
    unittest.main()
