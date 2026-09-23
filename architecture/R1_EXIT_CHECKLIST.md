# R1 Architecture/Evidence Mapping Exit Checklist

Branch: `research/uow-closure-architecture`

Control baseline: `f4dc767322233cd3bd9afc6c1b7af45a3987111d`

## Required mapping artifacts

- [x] Candidate axiom and structural-law inventory.
- [x] Capability preservation policy.
- [x] U1-U15/Q1/distributed-authority/A2 experiment catalog.
- [x] Individual reconstruction manifests through A2.8.
- [x] Current qualification claim -> experiment traceability.
- [x] Current source module -> semantic concept -> experiment map.
- [x] Initial machine-readable symbol map.
- [x] Archive runtime source dispositions.
- [x] Current and archived test -> experiment traceability.
- [x] Closure falsification matrix.
- [x] Requirement/capability unification falsification matrix.
- [x] Matched design vectors for closure tests.
- [x] Matched design vectors for requirement/capability tests.
- [x] Cross-language semantic/byte-conformance inventory.
- [x] Public API/export-surface architectural review.
- [x] Guarded P4 candidate register.

## Validation

Current canonical tests mapped: **27 / 27**.

Archived U1-U14B/Q1 tests mapped: **39 / 39**.

Unmapped current tests: **0**.

Unmapped archived tests: **0**.

Current claim-registry entries are mapped to experiment families. Historical U1-U13/U14-B/Q1 distinctions are intentionally preserved through manifests because the modern registry does not enumerate all of them individually.

## Preservation gaps carried into later phases

These are not blockers to R1 completion; they are explicit reconstruction obligations:

1. U14-B goal-driven graph synthesis — archive-only unique capability.
2. U12 threaded concurrent execution realization — archive-only.
3. U12 semantic matrix concurrency prior — archive-only.
4. Q1 logistics oracle/workload and human-signoff demonstration — archive lineage.
5. Python/C++ universal canonical-byte schema — not yet defined.
6. Canonical UoW vs A2 ParentContract/RealizationGraph — parallel ontologies requiring closure testing.
7. `QuorumCommitSequencer` -> qualification dependency inversion.
8. Flat top-level public API does not encode architectural layering.

## R1 exit decision

[
\boxed{R1 = COMPLETE}
]

R1 completion does **not** authorize refactoring.

It authorizes R2: drafting the language-neutral semantic specification in parallel with the existing runtime.

The branch remains additive:
- no source runtime modification;
- no public API modification;
- no deletion;
- no experiment deletion.
