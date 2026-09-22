# ESP32-S3 Dual-Core Hardware Qualification Report

**Target**: Physical ESP32-S3 (QFN56 revision v0.2)  
**Port**: USB-Serial/JTAG (COM10, USB VID:PID=303A:1001)  
**Firmware**: `qualification/embedded/esp32_dual_core`  
**Harness**: `host/interrogator.py`  
**Date**: September 22, 2026  

---

## 1. Architectural Milestone

The physical hardware campaign proves that authoritative state transitions, certification boundaries, and cryptographic evidence chains remain strictly invariant under physical core migration and severe clock perturbation:

$$
\boxed{
(P0,A1) \neq (P1,A0)
\quad\land\quad
\tau_P, \tau_A \text{ change/freeze}
\quad\Rightarrow\quad
S_f, \; H(S_f), \; E_f \text{ remain identical}
}
$$

### Demonstrated Properties

1. **Core-Affinity Independence**: Core assignments were physically swapped (proposer on Core 0 / authority on Core 1 vs. proposer on Core 1 / authority on Core 0) with zero impact on transition outcomes.
2. **Timer Independence**: Severely skewed clock strides (`1:1000003`, `999983:1`, `3:29`, `17:17`) and frozen local clocks (`P` frozen, `A` frozen) produced bit-for-bit identical certified state and cryptographic evidence roots.
3. **Proposal Isolation**: Malicious or corrupted proposals (`TAMPER_STATE`, `TAMPER_PREHASH`, `TAMPER_ROUTE`) were rejected deterministically.
4. **Zero Mutation on Rejection**: Rejected proposals caused zero mutation to authoritative state or sequence counters.
5. **Cryptographic Replay Identity**: Terminal state hashes and evidence ledger roots matched bit-for-bit across both physical core mappings.

---

## 2. Canonical Comparison Evidence

Running comparison between the two physical core mapping reports:

```powershell
python host/interrogator.py compare artifacts/p0a1.json artifacts/p1a0.json
```

```json
{
  "both_passed": true,
  "core_mapping_inverted": true,
  "evidence_root_identical": true,
  "state_hash_identical": true,
  "terminal_state_identical": true
}
```

### Verification Matrix

| Verification Metric | Mapping A (`P0 / A1`) | Mapping B (`P1 / A0`) | Parity |
|---|---|---|:---:|
| **Proposer Core** | Core 0 | Core 1 | Inverted |
| **Authority Core** | Core 1 | Core 0 | Inverted |
| **Terminal Registers** | `r0 = 0, r1 = 75` | `r0 = 0, r1 = 75` | Exact match |
| **Sequence Count** | 102 transitions | 102 transitions | Exact match |
| **Terminal State Hash** | `18295a4c8427f7a05eb2709aa59f212d5d18ecdd8c55c5f2857d9d4001cd2599` | `18295a4c8427f7a05eb2709aa59f212d5d18ecdd8c55c5f2857d9d4001cd2599` | **Bit-for-bit** |
| **Cryptographic Evidence Root** | `3c53a2626100991819d920a35d0cc07e7772e76100fa44cd7d23f67d9fb136dc` | `3c53a2626100991819d920a35d0cc07e7772e76100fa44cd7d23f67d9fb136dc` | **Bit-for-bit** |
| **All 19 Falsification Checks** | **19 / 19 PASS** | **19 / 19 PASS** | **PASS** |

---

## 3. 100-Trial Randomized Hardware Stress Results

Executing the seeded multi-trial hardware stress harness:

```powershell
python host/interrogator.py \
  --port COM10 \
  --transcript artifacts/stress-p0a1.jsonl \
  stress \
  --trials 100 \
  --seed 20260922 \
  --report artifacts/stress-p0a1.json
```

### Result
- **Trials Completed**: 100 / 100
- **Pass Rate**: 100% (100 / 100 passed)
- **Checks per Trial**:
  - Baseline execution with randomized clock pair $\alpha$
  - State forgery injection and assertion of zero state mutation
  - State reset and replay with independently randomized clock pair $\beta$
  - Invariance assertion of terminal state and cryptographic evidence root
