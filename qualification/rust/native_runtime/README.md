# Milestone v3.1-M4: Independent Rust Runtime Qualification

This package establishes the qualification evidence and cryptographic provenance for the **Independent Native Rust Runtime** (`uow-runtime`) under Unit-of-Work (UoW) protocol v3.1.

## Scope & Claim Boundary

- **Signoff Level**: Level 3 Runtime Qualified
- **Status**: **QUALIFIED**
- **Narrow Claim**:
  > **Rust is an independently executing UoW runtime qualified for canonical Level-0 semantics, transactional authority, crash replay, and deterministic DAG orchestration.**
- **Scope Boundary**:
  - **In Scope (Levels 0–2)**:
    - Level 0: Authoritative transitions ($PROPOSE \rightarrow CERTIFY \rightarrow COMMIT$), RFC-8785 canonical JSON, state hashing, guard evaluation, mutation application, evidence chaining, and idempotency caching.
    - Level 1: OCC transaction footprint validation, collision detection, deterministic commit sequencing, Write-Ahead Logging (WAL), and crash replay.
    - Level 2: Deterministic DAG orchestration, task dependency frontier resolution, cycle defense, and halt detection.
  - **Out of Scope**:
    - Autonomy, semantic mediation, learned proposers, economics, quorum, and physical hardware remain out of scope for M4.

## Architectural Separation

The package introduces and enforces a distinct architectural boundary:

$$\boxed{\text{SDK} \neq \text{Runtime}}$$

- `sdk/rust/` (`uow-core`): Protocol types, serialization, wire models, C ABI bindings.
- `runtimes/rust/` (`uow-runtime`): Independent execution engine, state authority, OCC sequencer, WAL recovery, and DAG scheduler.

## Verification Gates

| Gate ID | Name | Target / Criteria | Status |
|---|---|---|---|
| `RUST-M4-G01` | Canonical 16/16 Semantic Vectors | $\forall v \in V_{16}, \text{Exec}_{\text{Rust}}(v) = \text{Expected}(v)$ | **PASSED** |
| `RUST-M4-G02` | OCC Conflict Equivalence | Disjoint writes (ACCEPT); write/write, write/read, read/write, and stale sequence (REJECT) | **PASSED** |
| `RUST-M4-G03` | Deterministic Commit Sequencing | $Seq_{\text{Rust}}(S, T) = Seq_{\text{Python}}(S, T)$ across 50 repeated trials with zero wall-clock bias | **PASSED** |
| `RUST-M4-G04` | WAL Crash Replay Equivalence | $S_{\text{replayed}} = S_{\text{committed}} \land E_{\text{replayed}} = E_{\text{committed}}$; idempotent duplicate replay | **PASSED** |
| `RUST-M4-G05` | Deterministic DAG Orchestration | Frontier: $\{A, B\} \rightarrow \{B\} \rightarrow \{C\} \rightarrow \{D\} \rightarrow \text{HALT}$; cycle defense | **PASSED** |
| `RUST-M4-G06` | Proposer Non-Escalation | $\text{Proposer Capability} \not\Rightarrow \text{Commit Authority}$ (malicious proposals strictly rejected) | **PASSED** |

## Directory Contents

- `QUALIFICATION_MANIFEST.json`: Cryptographic manifest binding toolchain, commit hashes, and vector digests.
- `rust_native_runtime_qualification_report.md`: Formal qualification signoff report.
- `provenance/SOURCE_TRACE.md`: Complete provenance trace from lineage through compilation.
- `vectors/`: Machine-readable vectors for Gates 2 through 6.
- `results/rust_runtime_results.json`: Execution results and gate dispositions.
