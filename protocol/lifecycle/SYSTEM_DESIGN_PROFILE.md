# Architectural Specification: Design / Policy Plane & System Design Profile

## 1. Executive Summary & The Six Architectural Planes

The Unit-of-Work (UoW) v2.0 architecture establishes the **Design / Policy Plane** directly above the four runtime planes (Observation, Proposal, Authority, Execution) and the immutable Evidence Ledger.

While the runtime planes govern *who may observe, propose, certify, act, and record*, the Design / Policy Plane answers the fundamental question:
> **What is this particular system supposed to accomplish, and how should it behave while accomplishing it?**

$$\boxed{
\begin{aligned}
\text{Design} &: \text{defines what success means}\\
\text{Observation} &: \text{reports what is true}\\
\text{Proposal} &: \text{suggests what to do}\\
\text{Authority} &: \text{determines what may occur}\\
\text{Execution} &: \text{changes the world}\\
\text{Evidence} &: \text{records what occurred}
\end{aligned}
}$$

```mermaid
graph TD
    subgraph P0["Design / Policy Plane"]
        Architect["System Architect / AI Drafter"] -->|Drafts Profile| SDP["SystemDesignProfile (vX.Y.Z)"]
        Governance["Root Governance / Quorum Key"] -->|Cryptographic Activation| CertifiedSDP["Certified Active Profile P"]
    end

    subgraph P1["Observation Plane"]
        Sensors["Physical Sensors / Ingress Gateways"] -->|Telemetry & Claims| Obs["Observations Ot (Zero Proposal Authority)"]
    end

    subgraph P2["Proposal Plane"]
        Agents["Autonomous Agents / LLMs / Policies"] -->|Proposals πt = P_θ(St, Gt, Ct, At)| Proposals["Candidate Proposals πt (Zero Commit Authority)"]
    end

    subgraph P3["Authority Plane (Governance Kernel)"]
        CertifiedSDP -->|Invariants & Action Space| Certifier["UoW Certifier"]
        Obs -->|Certified Trigger Evaluation| ModeCtrl["Operating Mode Controller"]
        ModeCtrl -->|Active Mode Mt & Goals Gt| Certifier
        Proposals -->|Evaluate Invariants & Guards| Certifier
    end

    subgraph P4["Execution Plane"]
        Certifier -->|CertificateResult σt| Effectors["Certified Effectors (APIs, Actuators)"]
    end

    subgraph P5["Evidence Plane"]
        Certifier -->|Immutable Commit| Ledger["Evidence Ledger (WAL / Hash Chain)"]
    end
```

---

## 2. Core Architectural Invariants

### 2.1 Invariant 1: Constraints $\neq$ Objectives
Hard invariants define the **feasible state space** $\Omega \subset \mathcal{S}$. Objectives define the **directional optimization gradient** $\nabla J$ within $\Omega$.
$$\Omega = \{ s \in \mathcal{S} \mid \forall i \in \text{Invariants}, \; i(s) = \text{True} \}$$
No degree of objective attainment, utility gain, or agent confidence score can compensate for an invariant breach:
$$\forall \pi, \quad (\exists i \in \text{Invariants}: i(\pi(S_t)) = \text{False}) \implies \text{CERTIFY}(\pi, S_t) = \text{REJECT}(\text{ERR\_INVARIANT\_VIOLATION})$$

### 2.2 Invariant 2: Dynamic Goal Derivation
Active goals $G_t$ at any instant $t$ are a deterministic function of current verified state $S_t$ and active profile $P$:
$$G_t = f(S_t, P)$$

### 2.3 Invariant 3: Goal Authorization Bounding
Active goals can never exceed the authorized mission scope certified in the profile:
$$G_t \subseteq P_{\mathrm{authorized}}$$

### 2.4 Invariant 4: Conditioned Candidate Action Generation
Agent action proposals $\pi_t$ are explicitly conditioned on current state $S_t$, active goals $G_t$, constraints $C_t$, and authorized action space $A_t$:
$$\pi_t = P_\theta(S_t, G_t, C_t, A_t)$$

### 2.5 Invariant 5: Authority Separation for Policy Activation
$$\boxed{\text{AI may draft policy} \neq \text{AI may activate policy}}$$
Autonomous agents, planners, and LLMs may propose, draft, or simulate candidate `SystemDesignProfile` documents. However, activating a profile into the Authority Plane strictly requires verified root governance credentials (e.g. cryptographic multi-party signature or hardware security module token). An agent proposal attempting to activate or mutate policy fails closed with `ERR_AUTHORITY_DENIED`.

---

## 3. The 11 Sections of the System Design Profile

A compliant `SystemDesignProfile` adheres to [`system_design_profile.json`](file:///spec/schemas/system_design_profile.json) and contains the following 11 canonical sections:

### 3.1 `system_identity`
* **Name & Version**: Semantic identifier (e.g. `uow.grid.energy_balancer`, version `1.2.0`).
* **Domain & Classification**: Operational context and safety tier (`SAFETY_CRITICAL`, `FINANCIAL_AUDITED`, `MISSION_CRITICAL`, `OPERATIONAL_STANDARD`, `RESEARCH_EXPERIMENTAL`).
* **Authority Boundary**: Defines the issuing authority ID, public root keys, required quorum signature count ($M$-of-$N$), and the cryptographic activation signature.

### 3.2 `mission_statement`
* **Purpose**: Clear, unambiguous declaration of what the system exists to achieve.
* **Operational Scope**: Boundary of operations, physical or digital domains influenced.
* **Rationale**: Theoretical justification for chosen operational architecture.

### 3.3 `invariants` (Hard Constraints)
* Array of non-negotiable boundary conditions.
* Each invariant specifies:
  - `id`: Unique identifier (e.g. `INV-NO-NEGATIVE-INVENTORY`, `INV-THERMAL-CUTOFF`).
  - `formal_expression`: Deterministic boolean logic over `WorldState`.
  - `severity`: Must be `HARD_CONSTRAINT`.
  - `enforcement`: `FAIL_CLOSED` or `IMMEDIATE_HALT`.
  - `violation_code`: Error identifier emitted if violated.

### 3.4 `operating_modes`
* Discrete states of operational readiness and risk management:
  - `NORMAL`: Full operational capacity, maximum objective pursuit.
  - `DEGRADED`: Constrained operational capacity following non-fatal telemetry or subsystem degradation.
  - `EMERGENCY`: Immediate hazard containment; all non-safety operations suspended.
  - `RECOVERY`: Audited state reconciliation, evidence integrity verification, and controlled transition back to `NORMAL`.

### 3.5 `goals_by_mode`
* Mapping of active operating modes to sets of objectives:
  - `goal_id`: Identifier of the objective.
  - `priority_rank`: Lexicographic priority ($1 = \text{highest}$).
  - `target_predicate`: Boolean condition or threshold over `WorldState`.
  - `direction`: `MAXIMIZE`, `MINIMIZE`, `SATISFY_THRESHOLD`, or `MAINTAIN_RANGE`.
  - Invariant: `is_hard_constraint = false`.

### 3.6 `priority_rules`
* Formal rules defining deterministic conflict resolution:
  1. `INVARIANT_DOMINATES_OBJECTIVE`: Invariants always defeat any goal optimization.
  2. `LEXICOGRAPHIC_ORDER`: Lower rank number strictly dominates higher rank number.
  3. `FAIL_SAFE_DOMINANCE`: In ambiguous or tie scenarios, the system chooses the lowest-entropy, fail-safe state.

### 3.7 `performance_metrics`
* Quantified evaluation standards:
  - `metric_id`, `name`, `unit`.
  - `target_threshold` vs `critical_threshold`.
  - `evaluation_window_seconds`.

### 3.8 `observation_requirements`
* Telemetry and sensor prerequisites:
  - `namespace`: Required state path prefix (e.g. `obs.telemetry.temp`, `obs.battery.voltage`).
  - `min_confidence`: Minimum confidence score $\in [0.0, 1.0]$.
  - `max_staleness_ms`: Time window before observation expires.
  - `quorum_witness_count`: Minimum distinct sensor witnesses required.

### 3.9 `action_space`
* White-listed Unit-of-Work contracts allowed in each operating mode:
  - Mapping: `mode_id -> [{ operation_id, min_authority_level, rate_limit }]`.
  - Operations not explicitly white-listed for the active mode fail closed.

### 3.10 `escalation_triggers`
* Deterministic rules mapping observations to mode transitions:
  - `from_mode`, `to_mode`.
  - `trigger_condition`: Expression evaluated over certified observations.
  - `evidence_requirement`: Witness proof required.
  - `auto_reversion_allowed`: Boolean indicating whether recovery requires human/root intervention.

### 3.11 `decommission_criteria`
* Conditions under which the profile ceases to be valid:
  - `expiration_timestamp`: Absolute UTC sunset.
  - `max_causal_epoch`: Sequence limit.
  - `irreversible_breach_conditions`: Invariants whose breach irreversibly revokes the profile.
