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

## Derived layers

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
- **Certified Scheduler Materialization**:
  - `SchedulerMaterializer` lowers the ready frontier into an ordinary native UoW under `(RULES, PROCESSES)`.
  - `CompletionMaterializer` lowers task completion into `complete::<task>` under `(PROCESSES, RULES)`.
  - Zero privileged state mutations: all scheduling and completion transitions are verified by materialization certification and core `PROPOSE -> CERTIFY -> COMMIT`.
  - Deadlock is cleanly represented as generic `status="HALTED"` plus `__termination__="DEADLOCKED"`.

### 3. `uow.resources` (Authoritative Resource Governance & Legality Dominance)
- **Authoritative Hash-Bound State**:
  - Resource state $R_t \subset S_t$ is stored canonically in `state.attributes["__resources__"]`, directly altering $H(S_t)$ upon any lease, capacity, or counter change.
- **Leased Capacities vs. Consumable Budgets**:
  - $R^{lease} = \{\text{CPU, RAM, GPU, NPU slots}\}$ are temporarily allocated and return upon certified task completion.
  - $R^{consume} = \{\text{energy budget, financial cost}\}$ are permanently debited against host capacity upon dispatch.
- **Work-Bound Requirements**:
  - `ResourceBoundTask` binds the cryptographic requirement hash directly into `Header.parent_context`.
  - Direct invariant `verify_requirement_binding(task)` prevents forged registry requirements from being scheduled.
- **Certified Lease Lifecycle**:
  - `ResourceAwareSchedulerMaterializer` lowers dispatch into an ordinary UoW atomically updating $(Q, A, R) \to (Q', A', R')$.
  - `ResourceAwareCompletionMaterializer` lowers completion into an ordinary UoW releasing the task's exact lease.
- **Legality Dominance**:
  - Policy choice $\pi(O_t, R_t)$ proposes candidates, but independent deterministic certification recomputes $\sum_{u \in \Pi} \rho(u) \le R_t^{\text{avail}}$ before materialization.
- **Anti-Starvation Aging**:
  - Dynamic aging boosts starved tasks to urgency rank 0 after a configurable threshold of scheduling rounds.
- **Swappable Heuristics**:
  - Pluggable proposal heuristics (`FIFOSchedulingPolicy`, `GreedyCapacitySchedulingPolicy`, `PriorityDeadlineSchedulingPolicy`, `CostEnergySchedulingPolicy`) can be swapped interchangeably without altering correctness, certification, or replay determinism.

Dependency rule remains strictly invariant:
```
ontology -> state / contracts -> certification / evidence (kernel)
    ^                 ^
    |                 |
uow.transactions   uow.orchestration
                          ^
                          |
                    uow.resources
```
The kernel never imports derived layers.
