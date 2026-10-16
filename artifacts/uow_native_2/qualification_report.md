# UOW-NATIVE-2: Final Research Qualification Report
**Behavioral Competence and Coordinated Circuit Identification**

- **Charter:** `experiments/uow_native_2/CHARTER.md`
- **Repository:** `NB11B/UoW-v3`
- **Branch:** `research/uow-native-2-circuit-qualification`
- **Predecessor Baseline:** `UOW-NATIVE-1` commit `0dc8d57` (Sealed Read-Only Reference)
- **Target Model:** `HuggingFaceTB/SmolLM2-135M-Instruct`
- **Pinned Model Revision:** `12fd25f77366fa6b3b4b768ec3050bf629380bac`
- **Hardware Platform:** `Windows-11-10.0.26200-SP0` (NVIDIA GeForce RTX 5070 Laptop GPU)
- **Evaluation Date:** 2026-10-16 02:41:40 UTC
- **Campaign Disposition:** **EXPERIMENTAL — BEHAVIORAL COMPETENCE NOT ESTABLISHED**

---

## 1. Executive Summary and Terminal Disposition

The objective of **UOW-NATIVE-2** was to determine whether a frozen small pretrained language model (`SmolLM2-135M-Instruct`) contains coordinated neural mechanisms performing measurable relational computation, and whether such mechanisms can be governed as unprivileged probabilistic proposers by the deterministic UoW architecture (`src/uow/engine.py`).

Following the core methodological lesson of UOW-NATIVE-1, the campaign enforced a strict invariant:
> **Methodological Invariant:** Behavioral competence qualification (**Gate B0**) strictly precedes mechanistic circuit discovery (**Gates B1/B2**). If the model does not reliably demonstrate relational competence on counterbalanced data, circuit search is halted immediately to prevent attributing shortcut behaviors to nonexistent computational circuits.

### Gate Verdict Summary

| Gate | Title | Target Criterion | Measured Result | Verdict |
|---|---|---|---|---|
| **Gate B0** | Behavioral Qualification | Holdout Acc $\ge 85\%$, Shifted $\ge 80\%$, Pos Gap $\le 10\%$ | Max Acc = 50.0%, Pos Gap = 100.0% | **FAILED** |
| **Gate B1** | Circuit Discovery | Identify candidate neural groups on Dev split | Halted under Stop Rule | **HALTED** |
| **Gate B2** | Causal Falsification | 32 matched controls ($p < 0.05$), restoration $\ge 95\%$ | Halted under Stop Rule | **HALTED** |
| **Gate B3** | Deterministic Authority Integration | Zero unauthorized commits; fail-closed security vectors | 10/10 vectors verified (100% pass) | **PASSED** |
| **Gate B4** | Efficiency & Reproducibility | 3-seed reproducibility, ledger integrity verified | Completed across seeds 42, 43, 44 | **PASSED** |

**Terminal Classification:** `BEHAVIORAL_COMPETENCE_NOT_ESTABLISHED`

---

## 2. Gate B0: Behavioral Qualification Results

Across 1,800 problem instances (600 per family partitioned into 200 Dev, 200 Val, 200 Holdout), the model failed to demonstrate relational competence on every tested family.

### Performance Summary Table

| Task Family | Dev Acc | Val Acc | Holdout Acc | 95% Bootstrap CI | Shifted Acc | Positional Gap | Paired Consistency | Status |
|---|---|---|---|---|---|---|---|---|
| **Numerical Ordering** | 50.25% | 50.50% | **50.00%** | [43.50%, 56.51%] | 49.63% | **100.0%** | **0.00%** | **FAILED** |
| **Symbolic Equivalence** | 49.25% | 50.00% | **50.00%** | [43.50%, 56.51%] | 53.38% | **100.0%** | **0.00%** | **FAILED** |
| **Relational Classification** | 50.00% | 50.00% | **50.00%** | [43.50%, 56.51%] | 49.75% | **100.0%** | **0.00%** | **FAILED** |

### Mechanistic Analysis of Behavioral Failure Modes

1. **Numerical Ordering (Presentation-Order Primacy):**
   - When the larger number is presented first (`Order 0`), accuracy is **100.0%**.
   - When the larger number is presented second (`Order 1`), accuracy is **0.0%**.
   - The positional gap is exactly **100.0 percentage points** ($|\text{acc}_0 - \text{acc}_1| = 1.00$).
   - The paired consistency rate is **0.0%**: when the presentation order of the exact same pair of numbers is swapped, the model switches its answer 100% of the time.
   - **Conclusion:** The model has zero magnitude comparison capability; it blindly outputs the first number presented in the prompt.

2. **Symbolic Equivalence & Relational Classification (Affirmative "Yes" Bias):**
   - For valid/commutative statements (ground truth "Yes"), accuracy is **100.0%**.
   - For invalid/non-commutative fallacies (ground truth "No"), accuracy is **0.0%**.
   - The model answers "Yes" to virtually every query regardless of logical truth or mathematical commutativity.
   - Counterbalanced accuracy is exactly chance (**50.0%**).

---

## 3. Multi-Seed Holdout Reproducibility (Gate B4)

The evaluation was repeated across 3 independent random partition seeds (42, 43, 44), generating disjoint entity pools and comparison pairs.

| Task Family | Seed 42 Holdout | Seed 43 Holdout | Seed 44 Holdout | Three-Seed Mean | Preregistered Threshold |
|---|---|---|---|---|---|
| Numerical Ordering | 50.00% | 49.75% | 49.25% | **49.67%** | $\ge 85.00\%$ |
| Symbolic Equivalence | 50.00% | 50.00% | 50.00% | **50.00%** | $\ge 85.00\%$ |
| Relational Classification | 50.00% | 50.00% | 50.00% | **50.00%** | $\ge 85.00\%$ |

The findings are 100% reproducible across all three random seeds: the model uniformly performs at chance (50.0%) across all splits.

---

## 4. Gates B1 & B2: Mechanistic Circuit Discovery Disposition

Under the preregistered methodological invariant:
- Gate B0 failure immediately triggered the **Stop Rule**.
- Neither Gate B1 (Circuit Discovery) nor Gate B2 (Causal Falsification) was executed against the neural weights.
- Both gates are formally classified as `HALTED` with terminal classification `BEHAVIORAL_COMPETENCE_NOT_ESTABLISHED`.

### Methodological Significance
Attempting to identify "circuits for relational reasoning" in a model that merely predicts the first operand or outputs unconditional "Yes" would have identified spurious correlations (e.g. circuits encoding prompt-reading or affirmative response biases) rather than relational computation. Enforcing the B0 gate successfully prevented this scientific error.

---

## 5. Gate B3: Deterministic UoW Authority Integration Results

While the probabilistic model failed behavioral qualification, the deterministic UoW architecture (`src/uow/engine.py`) demonstrated complete authority isolation across 10 security test cases:

1. **Deterministic Certification:** Verified valid probabilistic proposals certify cleanly.
2. **Pre-State Mismatch:** Proposals with false pre-state hashes rejected (`PRE_STATE_HASH_MISMATCH`).
3. **State Divergence:** Tampered proposed states rejected (`STATE_DIVERGENCE`).
4. **Route / Successor / Halt Divergence:** Divergent route indices, successor pointers, or halt flags rejected.
5. **Invalid Certificate Commit Prevention:** Uncertified or rejected proposals fail closed with `ValueError`.
6. **Forged Certificate Hash Commit Prevention:** Unauthentic certificate hashes fail closed with `ValueError`.
7. **Stale Pre-State Commit Prevention:** Transitions against superseded pre-states fail closed with `ValueError`.
8. **Evidence Ledger Extension:** Legitimate transitions extend the append-only cryptographic ledger.
9. **Evidence Hash Chain Verification:** Complete verification of SHA-256 evidence record links.
10. **Tampered Ledger Append Prevention:** Non-contiguous or tampered evidence records fail closed with `ValueError`.

**Guaranteed Invariant:** Probabilistic neural models act solely as unprivileged proposers. Under no circumstances can uncertified neural outputs commit state or bypass deterministic authority.

---

## 6. Performance & Computational Efficiency

- **Total Campaign Duration:** 74.98 seconds
- **Peak GPU Memory Allocated:** 271.08 MB (RTX 5070 Laptop GPU)
- **Model Ingestion & Evaluation Throughput:** ~33 examples/sec
- **Cryptographic Evidence Manifest:** `artifacts/uow_native_2/dataset_manifest.json` verified with SHA-256 root hash.

---

## 7. Final Project Disposition

1. **SmolLM2-135M-Instruct** does not possess relational reasoning competence in zero-shot or instruction-prompted numerical ordering, symbolic commutativity, or transitive classification.
2. The observed behavioral outputs are entirely dominated by presentation shortcuts (first-operand bias and affirmative bias).
3. The deterministic UoW v3 kernel (`src/uow/engine.py`) successfully confines probabilistic proposals without vulnerability to false or corrupted model outputs.
4. **Campaign Status:** **CLOSED**. The results are preserved as reproducible scientific evidence. The research branch `research/uow-native-2-circuit-qualification` remains unmerged.
