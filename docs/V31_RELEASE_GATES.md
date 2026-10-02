# UoW v3.1 Release Gates & Qualification Checklist

This document formalizes the mandatory qualification gates required for the `v3.1.0-rc1` release candidate and final `v3.1.0` general availability of the Unit-of-Work (UoW) protocol and runtime.

While [`docs/V3_RELEASE_GATES.md`](V3_RELEASE_GATES.md) preserves the historical v3.0 release gate record, this document certifies the completed v3.1 qualification campaigns and cross-language regressions.

---

## 15-Item Release Gate Checklist

| # | Release Gate | Scope & Verification Command | Criteria | Status |
|---|---|---|---|---|
| **G01** | **M1 KryonOS Physical Qualification** | `qualification/kryonos/esp32_e4e/` (`pytest tests/test_kryonos_qualification_evidence.py`) | ESP32-S3 physical silicon qualification: dynamic application replacement isolation, 4/4 2D fencing quadrants, 10,000-op endurance with 0 unauthorized mutations. Tag: `v3.1-m1-kryonos-qualified`. | **PASSED** |
| **G02** | **M2 Atomic Economics Qualification** | `src/uow/economics/` (`pytest tests/test_atomic_economics_qualification.py`) | 6-dimension orthogonal atomic cost $C(u) = C_H + C_M + C_E + C_R + C_K + C_D$, recursive composition conservation, friction vs work separation, and optimizer-proposal/authority-certification boundary. Tag: `v3.1-m2-atomic-economics-qualified`. | **PASSED** |
| **G03** | **M3 C++ 16/16 Canonical Conformance** | `runtimes/cpp/` (`pytest tests/test_cpp_full_conformance.py`) | Native C++ core runtime passes all 16 canonical golden vectors without modifying vector definitions; modular state, evidence, idempotency, and protocol layers. Tag: `v3.1-m3-cpp-16vec-qualified`. | **PASSED** |
| **G04** | **M4 Independent Rust Runtime (Levels 0–2)** | `runtimes/rust/` (`pytest tests/test_rust_full_conformance.py`, `tests/test_rust_qualification_gates.py`) | Independent Rust runtime (`uow-runtime` 3.1.0): 16/16 golden vectors, OCC conflict tracking, deterministic sequencing, WAL crash replay, DAG task orchestration, and proposer zero-authority boundary. Tag: `v3.1-m4-rust-runtime-qualified`. | **PASSED** |
| **G05** | **M5 Heterogeneous Physical Reconfirmation** | `qualification/physical/v31_confirmation/` (`pytest tests/test_v31_physical_confirmation.py`) | Heterogeneous 3-node physical network (ESP32-S3 on COM4, Arduino UNO Q on COM3, Laptop Host x86-64, plus Rust host witness): pairwise agreement across 24 vectors, live 2-of-3 quorum, fail-closed partition resilience, replay/stale rejection, zero wrong commits. Tag: `v3.1-m5-physical-confirmation-qualified`. | **PASSED** |
| **G06** | **Minimal Python API Unchanged** | `python -c "import uow; print(uow.__all__)"` | Root public API strictly preserved: `['UoW', 'WorldState', 'execute', 'authority', 'runtime', 'autonomy', 'semantic', 'economics', 'protocol', 'adapters']`. Legacy compat remains isolated under `uow.compat.v2`. | **PASSED** |
| **G07** | **Python Full Regression** | `python -m pytest -q` | All Python tests pass across core primitives, transactions, orchestration, semantics, autonomy, economics, KryonOS, and M1–M5 qualification suites (648+ tests). | **PASSED** |
| **G08** | **TypeScript 16/16 Golden Vectors** | `npm test --prefix sdk/typescript` | TypeScript SDK & reference executor passes all 16 golden test vectors and schema checks. | **PASSED** |
| **G09** | **Rust Protocol SDK Regression** | `cargo test --manifest-path sdk/rust/Cargo.toml` | `uow-core` compiles cleanly and passes C ABI validation and Serde envelope roundtrips. | **PASSED** |
| **G10** | **Rust Runtime Regression** | `cargo test --manifest-path runtimes/rust/Cargo.toml` | `uow-runtime` compiles cleanly and passes 8 integration tests covering Levels 0–2 invariants. | **PASSED** |
| **G11** | **C++ 16/16 Regression** | `runtimes/cpp/conformance_runner.exe --all conformance/vectors` | Native C++ runner builds and executes all 16 canonical vectors with 100% agreement. | **PASSED** |
| **G12** | **Perl Tested Adapter Regression** | `perl -I adapters/perl adapters/perl/t/conformance.t` | Protocol adapter passes all 62 assertions against golden vectors and wire envelopes. | **PASSED** |
| **G13** | **Fresh-Clone Reproducibility** | `scripts/verify_v31_release.ps1` | A completely fresh clone in a clean environment reproduces all compilation, tests, and vector checks via a single automated script. | **PASSED** |
| **G14** | **Version Consistency** | `pyproject.toml`, `Cargo.toml`, `package.json` | Package versions synchronized across Python (`3.1.0rc1` / `3.1.0`), Rust SDK (`3.1.0-rc1` / `3.1.0`), Rust Runtime (`3.1.0-rc1` / `3.1.0`), and TypeScript (`3.1.0-rc1` / `3.1.0`). | **PASSED** |
| **G15** | **Immutable Milestone Provenance** | `git merge-base --is-ancestor <tag> HEAD` | All five milestone tags (`v3.1-m1` through `v3.1-m5`) verified as immutable direct ancestors of the release candidate. | **PASSED** |

---

## Qualification Signoff

- **Target RC Tag**: `v3.1.0-rc1`
- **Target GA Tag**: `v3.1.0`
- **Lineage Base**: `v3.1/development` (`82c5f6e`)
- **Release Disposition**: Ready for production release and general availability.
