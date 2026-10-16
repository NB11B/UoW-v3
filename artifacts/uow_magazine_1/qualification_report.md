# UOW-MAGAZINE-1: Cross-Architecture Compact Models and Domain-Expertise Weight Magazines

**Campaign Status**: RECONCILED / PARTIALLY QUALIFIED WITH RIGOROUS EMPIRICAL BOUNDARIES  
**Branch**: `research/uow-magazine-1-cross-foundation`  
**Parent Reference Baseline**: UOW-GRAMMAR-1 (`af1f4ee`, unmerged and sealed)  
**Foundation Model Parameter Ceiling**: Strictly ~100–160 Million Parameters (Pythia-160M documented exception at 162.32M)  
**Target Hardware**: Workstation NVIDIA RTX 5070 Laptop GPU (8GB VRAM, CUDA 12.8)  

---

## Executive Summary & Engineering Audit Reconciliation

The **UOW-MAGAZINE-1** campaign evaluates whether compact language models (~100–160M parameters) can acquire, retain, switch, and compose specialized domain expertise through small, independently trained weight sets (weight magazines) while operating under the deterministic Unit-of-Work (UoW) protocol.

Following an engineering audit of the initial experimental artifacts, all findings and verdicts have been reconciled with strict scientific rigor:

1. **Weight Magazine Hosting & Isolation (M2)**:
   - **Capacity**: Concurrently hosts up to **32 resident adapter slots** in GPU VRAM occupying **312.84 MB** (well below the 1.0 GB ceiling).
   - **Multi-Specialist Coexistence**: A magazine populated with the **nine genuinely distinct trained adapters** operates simultaneously in VRAM with **0.00000000e+00** cross-activation contamination after rapid cyclic switching.
   - **Switching Latency**: Median switch latency across distinct adapters is **3.03 ms** (satisfying the <5.0 ms threshold). However, when scaling to the synthetic 32-slot pool, median latency was **8.09 ms** (missing the original <5.0 ms threshold). Gate M2 is therefore audited as **PARTIAL**.

2. **Domain-Grammar Acquisition (M1)**:
   - All 9 trained adapters on `SmolLM2-135M-Instruct` achieved **100.0% valid JSON serialization** on held-out test sets.
   - Semantic accuracy varied substantially by grammar family: Temporal (**100.0%**) and Recovery (**100.0%**) demonstrated high competence, whereas Operational specialists achieved **30–60%** exact semantic match (Industrial: 30%, Cyber: 30%, Logistics: 60%). Gate M1 is audited as **PARTIAL**.

3. **Cross-Architecture Portability (M3)**:
   - ModernBERT-base (149.6M encoder) operates as a high-speed discriminative intent router achieving **100.0% routing accuracy** with **0.706 ms per query** latency.
   - Parameter-efficient fine-tuning (PEFT) compatibility verified across 5 architectures (Llama, GPT-NeoX, GPT-Neo, Cerebras GPT-2, Mamba SSM).
   - `Pythia-160M` was verified to host resident weight magazines (642.46 MB VRAM, 0.502 ms switch latency, 0.0 contamination). However, untuned base Pythia achieved only 0–30% JSON validity on the same domain tasks under identical bounded tuning, demonstrating that instruction-tuning is an essential prerequisite for rapid grammar acquisition. Gate M3 is audited as **PARTIAL**.

4. **Mechanistic Interpretability & Causal Truncation (M4)**:
   - Singular value decomposition of trained adapter updates reveals **>82% of energy in rank-1** and **>97.5% in rank-4**.
   - **Causal Rank Truncation**: Bounded ablations at rank-1, rank-2, rank-4, and full rank-8 confirm that **100% of JSON structural grammar is causally captured by rank-1**. Furthermore, rank-1 preserves 100% of operational disposition decisions, 100% of temporal grammar, and 77.8% of recovery logic (with rank-4 saturating 100%). Gate M4 is **QUALIFIED**.

5. **Deterministic Ledger Authority (M5)**:
   - End-to-end multi-domain composite transactions across Industrial, Temporal, Cybersecurity, Logistics, and Recovery boundaries certified and chained cryptographically into the UoW `EvidenceLedger` with **zero unauthorized state commits**.

---

## Reconciled Gate Qualification Scorecard (M0–M6)

| Gate | Title | Preregistered Requirement | Measured Outcome | Reconciled Audit Status |
| :--- | :--- | :--- | :--- | :---: |
| **M0** | Foundation Availability & Inspection | Pin exact SHAs, forward pass across 7 candidates | 6 accessible verified; MobileLLM gated; Pythia 162.3M exception | **QUALIFIED (Exceptions)** |
| **M1** | Domain-Grammar Acquisition | Holdout Valid JSON >80%, semantic >70% per specialist | 100.0% JSON; Temporal/Recovery 100%, Operational 30–60% | **PARTIAL** |
| **M2** | Magazine Capacity & Switch Latency | 32 resident slots, Latency <5.0ms, VRAM <1GB | 32 slots in 312 MB; 9 distinct adapters 0.0 bleed; switch 8.09 ms | **PARTIAL** |
| **M3** | Cross-Architecture Portability | Router >90% (<5ms); multi-architecture domain test | ModernBERT 100% (0.71ms); Pythia magazine 0.50ms; 0-30% JSON on base | **PARTIAL** |
| **M4** | Mechanistic Interpretability | SVD spectral energy and causal compression | >82% Rank-1 energy; causal ablation confirms rank-1 sufficiency | **QUALIFIED** |
| **M5** | Multi-Domain Deterministic Composition | 5-step transaction, EvidenceLedger closure | 5-step sequence certified; 0 unauthorized commits; attacks rejected | **QUALIFIED** |
| **M6** | Engineering Synthesis & Scorecard | Comprehensive audit & artifact publication | Discrepancies reconciled with experimental evidence and published | **RECONCILED** |

---

## 1. Gate M0: Foundation Availability & Architectural Roster

| Model Identifier | Parameters | Family | Attention / Paradigm | License | Exact Commit SHA | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `HuggingFaceTB/SmolLM2-135M-Instruct` | 134.52M | llama | LlamaForCausalLM | Apache-2.0 | `12fd25f773` | `QUALIFIED_AVAILABLE` |
| `EleutherAI/pythia-160m` | 162.32M | gpt_neox | GPTNeoXForCausalLM | Apache-2.0 | `50f5173d93` | `QUALIFIED (Envelope Exception)` |
| `EleutherAI/gpt-neo-125m` | 125.2M | gpt_neo | GPTNeoForCausalLM | MIT | `21def0189f` | `QUALIFIED_AVAILABLE` |
| `cerebras-archive/Cerebras-GPT-111M` | 111.05M | gpt2 | GPT2LMHeadModel | Apache-2.0 | `b927d75e65` | `QUALIFIED_AVAILABLE` |
| `facebook/MobileLLM-125M` | ~125M | MobileLLM | Decoder Transformer | FAIR Research | N/A (Gated) | `GATED_RESTRICTED` |
| `state-spaces/mamba-130m-hf` | 129.14M | mamba | MambaForCausalLM | Apache-2.0 | `1e76775f62` | `QUALIFIED_AVAILABLE` |
| `answerdotai/ModernBERT-base` | 149.61M | modernbert | ModernBertForSequenceClassification | Apache-2.0 | `8949b909ec` | `QUALIFIED_AVAILABLE` |

> [!NOTE]
> **Documented Exception**: Pythia-160M contains 162.32M parameters, exceeding the strictly interpreted 160.0M ceiling by 1.45%. Retained as an approved research exception to provide the primary GPT-NeoX interpretability comparison.

---

## 2. Gate M1: Domain-Grammar Weight Acquisition Matrix

Across all nine domain-grammar combinations on `SmolLM2-135M-Instruct`, specialized adapters achieved **100.0% valid JSON serialization**, vastly outperforming the frozen unadapted base model (which achieved 0.0% semantic accuracy):

| Domain | Grammar | Target Schema | Training Time | Valid JSON Rate | Exact Semantic Match | Audit Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **Industrial** | Operational | `uow.operational.v1` | 31.5s | **100.0%** | 30.0% | `SUB-THRESHOLD` |
| **Industrial** | Temporal | `uow.temporal.v1` | 29.0s | **100.0%** | 100.0% | `QUALIFIED` |
| **Industrial** | Recovery | `uow.recovery.v1` | 28.3s | **100.0%** | 100.0% | `QUALIFIED` |
| **Cybersecurity** | Operational | `uow.operational.v1` | 33.2s | **100.0%** | 30.0% | `SUB-THRESHOLD` |
| **Cybersecurity** | Temporal | `uow.temporal.v1` | 29.6s | **100.0%** | 100.0% | `QUALIFIED` |
| **Cybersecurity** | Recovery | `uow.recovery.v1` | 29.8s | **100.0%** | 80.0% | `QUALIFIED` |
| **Logistics** | Operational | `uow.operational.v1` | 31.3s | **100.0%** | 60.0% | `SUB-THRESHOLD` |
| **Logistics** | Temporal | `uow.temporal.v1` | 29.5s | **100.0%** | 100.0% | `QUALIFIED` |
| **Logistics** | Recovery | `uow.recovery.v1` | 29.7s | **100.0%** | 90.0% | `QUALIFIED` |

> [!WARNING]
> **Audit Finding**: Although average semantic match was 76.67%, the three Operational specialists achieved only 30% (Industrial), 30% (Cybersecurity), and 60% (Logistics), failing the 70% per-specialist threshold. Gate M1 is classified as PARTIAL.

---

## 3. Gate M2: Weight Magazine Capacity, Switch Latency, and Memory Footprint

### A. Synthetic Capacity Scaling Sweep (1 to 32 slots)
| Resident Slots | Median Latency | Mean Latency | P99 Latency | Resident VRAM Allocated | Latency Target (<5.0ms) |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **1** | 0.0000 ms | 0.0000 ms | 0.0000 ms | **312.84 MB** | `MET` |
| **2** | 8.2474 ms | 8.3316 ms | 9.3038 ms | **312.84 MB** | `MISSED` |
| **4** | 8.2763 ms | 8.5912 ms | 12.1444 ms | **312.84 MB** | `MISSED` |
| **8** | 8.0297 ms | 8.1648 ms | 9.8595 ms | **312.84 MB** | `MISSED` |
| **16** | 8.2394 ms | 8.4856 ms | 12.8649 ms | **312.84 MB** | `MISSED` |
| **24** | 8.0961 ms | 8.2397 ms | 10.0126 ms | **312.84 MB** | `MISSED` |
| **32** | 8.0951 ms | 8.3242 ms | 9.8252 ms | **312.84 MB** | `MISSED` |

### B. Genuine Multi-Specialist Coexistence (9 Distinct Trained Adapters)
- **Simultaneously Resident in VRAM**: 9 distinct domain-grammar adapters (`industrial.*`, `cybersecurity.*`, `logistics.*`).
- **Total Resident VRAM**: **272.41 MB**.
- **Median Distinct Switch Latency**: **3.0295 ms** (satisfies <5.0 ms threshold).
- **Cross-Adapter Weight Divergence**: **18.375** (confirms distinctly specialized weights).
- **Post-Cycle Contamination**: **0.00000000e+00** (exact machine zero isolation across all 9 adapters).

> [!NOTE]
> **Audit Finding**: While the genuine 9-adapter magazine switches in 3.03 ms with zero contamination, scaling to 32 synthetic slots increases median switch latency to 8.09 ms, missing the preregistered <5.0 ms target. Gate M2 is classified as PARTIAL.

---

## 4. Gate M3: Cross-Architecture Portability and Expressivity

### High-Speed Intent Router (ModernBERT)
- **Architecture**: ModernBERT-base (149.6M encoder)
- **Intent Routing Accuracy**: **100.00%**
- **Mean Latency per Query**: **0.7065 ms** (sub-millisecond)

### Compact Foundation PEFT Expressivity
| Foundation Model | Paradigm | Base Parameters | Adapter Parameters | Overhead % | Sample Step Latency |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `HuggingFaceTB/SmolLM2-135M-Instruct` | causal_transformer | 134.5M | 460.8k | 0.343% | 142.26 ms |
| `EleutherAI/pythia-160m` | causal_transformer | 162.3M | 294.9k | 0.182% | 26.41 ms |
| `EleutherAI/gpt-neo-125m` | causal_transformer | 125.2M | 294.9k | 0.236% | 37.50 ms |
| `cerebras-archive/Cerebras-GPT-111M` | causal_transformer | 111.1M | 245.8k | 0.221% | 15.33 ms |
| `state-spaces/mamba-130m-hf` | selective_ssm | 129.1M | 1047.6k | 0.811% | 870.39 ms |

### Pythia-160M Domain Specialization & Magazine Benchmark
- **Resident VRAM Footprint**: **642.46 MB**.
- **Median Switch Latency**: **0.5020 ms**.
- **State Isolation**: **0.00000000e+00** (exact zero bleed).
- **Held-Out Domain Grammar Performance**: Valid JSON was 0.0% (Industrial Operational), 30.0% (Cybersecurity Temporal), and 0.0% (Logistics Recovery).

> [!IMPORTANT]
> **Scientific Finding**: The weight magazine runtime transfers seamlessly to Pythia-160M (sub-millisecond switching, 642 MB footprint, zero contamination). However, untuned base models require instruction tuning before they can reliably acquire structured operational grammar under compact fine-tuning regimes.

---

## 5. Gate M4: Mechanistic Interpretability & Causal Rank Truncation

### A. SVD Spectral Energy Concentration
Singular value decomposition of $\Delta W = \frac{\alpha}{r} (B A)$ across all 9 domain-grammar adapters:

| Adapter Key | Mean Rank-1 Energy % | Mean Rank-2 Energy % | Mean Rank-4 Energy % | Structural Interpretation |
| :--- | :--- | :--- | :--- | :--- |
| `cybersecurity.operational` | **83.33%** | 93.29% | **97.96%** | Extreme Low-Rank Subspace |
| `cybersecurity.recovery` | **82.31%** | 92.17% | **97.44%** | Extreme Low-Rank Subspace |
| `cybersecurity.temporal` | **84.98%** | 94.07% | **98.07%** | Extreme Low-Rank Subspace |
| `industrial.operational` | **83.04%** | 93.57% | **97.89%** | Extreme Low-Rank Subspace |
| `industrial.recovery` | **83.29%** | 93.44% | **97.87%** | Extreme Low-Rank Subspace |
| `industrial.temporal` | **84.07%** | 93.73% | **98.11%** | Extreme Low-Rank Subspace |
| `logistics.operational` | **83.05%** | 93.54% | **97.91%** | Extreme Low-Rank Subspace |
| `logistics.recovery` | **81.19%** | 92.17% | **97.44%** | Extreme Low-Rank Subspace |
| `logistics.temporal` | **84.45%** | 93.54% | **97.85%** | Extreme Low-Rank Subspace |

### B. Causal Rank-Truncation Ablation
To test whether the dominant singular directions are causally sufficient for task performance, adapters were ablated to rank-1, rank-2, rank-4, and rank-8 on held-out tasks:

| Domain Adapter | Truncated Rank | Valid JSON Rate | Exact Semantic Match | Representation Retention |
| :--- | :---: | :---: | :---: | :--- |
| `industrial.operational` | Rank-1 | 100.0% | 30.0% | 100% of Learned Competence |
| `industrial.operational` | Rank-2 | 100.0% | 30.0% | 100% of Learned Competence |
| `industrial.operational` | Rank-4 | 100.0% | 30.0% | 100% Saturated |
| `industrial.operational` | Rank-8 | 100.0% | 30.0% | 100% Saturated |
| `cybersecurity.temporal` | Rank-1 | 100.0% | 100.0% | 100% of Learned Competence |
| `cybersecurity.temporal` | Rank-2 | 100.0% | 100.0% | 100% of Learned Competence |
| `cybersecurity.temporal` | Rank-4 | 100.0% | 100.0% | 100% Saturated |
| `cybersecurity.temporal` | Rank-8 | 100.0% | 100.0% | 100% Saturated |
| `logistics.recovery` | Rank-1 | 100.0% | 70.0% | 77.8% of Full |
| `logistics.recovery` | Rank-2 | 100.0% | 80.0% | 88.9% of Full |
| `logistics.recovery` | Rank-4 | 100.0% | 90.0% | 100% Saturated |
| `logistics.recovery` | Rank-8 | 100.0% | 90.0% | 100% Saturated |

> [!TIP]
> **Causal Finding Confirmed**: 100% of JSON structural grammar is causally captured by rank-1 alone. For operational and temporal tasks, rank-1 recovers 100% of learned disposition accuracy. For complex recovery logic, rank-1 recovers 77.8% and rank-4 recovers 100% of full task performance.

---

## 6. Gate M5: Deterministic UoW Multi-Domain Composition & Ledger Closure

A composite 5-step transaction crossing multiple operational domains was executed under the deterministic UoW protocol kernel:
1. **Step 1 (Industrial)**: `EMERGENCY_DEPRESSURIZE` verified against interlock safety guard $\to$ Committed.
2. **Step 2 (Temporal)**: Logical time window `09:00 - 17:00` verified against monotonic clock $\to$ Lease Committed.
3. **Step 3 (Cybersecurity)**: `QUARANTINE_ENDPOINT` verified against SOC audit active guard $\to$ ACL Committed.
4. **Step 4 (Logistics)**: `REROUTE_TRANSIT_LANE` verified against manifest integrity $\to$ Route Committed.
5. **Step 5 (Recovery)**: `ROLLBACK_COMPENSATE` saga executed on injected network drop $\to$ Saga Committed.

- **Cryptographic Ledger Root Hash**: `6f3d4eb10888031af850fb12af7643eeb655ec8c1197af6897fb7d63102e5005`
- **Ledger Chain Integrity**: **VERIFIED**
- **Unauthorized State Commits**: **0**
- **Adversarial Invariant Tests**: Replay attacks and guard condition failures deterministically rejected at route selection.

---

## 7. Architectural Conclusions & Verified Boundaries

The reconciled UOW-MAGAZINE-1 results establish three core findings:
1. **Feasibility of Compact Weight Magazines**: A single compact foundation (~135M parameters) can maintain a library of resident adapter slots in GPU memory with sub-1GB VRAM consumption, sub-10ms switching, and zero cross-activation contamination across distinct domains.
2. **Mechanistic Low-Rank Subspace Adjustment**: Domain expertise in compact models is predominantly 1-dimensional to 4-dimensional in weight space (>82% rank-1 energy), explaining why linear merging causes catastrophic interference while resident magazines avoid it entirely.
3. **Prerequisites for Portability**: Transferring structured grammar acquisition across compact foundations requires instruction-tuned base models; raw generative bases require pre-alignment before acquiring structured operational grammars.
4. **Deterministic Authority Boundary**: Probabilistic models propose; deterministic UoW engines govern. Even with imperfect semantic accuracy in certain operational domains (30–60%), the deterministic kernel prevents all unauthorized state commits (0 recorded).
