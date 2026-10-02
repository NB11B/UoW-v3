# KryonOS Realization Profile (ESP32-S3 Embedded Target)

This document formalizes the **KryonOS Embedded Realization Profile** for the Unit-of-Work (UoW) protocol.

---

## 1. Realization Scope: What KryonOS Is (and Is Not)

**KryonOS is not an alternate UoW protocol.**  
It is a concrete, physical edge realization of the UoW protocol designed for constrained microcontrollers:

\[
\boxed{
\text{UoW Protocol} \longrightarrow \text{KryonOS Runtime} \longrightarrow \text{Native Authority Gate} \longrightarrow \text{ESP32-S3 Silicon}
}
\]

In this architecture, work proposals originate from dynamically scheduled JavaScript applications running inside an embedded interpreter, but **all authoritative state transitions and physical actuations are governed by the native C++ authority kernel**:

```text
Duktape Application (Dynamic Script)
        │
        ▼ (Proposes / Requests Transition)
KryonOS Runtime Bridge
        │
        ▼
Native C++ UoW Authority Gate v1
        │
        ▼ (2D Epoch + Generation Fencing & Token Verification)
Certified Physical Effect
        │
        ▼
Actuator / GPIO / Physical World
```

---

## 2. Invariant: Application Replacement vs Authority Replacement

The central architectural finding demonstrated by the KryonOS realization is the strict separation between computational agency and execution authority:

\[
\boxed{
\text{Application Replacement} \not\Rightarrow \text{Authority Replacement}
}
\]

1. **Sandboxed Proposers**: Applications running in Duktape may be dynamically loaded, terminated, hot-swapped, or updated over the air.
2. **Immutable Gate**: The Native C++ Authority Gate enforces capability bounds, cryptographic token verification, authority epoch validation, and resource generation fencing regardless of what code runs in the application space.
3. **Escalation Defense**: An application script attempting direct hardware manipulation (e.g. bypassing `System.uow` to write directly to GPIO) is trapped and terminated at the OS/native boundary with zero physical effect.

---

## 3. Realization Compatibility Stack

The software surfaces are versioned hierarchically so that realization-specific components can evolve independently without altering the core protocol specification:

```text
UoW Protocol v3.1
    │
    ├── Embedded ABI v1           (Portable C ABI header & memory layout: uow.h)
    │
    ├── Native Authority Gate v1  (C++ core authority kernel: uow_native.cpp)
    │
    └── KryonOS Realization v1    (Duktape runtime bridge, NVS persistence, FreeRTOS tasks)
```

- **`@uow/* v1.0`**: Canonical TypeScript / JavaScript client interfaces (`packages/uow-kryonos`).
- **`Embedded ABI v1`**: Fixed-width, C99-compliant binary envelope structures.
- **`Native Authority Gate v1`**: Deterministic state machine enforcing HMAC-SHA256 signatures, 2D fencing, and fail-closed persistence.
- **`KryonOS Realization v1`**: Board support package, FreeRTOS task affinity, and NVS wear-leveling optimizations.

---

## 4. Separation of Realization Engineering from Protocol Rules

To maintain protocol universality, hardware-specific engineering practices within KryonOS are strictly quarantined to the realization layer:

| Mechanism | Classification | Architectural Justification |
|---|---|---|
| **Authority/resource freshness and stale-effect rejection** | **UoW Protocol Obligation** | Core causality invariant; stale authority or stale resource ownership must not authorize effects. Required across all valid realizations (databases, FPGAs, PLCs, distributed services). |
| **2D Epoch × Generation Fencing** | **KryonOS Qualified Realization Mechanism** | Concrete implementation tuple `(authority epoch, fencing generation)` satisfying freshness on embedded microcontroller silicon. |
| **Fail-Closed on Corrupted State** | **UoW Protocol Obligation** | Core evidence invariant; unverified or corrupted state must never execute optimistically. |
| **Batched Persistence** | **KryonOS Realization Optimization** | Flash memory wear-leveling and write-amplification mitigation on SPI flash. Not required for memory-only or battery-backed systems. |
| **FreeRTOS Yielding (`yield()`)** | **KryonOS Realization Optimization** | Prevents Task Watchdog Timer (TWDT) expiration on dual-core ESP32-S3. Unrelated to mathematical transition semantics. |

---

## 5. Physical Silicon Qualification Evidence

The KryonOS realization was qualified on physical **ESP32-S3-DevKitC-1-N16R8** hardware in the **Phase E4E Campaign**:
- **Cold Boot Safety**: Actuator outputs initialize to safe low (`GPIO 7 == 0`).
- **4-Quadrant Fencing**: Out-of-order epoch and generation injections denied with 0 physical pin leakage.
- **Delayed Network Packet Rejection**: Valid packets delivered after gate advancement rejected with 0 physical mutation.
- **10,000-Op Endurance**: Zero unauthorized mutations, zero duplicate effects, zero stale executions across 10,000 continuous stress operations.

Full campaign records: [`qualification/kryonos/esp32_e4e/`](../qualification/kryonos/esp32_e4e/).
