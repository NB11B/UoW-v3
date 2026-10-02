# KryonOS Phase E4E Provenance & Source Trace

This document records the exact physical and software provenance of the **Phase E4E (ESP32-S3 Individual Node Qualification)** campaign incorporated into UoW v3.1.

---

## 1. Physical Hardware Target

- **Microcontroller**: Espressif ESP32-S3-WROOM-1 / ESP32-S3-DevKitC-1-N16R8
- **Core Architecture**: Dual-Core Xtensa LX7 @ 240 MHz
- **Memory**: 16 MB SPI Quad/Octal Flash, 8 MB Octal PSRAM
- **Peripherals Qualified**: GPIO 7 (Actuator / Relay Gate), Internal RTC / NVS Persistence
- **Execution Profile**: FreeRTOS dual-core tasking with Core 0 authority affinity and periodic yields.

---

## 2. Software Substrate

- **Operating System**: KryonOS v1.0
- **Scripting Engine**: Duktape Embedded JavaScript Engine (sandboxed application runtime)
- **Authority Kernel**: Native C++ UoW Authority Gate (`uow_native.cpp`, `uow_policy_table.cpp`, `uow_crypto.cpp`)
- **Persistence Store**: Native EEPROM/NVS atomic record store with corruption detection (`uow_persistence.cpp`)
- **Qualification Runner**: `uow_e4e_runner.cpp` (581 lines executing tests 1 through 10)
- **Host Testing Bridge**: `@uow/kryonos` TypeScript package (`packages/uow-kryonos/test/kryonos.test.ts`)

---

## 3. Realization vs Protocol Separation

As mandated by UoW architectural invariants:

1. **Protocol Invariant**:
   - The UoW tuple $U = (H, \Gamma, M, R, B, E, T)$ and its state-transition rules are hardware-independent.
   - The boundary between proposal and authority is mathematically absolute:
     \[
     \boxed{\text{Application Replacement} \not\Rightarrow \text{Authority Replacement}}
     \]
2. **KryonOS Realization Optimization**:
   - Batched persistence flushing and FreeRTOS task yielding (`vTaskDelay` / `yield()`) are realization-specific implementation choices inside KryonOS. They are **not** UoW protocol rules.
3. **Heterogeneous Realization Parity**:
   - E4E confirms ESP32 parity with the already-qualified host/native semantics; combined with the prior Arduino qualification, the cumulative evidence supports heterogeneous realization parity:
     \[
     R_{\text{Laptop}}(W) \sim R_{\text{Arduino}}(W) \sim R_{\text{ESP32}}(W)
     \]
