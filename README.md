# UoW

**A typed, certifiable Unit-of-Work architecture for deterministic authority over flexible computation.**

A Unit of Work is represented as:

[
U=(H,Gamma,M,R,B,E,T)
]

and authoritative state changes follow one boundary:

[
oxed{	ext{PROPOSE}ightarrow	ext{CERTIFY}ightarrow	ext{COMMIT}}
]

A proposal may come from deterministic code, stochastic search, a learned model,
an accelerator, an external service, or human-guided work. Proposal mechanisms
do not receive state authority. Only certified transitions commit.

## Architectural model

### Tier 1 — Core primitives

`src/uow/` defines the primitive algebra:

- the 8 semantic work categories and 64 directed pairings;
- immutable, hash-bound `WorldState`;
- the UoW envelope (H,Gamma,M,R,B,E,T);
- guards, mutations, successors, proposal, certification, commit, and evidence.

The semantic matrix classifies **what kind of work is occurring**. It is not an
opcode table.

### Tier 2 — Foundational constructions

`foundations/universal_computation/` lowers a two-counter Minsky machine into
ordinary native UoWs.

[
oxed{	ext{Universal Kernel}subset	ext{UoW Transition Algebra}}
]

under the standard extensible-memory abstraction.

The runtime does not contain a Minsky interpreter; the Minsky machine is
constructed from normal UoW guards, mutations, routing, state, and
certification.

The bounded-state negative control demonstrates the boundary: an 8-bit counter
cycles after (2^8=256) increments, while extensible state continues beyond
(2^{1024}+17).

### Tier 3 — Derived runtime

The same authority boundary composes into:

- `transactions/`: OCC, durable commit sequencing, WAL recovery;
- `orchestration/`: self-hosted DAG scheduling;
- `resources/`: authoritative resource state and certified leases;
- `effects/`: external intent, receipts, idempotency, sagas;
- `proposer/`: replaceable stochastic, heuristic, learned, or hardware proposer seam.

Derived layers do not bypass `PROPOSE → CERTIFY → COMMIT`.

### Tier 4 — Qualification

Qualification exists to falsify the architecture, not to define new behavior.

The canonical suite includes foundational, runtime, timing-independence, and
integrated system acceptance tests.

## Timer independence

Timer independence is an original architectural requirement.

[
oxed{
	ext{local clocks are locally owned}
quadlandquad
	ext{coordination is causal}
quadlandquad
	ext{authority does not depend on one global timer}
}
]

The canonical timing qualification:

- assigns independently owned timing domains to lifecycle, realization,
  evidence, ports, parent, and child roles;
- detects a deliberately shared mutable clock;
- verifies parent/child clock isolation;
- perturbs local clocks across 1,000 randomized drift realizations;
- proves dependency/causal order dominates contradictory local clock readings;
- runs canonical orchestration while `time.time`, `time.monotonic`,
  `time.perf_counter`, and `time.sleep` are unavailable.

This does **not** claim arbitrary distributed physical-clock synchronization.
It establishes that UoW correctness does not require a shared mutable execution
clock.

See `docs/TIMING_INDEPENDENCE.md`.

## Semantic orthogonality

The 64 directed semantic cells answer what kind of work is occurring.
Computational semantics remain in the transition contract.

[
oxed{	ext{Semantic Classification}perp	ext{Computational Semantics}}
]

Changing semantic-cell assignment does not alter the resulting computational
state or transition semantics. Semantic metadata may still affect audit
evidence because classification is intentionally evidence-bound.

## Hybrid authority boundary

The proposer seam preserves the hybrid architecture:

[
P_	heta(S_t)
ightarrow
pi_t
ightarrow
operatorname{CERTIFY}(pi_t,S_t)
ightarrow
operatorname{COMMIT/REJECT}
]

The proposal implementation may be replaced without changing authority
semantics.

## Reproducing the architecture

Requires Python 3.10+ and pytest.

```bash
python -m pip install -e .
python -m pip install pytest
```

Run the full repository suite:

```bash
python -m pytest -q
```

Run the original timing-independence invariant directly:

```bash
python -m pytest -v tests/test_timing_independence.py
```

Run the Minsky/universality construction:

```bash
python -m pytest -v tests/test_universal_computation.py
```

Run the integrated canonical acceptance campaign:

```bash
python qualification/uow_system_acceptance.py
```

The integrated campaign includes 1,000 randomized timing-drift realizations by
default.

For the larger foundational stress run:

```bash
python qualification/uow_system_acceptance.py \
  --step-programs 1000 \
  --steps-per-program 20 \
  --terminating-runs 500 \
  --timing-seeds 1000
```

This performs 20,000 randomized Minsky single-step comparisons, 500 terminating
whole-program comparisons, the timer-independence qualification, and the
integrated orchestration/durability/resource/effects/replay campaign.

## Canonical claims

The executable qualification suite is designed to reproduce these claims:

1. UoW is a typed, certifiable state-transition architecture.
2. Native UoW execution is computationally universal under extensible memory.
3. Semantic classification is orthogonal to computational semantics.
4. Local timing is independently owned; causal coordination does not require a global execution clock.
5. Proposals have zero authoritative state authority.
6. Only certified transitions commit.
7. Orchestration state can itself be represented by certified UoW transitions.
8. Unsafe concurrent transitions are rejected before mutation.
9. Resource legality remains deterministic independently of scheduling policy.
10. Durable recovery reconstructs authoritative state and evidence lineage.
11. External effects can be governed by durable intent, idempotency, receipt certification, and compensation.
12. The proposer implementation is replaceable without changing the authority model.

The architecture can be summarized as:

[
oxed{
	ext{Flexible Proposal}
ightarrow
	ext{Deterministic Certification}
ightarrow
	ext{Authoritative State + Evidence}
}
]
