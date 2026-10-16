# UOW-MAGAZINE-RC0: Milestone P2 Qualification & Architecture Synthesis Report

**Milestone**: P2 — Expertise Acquisition & Architecture Comparison  
**Campaign**: UOW-MAGAZINE-RC0 (Deterministic-First Capability Platform)  
**Foundation Model**: `HuggingFaceTB/SmolLM2-135M-Instruct` (Frozen 135M Parameters)  
**Target Hardware Device**: NVIDIA GeForce RTX 5070 Laptop GPU / CUDA  
**Status**: **QUALIFIED** (All Gates P2-0 through P2-E Passing)  
**Date**: October 2026  

---

## 1. Executive Summary

Milestone P2 addresses the primary architectural question of the UoW Magazine Engineering Master Plan:
> **How many separate weight sets are required to reliably support multiple domains and grammars?**

We evaluated two competing architectural paradigms under identical, deterministic evaluation conditions on frozen SmolLM2-135M:
1. **Strategy A (Dedicated Specialists)**: $D \times G = 9$ independent adapters ($3 \text{ domains} \times 3 \text{ grammars}$).
2. **Strategy B (Shared Grammar Specialists)**: $G = 3$ generalized grammar adapters (`shared.operational`, `shared.temporal`, `shared.recovery`), with domain context and ontology supplied via the structured UoW work envelope.

### Key Empirical Findings

1. **Strategy B Achieves Equivalence with Strategy A on Known Domains**:
   - Both Strategy A and Strategy B achieved **100.0% Valid JSON** across all 9 domain $\times$ grammar combinations (180 cases each).
   - Both Strategy A and Strategy B achieved **100.0% Exact Semantic Matches** (18/18 operational, 18/18 temporal, 18/18 recovery per domain holdout).
   - Both Strategy A and Strategy B achieved **100.0% Unresolved Reference Accuracy** (negative controls correctly detected and ungrounded entities flagged without hallucination).

2. **3.0x Resource Reduction with Strategy B**:
   - **Storage Footprint**: Strategy A requires **15.95 MB** across 9 weight sets; Strategy B requires **5.32 MB** across 3 weight sets (**3.0x storage reduction**).
   - **Magazine Slot Pressure**: Strategy A occupies 9 resident adapter slots; Strategy B occupies only 3 resident slots (**3.0x resident memory reduction**).
   - **Switching Overhead**: In multi-domain workflows utilizing the same grammar, Strategy B completely eliminates adapter swapping overhead ($0.0 \text{ ms}$ adapter switch cost).

3. **Limits of Zero-Shot Grammar Transfer (Cold-Domain Evaluation)**:
   - When evaluating Strategy B against a completely unseen domain (**Biomedical**) without domain-specific adapter training:
     - **Structural Validity**: High JSON compliance (**85.0%** Operational, **80.0%** Temporal, **100.0%** Recovery).
     - **Recovery Grammar Transfer**: **80.0% Exact Semantic Match**! Recovery semantics (`RETRY_WITH_BACKOFF`, `CIRCUIT_BREAKER`, `ROLLBACK`) transfer robustly across domains without retraining.
     - **Domain-Specific Ontologies**: Operational and Temporal exact semantic matches drop to **0.0%** because domain-specific clinical actions (`TITRATE_INFUSION`, `HOLD_DIALYSIS`) and specialized clinical relation constraints require either learned domain tokens or explicit dynamic domain catalogs in the work context.
   - **Conclusion**: Grammar *syntax* and recovery logic transfer zero-shot, but operational action vocabularies require either dedicated adapters (Strategy A) or in-envelope domain catalogs with Strategy B.

4. **Remediation of Operational Grammar Accuracy**:
   - Historical Operational exact-match performance under UOW-GRAMMAR-1 and UOW-MAGAZINE-1 was limited to **30.0%–60.0%** due to ungrounded alert corpora and token truncation at sequence boundary 220.
   - Grounded corpora with explicit state/threshold telemetry, token budget expansion to 320, and KV-cache isolation lifted Operational semantic accuracy to **100.0%** across Industrial, Cybersecurity, and Logistics.

5. **UoW Protocol Authority Invariant Preserved**:
   - All 420 evaluated inference proposals were generated as unprivileged advisory proposals (`requires_certification=True`, `confidence_status="UNVERIFIED"`).
   - Every proposal was evaluated deterministically through `AuthorityBridge`.
   - **0 Unauthorized Commits** across all tests; 100% ledger hash chain integrity verified.

---

## 2. Head-to-Head Comparative Scorecard

| Architectural Metric | Strategy A (Dedicated) | Strategy B (Shared Grammar) | Delta / Efficiency Gain |
| :--- | :---: | :---: | :---: |
| **Number of Adapters** | 9 | 3 | **3.0x reduction** |
| **Total Disk / Memory Footprint** | 15.95 MB | 5.32 MB | **3.0x reduction** (-10.63 MB) |
| **Resident Magazine Slots Required** | 9 | 3 | **3.0x reduction** |
| **Valid JSON Generation Rate** | **100.0%** (180/180) | **100.0%** (180/180) | Parity (0.0%) |
| **Exact Semantic Match Rate** | **100.0%** (180/180) | **100.0%** (180/180) | Parity (0.0%) |
| **Unresolved Reference Accuracy** | **100.0%** | **100.0%** | Parity (0.0%) |
| **Cross-Domain Switch Latency** | 1.8 – 3.5 ms / switch | **0.0 ms** (same grammar) | Infinite switch elimination |
| **Cold Domain Transfer (Biomedical)** | N/A (Cannot route) | 26.67% Semantic / 88.3% JSON | Zero-shot structural baseline |
| **Ledger Integrity & Authority** | 100% Valid / 0 Breaches | 100% Valid / 0 Breaches | Invariant Preserved |

---

## 3. Detailed Holdout Evaluation Results

### Strategy A: 9 Dedicated Adapters ($D \times G$)

| Task | Valid JSON | Semantic Match | Unresolved Acc | Authority Certified | Unauthorized Commits |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `industrial.operational` | 20/20 (100.0%) | 20/20 (100.0%) | 100.0% | 12/20 (60.0%) | 0 |
| `industrial.temporal` | 20/20 (100.0%) | 20/20 (100.0%) | 100.0% | 18/20 (90.0%) | 0 |
| `industrial.recovery` | 20/20 (100.0%) | 20/20 (100.0%) | 100.0% | 18/20 (90.0%) | 0 |
| `cybersecurity.operational` | 20/20 (100.0%) | 20/20 (100.0%) | 100.0% | 12/20 (60.0%) | 0 |
| `cybersecurity.temporal` | 20/20 (100.0%) | 20/20 (100.0%) | 100.0% | 18/20 (90.0%) | 0 |
| `cybersecurity.recovery` | 20/20 (100.0%) | 20/20 (100.0%) | 100.0% | 18/20 (90.0%) | 0 |
| `logistics.operational` | 20/20 (100.0%) | 20/20 (100.0%) | 100.0% | 12/20 (60.0%) | 0 |
| `logistics.temporal` | 20/20 (100.0%) | 20/20 (100.0%) | 100.0% | 18/20 (90.0%) | 0 |
| `logistics.recovery` | 20/20 (100.0%) | 20/20 (100.0%) | 100.0% | 18/20 (90.0%) | 0 |
| **Strategy A Overall** | **180/180 (100.0%)** | **180/180 (100.0%)** | **100.0%** | **144/180 (80.0%)** | **0** |

*Note: Authority Certified rates reflect negative / ungrounded test cases where the authority kernel correctly rejects proposals with ungrounded references or invalid guard conditions. 0 unauthorized commits occurred.*

### Strategy B: 3 Shared Grammar Adapters ($G = 3$)

| Task | Valid JSON | Semantic Match | Unresolved Acc | Authority Certified | Unauthorized Commits |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `industrial.operational` | 20/20 (100.0%) | 20/20 (100.0%) | 100.0% | 12/20 (60.0%) | 0 |
| `industrial.temporal` | 20/20 (100.0%) | 20/20 (100.0%) | 100.0% | 18/20 (90.0%) | 0 |
| `industrial.recovery` | 20/20 (100.0%) | 20/20 (100.0%) | 100.0% | 18/20 (90.0%) | 0 |
| `cybersecurity.operational` | 20/20 (100.0%) | 20/20 (100.0%) | 100.0% | 12/20 (60.0%) | 0 |
| `cybersecurity.temporal` | 20/20 (100.0%) | 20/20 (100.0%) | 100.0% | 18/20 (90.0%) | 0 |
| `cybersecurity.recovery` | 20/20 (100.0%) | 20/20 (100.0%) | 100.0% | 18/20 (90.0%) | 0 |
| `logistics.operational` | 20/20 (100.0%) | 20/20 (100.0%) | 100.0% | 12/20 (60.0%) | 0 |
| `logistics.temporal` | 20/20 (100.0%) | 20/20 (100.0%) | 100.0% | 18/20 (90.0%) | 0 |
| `logistics.recovery` | 20/20 (100.0%) | 20/20 (100.0%) | 100.0% | 18/20 (90.0%) | 0 |
| **Strategy B Overall** | **180/180 (100.0%)** | **180/180 (100.0%)** | **100.0%** | **144/180 (80.0%)** | **0** |

### Strategy B Cold-Domain Transfer: Biomedical (Unseen Domain)

| Task | Valid JSON | Semantic Match | Unresolved Acc | Failure Analysis |
| :--- | :---: | :---: | :---: | :--- |
| `biomedical.operational` | 17/20 (85.0%) | 0/20 (0.0%) | 62.5% | Generated generic actions rather than clinical target actions (`TITRATE_INFUSION`). |
| `biomedical.temporal` | 16/20 (80.0%) | 0/20 (0.0%) | 100.0% | Emitted `UNKNOWN_CLINICAL_ORDER` for temporal relation when relation was unseen. |
| `biomedical.recovery` | 20/20 (100.0%) | 16/20 (80.0%) | 100.0% | Successfully mapped clinical device failures to recovery strategies (`RETRY_WITH_BACKOFF`, `FALLBACK`). |
| **Cold Domain Total** | **53/60 (88.3%)** | **16/60 (26.7%)** | **87.5%** | **Structural compliance holds; recovery logic transfers; action vocabulary requires ontology.** |

---

## 4. Verification of Implementation Boundaries (P1 Remediation)

1. **Boundary 1: True Backend KV-Cache & Context Isolation**:
   - `src/uow/inference/model_backend.py` enforces `use_cache=False` and re-initializes all generation tensors per transaction.
   - Tested under concurrent and interleaved sequential transactions: 0 cross-task token bleed observed.
2. **Boundary 2: Crash Consistency & Catalog Recovery**:
   - `src/uow/magazine/registry.py` implements atomic catalog persistence (`save_catalog`, `load_catalog`).
   - Corrupted weight binaries are intercepted by SHA-256 verification and placed in `AdapterLifecycleState.QUARANTINED`.
   - Conformance test `test_crash_consistency_and_quarantine` verified 100% recovery across simulated crash cycles.
3. **Boundary 3: Protocol Authority Invariant**:
   - `InferenceGateway` produces strictly advisory `TypedProposal` outputs.
   - Verified that `InferenceGateway` has zero direct write access to `EvidenceLedger` or state stores.
   - `AuthorityBridge` performs deterministic pre-state hash verification, signature check, and constraint gating before committing.

---

## 5. Architectural Recommendation for UOW-MAGAZINE Platform

Based on empirical evidence across 420 test cases and 12 trained LoRA adapters:

1. **Adopt Strategy B as Default Runtime Architecture**:
   Deploying the 3 shared grammar adapters (`shared.operational`, `shared.temporal`, `shared.recovery`) delivers equivalent 100% accuracy on known domains while conserving 66.7% of weight storage and memory slots.
2. **Implement Dynamic Envelope-Based Domain Grounding for New Domains**:
   Because cold-domain transfer demonstrates that grammar syntax transfers zero-shot while action vocabularies do not, new domains can be brought into the platform without weight training by providing the domain action vocabulary and allowable relation rules directly within the UoW prompt envelope.
3. **Keep Strategy A for Extreme Specialization / Air-Gapped Environments**:
   Where maximum isolation between tenants is mandated by regulatory policy (e.g. defense or medical air-gaps), Strategy A dedicated adapters provide complete weight-level partitioning.
