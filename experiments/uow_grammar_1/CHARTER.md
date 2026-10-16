# UOW-GRAMMAR-1: Multi-Grammar Adaptation and Deterministic UoW Composition

**Campaign Status**: OPEN / ISOLATED RESEARCH  
**Branch**: `research/uow-grammar-1-multi-adapter`  
**Parent Reference Baseline**: UOW-NATIVE-3 (`be79324`)  
**Foundation Model**: `HuggingFaceTB/SmolLM2-135M-Instruct` (frozen, revision `12fd25f77366fa6b3b4b768ec3050bf629380bac`)  
**Target Hardware**: Workstation NVIDIA RTX 5070 (CUDA)  

---

## 1. Architectural Objective

Transition the UoW neural boundary from a single operational proposal generator into a **modular family of specialized, compact grammar adapters** composed via deterministic UoW transactional machinery:

$$\text{Probabilistic Interpretation } (M_0 + \Delta W_g) \xrightarrow{\text{Typed Proposal}} \text{Deterministic UoW Authority } (\text{Certify} \to \text{Commit})$$

Instead of scaling a monolithic model, we train compact, versioned parameter updates $\Delta W_g$ ($\approx 0.92\text{ MB}$ each, $r=8$ or low-rank) on top of the shared frozen 135M foundation model, and coordinate their outputs deterministically.

---

## 2. Grammar Responsibilities

The campaign focuses on three core operational specializations:

| Grammar ($g$) | Computational Responsibility | Output IR Schema | Deterministic UoW Boundary |
| :--- | :--- | :--- | :--- |
| **Operational** | Action selection, slot binding, disposition routing | `uow.operational.v1` (`bindings`, `alternatives`, `unknowns`) | Guard satisfiability, transaction route selection |
| **Temporal** | Order, window, duration, synchronization | `uow.temporal.v1` (`order`, `window`, `deadline`, `trigger`) | Sequencer logical time, monotonic clock, lease bounds |
| **Recovery** | Failure triage, retry strategy, compensation routing | `uow.recovery.v1` (`strategy`, `retry_policy`, `compensation_uow`) | Idempotency keys, WAL rollback, saga coordinator |

---

## 3. Preregistered Research Gates

### Gate G0 — Operational Baseline & Regression Lock
- Verify local H3 adapter SHA-256 (`64d77db0...`) and base model revision.
- Evaluate base model $M_0$ and full adapter $H_{3\_full}$ on the original 20-case holdout under the authoritative UoW-v2 closure engine.
- Document and lock the rank-8 SVD numerical reconstruction control.

### Gate G1 — Independent Grammar Specialization
- Design typed schemas and family-disjoint synthetic datasets for **Temporal** and **Recovery** grammars (train/holdout partitions strictly disjoint).
- Train $\Delta W_{\text{temporal}}$ and $\Delta W_{\text{recovery}}$ independently using PEFT LoRA ($r=8, \alpha=16$, `q_proj`, `v_proj`). Base weights remain frozen.
- Acceptance criterion: Both adapters significantly exceed frozen base model performance on their respective held-out test suites ($>85\%$ valid serialization and correct structured routing).

### Gate G2 — Cross-Grammar Interference & Weight Alignment
- Measure normalized Frobenius weight-space alignment matrix across corresponding projections:
  $$\kappa(g, h) = \frac{\langle \Delta W_g, \Delta W_h \rangle_F}{\|\Delta W_g\|_F \|\Delta W_h\|_F}$$
- Evaluate all 3 adapters across all 3 grammar holdouts ($3 \times 3$ evaluation matrix) to empirically quantify specialization versus cross-grammar interference.

### Gate G3 — Deterministic UoW Multi-Grammar Composition
- Implement multi-grammar pipeline using **Architecture A (Resident Switchable Adapters)**:
  - Base model loaded once into VRAM ($\approx 270\text{ MB}$).
  - All three adapters resident; active grammar selected dynamically via `model.set_adapter(grammar_name)`.
- Compose multi-step transaction: User Signal $\to$ Temporal Parsing $\to$ Operational Proposal $\to$ Recovery Specification.
- Route proposals through authoritative deterministic UoW sequencer and saga coordinator.
- Acceptance criterion: Correct typed handoffs, valid execution traces, and **zero unauthorized state commits**.

### Gate G4 — Architecture Comparison (Switchable vs Merged)
- Construct Architecture C composite adapter: $W = W_0 + \sum_g \lambda_g \Delta W_g$ ($\lambda_g = 1/3$).
- Benchmark Architecture A (resident switchable) against Architecture C (linear combination) across:
  1. Serialization validity and semantic accuracy.
  2. Latency and memory consumption.
  3. Cross-grammar degradation/interference.
- Acceptance criterion: Provide empirical trade-off analysis determining whether weight merging is viable or if Architecture A remains the preferred production deployment.

---

## 4. Methodological Invariants
1. **Base Weights Frozen**: The underlying 135M base model is never fine-tuned or mutated.
2. **Authority Isolation**: Neural proposals never possess execution authority. All state mutations require independent deterministic validation and certification.
3. **Weight Privacy**: No raw model weights or adapter `.safetensors` will be staged or uploaded to GitHub.
4. **Disjoint Holdouts**: Holdout evaluation sets must be structurally disjoint from training distributions.
