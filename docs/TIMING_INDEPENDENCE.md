# Timing Independence

Timer independence is a foundational fidelity requirement of the UoW architecture.

The canonical claim is not that distributed physical clocks can always be globally
synchronized. The claim is narrower and more important to the authority model:

> **UoW correctness does not require a shared mutable execution clock.**

## Invariant

Each timing domain may advance independently:

[
\tau_i \neq \tau_j
]

while legal coordination is determined by causal and contractual relationships,
not by a globally shared timer.

For permissible local-clock variation:

[
\boxed{
\text{causal/contract constraints preserved}
\Rightarrow
\text{certified computational result preserved}
}
]

The timing descriptor remains part of the UoW envelope:

[
U=(H,\Gamma,M,R,B,E,T)
]

but timing metadata does not grant state authority.

## What is qualified

The canonical timing campaign in
`qualification/timing_independence.py` reproduces the original Orchestrator
timing requirement without adding a new clock service to the kernel.

It verifies:

1. independently owned synthetic clocks for lifecycle, realization, evidence,
   and port roles;
2. parent/child clock isolation;
3. detection of a deliberately shared mutable clock;
4. causal dependency order winning over contradictory local clock readings;
5. 1,000 randomized independent clock-drift realizations with invariant
   certified domain state and transition ordering;
6. execution of canonical orchestration while `time.time`,
   `time.monotonic`, `time.perf_counter`, and `time.sleep` are forbidden.

The regression suite is:

```bash
python -m pytest -v tests/test_timing_independence.py
```

The integrated system acceptance campaign also runs the same timing gate.

## What is not claimed

This qualification does **not** establish a general solution for:

- distributed wall-clock synchronization;
- arbitrary network clock skew;
- global cross-domain deadline comparison;
- physical-clock drift estimation or resynchronization.

Those are separate distributed-systems concerns.

The architectural property being preserved is:

[
\boxed{
\text{local clocks are locally owned}
\quad\land\quad
\text{coordination is causal}
\quad\land\quad
\text{authority does not depend on one global timer}
}
]
