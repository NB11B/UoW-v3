# Canonical UoW System Acceptance Campaign

This is an **isolated qualification harness**, not a new UoW feature.

Its purpose is to answer one question:

> Does the extracted Unit-of-Work architecture behave as claimed when its major trust boundaries are exercised together?

## Claims exercised

The campaign covers:

- native UoW realization of a 2-counter Minsky machine;
- randomized differential equivalence against an independent reference machine;
- semantic-cell/computational orthogonality;
- independent local clocks with no shared mutable execution timer;
- causal ordering under randomized clock drift;
- bounded-state negative control;
- proposal isolation from state authority;
- stale/dependency/OCC/resource rejection;
- legal DAG completion;
- evidence-chain integrity;
- fsync-backed WAL state/evidence recovery;
- torn-tail handling;
- external-effect reconciliation after crash;
- idempotent compensation;
- exact reverse-order saga compensation;
- deterministic state/evidence replay.

## Run

```bash
python canonical_acceptance.py
```

To save the text report:

```bash
python canonical_acceptance.py --output acceptance_report.txt
```

## Important scope

The version in this directory uses a small reference backend so the **campaign design itself**
can be executed and falsified independently.

When moved into `NB11B/UoW`, keep the assertions and report format but replace the reference
backend calls with imports from the canonical repository:

- `uow` core primitives and engine;
- `foundations.universal_computation`;
- `uow.transactions`;
- `uow.orchestration`;
- `uow.resources`;
- `uow.effects`;
- the proposer seam once it is merged.

That local run is the decisive repository qualification. The standalone run here validates
that the acceptance scenario is coherent and that all required fault injections are executable.


## Timing-independence fidelity gate

The integrated repository acceptance includes the original Orchestrator timing
requirement. It runs 1,000 randomized independent clock-drift realizations by
default, verifies causal ordering, detects a deliberately shared mutable clock,
checks nested parent/child clock isolation, and executes canonical orchestration
with common host wall-clock APIs forbidden.

Run the timing regression directly:

```bash
python -m pytest -v tests/test_timing_independence.py
```

Change the integrated stress count with:

```bash
python qualification/uow_system_acceptance.py --timing-seeds 1000
```

This tests local timer independence. It does not claim arbitrary distributed
physical-clock synchronization.
