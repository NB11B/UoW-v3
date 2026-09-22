# UoW

**Unit of Work as a typed, certifiable state transition.**

This repository is the canonical implementation of the UoW architecture recovered
from the Orchestrator research program. The design deliberately separates semantic
work classification from computational execution.

## Core model

A Unit of Work is represented as:

```
U = (H, Gamma, M, R, B, E, T)
```

The authoritative transition lifecycle is:

```
WorldState
    |
    v
 PROPOSE      candidate transition only
    |
    v
 CERTIFY      independent deterministic recomputation
    |
    v
 COMMIT       authoritative state change + evidence
```

The 8 work categories form 64 directed semantic pairings. Those pairings classify
what kind of work is occurring; they are not opcodes and do not grant execution
authority.

## Trust boundary

The core package has no dependency on:

- learned or probabilistic models
- NPU/GPU runtimes
- transaction scheduling
- resource schedulers
- external tool APIs
- domain-specific workflows

Those capabilities are layered above the primitive transition kernel.

A learned system may propose a transition or graph. It cannot commit authoritative
state. Correctness remains inside the deterministic certification boundary.

## Package layout

```
src/uow/
    ontology.py     semantic 8 x 8 work matrix
    state.py        immutable, hash-bound typed state
    contracts.py    U = (H, Gamma, M, R, B, E, T)
    engine.py       PROPOSE -> CERTIFY -> COMMIT and evidence
```

Derived runtime packages will be curated separately for transactions, resources,
external effects, orchestration, and proposer integrations.

## Research lineage

The pre-curation Orchestrator runtime is preserved as an immutable research
snapshot in the dedicated archival branch of NB11B/weights-on-the-fly. See
`docs/LINEAGE.md` for the exact provenance and migration rules.

## Development

```bash
python -m pytest -q
```

The canonical branch is intentionally being built from primitives outward rather
than copied wholesale from gate-specific research code.
