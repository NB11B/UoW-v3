# UoW Closure Architecture Research

This directory is an additive research layer for the `research/uow-closure-architecture` branch.

## Purpose

The goal is not to minimize file count. The goal is to identify the smallest language-neutral architecture capable of reconstructing every demonstrated UoW capability and every meaningful falsification boundary.

The governing reconstruction criterion is:

[
\forall e \in \mathcal{E},\quad \operatorname{Reconstruct}(K,e)=PASS
]

where `K` is the candidate minimal invariant architecture and `\mathcal{E}` is the preserved experiment set.

## Branch rules

1. No production refactor or deletion until the mapping phase is complete.
2. Every experiment is treated as architectural evidence, not merely historical code.
3. Syntactic redundancy is not semantic redundancy.
4. A realization is retained when it provides a distinct substrate, performance, authority, durability, failure, or falsification property.
5. A component may be reduced only after its capabilities, negative controls, evidence level, and lineage are preserved elsewhere.
6. Repository organization should eventually reflect the architecture itself.
7. Language-specific implementations are realizations of language-neutral semantic contracts.

## Two repository axes

### Architectural axis

```text
axioms
  -> subaxioms
  -> capabilities
  -> realizations
  -> implementations
```

### Evidence axis

```text
U1-U10 -> U11 -> U12 -> U13 -> U14/U14-B -> Q1
       -> U15 -> distributed authority -> A2.0 ... A2.8
```

Every architectural primitive should point to experiments supporting it. Every experiment should declare the primitives and realizations it exercises.

## Initial semantic model

[
\mathcal{U}=(O,U,S,Q,R,B,P,C,A,\Delta,F,E)
]

- `O`: ontology
- `U`: semantic work contract
- `S`: authoritative state
- `Q`: requirements
- `R`: realization
- `B`: binding
- `P`: proposal
- `C`: conformance
- `A`: authority
- `Delta`: authorized transition
- `F`: external effect boundary
- `E`: evidence / lineage

This is a research hypothesis, not yet a replacement API.

## Current baseline

Branch base: `main@f4dc767322233cd3bd9afc6c1b7af45a3987111d` (A2.8 capstone).

The frozen pre-review research lineage remains in `NB11B/weights-on-the-fly` at `e9a143568180e612809dabd1352b023079c5001c`.
