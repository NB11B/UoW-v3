# Policy Semantics

Status: R7 additive specification surface.

A qualified policy is a versioned, evidence-backed rule that selects or constrains a valid realization for a region of work requirements and world state.

Conceptually:

[
Pi_k : (W,S) ightarrow G
]

subject to semantic, authority, evidence, temporal, resource, and failure constraints.

This surface is required by the frozen A3 and P1-P5 reference oracles.

## Required semantics

A policy specification must distinguish:

- work requirement projection from realization selection;
- policy candidate from qualified active policy;
- discovery from promotion authority;
- deterministic steady-state lookup from exploratory search;
- active policy from invalidated/stale policy;
- policy registry version from world-state version;
- policy lifecycle evidence from execution evidence;
- local execution capability from distributed policy authority.

## Registry

The policy registry is conceptually:

[
Pi_0 ightarrow Pi_1 ightarrow cdots ightarrow Pi_k
]

with each transition:
- atomic;
- versioned;
- causally bound;
- evidence-producing;
- authority-governed.

## A3 constraints

A3 requires:
- realization selection to operate over graphs, not device identifiers;
- policy reuse as normal execution under stable regimes;
- discovery as candidate generation only;
- prospective qualification before promotion;
- measurable policy residency, invalidation, and thrash.

## P1-P5 constraints

P1-P5 adds:
- deterministic U -> W projection;
- world snapshot S;
- distributed policy authority;
- transactional registry versioning;
- durable persistence and recovery;
- zero duplicate external effects;
- provenance linkage into execution certificates.

No Python class in the frozen policy branch is canonical merely because it implemented these semantics first.
