# UoW v3 Language Support Matrix

This matrix classifies the language implementations, SDKs, ABIs, adapters, and compatibility surfaces promoted from UoW v2 into UoW v3.
Per the consolidation rules: **finish the existing tested language surfaces first**. No new languages (e.g. Go, Java, .NET) are introduced in this phase.

---

## 1. Canonical Language Classification

| Language | Existing Role (v2) | V3 Role | Surface Type | Primary Target Location | Provenance Branch | Evidence Level | Conformance Vector Coverage |
|---|---|---|---|---|---|---|---|
| **Python** | Full canonical runtime | Reference runtime | Runtime | `runtimes/python/uow/` | `v2-origin/main` | L4 Formal & Host Qualified | 16/16 vectors |
| **C++** | Native/embedded qualification | Native runtime | Runtime | `runtimes/cpp/` | `feat/s2-heterogeneous-physical-qualification` | L3 Cross-language Qualified | Vectors 001, 002, 003, 004, 006 |
| **C** | ABI / constrained interface | ABI + embedded profile | C ABI Header | `abi/c/`, `runtimes/cpp/abi/` | `feat/runtime-substrate-semantics` | L3 ABI Qualified | Header ABI bounds |
| **Rust** | SDK + conformance work | Native SDK / runtime candidate | SDK / Runtime | `sdk/rust/`, `runtimes/rust/` | `feat/runtime-substrate-semantics` | L3 SDK Qualified | Vectors 001, 002, 003, 007 |
| **TypeScript** | SDK + executor + conformance | Primary integration SDK | SDK & Executor | `sdk/typescript/` | `feat/runtime-substrate-semantics` | L3 SDK Qualified | 16/16 vectors (`test/conformance.test.js`) |
| **JavaScript** | Example / client interoperability | SDK consumer | Example / Consumer | `examples/javascript/` | `feat/runtime-substrate-semantics` | L3 Example / Client | Client submission vector |
| **Perl** | Legacy client / conformance | Compatibility adapter | Adapter | `sdk/legacy/perl/`, `adapters/perl/` | `feat/runtime-substrate-semantics` | L3 Legacy Qualified | `legacy/perl/t/conformance.t` |
| **COBOL** | Copybooks / batch interface | Enterprise compatibility | Compatibility Surface | `sdk/legacy/cobol/` | `feat/runtime-substrate-semantics` | L3 Enterprise Qualified | 80-column card codec & copybooks |
| **Pascal** | Type / interface example | Compatibility / reference | Specification / Reference | `sdk/legacy/pascal/` | `feat/runtime-substrate-semantics` | L3 Type Qualified | Canonical record types |
| **ESP32 / Arduino C++** | Physical authority | Embedded runtime | Embedded Firmware | `runtimes/embedded/esp32/`, `runtimes/embedded/arduino/` | `feat/s2-heterogeneous-physical-qualification` | L1 Physical Hardware | Physical serial execution & quorum |

---

## 2. Detailed Technical Surface Profiles

### 2.1 Python (Reference Runtime)
- **Role**: Reference implementation containing complete algebraic state machine, OCC concurrency, DAG orchestration, resource accounting, external effect sagas, autonomous goal synthesis, and policy lifecycle.
- **Entry point**: Minimal root API: `from uow import UoW, WorldState, execute`
- **Submodules**:
  - `uow.authority`: PROPOSE, CERTIFY, COMMIT primitives, EvidenceLedger, DistributedQuorum
  - `uow.runtime`: DAG orchestration, OCC transactions, resource leasing, effect sagas, proposers
  - `uow.autonomy`: Goal profiles, gap/deficit analysis, autonomous repair, closure
  - `uow.semantic`: Mediation, disambiguation, governed egress filters
  - `uow.economics`: Economic observations, cost/energy metering
  - `uow.protocol`: Envelope, schemas, canonical types
  - `uow.adapters`: Hardware/model adapters (Intel AI Boost OpenVINO NPU, HuggingFace)
- **Testing**: 562 unit, integration, and qualification tests in `tests/`.

### 2.2 C++ & C ABI (Native Runtime & Interface)
- **Role**: High-performance native execution and portable FFI boundary for system integration.
- **Header**: `abi/c/include/uow.h` defines `uow_envelope_t`, `uow_state_t`, `uow_proposal_t`, `uow_certificate_t`, `uow_result_t`.
- **Wire & Conformance**: `runtimes/cpp/` implements SHA-256 state hashing and binary wire packing matching Python RFC-8785 canonical hashes.

### 2.3 Rust (Native SDK & Runtime Candidate)
- **Role**: Type-safe systems SDK with standalone serialization and kernel evaluation logic.
- **Crate**: `sdk/rust/` (`uow-sdk`)
- **Key Types**: `UoWContract`, `WorldState`, `Proposal`, `Certificate`, `EvidenceRecord`
- **Feature Set**: Cryptographic hash chaining (`sha2`), Serde JSON canonicalization, error taxonomy mapping.

### 2.4 TypeScript & JavaScript (Integration SDK & Consumer)
- **Role**: Web/Node integration tier providing complete envelope builders, validation against JSON schemas, and local deterministic execution harness.
- **Package**: `sdk/typescript/` (`@uow/sdk`)
- **Components**:
  - `client.ts`: High-level submission and validation client
  - `envelope.ts`: Envelope factory and canonical validator
  - `executor.ts`: Client-side deterministic execution engine
- **Test Suite**: `test/conformance.test.js` validating cross-language test vectors against canonical schemas.

### 2.5 Embedded C++ (ESP32-S3 & Arduino UNO Q)
- **Role**: Physical root-of-trust and deterministic edge authority.
- **Firmware Targets**:
  - ESP32-S3: Dual-core FreeRTOS firmware with core-affinity isolation (Core 0 = deterministic authority kernel, Core 1 = serial communication and proposal queue).
  - Arduino UNO Q: Microcontroller authority boundary for 2-of-3 heterogeneous quorum.
- **Evidence Reference**: Physical qualification logs preserved in v2 branch `feat/s2-heterogeneous-physical-qualification`.

### 2.6 Legacy Compatibility Surfaces (COBOL, Pascal, Perl)
- **COBOL**:
  - `UOWENVLP.cpy`: 80-column standard card layout copybook for batch transaction processing.
  - `UOWRSLT.cpy`: Execution result card layout copybook.
  - `card_codec.py`: Punch-card / fixed-width parser and canonical JSON bridge.
- **Pascal**:
  - `UoWTypes.pas`: Pascal record structures specifying standard field offsets and boundary constraints.
- **Perl**:
  - `UoW::Client`: Protocol client implementing envelope generation and REST/wire submission.
  - `t/conformance.t`: Test harness verifying protocol envelope compliance.
