# R6 Reduction Impact Map

## Purpose

Quantify where the validated R6 abstractions reduce duplicated control flow without erasing domain-specific semantics.

This is a structural measurement, not a deletion plan.

## Production recurrence census

Current `src/uow` search results:

| Pattern | Source modules |
|---|---:|
| proposal formation (`proposal = propose(...)`) | 11 |
| core certification (`certify(...)`) | 7 |
| transaction descriptor construction | 6 |
| sequencer commit calls | 5 |
| materialization certification | 4 |
| actor-binding validation | 5 |
| semantic projection | 4 |

The full proposal/certify/transaction/commit sequence is independently present in five high-level production modules:

1. `orchestration/runtime.py`
2. `proposer/engine.py`
3. `resources/runtime.py`
4. `effects/runner.py`
5. `effects/saga.py`

## What the common spine may consolidate

The validated R6 ApplicationSpine is a candidate home for the invariant sequence:

```text
candidate UoW
 -> proposal
 -> core conformance
 -> authorization profile
 -> authoritative transition
 -> evidence
```

A production-grade version would need a transaction/OCC-aware application strategy rather than assuming one local commit realization.

The spine can potentially remove repeated orchestration of these steps while preserving the existing implementations behind interfaces.

## What must remain outside the generic spine

### Materialization

Scheduler/completion/resource materializers derive domain-specific UoWs and require independent materialization certification.

The spine consumes the accepted UoW; it does not replace the materializer.

### Resource legality

Resource capacity, consumable budgets, leases, and starvation remain typed domain predicates.

### Model/proposer judging

Model proposal freshness, dependency readiness, batch OCC, resource legality, fallback, telemetry, and adaptation feedback remain proposer-domain logic.

### External effects

External invocation/reconciliation remains outside internal authority application.

Only intent/result/saga bookkeeping transitions can use the common application spine.

### Saga compensation

Reverse compensation order and unresolved external effects remain saga semantics.

### OCC

U12 demonstrates that whole-state freshness cannot replace typed read/write/coupling compatibility.

Transaction application must preserve an OCC-aware authority profile.

## Authority protocol reduction

The runtime-to-qualification import inversion is a separate reduction opportunity.

Current:

```text
src/uow/proposer/quorum_sequencer
        -> qualification.distributed_authority
```

Validated shadow target:

```text
runtime
   -> QuorumAuthorityProvider semantic interface
          -> portable authority realization
          -> physical authority realization
          -> test/qualification realization
```

This is a dependency-direction correction, not removal of distributed authority.

## Requirement/capability reduction

The R6 conformance registry tests a common typed invocation boundary for:

- quantitative resource capacity;
- resource binding integrity;
- relational OCC compatibility;
- qualified actor binding;
- semantic graph projection;
- delegation attenuation;
- external receipt authenticity;
- mutation-vote verification;
- quorum authorization verification.

Each registry entry retains the specialized canonical validator.

The intended reduction is:

```text
many incompatible invocation surfaces
        ->
one typed conformance interface
        ->
specialized predicates retained
```

not:

```text
all legality -> generic dictionary matcher
```

## Expected engineering impact

If R6 prototypes remain green, R7 can reorganize around three proven seams:

1. **Application seam** — how an accepted work item becomes authoritative.
2. **Conformance seam** — how typed domain requirements are evaluated.
3. **Authority-provider seam** — how authorization is formed and verified.

Realizations remain pluggable below those seams.

## Current reduction disposition

No file is deletion-eligible from this measurement alone.

The evidence supports interface/control-flow consolidation and dependency correction first.
