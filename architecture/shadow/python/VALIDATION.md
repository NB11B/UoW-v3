# R4 Validation Record

## U1-U10
Shadow runs 23 and 24: PASS.

## U11
Shadow runs 25 and 26: PASS.

## U12
Shadow runs 27 and 28: PASS.

## U13
Shadow runs 29 and 30: PASS.

## U14
Commit 3d208af — shadow runs 31 and 32: PASS.

Preserved:
- pure non-authoritative proposer seam;
- deterministic legality judge;
- dependency/OCC/resource/freshness rejection;
- deterministic fallback after proposer failure;
- deterministic telemetry replay;
- stochastic, heuristic, and portable edge proposer realizations.

Physical NPU evidence is intentionally not inferred from the portable seam.

## U14-B next

The archive-only graph-synthesis capability has been ported into the shadow research layer from the frozen pre-consolidation source.

The port adapts the old generated task graph to current:
- ResourceBoundTask;
- current WorkCategory/MatrixCell;
- current orchestration state;
- current resource state;
- minimal shadow authority execution.

Acceptance requires:
- valid reconcile goal certifies and executes;
- cycle rejected;
- invalid ontology category rejected;
- dangling dependency rejected;
- replay deterministic.

If green, the critical U14-B preservation gap is no longer archive-only.
