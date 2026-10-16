# UOW-NATIVE-3 Local engineering instructions

The branch was created from `main`; sealed Stage 2 (`0dc8d57`) is an immutable historical reference, not merged into this branch. The original H3 Arm N-B adapter **is not in GitHub**.

## Setup

```bash
python -m pip install torch safetensors "transformers>=4.45,<5" "peft>=0.12,<1" pytest
python -m unittest discover -s experiments/uow_native_3/tests -v
```

## C0 weight integrity and C1 spectral analysis

Run on the Windows host from UoW-v3 root (substitute actual local adapter path):

```powershell
python -m experiments.uow_native_3.spectral_adapter --adapter-dir "C:\Users\nateb\OneDrive\Documents\UoW-v2\checkpoints\uow_h3_native_smollm2_135m_arm_nb" --device cuda --output artifacts/uow_native_3/spectral_report.json
```

For rank k use `--rank 1`, `--rank 2`, `--rank 4` or `--rank 8` in **separate model loads**. Current runner records weight structure and applies modifications in memory; it does not imply that operational benchmarks have run. Do not promote spectral observations into behavioral claims.

## BLOCKER for actual C0/C1 behavioral scores
Obtain the original H3 20 family-disjoint evaluation cases, decoding settings, and **exact** evaluator from UoW-v2 (including JSON validity, final disposition, exact semantic bindings, unsafe-YES classification). Confirm provenance before evaluating base and adapter variants on precisely the same cases. Do not substitute a homegrown JSON validity rubric and call historical scores reproduced.

## Controls
- Base model vs unchanged full H3 adapter.
- Rank-8 SVD reconstructed adapter must numerically match full adapter output within specified tolerance on frozen inputs before rank-1/2/4 scoring.
- Compare baseline, rank 1, 2, 4, and full rank 8 on paired held-out cases.
- New independent set required for confirmatory claims.
- C2 layer ablation and C3 actual UoW authority integration are pending implementations; do not mark qualified.
- Keep adapter weights private and local. Upload only reports, not model weights.
