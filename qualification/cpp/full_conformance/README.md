# Unit-of-Work v3.1 Milestone 3: Native C++ 16/16 Semantic Conformance

This directory records the formal qualification evidence and conformance reports for **Milestone v3.1-M3: Native C++ 16/16 Canonical Vector Conformance**.

---

## 1. Executive Summary

Milestone v3.1-M3 qualifies the host-native **C++ Unit-of-Work Runtime** against all 16 canonical golden conformance vectors without modifying the vectors.

### Narrow Claim Boundary
> **Native C++ semantic conformance: 16/16 canonical UoW v3 vectors.**

This confirms that the native C++ kernel correctly implements the Level 0 protocol wire and transition semantics:
- State transitions, guard evaluation, and atomic state mutations
- Evidence ledger hash chaining ($E_2.\text{prev} = H(E_1)$)
- Idempotency store caching and payload conflict rejection
- Domain operation lowering (`inventory.reserve` to UoW mutations)
- Envelope schema and protocol version validation
- Quorum certificate verification and authority escalation denial
- Exact multilingual UTF-8 state canonicalization
- Signed 64-bit integer preservation (`9007199254740991`) without floating-point precision loss

This qualification establishes protocol-level semantic conformance. It does not claim full implementation equivalence across Python's higher-level subsystems (such as autonomous goal repair, DAG workflow scheduling, or semantic mediation).

---

## 2. Directory Structure

- [`QUALIFICATION_MANIFEST.json`](QUALIFICATION_MANIFEST.json): Machine-readable manifest referencing canonical vectors and cryptographic source digests.
- [`cpp_16_vector_qualification_report.md`](cpp_16_vector_qualification_report.md): Technical qualification report detailing test results and evaluation metrics.
- [`provenance/SOURCE_TRACE.md`](provenance/SOURCE_TRACE.md): Cryptographic hashes of all compiler tools, source files, and baseline executables.
- [`results/cpp_vector_results.json`](results/cpp_vector_results.json): Per-vector execution results.
- [`baseline/`](baseline/): Frozen baseline executable of the original embedded core semantics runner.
