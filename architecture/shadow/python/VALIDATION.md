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

## Canonical CI observation

Normal repository CI continues to fail before test execution because existing NPU tests import optional numpy/openvino dependencies not installed by the canonical CI workflow.

This is not attributed to shadow code.

## R3.2 next closure target

A2.1 graph substitution application:
- use accepted GraphReplacementCertificate as current runtime authorization artifact;
- lower active graph hash substitution into an ordinary UoW;
- preserve substitution epoch and certificate lineage;
- rejected/stale certificate must not be lowerable as authorized mutation.

This test preserves current A2.1 semantics. It does not add a new authority layer.
