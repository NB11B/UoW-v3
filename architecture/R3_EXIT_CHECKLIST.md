# R3 Shadow Minimal Implementation Exit Checklist

Control baseline: f4dc767322233cd3bd9afc6c1b7af45a3987111d

## Semantic shadow layer

- [x] Representation-neutral state, contract, proposal, conformance, attestation, evidence types.
- [x] Typed requirement/capability matcher primitives.
- [x] Canonical validator adapters.
- [x] Dedicated shadow CI.
- [x] No src/uow imports the shadow layer.
- [x] No public API changes.

## Validator parity

Initial parity established for:
- core deterministic certification;
- OCC;
- resource capacity;
- external receipt binding;
- actor binding;
- semantic projection;
- delegation attenuation.

## Closure results

- [x] A2.7 QC-authorized runtime mutation application — SUPPORTED.
- [x] A2.1 graph substitution application — SUPPORTED.
- [x] A2.2/A2.3 actor rebinding application — SUPPORTED WITH AUTHORITY CAVEAT.
- [x] A2.4 delegation registration/idempotent failover — SUPPORTED.
- [x] A2.5 verified canonical-history application — SUPPORTED WITH SELECTION/CONSENSUS CAVEAT.
- [x] External invocation preserved as an expected non-closure boundary.
- [x] Quorum formation/attestation formation remains outside application-closure claims.

## Minimal authority kernel

The research-only kernel explicitly separates:

Proposal
-> Conformance
-> Authorization
-> AuthorizedTransition
-> Evidence

Shadow workflow runs 21 and 22 passed the parity experiment.

The local deterministic authority profile intentionally models one current case where accepted deterministic conformance is sufficient local authorization. It does not generalize that rule to distributed authority or external effects.

## R3 conclusion

R3 demonstrates that a substantial part of the adaptive/meta-runtime can be represented as ordinary UoW-authorized state application once external validation/authorization artifacts exist.

The current evidence supports:

application closure != authorization-formation closure.

R3 is therefore complete enough to enter R4 experiment reconstruction.

No production implementation has been removed, modified, or replaced.
