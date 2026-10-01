# Protocol Specification: Authority Plane

## 1. The Three-Phase Authority Protocol

Authority in the UoW architecture is governed by a strict, three-phase deterministic protocol:

\[
\text{PROPOSE} \longrightarrow \text{CERTIFY} \longrightarrow \text{COMMIT}
\]

1. **PROPOSE (`propose`)**:
   - Any proposer (deterministic, heuristic, neural, stochastic, or external hardware) evaluates contract \(\Gamma\) against current pre-state \(S_0\).
   - Generates an uncommitted `Proposal` containing the proposed next state, selected route index, and successor pointer.
   - Proposing generates zero authoritative state mutations.

2. **CERTIFY (`certify`)**:
   - An authoritative certification entity independently re-evaluates the contract guards and mutations against the pre-state.
   - Verifies identity match, pre-state hash match, route determinism, state delta agreement, and successor alignment.
   - Emits a `CertificateResult`. If valid, generates a cryptographic certificate hash bound to the inputs. If invalid, emits a deterministic rejection code.

3. **COMMIT (`commit`)**:
   - Only a validly certified proposal can be committed.
   - Verifies certificate hash authenticity and state hash bindings.
   - Atomically advances the state sequence number, applies committed state, and appends an immutable `EvidenceRecord` to the evidence ledger.

## 2. Cryptographic Bindings

- Certificate Hash:
  \[
  H_{\text{cert}} = \text{SHA-256}(\text{canonical\_json}(U_{\text{id}}, H_{S_{\text{pre}}}, H_{S_{\text{prop}}}, \text{route\_idx}, \text{successor}, \text{halted}))
  \]
- Evidence Hash Chain:
  \[
  H_{E_i} = \text{SHA-256}(\text{canonical\_json}(i, U_{\text{id}}, H_{S_{\text{pre}}}, H_{S_{\text{post}}}, H_{\text{cert}}, H_{E_{i-1}}))
  \]
