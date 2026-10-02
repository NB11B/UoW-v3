# UoW v3.0 Release Gates & Qualification Checklist

This document formalizes the 15 mandatory qualification gates required for the `v3.0-rc1` release candidate and final `v3.0.0` general availability of the Unit-of-Work (UoW) protocol and runtime.

---

## 15-Item Release Gate Checklist

| # | Release Gate | Scope & Verification Command | Criteria | Status |
|---|---|---|---|---|
| **G01** | **Physically Minimal Root API** | `src/uow/__init__.py` | Root module exports strictly 10 symbols: `UoW`, `WorldState`, `execute`, and 7 namespaced subsystems (`authority`, `runtime`, `autonomy`, `semantic`, `economics`, `protocol`, `adapters`). | **PASSED** |
| **G02** | **Full Legacy Compatibility Layer** | `src/uow/compat/v2.py` | Complete v2 API surface (`make_uow`, `Guard`, `Mutation`, `DeterministicSequencer`, etc.) accessible via explicit compatibility import. | **PASSED** |
| **G03** | **API Surface Minimalism Verification** | `pytest tests/test_public_api_surface.py` | `hasattr(uow, sym)` returns `False` for legacy symbols; root minimal execution succeeds. | **PASSED** |
| **G04** | **Python Reference Suite Regression Gate** | `python -m pytest -q` | All 584 unit, integration, and qualification tests pass without regression (baseline: 562 passed). | **PASSED** |
| **G05** | **Zero ML Framework Import Leaks** | `pytest tests/test_semantic_harness.py -k test_frozen_facade_and_zero_framework_import_leaks` | Clean subprocess importing `uow` does not load `torch`, `transformers`, `peft`, or `huggingface_hub`. | **PASSED** |
| **G06** | **Canonical Schema Specification** | `schemas/canonical/canonical_objects.json` | All 11 canonical objects defined with explicit types, required fields, and determinism constraints. | **PASSED** |
| **G07** | **16 Golden Conformance Vectors** | `pytest tests/test_conformance_vectors.py` | Golden vectors 001–016 loaded, validated, and executed matching cross-language expected hashes. | **PASSED** |
| **G08** | **Negative Controls & Tamper Suite** | `pytest conformance/negative_controls/test_negative_controls.py` | 13 negative control tests verifying tamper detection, invalid states, route failure, and replay rejection. | **PASSED** |
| **G09** | **TypeScript SDK & Reference Executor** | `node --experimental-strip-types --test sdk/typescript/test/conformance.test.js` | 16/16 golden vectors verified against canonical schemas and deterministic local executor. | **PASSED** |
| **G10** | **Rust SDK & Runtime Candidate** | `cargo test --manifest-path sdk/rust/Cargo.toml` | Rust crate compiles, tests pass, hash chaining and Serde canonicalization verified. | **PASSED** |
| **G11** | **Native C++ Core Runtime** | `g++ -std=c++17 -I runtimes/embedded/esp32 runtimes/cpp/core_semantics.cpp runtimes/embedded/esp32/uow_embedded.cpp -o runtimes/cpp/core_semantics.exe` | Compiles cleanly; passes execution and rejection verification modes. | **PASSED** |
| **G12** | **Legacy Language Compatibility Profiles** | `perl -I sdk/legacy/perl sdk/legacy/perl/t/conformance.t` | Perl adapter passes 62 checks; COBOL card copybooks and Pascal record types verified. | **PASSED** |
| **G13** | **Implementation Surface De-duplication** | `runtimes/` & `sdk/` | Duplicate `runtimes/rust/` eliminated; `runtimes/python/README.md` documents `src/uow/` packaging. | **PASSED** |
| **G14** | **Capability & Language Matrix Recalibration** | `docs/CAPABILITY_LEDGER.md`, `docs/LANGUAGE_MATRIX.md` | Accurate classification of all language roles; unproven v3 economic models marked `NOT_YET_QUALIFIED`. | **PASSED** |
| **G15** | **Clean Metadata & Immutable Provenance** | `sdk/rust/Cargo.toml`, `sdk/typescript/package.json`, `docs/V2_TO_V3_PROVENANCE.md` | Author fields updated to UoW maintainers; versioning aligned to `3.0.0-rc1`; v2 provenance permanently linked. | **PASSED** |

---

## Qualification Signoff

- **Target Tag**: `v3.0-rc1`
- **Branch**: `v3/api-hardening`
- **Release Disposition**: Ready for release candidate tagging and multi-platform staging.
