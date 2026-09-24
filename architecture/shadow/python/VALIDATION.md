# R4 Validation Record

## Reconstructed and passing

- U1-U10 — runs 23/24 PASS.
- U11 — runs 25/26 PASS.
- U12 — runs 27/28 PASS.
- U13 — runs 29/30 PASS.
- U14 — runs 31/32 PASS.
- U14-B — runs 33/34 PASS; archive-only preservation gap closed.
- Q1 — runs 37/38 PASS after separating cursor-owned execution from detached certified control-plane transitions.

## Q1 architectural result

Effect/saga bookkeeping transitions do not own the enclosing workflow cursor. They still pass the full authority grammar:

Proposal -> Conformance -> Authorization -> AuthorizedTransition -> Evidence

but execute through an explicit supplied-UoW path whose contract preserves the enclosing cursor.

This is a semantic distinction, not an exception to certification.

## U15 portable reconstruction in execution

The U15.1-U15.4 reconstruction builds on the already reconstructed U14 proposer seam.

Flow:

adaptive proposer (zero authority)
-> deterministic U14 Judge
-> certified scheduler materialization
-> minimal shadow authority transition
-> authoritative post-state
-> cryptographically bound AdaptationObservation
-> learner feedback buffer
-> model update / new ModelIdentity generation

Negative controls retained:
- catastrophic weight poisoning may trigger fallback but cannot corrupt authoritative state;
- corrupted feedback is dropped;
- duplicate feedback is dropped;
- stale feedback is dropped;
- update crash rolls back model weights and identity.

Physical NPU/hot-swap/quorum claims remain separate future reconstruction targets and are not inferred from portable reconstruction.
