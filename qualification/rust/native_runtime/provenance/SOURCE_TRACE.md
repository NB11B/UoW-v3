# Provenance Trace: Milestone v3.1-M4 Independent Rust Runtime

## 1. Lineage & Base Commit

- **Milestone**: `v3.1-M4`
- **Campaign ID**: `V31-RUST-RUNTIME`
- **Base Integration Commit**: `9c0be9836e84fe978b9429fb9799d9e9807b2bfa` (`merge: integrate v3.1-M3 native C++ full conformance`)
- **Parent Milestone**: `v3.1-m3-cpp-16vec-qualified` (`a22c0a0`)
- **Branch**: `v3.1/rust-native-runtime`

---

## 2. Architectural Separation & Crate Layout

```text
sdk/rust/ (uow-core 3.0.0)
├── protocol types (UoWEnvelope, EvidenceRecord, UoWResult)
├── serde serialization
├── hashing primitives (sha256_hex)
└── C ABI validation interfaces (uow_validate_envelope)

runtimes/rust/ (uow-runtime 3.1.0)
├── state.rs: WorldState & canonical JSON RFC-8785
├── engine.rs: Level 0 Transition Engine & 16-vector dispatcher
├── evidence.rs: EvidenceLedger hash chaining & integrity
├── idempotency.rs: IdempotencyStore & payload conflict defense
├── transactions.rs: Level 1 OCC footprints & deterministic sequencer
├── wal.rs: Level 1 Write-Ahead Logging & crash replay
├── orchestration.rs: Level 2 DAG scheduler & cycle defense
└── bin/conformance_runner.rs: Native CLI batch/vector test runner
```

---

## 3. Cryptographic Hashes (SHA-256)

### 3.1 Source Files
| File Path | SHA-256 Digest |
|---|---|
| `runtimes/rust/Cargo.toml` | `53e64ca5db397629dc69ad0f01d06620cbd9ce576ea03df6b9220dd4a27e4df2` |
| `runtimes/rust/src/lib.rs` | `1107b9961c720f6d9673bca56807acb45732bec5959e76f0eea5889b7a6c5974` |
| `runtimes/rust/src/state.rs` | `ae11656c26014514ed8fe7c3526193f7c1b70240519ec6972e026e66cabbe3cb` |
| `runtimes/rust/src/engine.rs` | `d1abf5ef79536ef60a3cff3b3aa207ed045c0917138c210194208154c66d38f3` |
| `runtimes/rust/src/evidence.rs` | `2639404c11153c407923f4830951feee0335841149debe0eb3ddb8a4c39c56fd` |
| `runtimes/rust/src/idempotency.rs` | `6f7b253274e0db7d2be1c797e4b10711ce849be14d795b5a10055029c4b064d1` |
| `runtimes/rust/src/transactions.rs` | `248146b33dbbacaa001a38f8b3c449129032ac5d4025b3c08171ed30a219a577` |
| `runtimes/rust/src/wal.rs` | `a0694f973835635e7bb2835e3ee011db530c3a0170621eb7dec8f4a8a5590d6e` |
| `runtimes/rust/src/orchestration.rs` | `0f695d1f27ac9471444ffc6a24dd6653bbf8325be9b2caa12f469a3dbb9beea4` |
| `runtimes/rust/src/bin/conformance_runner.rs` | `20c532c9129278bed1584e9c773e68b71062f330d5fe7e53daa95edd246b678d` |

### 3.2 Machine-Readable Qualification Vectors
| Vector File | SHA-256 Digest |
|---|---|
| `qualification/rust/native_runtime/vectors/occ_vectors.json` | `6ef7c562d0465d603d4a71e4c3529fc200543e714b68f74fefd987bc63dd3b6c` |
| `qualification/rust/native_runtime/vectors/sequencing_vectors.json` | `adfd16b7e057e13248c9e2345c563f102e532bdb7b6b3efcea97c7828aa587f4` |
| `qualification/rust/native_runtime/vectors/wal_replay_vectors.json` | `9600ff7133d0c16e05fbf376f03dc90ca0f2a5adda6bbae3b50f5022b1bd53ee` |
| `qualification/rust/native_runtime/vectors/orchestration_vectors.json` | `0ccb8a03c4748f719bf933957ba35fc2026badefe1cd244cdcb40e74009e41d2` |
| `qualification/rust/native_runtime/vectors/proposer_boundary_vectors.json` | `b03b4a0f534be80674de618adced15d11a7616f62d9799ce5a9dab8ce823c84b` |

---

## 4. Cross-Milestone Test Portability Note

During M3 integration, `tests/test_atomic_economics_qualification.py` was normalized to strip `\r\n` line endings when calculating SHA-256 digests over text/JSON vector files. This resolved platform checkout differences (`core.autocrlf = true`) on Windows while preserving the exact immutable LF digests recorded in `qualification/economics/atomic_cost/QUALIFICATION_MANIFEST.json`. This cross-milestone test portability fix ensures continuous green builds across all operating systems.
