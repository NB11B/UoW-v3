# Protocol Specification: State Plane

## 1. WorldState Invariant

`WorldState` represents the immutable, globally addressable, hash-bound ledger state:

\[
S = (\mathcal{V}, H_S, N, c, \sigma)
\]

where:
- \(\mathcal{V}\): Key-value store of JSON-compatible typed data values.
- \(H_S\): Cryptographic hash (\(\text{SHA-256}\)) computed over the canonical serialization (RFC-8785) of \(\mathcal{V}\).
- \(N\): Monotonically increasing sequence number (\(N \in \mathbb{N}_{\ge 0}\)).
- \(c\): Current execution cursor pointing to the active UoW identity, or `None`.
- \(\sigma\): Lifecycle status enum (`RUNNING`, `HALTED`, `FAILED`).

## 2. Immutability & Transitions

1. Direct mutation of `WorldState` is forbidden across all language bindings.
2. State transitions occur strictly by deriving a new `WorldState` instance through certified mutations.
3. Every state instance is uniquely identified and content-addressed by its SHA-256 hex digest.
