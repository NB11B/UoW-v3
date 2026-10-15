"""CPU-only contract tests. No pretrained weights or network required."""
import unittest
import torch
from torch import nn
from pretrained_probe import rows, projections, ablate

class Tiny(nn.Module):
    def __init__(self):
        super().__init__()
        self.mlp=nn.Module()
        self.mlp.down_proj=nn.Linear(4,2,bias=False)
    def forward(self,x):
        return self.mlp.down_proj(x)

class TestProbe(unittest.TestCase):
    def test_projection_discovery(self):
        self.assertEqual(len(projections(Tiny())),1)

    def test_intervention_restores(self):
        model=Tiny()
        x=torch.ones((2,4))
        expected=model(x)
        with ablate(model.mlp.down_proj,0):
            actual=model(x)
            self.assertFalse(torch.equal(actual,expected))
        self.assertTrue(torch.equal(model(x),expected))

    def test_exception_does_not_leak_hook(self):
        model=Tiny()
        with self.assertRaises(RuntimeError):
            with ablate(model.mlp.down_proj,0):
                raise RuntimeError("controlled failure")
        self.assertEqual(len(model.mlp.down_proj._forward_pre_hooks),0)

    def test_deterministic_balanced_prompts(self):
        a=rows(17,20,0)
        self.assertEqual(a,rows(17,20,0))
        self.assertEqual(len(a),20)
        self.assertEqual(len({p for p,_,_ in a}),20)
        self.assertTrue(all(t!=o for _,t,o in a))

if __name__=="__main__":
    unittest.main()
