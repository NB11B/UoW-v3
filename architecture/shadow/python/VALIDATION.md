# R3/R4 Validation Record

## R3 shadow parity and closure

- Commit 195e330 — shadow run 2 PASS.
- Commit 0825554 — shadow run 4 PASS.
- Commit dd4a718 — shadow run 6 PASS: A2.7 authorized mutation application closure.
- Commit d3dfe58 — shadow run 8 PASS: A2.1 graph substitution application closure.
- Commit 1e77c9e — shadow runs 15/16 PASS: actor rebinding behavioral/causal closure.
- Commit 03f0ef9 — shadow runs 17/18 PASS: delegation registration and idempotent failover closure.
- Commit 6b52087 — shadow runs 19/20 PASS: complete verified canonical-history application closure.
- Commit 6083f28 — shadow runs 21/22 PASS: minimal authority kernel parity.

## R3 interpretation

Supported:
- application of accepted/certified/authorized meta-state transitions can often be expressed as ordinary UoW state transitions;
- rejected or context-mismatched applications fail closed;
- evidence/lineage can be preserved in the lowered path.

Not claimed closed:
- external physical invocation;
- quorum/attestation formation;
- canonical-history selection/consensus;
- physical/WAL persistence mechanisms.

## R4 start — U1-U10

The first reconstruction runner deliberately excludes canonical uow.engine.commit.

Flow:

native UoW contract
-> pure native proposal
-> canonical deterministic conformance oracle
-> explicit shadow local authorization
-> minimal shadow AuthorizedTransition
-> shadow EvidenceEntry

The next workflow reconstructs:
- primitive instruction behavior;
- multi-step Minsky execution;
- differential equivalence to independent reference interpreter;
- bounded-state periodicity negative control;
- extensible large-integer state;
- semantic-matrix orthogonality;
- replay determinism;
- non-halting external step budget.

This is an initial reconstruction, not yet removal justification for the canonical engine.
