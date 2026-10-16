"""Synthetic SVD regression tests; never substitutes for H3 evaluation."""
import unittest
import torch
from experiments.uow_native_3.spectral_adapter import truncate_factors, svd_spectrum, apply_rank

class FakeLoRA(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.lora_A = torch.nn.ModuleDict({"default": torch.nn.Linear(5, 3, bias=False)})
        self.lora_B = torch.nn.ModuleDict({"default": torch.nn.Linear(3, 4, bias=False)})
        self.scaling = {"default": 2.0}

class FakeLayer(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.q_proj=FakeLoRA()
        self.v_proj=FakeLoRA()

class FakeModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.model=torch.nn.Module()
        self.model.layers=torch.nn.ModuleList([FakeLayer(),FakeLayer()])

class TestSpectralAdapter(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(91)
        self.A=torch.randn(3,5)
        self.B=torch.randn(4,3)
    def test_full_rank_reconstruct(self):
        a,b=truncate_factors(self.A,self.B,3)
        torch.testing.assert_close(b@a,self.B@self.A,rtol=1e-5,atol=1e-5)
    def test_rank_truncation(self):
        original=self.B@self.A
        for k in (0,1,2,3):
            a,b=truncate_factors(self.A,self.B,k)
            self.assertLessEqual(torch.linalg.matrix_rank(b@a).item(),k)
            if k==0:
                self.assertTrue(torch.count_nonzero(b@a)==0)
            else:
                s=torch.linalg.svdvals(original)
                target=(s[k:].square().sum()).sqrt()
                observed=torch.linalg.matrix_norm(original-b@a)
                torch.testing.assert_close(observed,target,atol=1e-4,rtol=1e-4)
    def test_invalid_rank_or_shape(self):
        with self.assertRaises(ValueError): truncate_factors(self.A,self.B,4)
        with self.assertRaises(ValueError): truncate_factors(self.A,self.B[:,:2],1)
    def test_spectral_energy_bounds(self):
        report=svd_spectrum(self.A,self.B,2.)
        self.assertGreaterEqual(report["top1_energy"],0.)
        self.assertLessEqual(report["top2_energy"],1.00001)
        self.assertGreaterEqual(report["top2_energy"],report["top1_energy"])
    def test_layer_selection_isolated(self):
        model=FakeModel()
        before=model.model.layers[1].q_proj.lora_A["default"].weight.detach().clone()
        changed=apply_rank(model,0,layers={0})
        self.assertEqual(len(changed),2)
        torch.testing.assert_close(model.model.layers[1].q_proj.lora_A["default"].weight,before)
        self.assertEqual(torch.count_nonzero(model.model.layers[0].q_proj.lora_A["default"].weight).item(),0)

if __name__=="__main__":unittest.main()
