# R4 Validation Record

## Reconstructed and passing

- U1-U10 — runs 23/24 PASS.
- U11 — runs 25/26 PASS.
- U12 — runs 27/28 PASS.
- U13 — runs 29/30 PASS.
- U14 — runs 31/32 PASS.
- U14-B — runs 33/34 PASS; archive-only preservation gap closed.
- Q1 — runs 37/38 PASS; detached certified control-plane transition distinction preserved.
- U15.1-U15.4 portable — run 39 PASS.

## U15 portable result

The reconstructed loop preserves:

adaptive proposer (zero authority)
-> deterministic Judge
-> certified materialization
-> minimal shadow authority transition
-> authoritative post-state
-> cryptographically bound AdaptationObservation
-> learner feedback
-> model generation update

The run preserves both positive and negative claims:
- policy adaptation reduces rejection rate under the tested drift scenario;
- workload drift still completes under deterministic authority;
- catastrophic model poisoning degrades proposal quality/fallback behavior rather than authoritative correctness;
- corrupt, duplicate, and stale feedback remain contained;
- update crashes roll back model state.

Physical U15.5-U15.8 evidence is not inferred from this portable reconstruction and remains a separate preservation/requalification obligation.

## Next

Proceed to distributed-authority portable reconstruction and then A2.0-A2.8 reconstruction, using the same preservation rule: application semantics may be reconstructed while attestation formation, physical substrate evidence, and external effects remain explicit boundaries where appropriate.
