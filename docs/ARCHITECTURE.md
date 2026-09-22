# Architecture

## Invariant decomposition

The canonical architecture separates four primitive concerns:

1. **Ontology** — the semantic work pairing.
2. **Contract** — the deterministic transition relation.
3. **State** — immutable, hash-bound authoritative data.
4. **Authority** — PROPOSE -> CERTIFY -> COMMIT with append-only evidence.

Everything else is derived.

## Semantic ontology

The eight categories are:

- People
- Processes
- Data
- Devices
- Rules
- Policies
- Agents
- Guidance

Their Cartesian product yields exactly 64 directed matrix cells.

A matrix cell answers **what kind of work is this?** It does not answer how the
work executes and must never become an opcode table.

## Unit of Work

The canonical envelope remains:

```
U = (H, Gamma, M, R, B, E, T)
```

where H is identity/semantic classification, Gamma is the transition contract,
and M/R/B/E/T carry lifecycle, realization, boundary, evidence, and timing
descriptors without importing runtime implementations into the kernel.

## State

`WorldState` accepts immutable JSON-compatible typed values rather than the
research runtime's integer-only counter schema. This removes a proof-campaign
assumption while keeping canonical serialization and cryptographic hash binding.

The core state intentionally does not contain dedicated queue, active-set,
transaction, resource, model, or external-effect fields. Derived layers compose
those structures over the primitive state model.

## Successors

Dynamic routing is represented explicitly with `Successor.from_attribute(...)`.
The research sentinel `@DISPATCHED` is not part of the canonical contract.

## Authority boundary

A proposal has no state authority. Certification independently recomputes the
transition from the bound pre-state. Commit accepts only a certificate matching
the exact UoW, pre-state, route, post-state, successor, and halt decision.

This boundary is the stable seam for heuristic, optimization, learned, NPU, or
other probabilistic proposal systems.

## Derived layers: Transactions & Orchestration (Pass 2)

Pass 2 adds two foundational derived layers:

### 1. `uow.transactions` (OCC & Commit Sequencing)
- **Mathematical OCC Hazard Detection**:
  - `validate_occ(current_state, tx)` detects data hazards (`READ_WRITE_HAZARD`, `WRITE_WRITE_HAZARD`, and `HIDDEN_COUPLING_HAZARD`) purely without thread locks.
  - Read and write sets are recorded via `TransactionDescriptor`.
  - Zero partial mutation guarantee: transaction aborts leave authoritative state and evidence completely clean.
- **Commit Sequencer & Persistence**:
  - `CommitSequencer` protocol cleanly decouples concurrency execution from authoritative state commits.
  - `DeterministicSequencer`: in-memory sequential commit validation and state progression.
  - `WALSequencer`: append-only Write-Ahead Log persisting state transitions to disk for deterministic crash-recovery and audit replay.

### 2. `uow.orchestration` (Self-Hosted DAG Control)
- **Typed Orchestration State**:
  - `OrchestrationState` wraps `WorldState`, managing pending queue $Q_t$, active set $A_t$, DAG dependencies $D_t$, and completed set $C_t$ as typed views over immutable state attributes.
- **Native Scheduler UoW**:
  - Pure native scheduling step under `(RULES, PROCESSES)`.
  - Dynamically dispatches ready tasks, detects clean terminal completion, and detects cyclic/missing prerequisite deadlocks.

Dependency rule remains strictly invariant:
```
ontology -> state / contracts -> certification / evidence (kernel)
    ^                 ^
    |                 |
uow.transactions   uow.orchestration
```
The kernel never imports `transactions` or `orchestration`.
