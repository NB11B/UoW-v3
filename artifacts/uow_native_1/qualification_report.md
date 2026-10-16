# UOW-NATIVE-1: Terminal Qualification Report
**Stage 2: Pretrained SmolLM2 Neural-Intervention Campaign & Authority Integration**  
**Date:** 15 October 2026  
**Repository:** `https://github.com/NB11B/UoW-v3`  
**Branch:** `research/uow-native-1-goodfire-pilot` (unmerged research branch)  
**Commit:** `9e6f0a881cced3458dadfc3d7e34692fe5d51d98`  
**Model:** `HuggingFaceTB/SmolLM2-135M-Instruct`  
**Pinned Model Revision SHA:** `12fd25f77366fa6b3b4b768ec3050bf629380bac`  
**Disposition:** Experimental evidence complete; not qualified for production.

---

## 1. Executive Summary & Disposition

### Final Disposition: **INCONCLUSIVE (Relational Circuit Hypothesis) / UNMET (Single-Neuron Criterion) / QUALIFIED (Deterministic Authority Boundary)**
Overall campaign classification based on empirical evidence and audit review:
> 1. **Measurement Implementation**: **VERIFIED** — Sequence-level teacher-forced answer scoring is mathematically sound, bounds-checked, and passes 18/18 regression tests.  
> 2. **Single-Neuron Acceptance Criterion**: **NOT MET** — Zero-ablation of individual MLP hidden channels did not satisfy the prespecified causal effect criteria ($<0.05$ rank fraction) across all seeds.  
> 3. **Underlying Relational-Circuit Hypothesis**: **INCONCLUSIVE** — The experiment rejects the tested single-neuron specialization criterion on this prompt format, but does not falsify relational computation in neural networks generally. The underlying model exhibited strong presentation-order primacy bias and near-chance baseline accuracy ($\approx 41.67\%$), meaning the target relational comparison behavior was not reliably demonstrated prior to intervention.  
> 4. **Deterministic Authority Boundary**: **QUALIFIED (Within Local Scope)** — The production UoW v3 kernel (`src/uow/engine.py`) strictly bounds probabilistic outputs as unprivileged proposals. Zero unauthorized commits occur under false pre-state hashes, tampered states, or forged certificates.

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
| **Repository Git Commit** | `9e6f0a881cced3458dadfc3d7e34692fe5d51d98` |
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

| Seed | Selected Neuron | Baseline Holdout Acc | Baseline Margin | Intervened Holdout Acc | Intervened Margin | Signed Effect | Absolute Effect | Descriptive Control Rank | Shift Baseline Acc | Shift Interv Acc | Latency |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **42** | 525 | 39.58% | -0.2630 | 43.75% | -0.2637 | +0.00065 | 0.00065 | **0.9062** | 54.17% | 53.12% | 149.7 s |
| **43** | 645 | 41.67% | -0.1439 | 44.79% | -0.1009 | -0.04297 | 0.04297 | **0.0312** | 54.17% | 54.17% | 143.0 s |
| **44** | 1501 | 43.75% | -0.1602 | 43.75% | -0.1595 | +0.00065 | 0.00065 | **0.9375** | 52.08% | 52.08% | 129.5 s |
| **Mean**| — | **41.67%** | **-0.1890** | **44.10%** | **-0.1747** | **-0.01389** | **0.01476** | **0.6250** | **53.47%** | **53.12%** | **422.2 s** |

---

## 7. Audit Findings & Methodological Analysis

### A. Mathematical Reconciliation of Accuracy & Tied Margins
In Seed 42, a question arose regarding the reconciliation of 18 correct choices out of 48 with the recorded 39.58% accuracy. The audit decomposed the exact per-example margins:
* **Condition A (Larger number first in prompt, $j$ even, $n=24$):**
  * Strict wins ($\Delta > 0$): 18
  * Ties ($\Delta = 0.0$): 1
  * Losses ($\Delta < 0$): 5
* **Condition B (Larger number second in prompt, $j$ odd, $n=24$):**
  * Strict wins ($\Delta > 0$): 0
  * Ties ($\Delta = 0.0$): 1
  * Losses ($\Delta < 0$): 23
* **Exact Total Reconciliation:**
  $$\text{Accuracy} = \frac{\text{Wins} + 0.5 \times \text{Ties}}{48} = \frac{18 + 0.5 \times 2}{48} = \frac{19.0}{48} = 39.5833\%$$
  The recorded ties field (`ties: 2`) accounts exactly for the difference between $18/48 = 37.50\%$ and $39.58\%$.

### B. Prompt Presentation-Order Primacy Bias
The breakdown above reveals that SmolLM2-135M does not execute genuine numerical comparison on this prompt template:
* When the larger number is presented first: it selects the larger number **18/24 times (75%)**.
* When the larger number is presented second: it selects the larger number **0/24 times (0%)**.
The model is primarily exhibiting an **echo / primacy bias** favoring the first number mentioned. Because `independent_splits` strictly counterbalances presentation order, the aggregate accuracy is near chance ($41.67\%$).
* **Scientific consequence:** The intervention failure does not establish that neural networks lack relational mechanisms; rather, **the underlying model did not reliably perform the relational behavior before intervention**.

### C. Intervention Scope Across Token Positions
The current forward-pre-hook zeros a single hidden channel across *all* sequence token positions $[0, L)$. While this proves channel-level intervention feasibility, it cannot distinguish:
1. Parsing numerical tokens in the prompt.
2. Interpreting the task template instructions.
3. Formulating the comparative decision.
4. Emitting the continuation numerals.
Future causal investigations should employ token-position-scoped interventions (e.g. activation patching focused on operand or decision tokens).

---

## 8. Gate C: Independent UoW Authority Integration

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

## 9. Gate Compliance Summary

| Gate | Requirement | Disposition |
|---|---|:---:|
| **Gate A: Execution Integrity** | Corrected regression suite & smoke test pass cleanly | **PASS** |
| **Gate B: Causal Specialization** | Held-out rank fraction $< 0.05$ across 3 seeds with consistent direction | **NOT MET** |
| **Gate C: Authority Isolation** | Zero unauthorized commits; fail-closed rejection on invalid proposals | **PASS** |
| **Gate D: Evidence Integrity** | Valid SHA-256 evidence ledger hash chain | **PASS** |
| **Gate E: Generalization** | Shifted-template evaluation measured across all seeds | **PASS** |
| **Gate F: Reproducibility** | Three independently seeded runs (42, 43, 44) recorded | **PASS** |
| **Gate G: Efficiency** | Latency and hardware measured; no untested efficiency claims | **PASS** |

---

## 10. Recommendations & Next Directions

1. **Stage 2 Closure:** Stage 2 is formally closed as a completed, rigorous investigation. The prespecified single-neuron specialization criterion was not met on the frozen SmolLM2-135M model. These negative findings are preserved rather than extended through ad-hoc threshold shifting.
2. **Behavioral Qualification Prerequisite for Future Campaigns:** Any future investigation must first establish **behavioral competence qualification**:
   * Verify that the language model can perform the target relational task with accuracy significantly above chance under strictly counterbalanced orderings.
   * Only after baseline competence is qualified should circuit-level interventions be conducted.
3. **Multi-Neuron & Circuit Hypotheses:** Subsequent research should explore whether small coordinated sub-networks (circuits) or SAE features represent relational functions, treated as a newly formulated research hypothesis.
4. **Architectural Governance Preserved:** The core UoW architectural principle is reaffirmed: probabilistic components can supply candidate state proposals safely within deterministic UoW authority boundaries.
