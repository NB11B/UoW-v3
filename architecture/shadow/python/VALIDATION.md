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

## R3.2 actor rebinding experiment

Canonical A2.3 Tier-1 rebinding validates against the live active graph and then immediately mutates active_binding. It does not emit a separate authorization artifact.

The tightened shadow experiment therefore:
- requires accepted canonical validate_binding conformance;
- binds that conformance to the exact active graph hash;
- lowers only the binding-state mutation to an ordinary native UoW;
- records conformance identity in resulting meta-state/evidence;
- rejects reuse of accepted conformance under a different active graph;
- rejects invalid binding conformance before UoW construction.

Expected interpretation if PASS:
- behavioral and causal application closure is supported;
- full authority-equivalence remains OPEN because current A2.3 authority is implicit in runtime ownership rather than represented by a standalone artifact.
