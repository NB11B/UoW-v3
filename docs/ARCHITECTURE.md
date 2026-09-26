# Architecture

## 4-Tier Architectural Decomposition

The repository organizes the Unit-of-Work system into four strictly separated tiers:

```
Tier 1: Core Primitives (src/uow/)
        Defines UoW itself: Ontology, Envelope, State, Authority Loop
            │
            ▼
Tier 2: Foundational Constructions (foundations/)
        Proves what the algebra expresses: Universal Computation, Minsky Lowering, Bounded Control
            │
            ▼
Tier 3: Derived Runtime (src/uow/...)
        Orchestration, OCC Transactions, Resource Governance, External Effects, Proposers
            │
            ▼
Tier 4: Qualification Scenarios (qualification/ & tests/)
        Logistics benchmarks, synthetic hosts, adversarial models, differential campaign
```

### Invariant decomposition

The canonical architecture separates four primitive concerns:

1. **Ontology** — the semantic work pairing.
2. **Contract** — the deterministic transition relation.
3. **State** — immutable, hash-bound authoritative data.
4. **Authority** — PROPOSE -> CERTIFY -> COMMIT with append-only evidence.

Everything else is derived or foundational evidence.

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

## Timing independence

Timing is part of the canonical UoW envelope through `T`, but it does not
grant state authority. The original Orchestrator requirement is preserved as:

[
oxed{
	ext{local clocks are locally owned}
land
	ext{coordination is causal}
land
	ext{authority does not depend on one global timer}
}
]

The canonical regression campaign perturbs independently owned lifecycle,
realization, evidence, port, parent, and child timing domains while requiring
the same certified computational result and legal transition ordering. It also
runs canonical orchestration with common host wall-clock APIs disabled.

This is a local-clock independence claim, not a claim that arbitrary distributed
physical clocks can always be synchronized. See `docs/TIMING_INDEPENDENCE.md`.

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

### 4. `uow.effects` (External Effects & Sagas)
- **External Action != Internal Commit**:
  - The runtime strictly separates internal transactional state changes from non-deterministic, asynchronous external interactions (APIs, payment processors, hardware devices, human signoffs).
- **The 6-Stage Durable Effect Lifecycle**:
  $$\boxed{
  \text{CERTIFY INTENT}
  \rightarrow
  \text{DURABLY COMMIT INTENT}
  \rightarrow
  \text{INVOKE}
  \rightarrow
  \text{OBSERVE}
  \rightarrow
  \text{CERTIFY RECEIPT}
  \rightarrow
  \text{COMMIT EFFECT RESULT}
  }$$
- **Deterministic Idempotency Key**:
  - Cryptographic token $K_{\text{idemp}} = H(uow\_id, state\_hash, intent, request)$ prevents duplicate external execution during crash recovery and retry loops.
- **Asynchronous Suspension (`PENDING_EXTERNAL`)**:
  - Long-running or multi-day external operations suspend the UoW cleanly into `PENDING_EXTERNAL` without holding system threads. When the external receipt arrives, an observation UoW advances $S_t \to S_{t+1}$.
- **Recovery Reconciliation**:
  - If a crash occurs after external invocation succeeds but before the receipt is committed, the reconciler queries external state using $K_{\text{idemp}}$ before deciding whether to invoke, guaranteeing zero duplicate side-effects.
- **Saga Orchestration & Reverse-Order Compensation**:
  - On downstream failure, the `SagaCoordinator` executes registered compensations in strict reverse order $[F_n, \dots, F_1]$.
  - If a compensation action itself fails, the effect enters `COMPENSATION_FAILED`, and the unresolved state is durably preserved in `__compensation_failed__` for operator remediation.
- **Replay Determinism**:
  - Replaying a certified history never re-executes external calls; cached certified receipts in the ledger provide deterministic transition outcomes.

### 5. `uow.proposer` (Proposer Seam, Reference Heuristic & Deterministic Judge)
- **Proposal Has Zero Authority**:
  - The model proposer emits pure speculative `ModelProposal` objects containing candidate schedules and predicted metrics.
  - Proposers possess zero direct authority over `WorldState`; all mutations must be materialized, certified, and committed through the authoritative engine.
  - Anything affecting authority or certification is hash-bound (`proposal_hash`); non-authoritative observational telemetry (e.g. accelerator device tags, debug logs) lives in `metadata` and is excluded from `proposal_hash`.
- **Deterministic Judge (Legality Dominance)**:
  - `certify_proposal(proposal, ready_tasks, graph, state)` independently validates candidate schedules against four strict invariants:
    1. *Freshness Check*: `input_state_hash` and `input_sequence` match current authoritative `WorldState` (Gate U14.6).
    2. *Dependency Readiness*: candidate tasks exist in graph and are present in the pending ready frontier (Gate U14.3).
    3. *Intra-Batch OCC Hazard Freedom*: concurrently proposed tasks have disjoint read/write footprints without write-write or read-write hazards (Gate U14.4).
    4. *Resource Capacity Bounds*: aggregate batch resource demand $\le$ available host capacities (Gate U14.5).
- **Deterministic Fallback Scheduler**:
  - The deterministic fallback provides a certified deterministic schedule whenever a legal ready task exists; correctness does not depend on proposer availability.
  - If a model proposer crashes, times out, or emits an empty or fully rejected schedule, the runtime immediately engages `DeterministicFallbackScheduler` (`PriorityDeadlineSchedulingPolicy`) (Gate U14.7).
- **Replay Determinism & Telemetry**:
  - Proposals and certificates are recorded in hash-bound `TelemetryRecord` objects. Replaying identical proposals reproduces byte-for-byte identical evidence roots and telemetry hashes (Gate U14.8).
- **Reference Heuristic & External Hardware Integrations**:
  - `HeuristicSchedulingProposer` provides a reference scheduling heuristic integrating priority ranking, deadline sensitivity, multidimensional bin-packing, and intra-batch OCC hazard avoidance.
  - External learned models and hardware accelerators (e.g. TFWR / NPU runtimes) plug in via `BaseProposer` (e.g. `integrations/tfwr/adapter.py`) without modifying the kernel (Gate U14.9, U14.10).
  - Gate U14 separates canonical executable qualification tests (reference heuristic vs random) from historical research campaign benchmarks (learned NPU model: 4.21 ms vs 2.61 ms, 2 rounds vs 3, 0 rejections vs 1).


### 6. Recursive composition boundary (Cybernetic System-as-Actor)
- **Conformance Boundary != Authority Grant**:
  - `CompositionBoundaryCertificate` attests that a child realization satisfies its own `ParentContract`.
  - It does not transfer parent mutation, verification, or commit authority. Explicit authority transfer remains governed by `DelegationCertificate` and authority attenuation.
- **Scoped Semantic Projection**:
  - Raw graph flattening is not a valid recursive operation because child-local roles would be interpreted as parent-local roles.
  - A nested child scope is first contracted to one certified logical actor boundary; only that contracted surface participates in the parent O/D/A/E/T/R/F projection.
  - The recursive conservation rule is therefore `Phi_parent(Contract(child), U_parent) = Phi(U_parent)`.
- **System-as-Actor Dispatch**:
  - `ActorRegistry` and `ActorBinding` continue to decide qualification and placement.
  - `ActorExecutionRegistry` is a derived runtime realization that optionally supplies how a qualified actor executes.
  - `CertifiedRuntimeActor` allows a complete boundary-certified `AdaptiveCompositionRuntime` to execute as one parent actor while the historical deterministic local simulator remains the fallback realization.
- **Encapsulation and Evidence**:
  - Only outputs explicitly declared by the parent logical node may cross the recursive boundary; unmapped or missing declared outputs fail closed.
  - Child execution evidence is hash-linked into the parent node result and parent execution evidence root.
  - Evidence chaining is timing-independent; diagnostic execution duration remains non-authoritative.
- **Fractal Reconfiguration**:
  - Child actor rebinding or semantically equivalent child topology replacement does not require parent recertification while the exported boundary projection remains invariant.
  - Boundary drift, recursive cycles, actor/authority loss, and output deficits fail closed before parent completion.


Dependency rule remains strictly invariant:
```
ontology -> state / contracts -> certification / evidence (kernel)
    ^                 ^                       ^
    |                 |                       |
uow.transactions   uow.orchestration      uow.composition
                          ^                    |
                          |                    v
                    uow.resources       actor execution realizations
                          ^
                          |
                      uow.effects
                          ^
                          |
                      uow.proposer
```
The kernel never imports derived layers.
