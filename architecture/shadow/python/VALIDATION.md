# R3 Validation Record

## Shadow parity status

### Commit 195e330
Shadow workflow run 2: PASS.

### Commit 0825554
Shadow workflow run 4: PASS.

Added parity coverage:
- actor capability binding;
- semantic projection;
- authority-bypass rejection;
- delegation authority attenuation.

### Commit dd4a718
Shadow workflow run 6: PASS.

Closure result:
- A2.7 QC-authorized graph/binding mutation application can be lowered to an ordinary native UoW transition.
- Wrong authorization hash fails closed with no meta-state mutation.

Scope limitation:
- QC formation remains outside the closure claim.
- QC signature verification remains outside the closure claim.
- distributed AuthoritativeHistory construction remains outside the closure claim.
- WAL persistence remains outside the closure claim.

### Commit d3dfe58
Shadow workflow run 8: PASS.

Closure result:
- A2.1 accepted GraphReplacementCertificate application can be lowered to an ordinary native UoW transition.
- active graph hash, substitution epoch, and certificate lineage are preserved.
- rejected/stale graph substitution certificate cannot be lowered as an authorized mutation.

### Commit 1e77c9e
Shadow workflow runs 15 and 16: PASS.

Closure result:
- A2.2/A2.3 validated actor rebinding application can be lowered to an ordinary native UoW transition.
- accepted binding conformance is bound to the exact live graph hash.
- invalid binding conformance cannot construct the lowering.
- reuse against a different graph context fails closed.

Interpretation:
- behavioral and causal application closure is supported.
- full authority-equivalence remains OPEN because canonical tier-1 rebinding does not emit a separate authority artifact.

## Canonical CI observation

Normal repository CI continues to fail before test execution because existing NPU tests import optional numpy/openvino dependencies not installed by the canonical CI workflow.

This is not attributed to shadow code.

## R3.2 next closure target

A2.4 delegation registration and failover:
- lower only the state mutation after canonical DelegationCertificate validation;
- preserve child identity, delegate actor, generation, authority scope, and certificate lineage;
- authority inflation must remain non-lowerable;
- idempotent failover may replace the registered certificate;
- non-idempotent failover must not create replacement authority.

Certificate issuance and attenuation validation remain outside the application-closure claim.
