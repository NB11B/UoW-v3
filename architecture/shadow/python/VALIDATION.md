# R4 Validation Record

## Reconstructed families already passing

- U1-U10: shadow runs 23/24 PASS.
- U11: shadow runs 25/26 PASS.
- U12: shadow runs 27/28 PASS.
- U13: shadow runs 29/30 PASS.
- U14: shadow runs 31/32 PASS.
- U14-B: shadow runs 33/34 PASS; archive-only preservation gap closed on the research branch.

## Q1 first run

Shadow run 36: 72 passed, 5 failed.

All five failures had the same cause:
- the generic reconstruction helper assumed an executing UoW must own WorldState.cursor;
- Q1 effect-intent/result and saga-progress transitions intentionally preserve an enclosing cursor and execute as certified bookkeeping/control-plane transitions.

No Q1 receipt, idempotency, compensation, or authority assertion failed. The tests failed before those semantics were reached.

## Q1 correction

A separate execution context is now explicit:

1. cursor-owned program execution:
   execute_one_reconstructed(graph, state)
   requires state.cursor to select the UoW.

2. detached certified control-plane transition:
   execute_explicit_uow_reconstructed(uow, state)
   does not claim cursor ownership and requires the UoW's own transition semantics to preserve/change cursor explicitly.

Both paths still use:
Proposal -> Conformance -> Local Authorization -> AuthorizedTransition -> Evidence.

The Q1 reconstruction now uses the detached path for:
- effect intent state;
- receipt/result state;
- pending-external state;
- saga progress;
- compensation status.

This preserves, rather than relaxes, cursor semantics.
