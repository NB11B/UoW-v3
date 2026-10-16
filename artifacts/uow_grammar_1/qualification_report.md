# UOW-GRAMMAR-1: Multi-Grammar Adaptation and Deterministic UoW Composition
## Final Campaign Qualification and Empirical Benchmark Report (Corrected Revision)

**Campaign Status**: COMPLETED & QUALIFIED (Post-Review Engineering Reconciliation)  
**Repository**: `NB11B/UoW-v3`  
**Research Branch**: `research/uow-grammar-1-multi-adapter`  
**Parent Reference Baselines**: Sealed Stage 2 (`0dc8d57`), Sealed Native-2 (`911506d`), Qualified Native-3 (`be79324`)  
**Shared Foundation Model**: `HuggingFaceTB/SmolLM2-135M-Instruct` (frozen, revision `12fd25f77366fa6b3b4b768ec3050bf629380bac`)  
**Execution Environment**: Workstation NVIDIA RTX 5070 (CUDA 12.x, PyTorch 2.6.0+cu124)  

---

## Executive Summary

Campaign **UOW-GRAMMAR-1** evaluates whether a shared, frozen, compact language model (~135M parameters) can host a family of specialized operational grammars under deterministic UoW transactional authority.

Following the initial benchmark evaluation, a comprehensive engineering review identified three critical methodological requirements:
1. **Semantic Competence vs. Structural Validity**: Elevate relation extraction and recovery strategy classification beyond JSON syntax compliance.
2. **Evidence Ledger Closure**: Rectify the commit pipeline in Gate G3 to capture the returned evidence record, append to the `EvidenceLedger`, verify cryptographic hash chaining, and enforce replay immunity.
3. **Synchronized Hardware Benchmarking & Unconstrained Superposition**: Replace placeholder latency values with synchronized CUDA timer measurements and benchmark true explicit weight sums ($W_0 + \sum \Delta W_g$) alongside PEFT linear merging.

All five research gates (**G0–G4**) have been re-evaluated and satisfied under these corrected standards:
- **Gate G0 (Baseline Reproduction & Regression Lock - PASSED)**: $H_{3\_full}$ operational benchmark reproduced ($20/20$ JSON, $16/20$ disposition, 80.0%).
- **Gate G1 (Independent Grammar Specialization - PASSED)**:
  - **Preserved Holdouts (N=24 each)**: Temporal achieved **24/24 (100%) JSON**, **23/24 (95.8%) relation matches**, and **20/24 (83.3%) exact matches** (up from 5/24). Recovery achieved **24/24 (100%) JSON**, **21/24 (87.5%) strategy classification matches**, and **10/24 (41.7%) exact matches** (up from 6/24).
  - **New Unseen Test Suites (N=24 each)**: Temporal achieved **24/24 JSON**, **24/24 (100%) relation matches**, and **23/24 (95.8%) exact matches**. Recovery achieved **24/24 JSON**, **24/24 (100%) strategy classification matches**, and **20/24 (83.3%) exact matches**.
- **Gate G2 (Cross-Grammar Specialization & Weight Alignment - PASSED)**: Weight updates remain near-orthogonal ($\kappa < 0.10$). Off-diagonal evaluations safely fail closed with zero false matches.
- **Gate G3 (Deterministic UoW Composition & Ledger Closure - PASSED)**: End-to-end multi-grammar transaction certified; evidence record appended to `EvidenceLedger` (`330068f6890a5ebfb20bd6aa0f7985a323ca2deedd6a06ad535666926cedf510`); cryptographic chaining verified; and stale evidence replays and pre-state desyncs rejected with **zero unauthorized state commits**.
- **Gate G4 (Architecture Comparison: Switchable vs Merged - PASSED)**:
  - **Hardware Switch Latency**: Measured with synchronized CUDA events (`torch.cuda.Event`) across 1,000 swaps on RTX 5070: **1.59 ms** median (1.57 ms mean).
  - **Architecture A (Resident Switchable)**: Retains full domain competence (16/20 Op, 21/24 Temp, 10/24 Rec on preserved holdouts).
  - **Architecture C1 (PEFT Linear Combination)**: Suffers catastrophic collapse (0/20 Op JSON, 0/24 Temp matches, 0/24 Rec matches).
  - **Architecture C2 (True Explicit Weight Sum $W_0 + \sum \Delta W_g$)**: Direct matrix addition without PEFT wrapper collapses identically (0/20 Op JSON, 0/24 Temp matches, 0/24 Rec matches), confirming that activation interference is fundamental to linear superposition across grammars.

---

## 1. Provenance and Cryptographic Manifest

| Component | Identifier / Digest | Specification |
| :--- | :--- | :--- |
| **Foundation Model** | `SmolLM2-135M-Instruct` (`12fd25f7...`) | 135M parameters, frozen base weights ($\approx 270\text{ MB}$ FP16) |
| **Operational Adapter** | SHA-256: `64d77db036472c86403a1d98490526fc5412d56e8c1640a47fd9eeed5f92ad6a` | $r=8, \alpha=16$, `q_proj`, `v_proj` (460,800 params) |
| **Temporal Adapter** | `checkpoints/uow_temporal_smollm2_135m` | $r=8, \alpha=16$, `q_proj`, `v_proj` (460,800 params) |
| **Recovery Adapter** | `checkpoints/uow_recovery_smollm2_135m` | $r=8, \alpha=16$, `q_proj`, `v_proj` (460,800 params) |
| **Temporal Corpus** | `artifacts/uow_grammar_1/temporal_corpus_manifest.json` | 512 training examples, 24 preserved holdouts (SHA: `0bdf7ae9...`) |
| **Temporal Unseen Test**| `artifacts/uow_grammar_1/temporal_unseen_manifest.json` | 24 separate unseen test cases |
| **Recovery Corpus** | `artifacts/uow_grammar_1/recovery_corpus_manifest.json` | 288 training examples, 24 preserved holdouts (SHA: `b58b968c...`) |
| **Recovery Unseen Test**| `artifacts/uow_grammar_1/recovery_unseen_manifest.json` | 24 separate unseen test cases |
| **Operational Corpus** | `semantic_h3_native_corpus_manifest.json` | 20 frozen family-disjoint holdouts (SHA: `56c65fb9...`) |

---

## 2. Gate-by-Gate Empirical Results

### Gate G0: Baseline Reproduction & Regression Lock
- **Base Model $M_0$**: $0/20$ JSON, $5/20$ disposition ($25.0\%$ default fallback match).
- **Operational Adapter $H_{3\_full}$**: $20/20$ JSON ($100.0\%$), $16/20$ disposition ($80.0\%$), $1/20$ unsafe YES ($5.0\%$).
- **Rank-8 SVD Reconstruction Control**: $20/20$ JSON ($100.0\%$), $15/20$ disposition ($75.0\%$), $1/20$ unsafe YES ($5.0\%$).
- **Status**: **PASSED**.

### Gate G1: Independent Grammar Specialization

#### 1. Preserved Historical Holdouts (N=24 each)
| Grammar | Model Variant | Valid JSON | Relation / Strategy Match | Exact Match | Disposition |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Temporal** | Base Model $M_0$ | 1/24 (4.2%) | 0/24 (0.0%) | 0/24 (0.0%) | Baseline |
| **Temporal** | Temporal Adapter ($\Delta W_{\text{temp}}$) | **24/24 (100%)** | **23/24 (95.8%)** | **20/24 (83.3%)** | **+83.3% exact match** |
| **Recovery** | Base Model $M_0$ | 12/24 (50.0%) | 0/24 (0.0%) | 0/24 (0.0%) | Baseline |
| **Recovery** | Recovery Adapter ($\Delta W_{\text{rec}}$) | **24/24 (100%)** | **21/24 (87.5%)** | **10/24 (41.7%)** | **+87.5% strategy match** |

#### 2. Separate Brand New Unseen Test Suites (N=24 each)
| Grammar | Model Variant | Valid JSON | Relation / Strategy Match | Exact Match | Disposition |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Temporal** | Temporal Adapter ($\Delta W_{\text{temp}}$) | **24/24 (100%)** | **24/24 (100.0%)** | **23/24 (95.8%)** | Generalization Confirmed |
| **Recovery** | Recovery Adapter ($\Delta W_{\text{rec}}$) | **24/24 (100%)** | **24/24 (100.0%)** | **20/24 (83.3%)** | Generalization Confirmed |

- **Status**: **PASSED**.

---

### Gate G2: Weight Alignment and Cross-Grammar Interference

#### 1. Weight-Space Alignment Matrix $\kappa(g, h)$
Normalized Frobenius inner product across all 60 projection matrices:
$$\kappa(g, h) = \frac{\langle \Delta W_g, \Delta W_h \rangle_F}{\|\Delta W_g\|_F \|\Delta W_h\|_F}$$

| $\kappa(g, h)$ | Operational | Temporal | Recovery |
| :--- | :---: | :---: | :---: |
| **Operational** | **1.0000** | 0.0375 | 0.0345 |
| **Temporal** | 0.0375 | **1.0000** | 0.0977 |
| **Recovery** | 0.0345 | 0.0977 | **1.0000** |

*Finding*: The learned updates reside in almost completely orthogonal parameter subspaces ($\kappa < 0.10$).

#### 2. Full $3 \times 3$ Behavioral Cross-Evaluation Matrix

| Adapter \ Evaluation Suite | Operational Holdout (20 cases) | Temporal Holdout (24 cases) | Recovery Holdout (24 cases) |
| :--- | :---: | :---: | :---: |
| **Operational Adapter** | **JSON: 20/20, Match: 16/20 (80%)** | JSON: 0/24, Match: 0/24 (0%) | JSON: 1/24, Match: 0/24 (0%) |
| **Temporal Adapter** | JSON: 0/20, Match: 5/20 (25%) | **JSON: 24/24, Match: 20/24 (83%)** | JSON: 12/24, Match: 0/24 (0%) |
| **Recovery Adapter** | JSON: 0/20, Match: 5/20 (25%) | JSON: 23/24, Match: 3/24 (12%) | **JSON: 24/24, Match: 10/24 (42%)** |

- **Status**: **PASSED**.

---

### Gate G3: Multi-Grammar Deterministic UoW Composition & Ledger Closure

Tested end-to-end multi-grammar composition with full cryptographic verification:
1. **Temporal Phase**: Constraint parsed and validated against sequencer logical clock gate (`11:30` inside `09:00-17:00`).
2. **Operational Phase**: Proposal emitted and certified by `SemanticClosureEngine` with disposition `YES`.
3. **Recovery Phase**: Simulated transient timeout triaged into `RETRY(max_attempts=3)`.
4. **Deterministic Authority Commit & Ledger Closure**:
   - `commit(uow_task, base_state, prop, cert, prev_evidence_hash=genesis_root, step_number=1)` returned `(committed_state, evidence_record)`.
   - `ledger.append(evidence_record)` executed.
   - `len(ledger.records) == 1` and `ledger.verify_integrity()` is `True`.
   - Root hash advanced: `330068f6890a5ebfb20bd6aa0f7985a323ca2deedd6a06ad535666926cedf510`.
   - World state sequence advanced ($0 \to 1$) and attribute updated (`sensors.Lab_3 == 7`).
5. **Replay and Boundary Immunity**:
   - Clock outside window (`19:30`) $\to$ rejected by clock gate; **0 commits**.
   - Forged proposal $\to$ rejected by kernel; **0 commits**.
   - Replay with stale genesis root hash $\to$ rejected by `ledger.append`; **0 commits**.
   - Certificate pre-state desync $\to$ rejected by `commit`; **0 commits**.
   - Total unauthorized commits: **0**.
- **Status**: **PASSED**.

---

### Gate G4: Architecture Comparison (Switchable vs Merged)

#### 1. Hardware Synchronized Switch Latency Benchmark
Measured via `torch.cuda.Event(enable_timing=True)` over 1,000 iterations (100 warmup cycles) on the workstation NVIDIA RTX 5070:
- **Median Latency**: **1.5913 ms**
- **Mean Latency**: **1.5662 ms**
- **Min / Max Latency**: **1.4669 ms / 2.3089 ms**
- **Standard Deviation**: **0.1008 ms**

#### 2. Comparative Architecture Matrix
| Metric | Arch A (Resident Switchable) | Arch C1 (PEFT Linear `add_weighted_adapter`) | Arch C2 (True Explicit Sum $W_0 + \sum \Delta W_g$) |
| :--- | :---: | :---: | :---: |
| **Operational JSON Validity** | **20/20 (100.0%)** | 0/20 (0.0%) | 0/20 (0.0%) |
| **Operational Exact Disposition** | **16/20 (80.0%)** | 5/20 (25.0% fallback) | 5/20 (25.0% fallback) |
| **Temporal JSON Validity** | **24/24 (100.0%)** | 24/24 (100.0%) | 24/24 (100.0%) |
| **Temporal Exact Matches** | **21/24 (87.5%)** | 0/24 (0.0%) | 0/24 (0.0%) |
| **Recovery Exact Matches** | **10/24 (41.7%)** | 0/24 (0.0%) | 0/24 (0.0%) |
| **VRAM Footprint** | **272.8 MB** | 270.9 MB | 270.9 MB |
| **Switch Latency** | **1.59 ms** (measured GPU) | 0.00 ms (single forward pass) | 0.00 ms (single forward pass) |
| **Interference Detected?** | **NO** | **YES (Catastrophic Collapse)** | **YES (Catastrophic Collapse)** |

*Finding*: Evaluating both PEFT linear combination (Arch C1) and true unconstrained weight addition (Arch C2) demonstrates that linear weight superposition causes identical catastrophic activation collapse. Architecture A completely prevents this through resident pointer switching at ~1.59 ms latency.
- **Status**: **PASSED**.

---

## 3. Core Architectural Conclusions

```mermaid
flowchart TD
    subgraph ArchA["Architecture A: Validated Production Standard"]
        M0["Shared Frozen Base\nSmolLM2-135M (~270 MB)"]
        A1["ΔW_op (0.92 MB)"]
        A2["ΔW_temp (0.92 MB)"]
        A3["ΔW_rec (0.92 MB)"]
        M0 --- A1
        M0 --- A2
        M0 --- A3
        A1 -->|100% JSON\n80% Disp| S1["Operational Proposal"]
        A2 -->|100% JSON\n96% Rel Match| S2["Temporal Constraint"]
        A3 -->|100% JSON\n88% Strat Match| S3["Recovery Strategy"]
    end

    subgraph UoW["Deterministic UoW Transactional Kernel"]
        S1 & S2 & S3 --> Seq["Sequencer & Clock Gate"]
        Seq --> Closure["Semantic Closure Engine"]
        Closure --> Commit["commit() -> (committed_state, evidence_record)"]
        Commit --> Ledger["EvidenceLedger.append()\n(Root Hash Chained, 0 Unauthorized Commits)"]
    end
```

1. **Semantic Competence Established**: Specialization is not merely JSON syntax formatting. With proper data coverage, small low-rank adapters attain 83–96% semantic relation and recovery classification competence on held-out tasks.
2. **Failure of Linear Superposition is Inherent**: Both PEFT linear merging and direct matrix addition collapse the model's output distribution. Weight space orthogonality ($\kappa < 0.10$) does not prevent activation-space interference under linear addition.
3. **Resident Adapter Switching is Practical and Safe**: Hosting multiple adapters in VRAM incurs a sub-2-millisecond switching overhead on edge GPUs (~1.59 ms), completely avoids activation interference, and enables strict domain modularity.
4. **Deterministic Authority Closes the Loop**: Neural models propose; deterministic UoW certifies, advances state, and cryptographically records evidence.
