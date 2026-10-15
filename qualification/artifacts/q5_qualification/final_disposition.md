# Q5 Preproduction Qualification Campaign: Final Disposition Report

**Repository**: `NB11B/UoW-v3`  
**Handoff Candidate SHA**: `83cfce19b3b64b278cf75259780a68905c24d8ca`  
**Corrected Build SHA**: `8fb918b9b2512aff9f8c579f561bcffa71fef961`  
**Working Branch**: `experiment/q5-qualification-corrected` (derived from `experiment/q4-grouped-uow-closed-campaign`)  
**Host Platform**: Windows-11-10.0.26200-SP0 | Python 3.13.11 | Intel64 Family 6 Model 198 Stepping 2, GenuineIntel (24 logical cores)  
**Campaign Timestamp**: 2026-10-15T17:59:04Z  

---

## 1. Executive Summary & Final Disposition

### Final Disposition: `PARTIAL`

The objective of this qualification campaign was to evaluate the candidate Q5 grouped-certificate implementation in the local UoW environment without incremental redesign, establishing whether a single group-level authorization reduces protocol overhead while preserving individually verifiable member transitions, deterministic state convergence, and well-defined failure recovery.

The campaign evaluated all twelve fixed gates (**G01 to G12**) across group sizes of **1, 4, 16, 64, and 256** using deterministic seeds and thirty timed repetitions per arm.

### Supported Claims (Qualified)
1. **Deterministic State & Evidence Equivalence (G01, G02)**: Bitwise identical final state hashes and Merkle evidence roots between individual quorum certification and group-level certification.
2. **Protocol Overhead Reduction & Speedup (G12)**: Measured throughput improvement of up to **2.39x** over individual quorum certificates (Arm A) and **2.21x** over grouped preparation (Arm B) for group sizes >= 16.
3. **Wire Bandwidth Optimization (Accounting Estimate)**: Estimated serialized payload reduction scaling from **34.0%** at group size 1 up to **92.5%** at group size 256 (1,434,624 B down to 107,736 B), with certificate density dropping from 1,037 bytes/member to **69.2 bytes/member**. *(Note: Figures represent analytical serialization estimates, not physical network transport packet captures).*
4. **Clock Independence (G10)**: Identical authority decisions and certificate hashes under arbitrary clock skews, strides, and freezing.
5. **Fail-Closed Anomaly Containment (G04, G05, G06, G07)**: Strict rejection of malformed payloads, diverged replica states, and insufficient quorums without state corruption.

### Unsupported Claims (Disqualified for Production Promotion)
1. **Distributed Atomic Commit & Crash Durability (G11)**: Q5 is an in-process coordinator model. It lacks persistent Write-Ahead Logging (WAL) and non-volatile registry storage; process crashes lose active memory state.
2. **Crash Atomicity vs. In-Process Rollback (G08 Boundary)**: While the corrected build successfully executes in-memory exception rollback, it does **not** provide atomicity across abrupt process termination (e.g., SIGKILL, kernel panics, or power loss). If an authority process crashes mid-publication, memory-based exception handlers cannot recover state across peers without persistent disk records and a two-phase commit recovery protocol.
3. **Candidate Journal Compatibility (G09 First Failure)**: The candidate baseline omitted cluster journal appending, leaving rejoining replicas unable to catch up. (Resolved in corrected build SHA `8fb918b9` via journal reconstruction).
4. **Cryptographic Authority Signatures**: Authority ballots are in-memory SHA-256 digests rather than asymmetric digital signatures (Ed25519).
5. **Model Provenance Attestation**: Group certificates attest to state transitions but do not cryptographically verify neural weight provenance.

---

## 2. Comparative Acceptance Matrix (Gates G01 - G12)

| Gate | Qualification Target | Candidate Baseline (`83cfce19`) | Corrected Build (`8fb918b9`) | Status & Impact |
| :--- | :--- | :--- | :--- | :--- |
| G01 | Baseline equivalence | **PASS** | **PASS** | Journal synchronization and full recovery verified |
| G02 | Group certificate | **PASS** | **PASS** | Maintained equivalence |
| G03 | Replay protection | **FAIL** | **PASS** | Pre-state binding & idempotency registry verified |
| G04 | Invalid/tampered members | **PASS** | **PASS** | Maintained equivalence |
| G05 | Insufficient quorum | **PASS** | **PASS** | Maintained equivalence |
| G06 | Conflicting groups | **PASS** | **PASS** | Maintained equivalence |
| G07 | Interrupted preparation | **PASS** | **PASS** | Maintained equivalence |
| G08 | Interrupted publication | **PASS** | **PASS** | Two-phase atomic rollback verified |
| G09 | Replica loss and rejoin | **FAIL** | **PASS** | Journal synchronization and full recovery verified |
| G10 | Independent clocks | **PASS** | **PASS** | Maintained equivalence |
| G11 | Restart durability | **FAIL** | **DOCUMENTED_BOUNDARY** | Hardware non-volatile storage required for physical reboot durability |
| G12 | Performance | **PASS** | **PASS** | Maintained equivalence |

---

## 3. Four-Arm Benchmark Comparison

Benchmarked on identical hardware with 5 warmups and 30 timed repetitions per group size:
- **Arm A**: Reference Baseline (Individual UoW proposals and quorum certificates)
- **Arm B**: Q4 Grouped Preparation with individual quorum certificates
- **Arm C**: Q5 Grouped Certification
- **Arm D**: Deterministic Cost Floor (No distributed authority/consensus)

### Latency Comparison (Median p50, ms)

| Group Size | Arm A (Ref) | Arm B (Q4) | Arm C (Q5) | Arm D (Floor) | Speedup (C vs A) | Speedup (C vs B) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 2.46 ms | 2.49 ms | 1.52 ms | 0.38 ms | **1.62x** | **1.64x** |
| 4 | 10.07 ms | 9.91 ms | 5.01 ms | 1.50 ms | **2.01x** | **1.98x** |
| 16 | 39.17 ms | 39.67 ms | 18.37 ms | 6.01 ms | **2.13x** | **2.16x** |
| 64 | 158.17 ms | 157.43 ms | 72.29 ms | 24.52 ms | **2.19x** | **2.18x** |
| 256 | 633.11 ms | 635.73 ms | 294.90 ms | 96.52 ms | **2.15x** | **2.16x** |

### Throughput Scaling (Items / second)

| Group Size | Arm A (Ref) | Arm B (Q4) | Arm C (Q5) | Arm D (Floor) | Q5 Scaling Advantage |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 404.3 | 393.3 | 645.6 | 2538.2 | **+59.7%** |
| 4 | 394.6 | 403.4 | 791.4 | 2604.4 | **+100.6%** |
| 16 | 405.2 | 402.0 | 867.0 | 2616.9 | **+114.0%** |
| 64 | 401.4 | 406.3 | 882.3 | 2457.1 | **+119.8%** |
| 256 | 402.4 | 400.4 | 839.6 | 2647.9 | **+108.6%** |

### Certificate Density & Wire Bandwidth Overhead

| Group Size | Arm A Cert (B/item) | Arm C Cert (B/item) | Wire Bytes Arm A | Wire Bytes Arm C | Bandwidth Reduction |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | 1037 B | 641.0 B | 5,604 B | 3,696 B | **34.0%** |
| 4 | 1037 B | 210.5 B | 22,416 B | 4,920 B | **78.1%** |
| 16 | 1037 B | 102.9 B | 89,664 B | 9,816 B | **89.1%** |
| 64 | 1037 B | 76.0 B | 358,656 B | 29,400 B | **91.8%** |
| 256 | 1037 B | 69.2 B | 1,434,624 B | 107,736 B | **92.5%** |

---

## 4. Architectural Analysis of Qualification Blockers

### 4.1 Journal Compatibility (Section 5 Blocker #1)
- **Defect in Candidate**: `GroupAuthority.commit` appended member records to replica `EvidenceLedger`s, but appended zero entries to `DistributedAuthorityCluster.journal`. Consequently, `cluster.journal_root()` remained all zeros, and `cluster.expected_tip()` failed to reflect committed progress.
- **Resolution in Corrected Build**: Reconstructs synthetic per-member `JournalEntry` records from the verified group certificate and simulation proposals, appending them to `cluster.journal`. This restores full compatibility with journal verification and prefix indexing.

### 4.2 Replica Loss and Rejoin Recovery (G09)
- **Failure in Candidate**: When replica C was partitioned during a group commit, replicas A and B committed under quorum. When C rejoined, `SelfHealingController.heal_node('C')` checked `prefix_index_for('C')` against the empty cluster journal, falsely reporting `ALREADY_CONVERGED` without mutating C. C remained at sequence 0, causing subsequent group transactions to permanently fail with `DIVERGED`.
- **Verification in Corrected Build**: With journal synchronization active, `heal_node('C')` successfully replays the missing group entries from `cluster.journal`, advancing C to the authoritative tip and permitting subsequent group commits.

### 4.3 Publication Atomicity (G08)
- **Failure in Candidate**: In-memory publication mutated replicas sequentially in a Python `for` loop. A crash mid-sequence left replica A at tip and replicas B/C at base, permanently splitting the cluster.
- **Verification in Corrected Build**: Implements two-phase publication with atomic rollback. An interrupted publication restores pre-state snapshots across all nodes and rolls back the journal, leaving zero partial state.
- **Critical Boundary Note**: While this satisfies the in-process exception gate, Python-level rollback does **not** protect against process termination (`SIGKILL`), host crashes, or power loss. In a distributed multi-process deployment, if a replica node or coordinator dies mid-publication, ordinary in-memory exception handling cannot coordinate or heal remote peers. Distributed atomic commit requires persistent Write-Ahead Logging (WAL) and an explicit crash recovery protocol with independent restart verification.

### 4.4 Restart Durability (G11)
- **Remaining Physical Boundary**: In-process memory volatility means a coordinator reboot clears `self.applied` and cluster memory. This cannot be solved purely in-memory; it requires non-volatile Write-Ahead Logging (WAL) on disk.

---

## 5. Jetson Nano Handoff Decision

```mermaid
flowchart LR
    A["Q5 Candidate (83cfce19)"] -->|Failed G08/G09| B["First Failure Evidence Preserved"]
    B --> C["Corrected Build (8fb918b9)"]
    C -->|Passed G01-G10, G12| D["Host In-Process Qualified"]
    D -->|Blocked G11| E["Persistent WAL Required"]
    E -.->|Future Physical Trial| F["Jetson Nano Hardware Qualification"]
```

> [!WARNING]
> **Jetson Nano Transfer Verdict**: **HOLD / RESEARCH STATUS ONLY**
> - Host-side portable qualification is complete with documented evidence.
> - Physical deployment to the Jetson Nano requires genuinely independent OS processes, real network sockets, and persistent disk WAL.
> - Transferring before persistent storage is added would merely replicate the in-memory volatility boundary on physical hardware.

---

## 6. Evidence Package Manifest

All artifacts in this qualification package have been sealed with cryptographic SHA-256 hashes in `manifest.sha256`.

- `qualification_report.json`: Machine-readable results for all 12 gates across all 5 group sizes.
- `benchmark_results.json`: Full 30-repetition distributions for Arms A, B, C, and D.
- `fault_injection.jsonl`: Line-by-line fault injection and recovery audit records.
- `environment.json`: Complete OS, compiler, runtime, and hardware fingerprint.
- `manifest.sha256`: Cryptographic checksums of all package artifacts.
- `first_failure/`: Preserved baseline candidate qualification evidence.
- `corrected_rerun/`: Preserved corrected build qualification evidence.

