# Unit-of-Work (UoW) v2.0 Developer & Operator Guide

> **Authoritative, Deterministic Governance for Heterogeneous & AI-Augmented Systems**

---

## Table of Contents

1. [Executive Overview & Philosophy](#1-executive-overview--philosophy)
2. [The Core Mental Model](#2-the-core-mental-model)
   - [The Unit-of-Work 7-Tuple](#the-unit-of-work-7-tuple)
   - [The Three-Phase Authority Loop](#the-three-phase-authority-loop)
   - [Deterministic Primacy Invariant ($\beta_D = 0$)](#deterministic-primacy-invariant-beta_d--0)
3. [Installation & Environment Setup](#3-installation--environment-setup)
4. [Step-by-Step API Tutorials](#4-step-by-step-api-tutorials)
   - [Production Autonomy API](#production-autonomy-api)
   - [Level 0: Core State Transitions & Algebraic Invariants](#level-0-core-state-transitions--algebraic-invariants)
   - [Level 1: Optimistic Concurrency Control (OCC) & Crash Recovery](#level-1-optimistic-concurrency-control-occ--crash-recovery)
   - [Level 2: Self-Hosted DAG Workflow Orchestration](#level-2-self-hosted-dag-workflow-orchestration)
   - [Level 3: Multi-Dimensional Resource Governance & Leases](#level-3-multi-dimensional-resource-governance--leases)
   - [Level 4: External Side Effects, Sagas & The Idempotent Outbox](#level-4-external-side-effects-sagas--the-idempotent-outbox)
   - [Level 5: Replaceable & Adaptive Neural Proposers](#level-5-replaceable--adaptive-neural-proposers)
   - [Level 6: Recursive Composition & The System-as-Actor Pattern](#level-6-recursive-composition--the-system-as-actor-pattern)
   - [Level 7: Byzantine-Resilient Distributed Quorum Authority](#level-7-byzantine-resilient-distributed-quorum-authority)
   - [Level 8: Bounded Semantic Mediation & Governed Egress](#level-8-bounded-semantic-mediation--governed-egress)
   - [Level 9: Dynamic Policy Plane, Drift & Requalification](#level-9-dynamic-policy-plane-drift--requalification)
5. [Heterogeneous Hardware Spectrum & Embedded Deployment](#5-heterogeneous-hardware-spectrum--embedded-deployment)
   - [Host Accelerators (Intel AI Boost NPU & NVIDIA CUDA GPU)](#host-accelerators-intel-ai-boost-npu--nvidia-cuda-gpu)
   - [Embedded Microcontroller Nodes (ESP32-S3 Dual-Core FreeRTOS)](#embedded-microcontroller-nodes-esp32-s3-dual-core-freertos)
   - [Edge Semantic Harness on Arduino (STM32U585 / Embedded Micro-GPU)](#edge-semantic-harness-on-arduino-stm32u585--embedded-micro-gpu)
   - [Hardware Qualification & Testing Roadmap](#hardware-qualification--testing-roadmap)
6. [Best Practices, Testing Patterns & Anti-Patterns](#6-best-practices-testing-patterns--anti-patterns)
   - [The Golden Rules of UoW Engineering](#the-golden-rules-of-uow-engineering)
   - [Writing Clean Pytest Suites via the Public API](#writing-clean-pytest-suites-via-the-public-api)
   - [Common Anti-Patterns & How to Avoid Them](#common-anti-patterns--how-to-avoid-them)
7. [Public API Quick-Reference](#7-public-api-quick-reference)

---

## 1. Executive Overview & Philosophy

In modern distributed computing, autonomous agents, heuristics, machine learning models, and microservices often attempt to directly mutate application state. When unconstrained, these stochastic components introduce nondeterminism, lost updates, unreplayable errors, and audit failures.

**Unit-of-Work (UoW) v2.0** provides a mathematically rigorous, hardware-agnostic architecture that strictly separates:
- **Heuristics & Proposal:** Flexible, stochastic, AI-driven, or distributed logic proposes candidate transitions.
- **Authoritative Certification & Commitment:** A pure, deterministic state machine verifies preconditions (guards), checks causal invariants, cryptographically links evidence, and commits transitions.

No model, agent, network packet, or external side effect can directly touch authoritative state without progressing through the canonical authority loop.

---

## 2. The Core Mental Model

### The Unit-of-Work 7-Tuple

Every quantum of state evolution in UoW is represented as an immutable mathematical tuple:

$$U = (H, \Gamma, M, R, B, E, T)$$

```
+-----------------------------------------------------------------------+
|                       Unit of Work (U)                                |
+-----------------------------------------------------------------------+
|  H (Header)    : ID, epoch, lineage ancestry, content fingerprint    |
|  Γ (Guards)    : Set of preconditions evaluated over WorldState       |
|  M (Mutations) : Pure deterministic state mutation operations         |
|  R (Routing)   : Directed successor emission criteria (CONTINUE/HALT) |
|  B (Boundary)  : Resource bounds, authority constraints, leases       |
|  E (Evidence)  : Cryptographic hash links and witness obligations     |
|  T (Timing)    : Local causal tick (independent of wall clocks)       |
+-----------------------------------------------------------------------+
```

### The Three-Phase Authority Loop

State transitions proceed through three distinct phases:

```
 [ Input Signal / Heuristic / LLM ]
                 │
                 ▼
          1. PROPOSE (U)  ──► Generates candidate transition Proposal
                 │
                 ▼
          2. CERTIFY (U, S_t)  ──► Evaluates Guards Γ against WorldState S_t
                 │                  Fails if any guard precondition fails
                 ▼
          3. COMMIT (U, S_t, Cert) ──► Applies Mutations M atomically to S_t+1
                 │                      Emits cryptographic EvidenceRecord
                 ▼
          [ Committed State S_t+1 ]
```

### Deterministic Primacy Invariant ($\beta_D = 0$)

The parameter $\beta_D$ represents the degree of nondeterministic or stochastic control on the authoritative state-mutation path. In UoW v2.0:
$$\beta_D = 0$$

All neural networks, LLMs, external APIs, and heuristics operate strictly on the proposal side of the boundary. State machines, ledgers, and quorum coordinators remain 100% deterministic, auditable, and replayable from write-ahead logs.

---

## 3. Installation & Environment Setup

UoW v2.0 requires **Python 3.10+** and adheres strictly to a clean, isolated virtual environment.

```bash
# Clone the repository
git clone https://github.com/NB11B/UoW-v2.git
cd UoW-v2

# Create and activate a virtual environment
python -m venv .venv
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate

# Install dependencies in editable mode
pip install -e .
```

Verify your installation by running the public API verification test suite:

```bash
python -m pytest tests/test_api_quickstart_verification.py tests/test_autonomy_public_api.py -v
```

---

## 4. Step-by-Step API Tutorials

All examples in this section use production APIs:
- `uow`: Core transitions, transactions, orchestrators, resources, sagas, proposers, composition, distributed quorums, and policies.
- `uow.semantic`: Natural-language ingress, bounded semantic harnesses, compilers, and governed egress engines.
- `uow.autonomy`: Goal-directed planning, metacognitive deficit detection, bounded repair/adaptation routing, and autonomous closure. Its high-level facade is intentionally small; typed construction and execution adapters live under `uow.autonomy.model` and `uow.autonomy.ports`.

---

### Production Autonomy API

The production autonomy layer is the goal-directed control plane promoted to `main`. Its governing separation is:

```text
Autonomy proposes/organizes work
        ↓
WorkItemCompiler lowers proposed work
        ↓
native UoW
        ↓
ApplicationSpine: PROPOSE -> CERTIFY -> COMMIT
        ↓
authoritative WorldState + EvidenceLedger
```

`AutonomousRuntime` combines planning, semantic-deficit detection, bounded repair, adaptation routing, and closure. It never receives direct `commit()` authority.

#### Simulation / local development

Use `SimulatedExecutionPort` for deterministic tests and exploratory runs:

```python
from uow import WorldState
from uow.autonomy import (
    AutonomousRuntime,
    AutonomyBudget,
    AutonomyRequest,
    CapabilitySpec,
    GoalSpec,
    TerminalDisposition,
)
from uow.autonomy.model import PredicateOp, StatePredicate
from uow.autonomy.ports import SimulatedExecutionPort

initial = WorldState(attributes={"stepA": "pending", "stepB": "pending"})

request = AutonomyRequest(
    goal=GoalSpec(
        goal_id="complete_pipeline",
        desired_state=(
            StatePredicate("stepA", PredicateOp.EQ, "done"),
            StatePredicate("stepB", PredicateOp.EQ, "done"),
        ),
    ),
    capabilities=(
        CapabilitySpec(
            capability_id="do_a",
            effects=(StatePredicate("stepA", PredicateOp.EQ, "done"),),
        ),
        CapabilitySpec(
            capability_id="do_b",
            preconditions=(StatePredicate("stepA", PredicateOp.EQ, "done"),),
            effects=(StatePredicate("stepB", PredicateOp.EQ, "done"),),
        ),
    ),
    initial_state=initial,
    budget=AutonomyBudget(max_steps=20),
)

runtime = AutonomousRuntime(
    execution_port=SimulatedExecutionPort(initial_state=initial)
)
result = runtime.run(request)

assert result.success
assert result.disposition is TerminalDisposition.COMPLETE
assert result.final_state.require("stepA") == "done"
assert result.final_state.require("stepB") == "done"
```

`SimulatedExecutionPort` mutates only its simulation environment. Do not use it as the authoritative production state path.

#### Authoritative production execution

For production, implement a domain `WorkItemCompiler`, then use `ApplicationExecutionPort`. The compiler translates a domain-neutral autonomy `WorkItem` into the native UoW contract; the port performs authority checks and sends the resulting UoW through `ApplicationSpine`.

```python
from uow import (
    Guard,
    GuardOp,
    MatrixCell,
    Mutation,
    MutationOp,
    Route,
    Successor,
    WorkCategory,
    WorldState,
    make_uow,
)
from uow.autonomy import AutonomousRuntime, AutonomyRequest, CapabilitySpec, GoalSpec
from uow.autonomy.model import AuthorityScope, PredicateOp, StatePredicate, WorkItem
from uow.autonomy.ports import ApplicationExecutionPort
from uow.transactions import DeterministicSequencer

class DomainCompiler:
    def compile(self, item: WorkItem, state: WorldState):
        # In a real integration this mapping belongs to the domain adapter.
        if item.work_kind != "finish":
            raise ValueError(f"Unsupported work kind: {item.work_kind}")
        return make_uow(
            item.work_id,
            [
                Route(
                    guard=Guard(GuardOp.ALWAYS),
                    mutations=(Mutation(MutationOp.SET, "stage", "done"),),
                    successor=Successor.halt(),
                )
            ],
            MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA),
        )

initial = WorldState(attributes={"stage": "pending"})
sequencer = DeterministicSequencer(initial)
port = ApplicationExecutionPort(sequencer=sequencer, compiler=DomainCompiler())

request = AutonomyRequest(
    goal=GoalSpec(
        goal_id="finish_stage",
        desired_state=(StatePredicate("stage", PredicateOp.EQ, "done"),),
        authority_scope=AuthorityScope(("authority.default",)),
    ),
    capabilities=(
        CapabilitySpec(
            capability_id="finish",
            effects=(StatePredicate("stage", PredicateOp.EQ, "done"),),
            required_authority=("authority.default",),
        ),
    ),
    initial_state=initial,
)

result = AutonomousRuntime(execution_port=port).run(request)

assert result.success
assert sequencer.current_state.require("stage") == "done"
assert len(sequencer.ledger.records) == 1
```

Important boundaries:

- `AutonomousRuntime` may decide what work is necessary, but it cannot directly commit authoritative state.
- `CapabilitySpec` describes what the planner may use; `WorkItemCompiler` defines how that proposed work becomes a native UoW.
- `ApplicationExecutionPort` rejects missing authority before calling `ApplicationSpine`.
- If native UoW certification fails, authoritative state and the evidence ledger remain unchanged.
- The frozen research/evaluator implementation is not a runtime dependency of `uow.autonomy`; conformance is checked against sealed reference vectors.

---
### Level 0: Core State Transitions & Algebraic Invariants

Level 0 is the foundational algebraic transition kernel. You define preconditions (`Guard`), deterministic state transformations (`Mutation`), and causal routing (`Route`).

```python
from uow import (
    Guard,
    GuardOp,
    MatrixCell,
    Mutation,
    MutationOp,
    Route,
    Successor,
    WorkCategory,
    WorldState,
    certify,
    commit,
    make_uow,
    propose,
)

# 1. Initialize immutable WorldState
state = WorldState(attributes={"balance": 100, "status": "ACTIVE", "transfers_completed": 0})

# 2. Construct a Unit of Work with a balance guard and subtraction mutation
uow = make_uow(
    "tx_001",
    routes=[
        Route(
            guard=Guard(GuardOp.GTE, "balance", 30),
            mutations=(
                Mutation(MutationOp.SUB, "balance", 30),
                Mutation(MutationOp.ADD, "transfers_completed", 1),
            ),
            successor=Successor.halt(),
        )
    ],
    matrix_cell=MatrixCell(WorkCategory.PROCESSES, WorkCategory.DATA),
)

# 3. Propose candidate transition
proposal = propose(uow, state)
assert proposal.uow_id == "tx_001"

# 4. Certify preconditions against current WorldState
cert = certify(uow, state, proposal)
assert cert.is_valid is True

# 5. Commit state transition with causal evidence linkage
new_state, evidence = commit(
    uow,
    state,
    proposal,
    cert,
    prev_evidence_hash="0" * 64,
    step_number=1,
)

assert new_state.require("balance") == 70
assert new_state.require("transfers_completed") == 1
assert evidence.step_number == 1
assert evidence.record_hash is not None
print("Committed balance:", new_state.require("balance"))
```

---

### Level 1: Optimistic Concurrency Control (OCC) & Crash Recovery

When multiple concurrent operations target the same state, Level 1 provides transactional isolation with write-ahead logging (WAL) and replayable sequencer logic.

```python
from uow import (
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    Route,
    Successor,
    WorldState,
    certify,
    make_uow,
    propose,
)
from uow.transactions import DeterministicSequencer, create_transaction_descriptor, validate_occ

state = WorldState(attributes={"account_A": 500, "account_B": 200})
sequencer = DeterministicSequencer(state)

# 1. Construct transaction UoW
tx_uow = make_uow(
    "tx_transfer_01",
    routes=[
        Route(
            guard=Guard(GuardOp.ALWAYS),
            mutations=(
                Mutation(MutationOp.SUB, "account_A", 100),
                Mutation(MutationOp.ADD, "account_B", 100),
            ),
            successor=Successor.halt(),
        )
    ],
)
proposal = propose(tx_uow, state)
tx_desc = create_transaction_descriptor(tx_uow, state)
cert = certify(tx_uow, state, proposal)

# 2. OCC validation succeeds if read-set versions have not conflicted
is_valid, hazard, _ = validate_occ(state, tx_desc)
assert is_valid is True

# 3. Commit through sequencer to log in write-ahead log and advance state
new_state, evidence = sequencer.commit(tx_uow, proposal, tx_desc, cert)
assert new_state.require("account_A") == 400
assert new_state.require("account_B") == 300
assert len(sequencer.ledger.records) == 1
```

---

### Level 2: Self-Hosted DAG Workflow Orchestration

Complex multi-step workflows are structured as Directed Acyclic Graphs (DAGs) executed by the self-hosted orchestration engine.

```python
from uow import Guard, GuardOp, Mutation, MutationOp, Route
from uow.orchestration import (
    create_initial_orchestration_state,
    make_domain_task,
    run_orchestration,
)

# 1. Define modular domain tasks
task_a = make_domain_task("extract_features", [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 10),))])
task_b = make_domain_task("train_model", [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "r0", 20),))])

# 2. Wire dependency topology: train_model depends on extract_features
orch_init = create_initial_orchestration_state(
    ["extract_features", "train_model"],
    {"train_model": ["extract_features"]},
    attributes={"r0": 0},
)

# 3. Run orchestration engine to completion
orch_final, orch_seq = run_orchestration({"extract_features": task_a, "train_model": task_b}, orch_init)
assert orch_final.require("r0") == 30
assert orch_final.status == "HALTED"
print("Orchestration complete. Final r0:", orch_final.require("r0"))
```

---

### Level 3: Multi-Dimensional Resource Governance & Leases

Level 3 guarantees that compute, memory, bandwidth, or token allowances are not over-committed across concurrent workloads.

```python
from uow import Guard, GuardOp, Mutation, MutationOp, Route
from uow.orchestration import create_initial_orchestration_state
from uow.resources import (
    FIFOSchedulingPolicy,
    ResourceRequirement,
    ResourceState,
    get_authoritative_resource_state,
    make_resource_domain_task,
    run_resource_orchestration,
    set_authoritative_resource_state,
)

# 1. Initialize cluster resource capacities
cluster_resources = ResourceState(capacities={"cpu_cores": 16.0, "ram_units": 16.0, "gpu_slots": 2})

# 2. Create resource-governed domain task
npu_task = make_resource_domain_task(
    "inference_batch",
    [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "inferences", 10),))],
    requirement=ResourceRequirement(cpu_cores=2, ram_units=4),
)

# 3. Set authoritative resource state and schedule
initial_base = create_initial_orchestration_state(["inference_batch"], {}, attributes={"inferences": 0})
initial_state = set_authoritative_resource_state(initial_base, cluster_resources)
final_state, seq = run_resource_orchestration({"inference_batch": npu_task}, initial_state, FIFOSchedulingPolicy())

assert final_state.require("inferences") == 10
# All leases are cleanly released upon workflow completion
assert len(get_authoritative_resource_state(final_state).leases) == 0
```

---

### Level 4: External Side Effects, Sagas & The Idempotent Outbox

External network calls (REST APIs, cloud databases, hardware signals) must never run inside atomic state mutations. Level 4 encapsulates them into **Sagas** and **Effect Runners** backed by an idempotent outbox.

```python
from uow import WorldState
from uow.effects import EffectRunner, MockExternalClient, SagaCoordinator, SagaStep, create_effect_descriptor
from uow.transactions import DeterministicSequencer

client = MockExternalClient()
sequencer = DeterministicSequencer(WorldState(attributes={}))
runner = EffectRunner(sequencer, client)
coordinator = SagaCoordinator(runner)

# Define effect descriptor with idempotency token and compensation logic
step = SagaStep(
    "provision_storage",
    lambda state: create_effect_descriptor(
        uow_id="provision_storage",
        pre_state_hash=state.state_hash,
        intent="allocate_volume",
        request={"volume_id": "vol_42", "size_gb": 100},
        compensation_intent="deallocate_volume",
        compensation_request={"volume_id": "vol_42"},
    ),
)

# Execute saga: effects are dispatched and receipts logged idempotently
records = coordinator.execute_saga([step], saga_id="storage_saga_01")
assert len(records) == 1
assert len(client.call_log) > 0
```

---

### Level 5: Replaceable & Adaptive Neural Proposers

Heuristics, neural networks, or solvers can propose DAG task structures. If an accelerator fails or returns an invalid structure, the adaptive proposer cascades gracefully to deterministic fallbacks.

```python
from uow import Guard, GuardOp, Mutation, MutationOp, Route
from uow.orchestration import create_initial_orchestration_state
from uow.proposer import PortableAdaptiveProposer, ProposerOrchestrationEngine
from uow.resources import ResourceRequirement, ResourceState, make_resource_domain_task, set_authoritative_resource_state

res_caps = ResourceState(capacities={"cpu_cores": 8, "ram_units": 16})
res_req = ResourceRequirement(cpu_cores=2, ram_units=4)
res_task = make_resource_domain_task("res_1", [Route(Guard(GuardOp.ALWAYS), (Mutation(MutationOp.ADD, "out", 42),))], res_req)
res_base = create_initial_orchestration_state(["res_1"], {}, attributes={"out": 0})
res_init = set_authoritative_resource_state(res_base, res_caps)

# Initialize portable adaptive proposer with learned affinity weights
proposer = PortableAdaptiveProposer(initial_weights={"cpu_affinity": 1.0, "cpu_capacity": 8.0}, learning_rate=1.0)
engine = ProposerOrchestrationEngine(proposer=proposer)

final_state, seq, telem = engine.run_dag({"res_1": res_task}, res_init)
assert final_state.status == "HALTED"
assert final_state.require("out") == 42
```

---

### Level 6: Recursive Composition & The System-as-Actor Pattern

A complex subsystem DAG can be packaged and treated as a single atomic actor in a parent contract.

```python
from uow import (
    AuthorityObligation,
    CausalConstraint,
    EvidenceObligation,
    FailureSemantics,
    ParentContract,
    RealizationGraph,
    RealizationNode,
    ResourceConstraint,
    TemporalConstraint,
)
from uow.composition.boundary import certify_composition_boundary, verify_composition_boundary

# 1. Define parent boundary contract
pc = ParentContract(
    contract_id="pc_01",
    description="Cybernetic boundary",
    required_outputs=("out",),
    causal_constraints=(
        CausalConstraint("parser", "worker"),
        CausalConstraint("worker", "verifier"),
        CausalConstraint("verifier", "commit"),
    ),
    authority=AuthorityObligation(required_role="verifier", min_evidence_level="portable", quorum_threshold=1),
    evidence=EvidenceObligation(require_provenance=True, require_hash_chain=True, min_evidence_level="portable", verifier_id="recursive-test-judge"),
    temporal=TemporalConstraint(max_duration_ms=5000.0),
    resources=ResourceConstraint(max_cpu_cores=32, max_ram_units=64, max_gpu_slots=8, max_npu_slots=8, max_cost_units=500.0),
    failure_semantics=FailureSemantics.ROLLBACK,
)

# 2. Define realization graph
rg = RealizationGraph(
    "rg_01",
    {
        "parse": RealizationNode("parse", role="parser"),
        "work": RealizationNode("work", role="worker"),
        "verify": RealizationNode("verify", role="verifier", authority_tier="verifier"),
        "commit": RealizationNode("commit", role="commit", outputs=("out",)),
    },
    (("parse", "work"), ("work", "verify"), ("verify", "commit")),
)

# 3. Certify and verify boundary equivalence
bc = certify_composition_boundary("child-01", rg, pc)
assert bc.is_accepted and verify_composition_boundary(bc, rg, pc)
```

---

### Level 7: Byzantine-Resilient Distributed Quorum Authority

Decentralized deployments use quorum-certified mutations. Nodes collect signed cryptographic votes and construct a Quorum Certificate (`QC`) to mutate shared state.

```python
from uow import (
    ActorBinding,
    AuthoritativeHistory,
    AuthorityObligation,
    CausalConstraint,
    EvidenceObligation,
    FailureSemantics,
    ParentContract,
    RealizationGraph,
    RealizationNode,
    ResourceConstraint,
    TemporalConstraint,
)
from uow.composition import QuorumMutationCoordinator, assemble_mutation_qc

# 1. Setup parent contract and realization nodes
pc = ParentContract(
    contract_id="pc_01",
    description="Cybernetic boundary",
    required_outputs=("out",),
    causal_constraints=(
        CausalConstraint("parser", "worker"),
        CausalConstraint("worker", "verifier"),
        CausalConstraint("verifier", "commit"),
    ),
    authority=AuthorityObligation(required_role="verifier", min_evidence_level="portable", quorum_threshold=1),
    evidence=EvidenceObligation(require_provenance=True, require_hash_chain=True, min_evidence_level="portable", verifier_id="recursive-test-judge"),
    temporal=TemporalConstraint(max_duration_ms=5000.0),
    resources=ResourceConstraint(max_cpu_cores=32, max_ram_units=64, max_gpu_slots=8, max_npu_slots=8, max_cost_units=500.0),
    failure_semantics=FailureSemantics.ROLLBACK,
)
rg = RealizationGraph(
    "rg_01",
    {
        "parse": RealizationNode("parse", role="parser"),
        "work": RealizationNode("work", role="worker"),
        "verify": RealizationNode("verify", role="verifier", authority_tier="verifier"),
        "commit": RealizationNode("commit", role="commit", outputs=("out",)),
    },
    (("parse", "work"), ("work", "verify"), ("verify", "commit")),
)

binding_0 = ActorBinding("b0", "rg_01", {"parse": "a1", "work": "a1", "verify": "a1", "commit": "a1"})
binding_1 = ActorBinding("b1", "rg_01", {"parse": "a1", "work": "a1", "verify": "a1", "commit": "a1"})
auth_keys = {"a1": "k1_secret", "a2": "k2_secret", "a3": "k3_secret"}

# 2. Coordinator collects votes and assembles QC
qmc = QuorumMutationCoordinator(
    parent_contract=pc,
    active_graph=rg,
    active_binding=binding_0,
    history=AuthoritativeHistory(),
    authority_keys=auth_keys,
    generation=0,
    quorum_threshold=2,
)
prop = qmc.propose_mutation("npu_proposer", rg, binding_1)
votes = qmc.collect_votes(prop)
qc, msg = assemble_mutation_qc(prop, votes[:2], threshold=2)
assert qc is not None and msg == "QUORUM_CERTIFICATE_ASSEMBLED"

# 3. Apply mutation atomically across quorum
ok, status = qmc.apply_mutation(qc, rg, binding_1)
assert ok is True and status == "MUTATION_COMMITTED"
assert qmc.generation == 1
```

---

### Level 8: Bounded Semantic Mediation & Governed Egress

Level 8 connects language models and user text directly to UoW execution. Notice that **the model has zero mutation privileges**; it merely compiles to an admissible intent that passes through deterministic guards.

```python
from uow import WorldState
from uow.semantic import (
    DefaultSemanticAdmissibilityValidator,
    GovernedEgressEngine,
    IngressContext,
    RecipientProfile,
    SemanticApplicationAdapter,
    SemanticDisposition,
    SemanticHarness,
    SemanticRequirement,
    TransferUoWCompiler,
)
from uow.transactions import DeterministicSequencer

# 1. State and Ingress Context (Minimal deterministic context projection)
state_sem = WorldState(attributes={"default_operator": "transfer", "default_quantity": 25})
ingress = IngressContext(principal_id="alice", session_id="sess_01", channel="web", metadata={"recipient": "Bob"})

# 2. Bounded interpretation with deterministic primacy (beta_D = 0)
harness = SemanticHarness(admissibility_validator=DefaultSemanticAdmissibilityValidator())
sem_res = harness.interpret(
    "Transfer funds to Bob",
    state=state_sem,
    ingress=ingress,
    requirements=(
        SemanticRequirement("operator", state_key="default_operator"),
        SemanticRequirement("quantity", state_key="default_quantity"),
        SemanticRequirement("recipient", ingress_key="recipient"),
    ),
)
assert sem_res.disposition is SemanticDisposition.YES
assert sem_res.intent is not None

# 3. Deterministic compilation into governed UoW execution
adapter = SemanticApplicationAdapter()
prep = adapter.prepare(sem_res, state_sem, TransferUoWCompiler())
sem_seq = DeterministicSequencer(state_sem)
app_res = adapter.execute(prep, sem_seq)
assert app_res.state.attributes["transfers.Bob"] == 25

# 4. Governed Egress with Zero-Drift Verification
eg = GovernedEgressEngine()
eg_msg = eg.emit(sem_res, RecipientProfile.default_human(), status="COMMITTED")
assert eg_msg.mode == "DETERMINISTIC"
assert "Bob" in eg_msg.text
assert "25" in eg_msg.text
print("Egress rendered message:", eg_msg.text)
# Output: TRANSFER committed: quantity=25, recipient=Bob.
```

---

### Level 9: Dynamic Policy Plane, Drift & Requalification

The policy plane provides runtime policy discovery, qualification, and drift monitoring.

```python
from uow.policy import (
    DiscoveryEngine,
    DriftMonitor,
    PolicyRegistry,
    PolicyResolver,
    QualificationEngine,
)

registry = PolicyRegistry()
resolver = PolicyResolver(registry)
discovery = DiscoveryEngine()
qualifier = QualificationEngine(registry)
drift_monitor = DriftMonitor(registry=registry)

assert registry.total_policies == 0
```

---

## 5. Heterogeneous Hardware Spectrum & Embedded Deployment

UoW v2.0 is designed from the mathematical ground up to run across heterogeneous tiers of hardware without altering the execution semantics.

```
+---------------------------------------------------------------------------------------+
|                                    UoW Host System                                    |
|   +--------------------------+  +--------------------------+  +-------------------+   |
|   |   Intel AI Boost NPU     |  | NVIDIA GeForce RTX GPU   |  |   x86_64 CPU      |   |
|   | (OpenVINO ONNX Runtime)  |  |   (PyTorch CUDA Driver)  |  | (Deterministic)   |   |
|   +--------------------------+  +--------------------------+  +-------------------+   |
+------------------------------+------------------------------+-------------------------+
                               |              |
                      USB CDC  |              | Serial / ADB
                      (COM10)  |              | (COM5)
                               v              v
               +-----------------------+  +-------------------------------+
               | Node A: ESP32-S3      |  | Node B: Arduino / STM32U585   |
               | Dual-Core FreeRTOS    |  | Embedded Authority & Edge LLM |
               +-----------------------+  +-------------------------------+
                               \              /
                                \   HTTP     /
                                 v  :9527   v
                        +---------------------------+
                        | Node C: Authority Service |
                        | (Distributed 2-of-3 Quorum)|
                        +---------------------------+
```

### Host Accelerators (Intel AI Boost NPU & NVIDIA CUDA GPU)

On host systems, neural proposers and large-scale model inference can be offloaded dynamically:
- **Intel AI Boost NPU:** Native acceleration via `openvino_npu` integration with zero CPU throttling.
- **NVIDIA CUDA GPU:** High-throughput batch inference for high-density proposal environments.
- **CPU Fallback:** Seamless deterministic fallback if accelerator hardware encounters thermal throttling or device detachment.

### Embedded Microcontroller Nodes (ESP32-S3 Dual-Core FreeRTOS)

- Located in `qualification/embedded/esp32_dual_core`.
- **Core 0:** Frame decoding, hash verification, cryptographic signature generation.
- **Core 1:** Deterministic transition evaluation and local ring-buffer commit storage.

### Edge Semantic Harness on Arduino (STM32U585 / Embedded Micro-GPU)

Modern edge microcontrollers (such as the Arduino with high-density SRAM, Flash, and embedded micro-GPU / neural coprocessors) have sufficient compute and memory capacity to host quantized language models (e.g., 0.5B to 1B parameter models quantized to 2-bit or 4-bit weights).

The UoW architecture runs directly on edge devices with the exact same API:
1. **Edge LLM as Ingress Proposer:** The quantized model on the Arduino executes `SemanticHarness.interpret()` to extract typed intent from sensor or voice input.
2. **On-Device Deterministic Certification:** The micro-engine on the microcontroller verifies guards $\Gamma$ and executes mutations $M$. Even if the edge LLM hallucinates, invalid proposals are rejected before state is touched.
3. **Low-Power Distributed Quorums:** The edge node can participate in multi-node Byzantine consensus via serial, SPI, or 802.15.4 / BLE mesh.

### Hardware Qualification & Testing Roadmap

To ensure hardware-wide parity, future testing will systematically benchmark:
- **Micro-GPU / NPU Inference Latency:** Quantized semantic interpretation across Arduino and host NPUs.
- **Memory Footprint Verification:** Ensuring peak RAM stays well within embedded limits under sustained proposal loads.
- **Thermal & Clock Perturbation:** Validating the Timing Independence theorem across varying ambient temperatures and clock jitters.

---

## 6. Best Practices, Testing Patterns & Anti-Patterns

### The Golden Rules of UoW Engineering

1. **Keep Mutations Pure:** Never invoke network, file I/O, or random number generators inside a `Mutation`. Use Level 4 Effects / Sagas for external operations.
2. **Timing Decoupling:** Never use `time.time()` or wall-clock timestamps inside state transition guards. Rely on monotonic causal ticks ($T$).
3. **Zero Mutation Privileges for AI or Autonomy:** Language models, neural heuristics, and `uow.autonomy` may propose or organize work, but authoritative state changes must flow through the native certification/commit path (`ApplicationSpine` for autonomy integrations).
4. **Always Verify Egress Drift:** When rendering natural language confirmations to users, verify bidirectional round-trip consistency ($\text{parse}(\text{render}(I_B)) == I_B$).

### Writing Clean Pytest Suites via the Public API

Use the documented production namespaces: `uow`, `uow.semantic`, and `uow.autonomy`. Avoid `architecture.shadow`, `uow_shadow`, and qualification modules in application or production tests. Here is a complete core test template:

```python
import pytest
from uow import (
    Guard,
    GuardOp,
    Mutation,
    MutationOp,
    Route,
    Successor,
    WorldState,
    certify,
    commit,
    make_uow,
    propose,
)

def test_governed_counter_increment():
    state = WorldState(attributes={"count": 0, "max_limit": 10})
    uow = make_uow(
        "inc_1",
        routes=[
            Route(
                guard=Guard(GuardOp.LT, "count", 10),
                mutations=(Mutation(MutationOp.ADD, "count", 1),),
                successor=Successor.halt(),
            )
        ],
    )
    
    proposal = propose(uow, state)
    cert = certify(uow, state, proposal)
    assert cert.is_valid is True
    
    new_state, evidence = commit(uow, state, proposal, cert, prev_evidence_hash="0" * 64, step_number=1)
    assert new_state.require("count") == 1
    assert evidence.step_number == 1
```

### Common Anti-Patterns & How to Avoid Them

| Anti-Pattern | Why It Fails | Correct Solution |
| :--- | :--- | :--- |
| **Direct Mutation by LLM** | Stochastic corruption, lack of audit trail | Use `SemanticHarness` + `SemanticApplicationAdapter` |
| **Wall Clock in Guards** | Clock drift causes distributed nodes to diverge | Use causal tick sequence numbers ($T$) |
| **Side Effects in State Mutator** | Network failure during commit corrupts WAL replay | Use Level 4 `EffectRunner` and `SagaCoordinator` |
| **Research / Qualification Imports in Runtime Code** | Couples production to experiment-only implementations | Import from `uow`, `uow.semantic`, or `uow.autonomy`; keep `uow_shadow` and `qualification` outside runtime dependencies |
| **Direct Autonomous State Mutation** | Bypasses certification, evidence, and authority checks | Use `ApplicationExecutionPort` + a domain `WorkItemCompiler` so work passes through `ApplicationSpine` |

---

## 7. Public API Quick-Reference

### Core Facade (`from uow import ...`)
- **Primitives:** `WorldState`, `UoW`, `make_uow`, `Route`, `GuardOp`, `MutationOp`, `Guard`, `Mutation`, `Successor`
- **Execution:** `propose`, `certify`, `commit`, `run`, `execute_one`, `validate_graph`
- **Transactions:** `DeterministicSequencer`, `create_transaction_descriptor`, `validate_occ`, `TransactionDescriptor`
- **Orchestration:** `make_domain_task`, `create_initial_orchestration_state`, `run_orchestration`, `OrchestrationState`
- **Resources:** `ResourceState`, `make_resource_domain_task`, `run_resource_orchestration`
- **Effects & Sagas:** `EffectRunner`, `MockExternalClient`, `SagaCoordinator`, `create_effect_descriptor`, `SagaStep`
- **Adaptive Proposers:** `PortableAdaptiveProposer`, `ProposerOrchestrationEngine`
- **Composition:** `ParentContract`, `RealizationGraph`, `RealizationNode`, `ActorBinding`, `QuorumMutationCoordinator`
- **Boundary & Quorum Helpers:** `from uow.composition.boundary import certify_composition_boundary, verify_composition_boundary`, `from uow.composition import assemble_mutation_qc`
- **Policy Plane:** `PolicyRegistry`, `PolicyResolver`, `DiscoveryEngine`, `QualificationEngine`, `DriftMonitor`

### Autonomy Facade (`from uow.autonomy import ...`)
- **Runtime:** `AutonomousRuntime`
- **Request/Result:** `AutonomyRequest`, `AutonomyResult`, `TerminalDisposition`
- **Public Specs:** `GoalSpec`, `CapabilitySpec`, `AutonomyBudget`
- **Execution Boundary:** `ExecutionPort`
- **Typed construction helpers:** `PredicateOp`, `StatePredicate`, `AuthorityScope`, `ResourceEnvelope`, and `WorkItem` are available from `uow.autonomy.model`
- **Execution adapters:** `SimulatedExecutionPort`, `ApplicationExecutionPort`, and `WorkItemCompiler` are available from `uow.autonomy.ports`

### Semantic Facade (`from uow.semantic import ...`)
- **Ingress:** `IngressContext`, `SemanticRequirement`, `SemanticDisposition`, `DefaultSemanticAdmissibilityValidator`
- **Harness & Adapter:** `SemanticHarness`, `SemanticApplicationAdapter`, `TransferUoWCompiler`, `PreparedSemanticApplicationExecution`
- **Governed Egress:** `GovernedEgressEngine`, `RecipientProfile`, `GovernedEgressResult`
