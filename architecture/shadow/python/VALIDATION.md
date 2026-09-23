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

Scope limitation:
- GraphReplacementCertificate formation remains outside the application-closure claim.
- this preserves current A2.1 semantics and does not assert that all certification is authority in every subsystem.

## Canonical CI observation

Normal repository CI continues to fail before test execution because existing NPU tests import optional numpy/openvino dependencies not installed by the canonical CI workflow.

This is not attributed to shadow code.

## R3.2 next closure target

A2.2/A2.3 actor rebinding application:
- current runtime validates binding and applies it in one method;
- no separate authority certificate is emitted for tier-1 rebinding;
- shadow lowering will record the accepted binding conformance identity as the application guard only for parity;
- rejected conformance or wrong guard must fail closed;
- the result will explicitly distinguish "validated application closure" from "authorization closure".
