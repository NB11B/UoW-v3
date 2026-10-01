# Unit-of-Work (UoW) v3.0

[![CI Test Suite](https://github.com/NB11B/UoW-v3/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/NB11B/UoW-v3/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Rust: 1.80+](https://img.shields.io/badge/rust-1.80+-orange.svg)](https://www.rust-lang.org/)
[![TypeScript: 5.0+](https://img.shields.io/badge/typescript-5.0+-blue.svg)](https://www.typescriptlang.org/)
[![Physical Qualification: Sealed](https://img.shields.io/badge/Physical%20Qualification-ESP32%20%2B%20Arduino%20Passed-success.svg)](docs/V2_TO_V3_PROVENANCE.md)

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
│   ├── python/                # Python reference runtime
│   ├── rust/                  # Rust high-performance runtime
│   ├── cpp/                   # Native C++ runtime and wire serialization
│   └── embedded/              # Microcontroller authority kernels (ESP32-S3, Arduino UNO Q)
│
├── sdk/
│   ├── typescript/            # Primary TypeScript/JavaScript SDK and executor
│   ├── rust/                  # Native Rust SDK crate
│   └── legacy/                # Enterprise & legacy surfaces (COBOL, Pascal, Perl)
│
├── adapters/                  # Hardware, model, and legacy compatibility adapters
├── examples/                  # Multilingual quickstarts (JS, TS, Rust, Python, COBOL, Pascal, Perl)
├── docs/                      # Capability ledger, language matrix, and provenance records
└── tests/                     # Comprehensive test suite
```

---

## 3. Language Support Matrix

| Language | V3 Role | Technical Surface | Primary Location | Test Coverage |
|---|---|---|---|---|
| **Python** | Reference runtime | Full algebraic engine, OCC, DAG, Autonomy | `src/uow/` | 580 pytest tests |
| **C++** | Native runtime | High-performance state machine & hash profile | `runtimes/cpp/` | Native g++ & cross-language suite |
| **C** | ABI + embedded profile | Portable C header (`uow.h`) | `abi/c/` | FFI / ABI bounds |
| **Rust** | Native SDK / runtime candidate | Crate (`uow-core` / `uow-sdk`) | `sdk/rust/`, `runtimes/rust/` | `cargo test` |
| **TypeScript** | Primary integration SDK | Client, envelope factory, and local executor | `sdk/typescript/` | `node --test` (16 golden vectors) |
| **JavaScript** | SDK consumer | Client interoperability demo | `examples/javascript/` | Pure JS execution |
| **Perl** | Compatibility adapter | `UoW::Client` protocol adapter | `sdk/legacy/perl/` | `conformance.t` (62 checks) |
| **COBOL** | Enterprise compatibility | 80-column card copybooks (`UOWENVLP.cpy`) | `sdk/legacy/cobol/` | Batch card codec |
| **Pascal** | Compatibility / reference | Type specification (`UoWTypes.pas`) | `sdk/legacy/pascal/` | Type alignment |
| **ESP32 / Arduino C++**| Embedded runtime | Dual-core FreeRTOS & microcontroller authority | `runtimes/embedded/` | Hardware qualification sealed |

See [**`docs/LANGUAGE_MATRIX.md`**](docs/LANGUAGE_MATRIX.md) for detailed surface profiles.

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

In UoW v3, economics is treated as data, not policy:

\[
\boxed{
\begin{aligned}
\text{Economic Observation} &= \text{Protocol (Data Plane)} \\
\text{Pricing Decision} &= \text{Replaceable Realization (Policy Plane)}
\end{aligned}
}
\]

The protocol carries compute cost, human cost, energy (Watts/Joules), resource cost, latency penalties, failure/recovery cost, market prices, and capacity/scarcity observations without dictating any specific pricing algorithm.

---

## 6. Verification and Conformance

### Python Test Suite
```powershell
python -m pytest -q
```

### Cross-Language Golden Vectors (TypeScript / JavaScript)
```powershell
node --experimental-strip-types --test sdk/typescript/test/conformance.test.js
```

### Rust SDK
```powershell
cd sdk/rust
cargo test
```

### Native C++ Core
```powershell
g++ -std=c++17 -I runtimes/embedded/esp32 runtimes/cpp/core_semantics.cpp runtimes/embedded/esp32/uow_embedded.cpp -o runtimes/cpp/core_semantics.exe
./runtimes/cpp/core_semantics.exe transfer
```

### Perl Conformance
```powershell
perl -I sdk/legacy/perl sdk/legacy/perl/t/conformance.t
```

---

## 7. Provenance & Research Campaigns

All empirical proofs and mathematical campaign records (JEV operator closure, semigroup associativity, bilinearity, finite-size scaling, and physical qualification artifacts) are permanently sealed and immutable in UoW v2 history.
See [**`docs/V2_TO_V3_PROVENANCE.md`**](docs/V2_TO_V3_PROVENANCE.md) and [**`docs/CAPABILITY_LEDGER.md`**](docs/CAPABILITY_LEDGER.md).
