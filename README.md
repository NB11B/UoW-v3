# Unit-of-Work (UoW) v3.1

[![CI Test Suite](https://github.com/NB11B/UoW-v3/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/NB11B/UoW-v3/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Rust: 1.80+](https://img.shields.io/badge/rust-1.80+-orange.svg)](https://www.rust-lang.org/)
[![TypeScript: 5.0+](https://img.shields.io/badge/typescript-5.0+-blue.svg)](https://www.typescriptlang.org/)
[![v3.1 Physical Qualification](https://img.shields.io/badge/v3.1%20Physical%20Qualification-Qualified-success.svg)](docs/V3_QUALIFICATION_PROVENANCE.md)

> **A typed, certifiable Unit-of-Work protocol and multi-language runtime architecture for deterministic authority over flexible computation across heterogeneous distributed hardware.**

Repository: [**https://github.com/NB11B/UoW-v3**](https://github.com/NB11B/UoW-v3)

---

## 1. Minimal Public API

The root API in v3 is intentionally minimal and ergonomic:

```python
from uow import UoW, WorldState, execute
```

Execution is unified and deterministic:

```python
# Execute a single Unit of Work:
state, ledger = execute(my_uow, state=initial_state)

# Execute an entire DAG of Work:
final_state, ledger = execute(uow_graph, state=initial_state)
```

All subsystem internals are strictly namespaced:

```python
import uow.authority   # PROPOSE -> CERTIFY -> COMMIT, distributed quorum, evidence ledgers
import uow.runtime     # DAG orchestration, OCC transactions, resource leases, effects, proposers
import uow.autonomy    # Goal profiles, gap/deficit analysis, autonomous repair, closure
import uow.semantic    # Semantic mediation, 64-cell ontology matrix, governed egress filters
import uow.economics   # Economic observations (compute/energy/market costs) as protocol data
import uow.protocol    # Canonical schemas and wire envelope definitions
import uow.adapters    # Hardware and neural model adapters (e.g. OpenVINO NPU)
```

Full backward compatibility with legacy v2 APIs is maintained via the compatibility layer:

```python
from uow.compat.v2 import (
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    Route,
    Successor,
    make_uow,
    DeterministicSequencer,
    FIFOSchedulingPolicy,
    CostEnergySchedulingPolicy,
    AdaptiveProposer,
    RealizationGraph,
    run,
)
```

---

## 2. Protocol Boundaries & Repository Architecture

The v3 repository is structured strictly around protocol boundaries:

```text
UoW-v3/
├── protocol/
│   ├── core/                  # Tuple definition, determinism rules, error taxonomy
│   ├── state/                 # WorldState immutability and RFC-8785 canonical hashing
│   ├── requirements/          # Resource envelopes and constraint definitions
│   ├── capabilities/          # Capability ontology, discovery, and placement
│   ├── realization/           # Sensor and execution harness boundaries
│   ├── authority/             # PROPOSE -> CERTIFY -> COMMIT specification
│   ├── evidence/              # Merkle hash chaining and non-repudiation
│   ├── transition/            # Route selection, guard evaluation, atomic mutations
│   ├── effects/               # Side-effect intents, receipts, and sagas
│   ├── lifecycle/             # Operating modes, goal profiles, policy transitions
│   └── economics/             # Economic observations (data plane) vs pricing policies
│
├── schemas/
│   ├── canonical/             # Authoritative schema definitions for all 11 core objects
│   ├── json/                  # 21 JSON schemas for contract, envelope, proposals, etc.
│   └── wire/                  # OpenAPI and wire protocol envelope definitions
│
├── conformance/
│   ├── vectors/               # 16 canonical cross-language golden test vectors
│   ├── semantic/              # Semantic equivalence test vectors
│   ├── wire/                  # Wire envelope executor reference
│   ├── authority/             # Authority verification vectors
│   └── negative_controls/     # Comprehensive rejection and boundary verification suite
│
├── runtimes/
│   ├── python/                # Python reference runtime pointer (packaged from src/uow/)
│   ├── cpp/                   # Native C++ core runtime (16/16 canonical vectors)
│   ├── rust/                  # Rust native runtime (Levels 0–2, OCC, WAL replay, DAG scheduler)
│   └── embedded/              # Microcontroller authority kernels (ESP32-S3, Arduino UNO Q)
│
├── sdk/
│   ├── typescript/            # Integration SDK + deterministic reference executor
│   ├── rust/                  # Rust native SDK crate (uow-core)
│   └── legacy/                # Enterprise & legacy surfaces (COBOL, Pascal, Perl)
│
├── adapters/                  # Hardware, model, and legacy compatibility adapters
├── examples/                  # Multilingual quickstarts (JS, TS, Rust, Python, COBOL, Pascal, Perl)
├── docs/                      # Capability ledger, language matrix, and provenance records
└── tests/                     # Comprehensive test suite
```

---

## 3. Language Support Matrix

UoW v3.1 Language Realizations:

```text
Python      Reference Runtime
C++         Native Core Runtime — 16/16 canonical vectors
Rust        Independent Native Runtime — Levels 0–2, 16/16 vectors
TypeScript  Integration SDK + deterministic reference executor
ESP32       KryonOS qualified physical realization
Arduino     Embedded physical authority
```

| Language | V3.1 Role | Technical Surface | Primary Location | Qualification & Conformance |
|---|---|---|---|---|
| **Python** | Reference runtime | Full algebraic engine, OCC, DAG, Autonomy | `src/uow/` | Pytest test suite (all gates passing) |
| **C++** | Native core runtime | 16/16 canonical vectors, modular state/evidence/idempotency | `runtimes/cpp/` | `conformance_runner.exe --all` (16/16 vectors) |
| **C** | ABI + embedded profile | Portable C header (`uow.h`) | `abi/c/` | FFI / ABI bounds |
| **Rust** | Independent native runtime & SDK | Levels 0–2 runtime (`uow-runtime`) + protocol SDK (`uow-core`) | `runtimes/rust/`, `sdk/rust/` | 16/16 canonical vectors + cargo integration tests |
| **TypeScript** | Integration SDK + deterministic reference executor | Client, envelope factory, and local executor | `sdk/typescript/` | `node --test` (16 golden vectors) |
| **JavaScript** | SDK consumer | Client interoperability demo | `examples/javascript/` | Pure JS execution |
| **Perl** | Tested protocol adapter | `UoW::Client` protocol adapter | `adapters/perl/`, `sdk/legacy/perl/` | `conformance.t` (62 checks) |
| **COBOL** | Wire/batch compatibility profile | 80-column card copybooks (`UOWENVLP.cpy`) | `sdk/legacy/cobol/` | Batch card codec |
| **Pascal** | Type/interface compatibility profile | Type specification (`UoWTypes.pas`) | `sdk/legacy/pascal/` | Type alignment |
| **ESP32** | KryonOS qualified physical realization | KryonOS + Native C++ Authority Gate (2D fencing) | `runtimes/embedded/esp32/` | Physical silicon qualification (E4E + M5) |
| **Arduino** | Embedded physical authority | Microcontroller authority kernel | `runtimes/embedded/arduino/` | Physical hardware qualification (M5) |

Detailed surface profiles and evidence mappings are maintained in [**`docs/LANGUAGE_MATRIX.md`**](docs/LANGUAGE_MATRIX.md) and [**`docs/V3_QUALIFICATION_PROVENANCE.md`**](docs/V3_QUALIFICATION_PROVENANCE.md).

---

## 4. The Canonical Protocol Envelope

All language runtimes, SDKs, and wire codecs conform to the same 11 canonical objects:

1. `UoWContract`
2. `State`
3. `Requirement`
4. `Capability`
5. `Proposal`
6. `Certificate`
7. `EvidenceRecord`
8. `ExecutionResult`
9. `EffectIntent`
10. `ResourceObservation`
11. `CostObservation`

The core invariant across all implementations is:

\[
\boxed{
\text{Same semantic work} + \text{same input state} + \text{same authority/evidence conditions} = \text{same valid result}
}
\]

---

## 5. Economics: Data, Not Policy

In UoW v3.1, economics is treated as data, not policy:

\[
\boxed{
\begin{aligned}
\text{Economic Observation} &= \text{Protocol (Data Plane)} \\
\text{Pricing Decision} &= \text{Replaceable Realization (Policy Plane)}
\end{aligned}
}
\]

The protocol carries compute cost, human cost, energy (Watts/Joules), resource cost, latency penalties, failure/recovery cost, market prices, and capacity/scarcity observations without dictating any specific pricing algorithm:

\[
C(u) = C_H + C_M + C_E + C_R + C_K + C_D
\]

- **Directly Measured Consumption**: Machine compute cycles ($C_M$), physical energy ($C_E$), and leased resource capacity ($C_R$) are directly measured from the execution substrate.
- **Deterministic Given Declared Inputs**: Human review cost ($C_H$), expected recovery cost ($C_K$), and delay/opportunity cost ($C_D$) are deterministic given declared valuation models and expectation inputs.

---

## 6. Verification and Conformance

A single reproducible release verification script is provided at `scripts/verify_v31_release.ps1`. Individual subsystem gates can also be verified directly:

### Python Test Suite
```powershell
python -m pytest -q
```

### Cross-Language Golden Vectors (TypeScript / JavaScript)
```powershell
npm test --prefix sdk/typescript
```

### Rust Protocol SDK
```powershell
cargo test --manifest-path sdk/rust/Cargo.toml
```

### Rust Native Runtime (Levels 0–2)
```powershell
cargo test --manifest-path runtimes/rust/Cargo.toml
```

### Native C++ Core (16/16 Vectors)
```powershell
g++ -std=c++17 -I runtimes/cpp/include runtimes/cpp/native_state.cpp runtimes/cpp/native_evidence.cpp runtimes/cpp/native_idempotency.cpp runtimes/cpp/native_protocol.cpp runtimes/cpp/conformance_runner.cpp -o runtimes/cpp/conformance_runner.exe
./runtimes/cpp/conformance_runner.exe --all conformance/vectors
```

### Perl Conformance
```powershell
perl -I adapters/perl adapters/perl/t/conformance.t
```

---

## 7. Provenance & Release Records

- **v3.1 Release Gates**: [**`docs/V31_RELEASE_GATES.md`**](docs/V31_RELEASE_GATES.md)
- **v3.1 Qualification Registry**: [**`docs/V3_QUALIFICATION_PROVENANCE.md`**](docs/V3_QUALIFICATION_PROVENANCE.md)
- **Capability Ledger**: [**`docs/CAPABILITY_LEDGER.md`**](docs/CAPABILITY_LEDGER.md)
- **Historical v3.0 Release Gates**: [**`docs/V3_RELEASE_GATES.md`**](docs/V3_RELEASE_GATES.md)
- **Inherited v2 Research & Mathematical Proofs**: [**`docs/V2_TO_V3_PROVENANCE.md`**](docs/V2_TO_V3_PROVENANCE.md)
