# UOW-NATIVE-1: Terminal Qualification Report
**Stage 2: Pretrained SmolLM2 Neural-Intervention Campaign & Authority Integration**  
**Date:** 15 October 2026  
**Repository:** `https://github.com/NB11B/UoW-v3`  
**Branch:** `research/uow-native-1-goodfire-pilot`  
**Commit:** `bf3933221d545dc1e6abb18748fd7e0f82fc7ffc` (unmerged research branch)  
**Disposition:** Experimental evidence complete; not qualified for production.

---

## 1. Executive Summary & Disposition

### Final Disposition: **FALSIFIED (Causal Specialization) / QUALIFIED (Deterministic Authority Boundary)**
Overall campaign classification according to prespecified Section 8 criteria:
> **FALSIFIED / PARTIALLY SUPPORTED**: Reliable experiments contradict the prespecified hypothesis that a single hidden MLP neuron acts as a localized, specialized relational operator in the frozen SmolLM2-135M model. Concurrently, the architectural hypothesis that *untrusted probabilistic models can be safely bounded as unprivileged proposers within the deterministic UoW v3 authority kernel* is **fully demonstrated and qualified**.

### Key Findings
1. **Measurement Defect Repaired (FIX-01)**: The single-token logit-margin assumption was replaced with teacher-forced sequence log-likelihood scoring. All 18 regression tests pass without regression.
2. **Pretrained Smoke Test Passed (Gate A)**: SmolLM2-135M loaded successfully under pinned immutable revision `12fd25f77366fa6b3b4b768ec3050bf629380bac`. All candidates scored, finite margins computed, hook cleanup verified.
3. **Three-Seed Causal Campaign Executed (Gate B)**:
   - Evaluated 32 randomly sampled candidate neurons across 120 disjoint pair instances per seed (Seeds 42, 43, 44).
   - Prespecified acceptance criterion (descriptive control rank fraction $< 0.05$ across all three seeds) was **NOT MET** (Seed 42: $0.906$, Seed 43: $0.031$, Seed 44: $0.938$).
   - Model baseline accuracy on the pairwise comparison task was below chance ($\approx 41.67\%$).
   - Directional effects were inconsistent across seeds (Seed 42: $+0.00065$, Seed 43: $-0.04297$, Seed 44: $+0.00065$).
4. **Authority Isolation Qualified (Gate C)**: The real UoW v3 kernel (`src/uow/engine.py`) was evaluated across 10 critical failure and integrity vectors. Probabilistic proposals are strictly bounded: false pre-state hashes, tampered proposed states, route divergences, successor divergences, and forged certificates are fail-closed rejected with zero unauthorized commits. Cryptographic SHA-256 evidence ledger chain integrity is verified.

---

## 2. Provenance & Execution Environment

| Parameter | Recorded Value |
|---|---|
| **OS / Platform** | Windows 11 (10.0.26200-SP0) |
| **CPU Architecture** | Intel64 Family 6 Model 198 Stepping 2 (GenuineIntel) |
| **GPU Hardware** | NVIDIA GeForce RTX 5070 Laptop GPU (CUDA 12.8) |
| **Python Version** | 3.13.11 |
| **PyTorch Version** | 2.11.0.dev20260127+cu128 |
| **Transformers Version** | 5.16.1 |
| **Hugging Face Hub** | 1.29.0 |
| **Safetensors** | 0.8.0 |
| **Pytest Version** | 9.0.2 |
| **Repository Git Commit** | `bf3933221d545dc1e6abb18748fd7e0f82fc7ffc` |
| **Target Model** | `HuggingFaceTB/SmolLM2-135M-Instruct` |
| **Pinned Model Revision SHA** | `12fd25f77366fa6b3b4b768ec3050bf629380bac` |

---

## 3. Defect Diagnosis and Source Modifications

### Original Defect Record
- **Run Record:** GitHub Actions run `38832972182` (`uow-native-pretrained-smoke.yml`)
- **Exception:** `ValueError: Requires single-token numeric answers`
- **Root Cause:** The measurement logic in `pretrained_probe.py` asserted `len(ids_pos) == 1 and len(ids_neg) == 1`. For SmolLM2's GPT2-based BPE tokenizer, two-digit numbers (e.g. `" 82"` $\to$ `[216, 40, 34]`) tokenize into multi-token sequences.
- **Evidence Preservation:** Preserved in `artifacts/uow_native_1/failed_run_evidence.json`.

### Implemented Fixes
1. **FIX-01: Sequence-Level Teacher-Forced Scoring**
   - Replaced single-token indexing with:
     $$\mathcal{L}(A \mid P) = \sum_{i=1}^m \log p(a_i \mid P, a_1, \dots, a_{i-1})$$
     $$\Delta(P) = \mathcal{L}(A \mid P) - \mathcal{L}(B \mid P)$$
   - Tokenizes full prompt and candidate continuation with consistent space separator.
   - Enforces prefix validation: verified that encoded prompt is an exact prefix of prompt+candidate (`full_ids[:n] == prompt_ids`).
   - Slices causal LM logits at positions $[n-1, L-1)$ to predict target tokens $[n, L)$.
   - Reports both primary summed log likelihood and normalized log likelihood sensitivity analysis.
   - Deterministic tie handling (credit 0.5 for equal scores, with exact tie counts tracked).
   - Rejects empty continuations, prefix-boundary mismatches, and non-finite values fail-closed.
2. **FIX-02: Native Scoped Forward Hooks**
   - Retained MLP `down_proj` input-channel intervention hook with `register_forward_pre_hook`.
   - Guaranteed cleanup via context manager `finally:` blocks even upon exceptions.
3. **FIX-03: Dataset Independence & Unordered Pair Splitting**
   - Maintained disjoint unordered number pairs across selection (24), holdout (48), and shifted-template (48) sets.
4. **FIX-04: Descriptive Control Statistics & Signed Effects**
   - Explicitly separated `signed_effect` ($\Delta_{\text{base}} - \Delta_{\text{interv}}$) from `absolute_effect` ($|\text{signed_effect}|$).
   - Explicitly documented descriptive rank fraction as non-confirmatory.

---

## 4. Regression & Verification Results

All 18 regression and contract tests passed with zero failures:

| Test Case | Method / Guard | Result |
|---|---|---|
| Single-token numerical answer | Analytical log-softmax match | **PASS** |
| Multi-token numerical answer | Multi-position sum log-likelihood | **PASS** |
| Unequal candidate token lengths | Differing candidate sequence evaluation | **PASS** |
| Prefix-boundary mismatch | Explicit rejection (`ValueError`) | **PASS** |
| Empty continuation | Explicit rejection (`ValueError`) | **PASS** |
| Equal candidate scores | Correct tie handling (margin=0.0, acc=0.5) | **PASS** |
| Ablation changes intended activation | Demonstration on linear MLP projection | **PASS** |
| Ablation cleanup after exception | Verified zero leaked hooks in `finally:` | **PASS** |
| Distinct selection/holdout pairs | Zero pair overlap across partitions | **PASS** |
| Repeat with identical seed | 100% reproducible partition output | **PASS** |
| Missing or invalid model revision | Fail closed on invalid/short SHA | **PASS** |
| Nonfinite likelihood or margin | Explicit rejection of NaN/Inf | **PASS** |
| Synthetic relational baseline tests | Fail-closed gate and reproducible probe | **PASS** |

Recorded in `artifacts/uow_native_1/regression_results.json`.

---

## 5. Gate A: Corrected Pretrained Smoke Test

- **Configuration:** Seed 42, 4 selection / 4 holdout / 4 shifted pairs, 3 candidate neurons.
- **Model Layer:** `model.layers.29.mlp.down_proj` (in_features = 1536)
- **Selected Unit:** Neuron 899
- **Execution Time:** 4.82 seconds (RTX 5070 GPU)
- **Status:** **PASS** (all outputs finite, model loaded, hooks cleaned, provenance captured).
- **Artifact:** `artifacts/uow_native_1/smoke_corrected.json`.

---

## 6. Gate B: Three-Seed Causal Intervention Campaign

### Experimental Design
- **Seeds:** 42, 43, 44
- **Partition Sizes per Seed:** Selection: 24 pairs, Holdout: 48 pairs, Shifted Template: 48 pairs (120 disjoint pairs per seed)
- **Intervention Site:** Last MLP down-projection: `model.layers.29.mlp.down_proj`
- **Candidate Pool:** 32 randomly sampled hidden neurons per seed
- **Selection Decision:** Unit with maximum absolute training-margin drop; choice frozen prior to holdout evaluation.

### Measured Empirical Data

| Seed | Selected Neuron | Baseline Holdout Acc | Baseline Margin | Intervened Holdout Acc | Intervened Margin | Signed Effect | Absolute Effect | Descriptive Control Rank | Shift Baseline Acc | Shift Interv Acc | Execution Time |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **42** | 525 | 39.58% | -0.2630 | 43.75% | -0.2637 | +0.00065 | 0.00065 | **0.9062** | 54.17% | 53.12% | 149.7 s |
| **43** | 645 | 41.67% | -0.1439 | 44.79% | -0.1009 | -0.04297 | 0.04297 | **0.0312** | 54.17% | 54.17% | 143.0 s |
| **44** | 1501 | 43.75% | -0.1602 | 43.75% | -0.1595 | +0.00065 | 0.00065 | **0.9375** | 52.08% | 52.08% | 129.5 s |
| **Mean**| — | **41.67%** | **-0.1890** | **44.10%** | **-0.1747** | **-0.01389** | **0.01476** | **0.6250** | **53.47%** | **53.12%** | **422.2 s** |

### Scientific Analysis of Causal Hypothesis
1. **Task Baseline Competence:** SmolLM2-135M demonstrates an average accuracy of only **41.67%** on the relational prompt template, which is at or below the 50% random chance baseline.
2. **Control Rank Threshold Failure:** The preregistered exploratory criterion required descriptive rank fraction $< 0.05$ across **all three seeds**. Only Seed 43 met this condition ($0.0312$), whereas Seeds 42 ($0.9062$) and 44 ($0.9375$) were in the bottom decile of control effects.
3. **Directional Inconsistency:** In Seed 43, zeroing neuron 645 produced a **negative signed effect** ($-0.04297$), meaning zeroing the neuron actually *improved* model accuracy and margin rather than impairing it. Seeds 42 and 44 produced negligible positive effects ($+0.00065$).
4. **Conclusion on Neural Modularity:** There is no evidence that individual hidden channels in `down_proj` of SmolLM2-135M represent isolated, reusable relational comparison circuits. The scientific hypothesis is **falsified** for this architecture.

Artifacts: `artifacts/uow_native_1/seed_42.json`, `seed_43.json`, `seed_44.json`, `causal_summary.json`.

---

## 7. Gate C: Independent UoW Authority Integration

The probabilistic model proposals were evaluated against the authoritative UoW kernel in `src/uow/engine.py`. Probabilistic models act solely as unprivileged proposal generators with zero authority:

| Test Vector | Expected Kernel Behavior | Observed Behavior | Gate Status |
|---|---|---|:---:|
| Valid relational proposal | Deterministic certification issued | `is_valid=True`, valid certificate hash | **PASS** |
| False pre-state hash | `PRE_STATE_HASH_MISMATCH` rejection | Rejected, no certificate issued | **PASS** |
| Corrupted / tampered proposed state | `STATE_DIVERGENCE` rejection | Rejected, certificate denied | **PASS** |
| Mismatched route index | `ROUTE_DIVERGENCE` rejection | Rejected | **PASS** |
| Unauthorized successor | `SUCCESSOR_DIVERGENCE` rejection | Rejected | **PASS** |
| Mismatched halt flag | `HALT_DIVERGENCE` rejection | Rejected | **PASS** |
| Attempt commit with rejected certificate | `ValueError` fail closed | Transition blocked, ledger unmodified | **PASS** |
| Attempt commit with forged certificate hash | `ValueError: Certificate hash is not authentic` | Blocked fail closed | **PASS** |
| Attempt commit with stale pre-state | `ValueError: Certificate is not bound` | Blocked fail closed | **PASS** |
| Legitimate certified commitment | Extends `EvidenceLedger` with hash record | Sequence incremented, record appended | **PASS** |
| Hash chain verification | `EvidenceLedger.verify_integrity()` | Cryptographic SHA-256 chain verified | **PASS** |
| Tampered / non-contiguous ledger record | `ValueError: step number is not contiguous` | Rejection confirmed | **PASS** |

Artifact: `artifacts/uow_native_1/authority_integration.json`.

---

## 8. Gate Compliance & Acceptance Evaluation

| Gate | Criterion | Status |
|---|---|:---:|
| **Gate A: Execution Integrity** | Corrected regression suite & smoke test pass cleanly | **PASS** |
| **Gate B: Causal Specialization** | Reproducible held-out causal effect with rank fraction $< 0.05$ across 3 seeds | **FALSIFIED** |
| **Gate C: Authority Isolation** | Zero unauthorized or invalid commits; fail-closed rejection | **PASS** |
| **Gate D: Evidence Integrity** | Immutable SHA-256 evidence ledger hash chain verified | **PASS** |
| **Gate E: Generalization** | Shifted-template evaluation measured across all seeds | **PASS** |
| **Gate F: Reproducibility** | Three independently seeded runs (42, 43, 44) recorded | **PASS** |
| **Gate G: Efficiency** | Latency and memory measured; no untested efficiency claims | **PASS** |

---

## 9. Explicit Scope Exclusions & Limitations

1. **No Production Qualification:** These results are experimental and do not qualify neural-probabilistic components for production UoW runtimes.
2. **No Claim of Single-Neuron Executable Modules:** The data contradicts the claim that individual neurons function as independent modular micro-operators.
3. **No Goodfire Replication Claim:** This test was conducted on SmolLM2-135M using an unaugmented prompt margin probe; it does not claim to replicate Goodfire's Sparse Autoencoder (SAE) findings.
4. **No Energy or Efficiency Inferences:** No computational or energy savings are claimed.
5. **No Production Modifications:** Core authority, engine, protocol, and transport files remain unmodified. The research branch `research/uow-native-1-goodfire-pilot` remains clean and unmerged.
