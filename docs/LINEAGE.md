# Research lineage and curation rules

## Frozen source

The canonical repository is curated from the frozen pre-review Orchestrator
research snapshot:

- Source repository: `NB11B/weights-on-the-fly`
- Branch: `archive/orchestrator-u1-u14b-q1-2026-09-21`
- Snapshot commit: `e9a1435`
- Scope: Gates U1-U14-B and Qualification Q1

The archive remains recovery/lineage evidence. It is not the canonical package.

## Findings preserved during curation

The research program established the following architectural intent:

- the 64 work pairings remain semantic metadata
- UoW transitions use PROPOSE -> CERTIFY -> COMMIT
- the deterministic boundary owns authoritative state
- self-hosting, concurrency, resources, model proposals, and external effects are
  derived runtime capabilities
- TFWR is an external proposer/adaptation system, not a UoW kernel dependency

## Assumptions removed from the canonical core

The curation explicitly removes or isolates four research conveniences:

1. integer-only world variables
2. the magic dynamic-routing string `@DISPATCHED`
3. local in-memory commit locking as a universal persistence model
4. synchronous external tool invocation as the only effect model

The first two are corrected in the primitive package. The latter two belong to
future derived runtime layers: durable sequencing/WAL and asynchronous effect
receipts.

## Migration rule

No gate-specific component is promoted merely because it passed an experiment.
A component enters the canonical public API only when its responsibility cannot
be expressed more cleanly as a derived layer over the primitive kernel.
