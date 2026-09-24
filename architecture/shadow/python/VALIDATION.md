# R3/R4 Validation Record

## R3 summary

Application closure supported for:
- A2.7 QC-authorized runtime mutation;
- A2.1 graph substitution;
- A2.2/A2.3 actor rebinding, with authority caveat;
- A2.4 delegation registration/idempotent failover;
- A2.5 verified canonical-history application, with selection/consensus caveat.

Minimal authority kernel parity passed shadow runs 21 and 22.

## R4 U1-U10

Commit 7485dbb — shadow runs 23 and 24: PASS.

Initial reconstruction preserves:
- primitive HALT/INC/DECJZ behavior;
- multi-step two-counter computation;
- independent reference-interpreter agreement;
- bounded-state periodicity negative control;
- extensible state beyond 1024 bits;
- semantic-matrix orthogonality;
- deterministic replay/evidence root;
- externally bounded non-halting growth.

The reconstruction runner explicitly excludes canonical uow.engine.commit. Native UoW proposal and deterministic certification remain the initial semantic oracle; accepted transitions are applied by the R3 minimal authority kernel.

Interpretation:
- U1-U10 can already be reproduced through the recovered authority invariants without the canonical commit implementation.
- This is not yet evidence that native proposal/certification code can be deleted or replaced.

## R4 U11 next

Self-hosted orchestration reconstruction:
- scheduler and completion remain dynamically materialized ordinary UoWs;
- every materialization must pass independent materialization certification;
- accepted scheduler/domain/completion transitions use the minimal shadow authority kernel;
- canonical run_orchestration and DeterministicSequencer.commit are excluded from the reconstruction path;
- deadlock and tampered materialization controls remain required.
