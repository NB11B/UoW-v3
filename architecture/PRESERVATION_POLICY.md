# Capability Preservation Policy

## Core rule

No code is redundant merely because another implementation looks similar.

A component is eligible for reduction only after the repository can show that its semantic capabilities, negative controls, evidence level, lineage role, and unique realization properties are preserved.

[
\text{syntactic redundancy} \neq \text{semantic redundancy}
]

## Preservation classes

- **P0 — Axiomatic:** candidate primitive/law required by the architecture.
- **P1 — Capability realization:** one valid implementation of a capability.
- **P2 — Falsification instrument:** baseline, oracle, negative control, adversarial implementation, or fault injector.
- **P3 — Evidence / lineage:** historical or physical evidence supporting architectural claims.
- **P4 — Possible scaffolding:** implementation detail with no unique capability, control, evidence, or realization property.

Only P4 items are straightforward reduction candidates.

## Required disposition before removal

Every implementation must end in one of:

1. **RECONSTRUCTED** — capability and controls reproduce on the replacement architecture.
2. **RETAINED_REALIZATION** — implementation remains because it provides a distinct valid realization.
3. **ARCHIVED_EVIDENCE** — implementation is no longer active but remains immutable evidence/lineage.

`DELETED_AS_REDUNDANT` is not a valid research disposition.

## Reduction proof obligation

For a proposed replacement `X -> X*`:

[
Cap(X) \subseteq Cap(X^*)
]

[
NC(X) \subseteq NC(X^*)
]

[
Evidence(X) \preceq Evidence(X^*)
]

and either the realization class is preserved or the original remains as a retained realization.

## Evidence levels

Preserve the repository distinction between:

- SIMULATED
- PORTABLE
- PHYSICAL

A portable or simulated replacement never upgrades or substitutes for physical evidence.

## Historical experiments

Historical experiments remain relevant when they contain a unique:
- falsification boundary;
- independent oracle;
- realization;
- physical substrate;
- performance baseline;
- recovery path;
- human/external boundary;
- causal or timing test.

A newer integrated experiment does not automatically subsume earlier isolated experiments.
