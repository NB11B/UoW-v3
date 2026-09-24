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
Shadow runs 31 and 32: PASS.

## U14-B
Commit e6b1080 — shadow runs 33 and 34: PASS.

The archive-only graph-synthesis capability is restored on the research branch:
- valid reconcile goal produces a certified executable five-step graph;
- cycle rejected before execution;
- invalid ontology category rejected;
- dangling dependency rejected;
- replay deterministic.

This closes the U14-B preservation gap without adding the implementation to src/uow.

## Q1 next

The Q1 reconstruction keeps the external-action boundary explicit.

Internal transitions:
- intent commit;
- pending-external state;
- result commit;
- saga progress;
- compensation state

use the minimal shadow authority kernel.

External operations:
- invoke;
- reconcile/query;
- compensation invocation

remain outside the internal transition algebra.

Acceptance requires crash-window reconciliation without duplicate invocation, reverse compensation order, and preserved compensation-failure state.
