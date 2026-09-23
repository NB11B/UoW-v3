# Capability Preservation Ledger

Status values:
- CURRENT
- CURRENT_GENERAL / ARCHIVE_DOMAIN
- ARCHIVE_ONLY
- CURRENT_SEMANTICS / ARCHIVE_REALIZATION
- EVIDENCE_ONLY

## Foundational and derived campaigns

| Experiment | Capability | Current mapping | Preservation |
|---|---|---|---|
| U1-U10 | universal native UoW computation | foundations/universal_computation + core | P0/P2/P3 |
| U11 | self-hosted orchestration | orchestration state/materialization/scheduler | P0/P1/P3 |
| U12 | OCC, serializable concurrency, hidden coupling | transaction semantics current; original general concurrent engine archived | P0/P1/P2/P3 |
| U13 | resource envelopes, leases, legality dominance, policy seam | resources package | P0/P1/P2 |
| U14 | proposal/authority separation and proposer swappability | proposer package + integrations | P0/P1/P2 |
| U14-B | high-level goal -> candidate UoW graph -> deterministic certification | no current canonical implementation located | **P1/P2/P3 — ARCHIVE_ONLY** |
| Q1 | external effects, idempotency, receipts, sagas, partial observability, human signoff | generic effects current; logistics/human qualification primarily archived | P0/P1/P2/P3 |
| Timing | correctness without shared mutable clock | timing qualification + docs | P0/P2/P3 |

## U15

| Gate | Capability | Preservation |
|---|---|---|
| U15.1 | adaptive proposer contract + model identity/lineage | P0/P1 |
| U15.2 | certified adaptation observation | P0/P3 |
| U15.3 | closed-loop adaptation from certified outcomes | P1 |
| U15.4 | catastrophic learning degradation contained by authority boundary | **P2 critical** |
| U15.5 | physical NPU proposer realization | P1/P3 |
| U15.6 | stage/health/promote/rollback/restart model lifecycle | P1 |
| U15.7 | continuous adaptation/drift endurance | P1/P2/P3 |
| U15.8 | adaptive proposer under heterogeneous physical quorum | P1/P3 |

## Distributed authority / physical qualification

Preserve independently:
- deterministic replica agreement;
- 2-of-3 quorum safety;
- network self-healing;
- divergence quarantine;
- heterogeneous ESP32/STM32 pair agreement;
- heterogeneous ESP32/STM32/x86 2-of-3 quorum;
- physical evidence-chain recomputation;
- CPU/GPU/NPU execution/adaptation/performance evidence.

These are P1/P2/P3 assets and are not replaced by portable simulation.

## A2 Adaptive Composition

| Gate | Capability | Preservation |
|---|---|---|
| A2.0 | semantic projection and topology-independent equivalence | P0/P2 |
| A2.1 | certified graph substitution and fallback | P1/P2 |
| A2.2 | adaptive graph selection and actor binding | P1/P2 |
| A2.3 | actor fabric, discovery/qualification separation, leases, churn | P1/P2 |
| A2.4 | recursive delegation and authority attenuation | P0/P1/P2 |
| A2.5 | multi-orchestrator concurrency and partition convergence | P1/P2 |
| A2.6 | independent processes/sockets, packet faults, WAL crash recovery | P1/P2/P3 |
| A2.7 | quorum-certified runtime topology mutation | P0/P1/P2 |
| A2.8 | continuous adaptive topology evolution, objective comparison, hysteresis, poisoned-feedback containment | P1/P2/P3 |

## A2.8 controls that must not be optimized away

- B0 fixed/static baseline;
- B1 rule-based baseline;
- adaptive runtime;
- matched perturbation trace;
- objective function J;
- anti-thrashing hysteresis;
- observation poisoning;
- topology lineage;
- crash/recovery path.

The capstone integrates earlier mechanisms but does not erase their independent diagnostic value.

## Known preservation gaps

1. **U14-B graph synthesis is archive-only** in the current canonical repository.
2. **U12 general concurrent execution realization is archived** while OCC semantics remain current.
3. U12 semantic concurrency priors are archive-only.
4. Q1 logistics reference workload/oracle is archive-only.
5. Q1 human-signoff demonstration is not prominent in current main.
6. Current claim registry is richer for U14/U15/A2/physical work than for U1-U13/Q1 historical distinctions.
7. Python and embedded C++ share semantic authority grammar but do not yet universally share canonical bytes/hashes.
8. Composition and canonical UoW currently form parallel contract/realization ontologies.

These gaps must be resolved by reconstruction, retained realization, or archived-evidence disposition before reduction.
