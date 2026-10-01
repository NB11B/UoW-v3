# Substrate Specification: State and Context Semantics

## 1. Executive Problem Statement

In distributed and intelligent systems, the single word **"state"** frequently conflates eight fundamentally different kinds of data:

$$\boxed{
\begin{aligned}
\text{Observation} &\neq \text{Authoritative Fact}\\
\text{Agent Context} &\neq \text{World State}\\
\text{Derived Projection} &\neq \text{Committed Reality}
\end{aligned}
}$$

Allowing raw sensor readings, LLM scratchpads, temporary caches, and committed financial balances to share a single untyped dictionary invites severe failure modes:
* An unverified sensor reading directly overwrites an authoritative inventory count.
* An agent hallucinating in its context window mutates the global database.
* A stale cache entry is treated as an immutable OCC sequence boundary.

---

## 2. The Eight State Categories

```mermaid
graph TD
    subgraph External["Physical Reality"]
        W["8. External-World State (W)"]
    end

    subgraph Ingress["Observation Boundary"]
        O["2. Observed State (O)"]
        W -->|Sensors / Gateways| O
    end

    subgraph Authority["Authority & Ledger Boundary"]
        S["1. Authoritative State (S)"]
        P["6. Policy State (P)"]
        X["7. Execution State (X)"]
        
        O -->|CERTIFY (Quorum / Guard)| S
        S -->|Advances OCC Sequence| S
    end

    subgraph Projections["Deterministic Views & Cache"]
        D["3. Derived State (D)"]
        C["4. Cached State (C)"]
        
        S -->|Pure Function Projections| D
        S -.->|TTL-Bound Mirror| C
    end

    subgraph Ephemeral["Agent Cognition Boundary"]
        K["5. Session / Context State (K)"]
        D -.->|Read Context| K
        S -.->|Read Verified State| K
    end
```

### 2.1 1. Authoritative State ($S$)
* **Definition**: Cryptographically signed, committed, non-repudiable state verified by the Authority Kernel and recorded in the Evidence Ledger.
* **Properties**: Monotonically increasing sequence numbers, Merkle/SHA-256 state hash binding, strict Optimistic Concurrency Control (OCC).
* **Authority Level**: Highest. Mutations require verified `CertificateResult`.

### 2.2 2. Observed State ($O$)
* **Definition**: Raw sensor telemetry, incoming webhooks, carrier network pings, and external claims.
* **Properties**: Explicit confidence score $\in [0.0, 1.0]$, timestamp, modality, witness signature.
* **Invariant**: Classified as `UNVERIFIED_CLAIM`. Cannot alter state cursors or mutate authoritative state keys directly.

### 2.3 3. Derived State ($D$)
* **Definition**: Factual values computed as pure deterministic projections over Authoritative State:
  $$D_t = g(S_t)$$
* **Examples**: Materialized balance views, aggregate ledger sums, average temperatures over a sliding window.
* **Properties**: Read-only, reconstructible from scratch from the Evidence Ledger. Never independently mutated.

### 2.4 4. Cached State ($C$)
* **Definition**: Ephemeral in-memory representations kept for latency optimization.
* **Properties**: Bound to a strict pre-state hash ($H_{\text{pre}}$) and Time-To-Live (TTL). Invalidate immediately upon sequence advance.

### 2.5 5. Session / Context State ($K$)
* **Definition**: Ephemeral cognitive state belonging to an autonomous agent, LLM conversational memory, or interactive user session.
* **Examples**: Chain-of-thought traces, token buffers, planning scratchpads, search trees.
* **Invariant**: Local to the proposing agent. Completely discarded upon task termination or context refresh. Never directly committed to the Evidence Ledger.

### 2.6 6. Policy State ($P$)
* **Definition**: The active `SystemDesignProfile`, operating mode ($M \in \{\text{NORMAL}, \text{DEGRADED}, \text{EMERGENCY}, \text{RECOVERY}\}$), and goal allocations.
* **Properties**: Certified by root governance keys. Mutated exclusively via certified policy transitions or root delegations.

### 2.7 7. Execution State ($X$)
* **Definition**: Operational runtime tracking for in-flight transactions.
* **Examples**: Acquired resource leases, lock tables, compensation stacks, active sagas.
* **Properties**: Ephemeral to transaction execution, reconciled upon commit or compensation abort.

### 2.8 8. External-World State ($W$)
* **Definition**: Physical reality outside software boundary (valve position, ambient room temperature, bank clearinghouse status).
* **Properties**: Incompletely observable, noisy, non-deterministic. Can only be sampled via sensors ($O$) or influenced via effectors.

---

## 3. Legal State Transitions

The runtime substrate enforces strict transition barriers between state categories:

$$\begin{array}{|l|l|c|l|}
\hline
\textbf{Source} & \textbf{Destination} & \textbf{Legal?} & \textbf{Enforcement Mechanism} \\
\hline
\text{Observed } (O) & \text{Authoritative } (S) & \checkmark & \text{Via Authority Kernel Certification } \text{CERTIFY}(O, S_t) \\
\text{Observed } (O) & \text{Authoritative } (S) & \times & \text{Direct attribute assignment rejected: } \text{ERR\_UNVERIFIED\_STATE\_MUTATION} \\
\text{Authoritative } (S) & \text{Derived } (D) & \checkmark & \text{Pure deterministic projection } g(S) \\
\text{Derived } (D) & \text{Authoritative } (S) & \times & \text{Derived views cannot mutate source: } \text{ERR\_READ\_ONLY\_PROJECTION} \\
\text{Agent Context } (K) & \text{Authoritative } (S) & \times & \text{Agent proposals have zero commit authority: } \text{ERR\_AUTHORITY\_DENIED} \\
\text{Agent Context } (K) & \text{Proposal } (\pi) & \checkmark & \text{Agent submits candidate action for kernel evaluation} \\
\text{Policy } (P) & \text{Operating Mode} & \checkmark & \text{Certified transition via escalation trigger or root signature} \\
\hline
\end{array}$$
