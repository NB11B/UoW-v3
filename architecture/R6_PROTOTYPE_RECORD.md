# R6 Prototype Record — Common Spine and Authority Protocol

## R6-A — Common authority application spine

Research-only module: `architecture/shadow/python/uow_shadow/spine.py`.

The prototype centralizes the native-UoW authority application sequence:

```text
UoW
 -> propose
 -> deterministic conformance
 -> local authorization profile
 -> AuthorizedTransition
 -> Evidence
```

Two execution-context policies are explicit:

- `OWNED`: the authoritative cursor must name the executing UoW.
- `DETACHED`: certified control-plane/bookkeeping work may execute without owning the enclosing cursor; its own transition relation determines whether the cursor changes.

This preserves the U11/U13/U14 cursor-owned path and the Q1 detached-control-plane finding without duplicated authority logic.

`reconstruction.py` now delegates native UoW application to this spine rather than directly calling:
- proposal formation;
- core conformance adapter;
- authorization;
- minimal transition application.

The full reconstructed experiment suite is the regression test for this consolidation.

## R6-B — Authority provider protocol

Research-only module: `architecture/shadow/python/uow_shadow/authority_protocol.py`.

The protocol requires semantic operations:

```text
collect_votes
form_authorization
apply_authorization
```

The shadow distributed-authority cluster implements this protocol.

Generic quorum submission therefore no longer depends on:
- qualification package classes;
- a particular physical transport;
- a specific replica implementation.

Qualification and physical authority systems are intended future realizations/adapters of the same semantic protocol.

## Reduction meaning

These prototypes demonstrate:

[
	ext{shared control flow}

eq
	ext{collapsed realizations}
]

They consolidate orchestration of invariants while retaining:
- specialized validators;
- authority profiles;
- WAL/quorum/memory realizations;
- physical authority evidence;
- external-effect boundaries;
- experiment controls.

## Acceptance

The prototype is accepted only if the complete shadow reconstruction/conformance suite remains green.

A passing R6-A/R6-B run makes these candidates eligible for later R7 repository reorganization, not immediate production deletion.
