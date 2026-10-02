# UoW v3 Qualification Provenance Registry

While [`docs/V2_TO_V3_PROVENANCE.md`](V2_TO_V3_PROVENANCE.md) documents the sealed, historical research campaigns inherited from UoW v2, this document tracks new physical and cross-language qualification campaigns conducted directly under the **UoW v3.x** lifecycle.

---

## 1. Summary of v3 Qualification Campaigns

| Campaign ID | Focus / Domain | Target Platform | Campaign Type | Evidence Level | Status | Milestone |
|---|---|---|---|---|---|---|
| **`KRYONOS-ESP32-E4E`** | Physical Authority & Application Isolation | ESP32-S3 (Xtensa Dual-Core) + KryonOS | Physical Silicon Qualification | L1 Physical Hardware | **QUALIFIED** | v3.1-M1 |
| **`ECON-ATOMIC-COST-M2`** | Atomic Economics ($C_H, C_M, C_E, C_R, C_K, C_D$) | Multi-host / Cloud | Schema & Protocol Verification | L2 Formal & Conformance | **QUALIFIED** | v3.1-M2 |
| **`V31-CPP-16VEC`** | Full C++ Conformance (16/16 Vectors) | Native Host C++17 | Conformance Matrix Verification | L3 Cross-Language | **QUALIFIED** | v3.1-M3 |
| **`V31-RUST-RUNTIME`** | Rust Native Runtime (OCC & Orchestration) | Rust Native (`runtimes/rust/`) | Independent Runtime Qualification | L3 Runtime Qualified | **QUALIFIED** | v3.1-M4 |
| **`V31-PHYS-CONFIRM`** | Integrated Heterogeneous Physical Reconfirmation | ESP32-S3 + Arduino UNO Q + Laptop Host (+ Rust witness) | Multi-Node Quorum & Parity Confirmation | L1 Physical Hardware | **QUALIFIED** | v3.1-M5 |

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

---

## 3. Campaign Detail: `ECON-ATOMIC-COST-M2`

### 3.1 Artifacts & Invariants
- **Target Subsystem**: `src/uow/economics/`
- **Cost Representation**: $C(u) = C_H + C_M + C_E + C_R + C_K + C_D$
- **Governing Separation**:
  - $\text{Cost Observation} \neq \text{Pricing Decision}$
  - $\text{Production Cost} \neq \text{Market Price} \neq \text{Consumer Value}$
  - $\text{Economic Optimizer Proposes} \rightarrow \text{Authority Gate Certifies} \rightarrow \text{State Changes}$
  - **Measurement Determinism**: Compute cycles ($C_M$), energy ($C_E$), and resource reservation ($C_R$) are directly measured from the execution substrate; human valuation ($C_H$), expected recovery cost ($C_K$), and opportunity cost ($C_D$) are deterministic given declared valuation models and expectation inputs.
- **Directory**: [`qualification/economics/atomic_cost/`](../qualification/economics/atomic_cost/)
- **Status**: **QUALIFIED** (6/6 gates verified in `tests/test_atomic_economics_qualification.py`).

---

## 4. Campaign Detail: `V31-CPP-16VEC`

### 4.1 Artifacts & Invariants
- **Target Runtime**: `runtimes/cpp/`
- **Compiler**: `g++.exe (MinGW-W64 x86_64-ucrt-posix-seh, built by Brecht Sanders, r8) 13.2.0`
- **Execution Target**: `runtimes/cpp/conformance_runner.exe`
- **Coverage**: **16/16 Canonical Vectors** passed without modifying the vectors.
- **Directory**: [`qualification/cpp/full_conformance/`](../qualification/cpp/full_conformance/)
- **Claim**: **Native C++ semantic conformance: 16/16 canonical UoW v3 vectors.**
- **Status**: **QUALIFIED** (17/17 tests passing in `tests/test_cpp_full_conformance.py`).

---

## 5. Campaign Detail: `V31-RUST-RUNTIME`

### 5.1 Artifacts & Invariants
- **Target Runtime**: `runtimes/rust/` (`uow-runtime` 3.1.0)
- **Compiler**: `rustc 1.98.1 (48a229cea 2026-09-01)`
- **Architectural Boundary**: $\boxed{\text{SDK} \neq \text{Runtime}}$
  - `sdk/rust/` (`uow-core` 3.0.0): Protocol models, envelopes, serialization, C ABI validation.
  - `runtimes/rust/` (`uow-runtime` 3.1.0): Independent execution authority, WorldState, OCC tracker, deterministic sequencer, WAL crash replay, and DAG scheduler.
- **Coverage**: **16/16 Canonical Golden Vectors** passed without modifying the vectors.
- **Transactional OCC**: 5/5 conflict patterns verified against typed transaction footprints.
- **Crash Replay**: $S_{\text{replayed}} = S_{\text{committed}} \land E_{\text{replayed}} = E_{\text{committed}}$ across simulated process crashes; duplicate replay is strictly idempotent.
- **Deterministic Orchestration**: Complete task eligibility frontier progression ($\{A, B\} \rightarrow \{B\} \rightarrow \{C\} \rightarrow \{D\} \rightarrow \text{HALT}$) with cycle defense.
- **Authority Boundary**: $\boxed{\text{Rust Proposer Capability} \not\Rightarrow \text{Rust Commit Authority}}$ (adversarial proposals strictly rejected).
- **Directory**: [`qualification/rust/native_runtime/`](../qualification/rust/native_runtime/)
- **Claim**: **Rust is an independently executing UoW runtime qualified for canonical Level-0 semantics, transactional authority, crash replay, and deterministic DAG orchestration.**
- **Status**: **QUALIFIED** (17/17 tests passing in `tests/test_rust_full_conformance.py`, 7/7 tests passing in `tests/test_rust_qualification_gates.py`, 8/8 cargo integration tests passing).

---

## 6. Campaign Detail: `V31-PHYS-CONFIRM`

### 6.1 Hardware Topology & Build Provenance
- **Authority A**: Espressif ESP32-S3-DevKitC-1-N16R8 (`auth_a_esp32` on COM4), running KryonOS + Native C++ Authority Gate v1.
- **Authority B**: Arduino UNO Q STM32U585 (`auth_b_uno_q` on COM3), running Embedded C++ Authority Kernel.
- **Authority C**: Laptop Host x86-64 (`auth_c_laptop` on localhost), running Python Reference Authority Service.
- **Realization Witness**: Native Rust Runtime (`uow-runtime` 3.1.0 on x86-64), serving as host realization witness.
- **Software Baseline SHA**: `2132f0a7cb078d882829a10aa116a9f89542b79c`
- **Firmware Sources & Artifacts**:
  - `esp32_s3_firmware.bin` (SHA-256: `06e330ea3414902b4ce70a307e052ebf33a890cf2df3273e9703aa4e7fb7da55`)
  - `uno_q_firmware.bin` (SHA-256: `4815b81a8b9816d2319ef0ae93f54d19b4f91e92d77053c89b71e16f7fb1b11e`)
- **Directory**: [`qualification/physical/v31_confirmation/`](../qualification/physical/v31_confirmation/)

### 6.2 Qualification Gates & Invariants Verified
1. **`PHYS-M5-G01` (Exact Provenance)**: Verified exact toolchain versions, firmware binary digests, board serial IDs, and COM bindings against repository git baseline.
2. **`PHYS-M5-G02` (Pairwise Deterministic Agreement)**: 24/24 canonical transition vectors executed with complete agreement:
   \[
   S'_{\text{ESP32}} = S'_{\text{Arduino}} = S'_{\text{Host}}
   \]
3. **`PHYS-M5-G03` (Live 2-of-3 Quorum Certification)**: Any 2-of-3 pair ($\{A, B\}$, $\{B, C\}$, $\{A, C\}$) successfully authorizes and commits transitions. Singletons strictly fail:
   \[
   |Q| \ge 2 \implies \text{COMMIT}, \quad |Q| < 2 \implies \text{NO\_COMMIT}
   \]
4. **`PHYS-M5-G04` (Partition / Fail-Closed Resilience)**: Communication severance induces fail-closed state; no partial partition permits authority escalation:
   \[
   \text{Loss of communication} \not\Rightarrow \text{Gain of authority} \quad (0 \text{ unauthorized commits})
   \]
5. **`PHYS-M5-G05` (Replay & Stale Authority Rejection)**: 5/5 stale freshness attacks (stale epoch, stale generation, reused proposal hash, delayed packet) strictly rejected with zero physical actuator mutation.
6. **`PHYS-M5-G06` (Cross-Realization v3.1 Confirmation)**: Heterogeneous parity confirmed across all nodes, with Rust host realization witness confirming identical final state ($S = 105, \text{ACTIVE}$):
   \[
   R_{\text{ESP32}}(W) \sim R_{\text{Arduino}}(W) \sim R_{\text{Host}}(W) \sim R_{\text{Rust}}(W)
   \]
7. **`PHYS-M5-G07` (Recovery Continuity & Quarantine)**: Clean reboot resynchronizes to canonical chain; tampered/forged historical state quarantined with transition halted.

### 6.3 Final Outcome & Governing Invariant
- **Wrong Authoritative Commits**: $\boxed{N_{\text{wrong authoritative commits}} = 0}$
- **Overall Campaign Status**: **QUALIFIED** (10/10 integrity assertions verified in `tests/test_v31_physical_confirmation.py`).


