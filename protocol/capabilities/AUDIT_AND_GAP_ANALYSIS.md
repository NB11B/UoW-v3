# Runtime Substrate: Audit and Gap Analysis

## 1. Executive Problem Statement

The polyglot interoperability layer proved that diverse execution environments (Python, TypeScript/Node, Rust, Perl, COBOL, Pascal, C ABI, SMS) can express identical work semantics. However, before deploying autonomous planning agents or generative reasoning loops, the **runtime substrate itself must be made sufficiently explicit**.

When agents are introduced too early, they are forced to invent the operating system around themselves—guessing what counts as state, assuming functions have no side effects, conflating telemetry with ground truth, and ignoring resource limits or mid-flight authority revocation.

$$\boxed{
\begin{array}{rcl}
\text{Language Interoperability} &\longrightarrow& \text{Proves common work representation}\\
\text{Runtime Substrate Semantics} &\longrightarrow& \text{Makes world boundaries, costs, and state explicit}\\
\text{Policy / Design Plane} &\longrightarrow& \text{Defines what success and safety mean}\\
\text{Proposal / Agent Plane} &\longrightarrow& \text{Reasons over an explicit machine world}
\end{array}
}$$

---

## 2. Comprehensive Substrate Audit

| Substrate Dimension | Current Implementation in UoW v2.0 | Architectural Gap / Conflation | Required Formalization |
|---|---|---|---|
| **1. Capability Ontology** | `spec/operations/manifest.yaml` lists endpoints; `ontology.py` defines 64 matrix cells; `models.py` has hardware slots. | **Function conflated with Capability**. A function is an invocation artifact; a capability is a verified system competency with explicit read/write scopes, side-effects, and compensation. | Establish `CapabilityDescriptor` defining identity, side-effect class, reversibility, preconditions, and compensation binding. |
| **2. State & Context Semantics** | `WorldState` (`src/uow/state.py`) stores a monolithic frozen dictionary of `attributes`. | **State classes conflated**. Telemetry (`obs.*`), resources (`__resources__`), agent thoughts, and authoritative facts live in one untyped namespace. | Define 8 discrete state classes: Authoritative, Observed, Derived, Cached, Session/Context, Policy, Execution, External-World. |
| **3. Event & Trigger Semantics** | `SensorObservation` exists; `EscalationTrigger` exists; `Guard` evaluates state keys. | **Causal pipeline implicit**. Raw observations are often treated as direct triggers without intermediate event extraction or condition debouncing. | Formalize $O_t \to E_t \to C_t \to U_t$: Observation $\to$ Event $\to$ Condition/Trigger $\to$ UoW. |
| **4. Trust & Delegation Lifecycle** | Envelope `Actor` has `claim_type`; `delegation.py` has delegation tokens. | **Authority binding points and mid-flight revocation undefined**. Unclear what happens if authority is revoked after proposal but before execution. | Formalize multi-point binding (Proposal, Certification, Commit, Effect) and instant fail-closed abortion on revocation. |
| **5. Failure & Effect Semantics** | `spec/errors/taxonomy.yaml` lists error codes; `descriptor.py` has `EffectStatus`. | **Failure conflated with Unknown Outcome**. An external timeout is not a rejected transaction; it is an indeterminate state. | Distinguish deterministic rejection from unknown outcome; classify effects: `PURE_READ`, `REVERSIBLE`, `COMPENSATABLE`, `IRREVERSIBLE`, `EXTERNAL_UNCERTAIN`, `PHYSICAL`. |
| **6. Composition Semantics** | `RealizationGraph` exists; `Route.successor` resolves sequential steps. | **No formal composition algebra for $U_1 \circ U_2$**. Dependency DAGs, partial certification, and atomicity boundaries vs saga compensation are ad-hoc. | Formalize $U_1 \circ U_2$, input-to-output bindings, branch/join semantics, and compensation trees. |
| **7. Resource & Lease Model** | `ResourceState` tracks CPU, RAM, GPU, NPU slots, energy. | **Narrow resource scope**. Financial cost, bandwidth, human attention, storage, and API quotas are omitted. | Universal resource vector $R = \{r_1, \dots, r_n\}$ with unified lifecycle (reservation, lease, consumption, release, contention). |
| **8. Temporal Semantics** | `Timing` has `causal_epoch`; `WorldState` has `sequence`. | **Time coordinates conflated**. Event ordering vs wall-clock timestamps vs validity intervals vs deadlines are not distinguished. | Establish temporal coordinates: observed time, received time, logical time, deadline, lease expiry, validity window. $\text{Event Order} \neq \text{Wall-Clock Order}$. |
| **9. Version Negotiation & Placement** | `protocol_version` and `operation_version` in envelope. | **Drift resolution and location independence implicit**. When Agent v3 calls Executor v2 under Policy v1, behavior is unspecified. | Formalize version compatibility rules and placement decoupling: $\text{Capability} \neq \text{Location}$. |
| **10. Evidence vs Observability** | `EvidenceLedger` stores witness hashes and receipts. | **Audit proof conflated with diagnostic telemetry**. Debug logs, spans, and metrics mingled with cryptographic evidence. | Rigorous separation: Evidence (non-repudiable proof) vs Observability (operational inspection). |

---

## 3. Prioritization and Phasing

We address these layers in the sequence established by the architectural guidance:
1. **Capability Ontology** ($\text{Function} \neq \text{Capability}$)
2. **State & Context Semantics** ($\text{Observation} \neq \text{Authoritative Fact}$, $\text{Agent Context} \neq \text{World State}$)
3. **Event & Trigger Semantics** ($O_t \to E_t \to C_t \to U_t$)
4. **Authority & Delegation Lifecycle** (Trust model, multi-point binding, mid-flight revocation)
5. **Failure & Effect Semantics** ($\text{Failure} \neq \text{Unknown Outcome}$, typed effect taxonomy)
6. **Composition Semantics** ($U_1 \circ U_2$, dependency DAG, compensation)
7. **Resource & Lease Model** ($R = \{r_1, \dots, r_n\}$, contention)
8. **Temporal Semantics** (Causal vs logical vs physical time)
9. **Version Negotiation & Placement** ($\text{Capability} \neq \text{Location}$)
10. **Evidence vs Observability** (Cryptographic proof vs diagnostic inspection)
