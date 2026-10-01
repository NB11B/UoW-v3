# Protocol Specification: Core Primitives

## 1. Unit of Work Invariant

A Unit of Work (UoW) is an immutable, mathematically certified transition contract defined by the tuple:

\[
U = (H, \Gamma, M, R, B, E, T)
\]

where:
- **\(H\) (Header)**: Cryptographic identity and semantic category pairing \((C_{\text{src}} \to C_{\text{tgt}})\) within the 8-category ontology (People, Processes, Data, Devices, Rules, Policies, Agents, Guidance).
- **\(\Gamma\) (Contract)**: Deterministic state transition function composed of ordered routes, conditional guards, atomic mutations, and terminal or successor routing.
- **\(M\) (Lifecycle)**: Execution phase, state classification, and termination criteria.
- **\(R\) (Realization)**: Target execution environment, hardware affinity, or delegate bindings.
- **\(B\) (Boundary)**: Information-flow isolation boundaries, taint tracking, and permission membranes.
- **\(E\) (Evidence)**: Append-only hash chain linking previous evidence root, certificate hash, pre-state hash, and post-state hash.
- **\(T\) (Timing)**: Local causal timing constraints, deadlines, and execution duration bounds independent of any global host clock.

## 2. Universal Determinism Rule

\[
\boxed{
\text{Same semantic work} + \text{same input state} + \text{same authority/evidence conditions} = \text{same valid result}
}
\]

Every conforming runtime, in every supported programming language, must compute identical state deltas, route selections, and cryptographic certificate hashes for the same inputs.
