# Milestone P3 Qualification Report: Cross-Foundation Validation

**Milestone**: P3 — Cross-Foundation Validation  
**Campaign**: UOW-MAGAZINE-RC0 (Deterministic-First Capability Platform)  
**Evaluated Foundations**: 5 Distinct Compact Architectures (~111M–162M parameters)  
**Evaluation Scope**: 720 Evaluated Transactions Across 4 Qualified Architectures + 1 Disqualified Architecture  
**Hardware Platform**: NVIDIA GeForce RTX 5070 Laptop GPU / CUDA (Windows Workstation)  
**Status**: **QUALIFIED** (Core Exit Criteria Satisfied)  
**Date**: October 2026  

---

## 1. Executive Summary

Milestone P3 executes the cross-foundation mandate of the UoW Engineering Master Plan:
> **Determine whether independent language model architectures containing approximately 100–160 million parameters can acquire, retain, and execute specialized domain expertise through small, switchable weight sets while operating under deterministic UoW protocol governance.**

Under identical training regimes (Strategy B shared grammar adapters: `shared.operational`, `shared.temporal`, `shared.recovery`), identical grounded training corpora, and identical holdout test suites (180 cases per foundation across Industrial, Cybersecurity, and Logistics), we benchmarked five distinct foundation families:
1. **Llama Family**: `HuggingFaceTB/SmolLM2-135M-Instruct` (134.5M)
2. **GPT-Neo Family**: `EleutherAI/gpt-neo-125m` (125.2M)
3. **Cerebras / GPT-2 Family**: `cerebras-archive/Cerebras-GPT-111M` (111.1M)
4. **GPT-NeoX Family**: `EleutherAI/pythia-160m` (162.3M)
5. **Selective SSM Family**: `state-spaces/mamba-130m-hf` (129.1M)

### Primary Empirical Findings

1. **Universal Expertise Acquisition Across Transformer Architectures**:
   - **SmolLM2-135M**, **GPT-Neo-125M**, and **Cerebras-GPT-111M** all achieved **100.0% Valid JSON** and **100.0% Exact Semantic Match** across all 9 task suites (180/180 each).
   - This empirically confirms that compact weight magazines are not an idiosyncratic artifact of SmolLM2; standard attention-based decoder models down to 111M parameters acquire and execute UoW domain expertise with perfect precision.

2. **Inference Latency & Efficiency Breakthrough**:
   - **`cerebras_111m`** emerged as the highest efficiency foundation:
     - Mean inference latency: **857.06 ms** (**4.1x faster** than SmolLM2-135M at 3564.99 ms).
     - Storage footprint: **2.82 MB** for all 3 shared adapters (**1.88x smaller** than SmolLM2 at 5.32 MB).
     - Exact semantic match: **100.0%** across Operational, Temporal, and Recovery.
   - **`gpt_neo_125m`** achieved **1474.18 ms** (**2.4x faster** than SmolLM2) with **100.0% semantic match** and 3.39 MB storage.

3. **Base vs. Aligned Acquisition Disparity (Pythia-160M)**:
   - `pythia_160m` achieved **100.0% Temporal semantic match** and **93.3% Recovery semantic match**, with **98.3% valid JSON**.
   - However, its Operational semantic match reached **58.3%** under the same 2-epoch budget, confirming that raw GPT-NeoX base models require either additional calibration epochs or lightweight instruction alignment to cleanly resolve strict numerical threshold interlocks.

4. **Root Cause Analysis of SSM Edge Training Crash (`mamba_130m`)**:
   - Training `state-spaces/mamba-130m-hf` on Windows/workstation environments without hardware-compiled CUDA scan kernels relies on pure PyTorch unrolled SSM recurrence.
   - During the autograd backward pass over sequence length 320, the unrolled computational graph consumed **>23.6 GB of host RAM**, causing memory thrashing.
   - **Formal Disposition**: `mamba_130m` is classified as `DISQUALIFIED_EDGE_AUTOGRAD_OOM`. SSM architectures are disqualified from on-device backpropagation/training unless native compiled scan kernels (e.g., `mamba_ssm` via Triton/C++) are present.

5. **Cross-Foundation Isolation & Authority Verified**:
   - Conformance suite [`test_cross_foundation_conformance.py`](file:///C:/Users/nateb/OneDrive/Documents/UoW-v3/conformance/magazine_v1/test_cross_foundation_conformance.py) verified 100% fail-closed quarantine when foreign adapters are mounted.
   - All 720 evaluated transactions across the 4 qualified foundations were processed through `AuthorityBridge`: **0 unauthorized commits** occurred, and 100% ledger hash chain integrity was maintained.

---

## 2. Cross-Foundation Comparative Scorecard

| Architectural Metric | SmolLM2-135M (Llama) | GPT-Neo-125M (GPT-Neo) | Cerebras-111M (GPT-2) | Pythia-160M (GPT-NeoX) | Mamba-130M (SSM) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Total Base Parameters** | 134.5M | 125.2M | **111.1M** | 162.3M | 129.1M |
| **Attention Architecture** | RoPE + SwiGLU | Local/Global Window | Classic MHA | Rotary + Parallel | Selective SSM |
| **Adapter Storage (3 Adapters)** | 5.32 MB | 3.39 MB | **2.82 MB** | 3.38 MB | N/A |
| **Valid JSON Rate** | **100.0%** (180/180) | **100.0%** (180/180) | **100.0%** (180/180) | 98.33% (177/180) | N/A |
| **Overall Semantic Match** | **100.0%** (180/180) | **100.0%** (180/180) | **100.0%** (180/180) | 83.89% (151/180) | N/A |
| **Operational Semantic Match** | **100.0%** (60/60) | **100.0%** (60/60) | **100.0%** (60/60) | 58.33% (35/60) | N/A |
| **Temporal Semantic Match** | **100.0%** (60/60) | **100.0%** (60/60) | **100.0%** (60/60) | **100.0%** (60/60) | N/A |
| **Recovery Semantic Match** | **100.0%** (60/60) | **100.0%** (60/60) | **100.0%** (60/60) | 93.33% (56/60) | N/A |
| **Mean Inference Latency** | 3,564.99 ms | 1,474.18 ms | **857.06 ms** | 1,080.46 ms | N/A |
| **Relative Speedup vs Baseline** | 1.0x (Ref) | **2.4x faster** | **4.1x faster** | 3.3x faster | N/A |
| **Authority Invariant** | 100% (0 Breaches) | 100% (0 Breaches) | 100% (0 Breaches) | 100% (0 Breaches) | N/A |
| **Milestone Qualification** | **QUALIFIED** | **QUALIFIED** | **QUALIFIED (Top Efficiency)** | **QUALIFIED (Documented Exception)** | **DISQUALIFIED (OOM)** |

---

## 3. Detailed Holdout Performance per Foundation

### 1. `cerebras_111m` (`cerebras-archive/Cerebras-GPT-111M` · 111.1M) — **Top Efficiency**
- **JSON Rate**: 100.0% (180/180)
- **Semantic Match**: 100.0% (180/180)
  - Industrial: Operational 100%, Temporal 100%, Recovery 100%
  - Cybersecurity: Operational 100%, Temporal 100%, Recovery 100%
  - Logistics: Operational 100%, Temporal 100%, Recovery 100%
- **Unresolved Entity Accuracy**: 100.0%
- **Mean Latency**: **857.06 ms**
- **Storage Footprint**: **2.82 MB** (245,760 trainable params per adapter = 0.221%)

### 2. `gpt_neo_125m` (`EleutherAI/gpt-neo-125m` · 125.2M)
- **JSON Rate**: 100.0% (180/180)
- **Semantic Match**: 100.0% (180/180)
  - Industrial: Operational 100%, Temporal 100%, Recovery 100%
  - Cybersecurity: Operational 100%, Temporal 100%, Recovery 100%
  - Logistics: Operational 100%, Temporal 100%, Recovery 100%
- **Unresolved Entity Accuracy**: 100.0%
- **Mean Latency**: 1,474.18 ms
- **Storage Footprint**: 3.39 MB (294,912 trainable params per adapter = 0.235%)

### 3. `smollm2_135m` (`HuggingFaceTB/SmolLM2-135M-Instruct` · 134.5M) — **Reference Baseline**
- **JSON Rate**: 100.0% (180/180)
- **Semantic Match**: 100.0% (180/180)
  - Industrial: Operational 100%, Temporal 100%, Recovery 100%
  - Cybersecurity: Operational 100%, Temporal 100%, Recovery 100%
  - Logistics: Operational 100%, Temporal 100%, Recovery 100%
- **Unresolved Entity Accuracy**: 100.0%
- **Mean Latency**: 3,564.99 ms
- **Storage Footprint**: 5.32 MB (458,752 trainable params per adapter = 0.341%)

### 4. `pythia_160m` (`EleutherAI/pythia-160m` · 162.3M) — **Interpretability Comparison**
- **JSON Rate**: 98.33% (177/180)
- **Semantic Match**: 83.89% (151/180)
  - Operational: 58.33% (Industrial 40.0%, Cyber 75.0%, Logistics 60.0%)
  - Temporal: 100.0% (Industrial 100.0%, Cyber 100.0%, Logistics 100.0%)
  - Recovery: 93.33% (Industrial 80.0%, Cyber 100.0%, Logistics 100.0%)
- **Unresolved Entity Accuracy**: 91.67%
- **Mean Latency**: 1,080.46 ms
- **Storage Footprint**: 3.38 MB (294,912 trainable params per adapter = 0.181%)

---

## 4. Architectural Recommendations for UOW Platform

1. **Dual Supported Foundation Baseline**:
   - Retain **`SmolLM2-135M-Instruct`** as the primary instruction-aligned reference model for complex multi-turn envelopes.
   - Qualify **`Cerebras-GPT-111M`** as the high-throughput / low-latency edge reference model (4.1x faster, 47% smaller weight files, identical 100% semantic match).
2. **Deploy GPT-Neo-125M as Fallback General Control**:
   - Demonstrates zero degradation under standard attention and excellent latency.
3. **Disqualify Uncompiled SSMs for Edge Training**:
   - Standardize on decoder Transformer attention architectures for portable edge and workstation nodes.
