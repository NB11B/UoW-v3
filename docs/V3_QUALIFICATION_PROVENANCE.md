# UoW v3 Qualification Provenance Registry

While [`docs/V2_TO_V3_PROVENANCE.md`](V2_TO_V3_PROVENANCE.md) documents the sealed, historical research campaigns inherited from UoW v2, this document tracks new physical and cross-language qualification campaigns conducted directly under the **UoW v3.x** lifecycle.

---

## 1. Summary of v3 Qualification Campaigns

| Campaign ID | Focus / Domain | Target Platform | Campaign Type | Evidence Level | Status | Milestone |
|---|---|---|---|---|---|---|
| **`KRYONOS-ESP32-E4E`** | Physical Authority & Application Isolation | ESP32-S3 (Xtensa Dual-Core) + KryonOS | Physical Silicon Qualification | L1 Physical Hardware | **QUALIFIED** | v3.1-M1 |
| *`V31-ECON-ATOMIC`* | Atomic Economics ($C_H, C_M, C_E, C_R, C_K, C_D$) | Multi-host / Cloud | Schema & Protocol Verification | L3 Protocol Qualified | *STAGED* | v3.1-M2 |
| *`V31-CPP-16VEC`* | Full C++ Conformance (16/16 Vectors) | Native Host C++17 | Conformance Matrix Verification | L3 Cross-Language | *STAGED* | v3.1-M3 |
| *`V31-RUST-RUNTIME`* | Rust Native Runtime (OCC & Orchestration) | Rust Native (`runtimes/rust/`) | Independent Runtime Qualification | L3 Runtime Qualified | *STAGED* | v3.1-M4 |
| *`V31-PHYS-CONFIRM`* | Hardware Reflash & Reconfirmation | ESP32-S3 + Arduino UNO Q | Dual-Node Quorum Confirmation | L1 Physical Hardware | *STAGED* | v3.1-M5 |

---

## 2. Campaign Detail: `KRYONOS-ESP32-E4E`

### 2.1 Hardware and Software Artifacts
- **Target Silicon**: Espressif ESP32-S3-DevKitC-1-N16R8 (16MB Flash, 8MB PSRAM)
- **Host Testing Bridge**: Node.js `@uow/kryonos` test runner (`test/kryonos.test.ts`)
- **Firmware Target**: KryonOS v1.0 running Duktape Embedded JavaScript and Native C++ Authority Gate v1
- **Physical Test Runner**: `uow_e4e_runner.cpp` (581 lines)
- **Directory**: [`qualification/kryonos/esp32_e4e/`](../qualification/kryonos/esp32_e4e/)

### 2.2 Core Invariants Verified
1. **Dynamic Application Replacement Isolation**:
   \[
   \boxed{\text{Application Replacement} \not\Rightarrow \text{Authority Replacement}}
   \]
   Replacing the dynamic Duktape JavaScript application script does not grant capability escalation or bypass the native C++ authority kernel.
2. **2D Fencing Matrix**:
   4/4 quadrants correctly evaluated on physical silicon. Zero actuator pin mutation on any denied transition.
3. **10,000-Operation Bounded Physical Endurance**:
   Continuous stress run completed with **0 unauthorized mutations, 0 stale executions, 0 duplicate effects, and 0 authority escalations**.
4. **Cumulative Heterogeneous Realization Parity**:
   > E4E confirms ESP32 parity with the already-qualified host/native semantics; combined with the prior Arduino qualification, the cumulative evidence supports heterogeneous realization parity:
   \[
   R_{\text{Laptop}}(W) \sim R_{\text{Arduino}}(W) \sim R_{\text{ESP32}}(W)
   \]

### 2.3 Optimization vs Protocol Separation
- Flash wear-leveling (batched persistence) and FreeRTOS task yielding are classified strictly as **KryonOS realization optimizations**, not UoW protocol rules.
