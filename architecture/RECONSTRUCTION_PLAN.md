# UoW Architecture Reconstruction Plan

## Goal

Reconstruct the complete demonstrated UoW research program from the smallest defensible language-neutral invariant architecture, while preserving useful realizations, falsification instruments, physical evidence, and historical lineage.

The target is not minimum lines of code.

[
\boxed{
\text{Minimal architecture}
\;\land\;
\text{complete capability reconstruction}
}
]

## R0 — Frozen control

Control baseline:

- repository: `NB11B/UoW`
- commit: `f4dc767322233cd3bd9afc6c1b7af45a3987111d`
- state: A2.8 capstone
- branch: `research/uow-closure-architecture`

Rules:
- no deletion;
- no `src/uow` refactor;
- no public API change.

## R1 — Architecture/evidence mapping

Deliverables:
- candidate axiom map;
- capability ledger;
- experiment manifests;
- dependency/closure map;
- preservation policy;
- preservation-gap list.

Exit criterion:

[
\forall e \in \mathcal{E},\quad e\text{ has an explicit manifest or gap disposition}
]

## R2 — Language-neutral semantic specification

Define representation-independent contracts for:
- authoritative state;
- canonical identity;
- work contract;
- requirement/capability relation;
- realization;
- binding;
- proposal;
- conformance;
- authority;
- authorized transition;
- external effect;
- evidence/lineage.

Separate:
1. semantic conformance;
2. canonical byte/wire conformance.

No production code replacement at this stage.

## R3 — Shadow minimal implementation

Build a new implementation beside the existing runtime.

Requirements:
- no existing implementation removed;
- old and new paths can execute matched experiments;
- every shadow primitive cites the axiom/structural law it realizes.

This stage tests whether the proposed architecture is actually sufficient.

## R4 — Experiment reconstruction

Reconstruct in dependency order:

1. U1-U10 universal kernel
2. U11 self-hosting
3. U12 transactional concurrency
4. U13 resource governance
5. U14 proposer boundary
6. U14-B goal-driven graph synthesis
7. Q1 external effects
8. timing independence
9. U15 adaptation
10. distributed authority
11. A2.0-A2.7
12. A2.8 integration capstone

An integrated later experiment does not waive an earlier experiment.

## R5 — Cross-language conformance

At minimum compare existing Python and embedded C++ semantics.

Then define conformance vectors suitable for additional implementations such as Rust.

Required distinction:

[
Exec_L(U,S)=Exec_{reference}(U,S)
]

is semantic conformance.

[
CanonicalBytes_L(x)=CanonicalBytes_{reference}(x)
]

is byte/wire conformance.

These are tested separately.

## R6 — Reduction eligibility

Only after reconstruction passes may a current component be considered P4 scaffolding.

For every reduction candidate:

[
Cap(X)\subseteq Cap(X^*)
]

[
NC(X)\subseteq NC(X^*)
]

[
Evidence(X)\preceq Evidence(X^*)
]

and the unique realization set of `X` must be empty or explicitly retained.

## R7 — Repository structural reflection

Only after the invariant model survives reconstruction should the repository itself be reorganized around the architecture.

Target organizational dimensions:

```text
specification/
  ontology
  state
  identity
  requirements
  realization
  binding
  proposal
  conformance
  authority
  transition
  effects
  evidence

implementations/
  python
  cpp
  embedded
  future languages

realizations/
  scheduling
  commit
  persistence
  authority
  networking
  effects
  adaptation

experiments/
  historical and reconstructed manifests

qualification/
  portable
  physical
  negative-controls
  evidence
```

Exact directory names remain provisional until R4/R5 establish the true minimal boundaries.

## Final acceptance condition

Let `K_min` be the proposed minimal architecture and `E` the preserved experiment set.

The architecture is acceptable only if:

[
\forall e\in E,\quad Reconstruct(K_{min},e)=PASS
]

and removal of a claimed necessary invariant makes at least one required reconstruction fail.

That provides an experimental definition of architectural minimality rather than an aesthetic one.
