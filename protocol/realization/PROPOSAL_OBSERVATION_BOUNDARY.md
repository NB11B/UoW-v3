# Architectural Specification: Proposal Plane & Observation Plane Boundaries

## 1. Executive Formal Invariant

The Unit-of-Work (UoW) v2.0 architecture strictly decouples the four fundamental roles of intelligent distributed systems:

$$\boxed{
\begin{aligned}
\text{Observation Plane (Sensors)} &\longrightarrow \text{observations only}\\
\text{Proposal Plane (Agents)} &\longrightarrow \text{proposals only}\\
\text{Authority Plane (Governance)} &\longrightarrow \text{authorization \& certification}\\
\text{Execution Plane (Effectors)} &\longrightarrow \text{certified effects only}
\end{aligned}
}$$

Conflating any of these planes introduces catastrophic failure modes:
* If **Sensors** can propose mutations, noisy or spoofed sensor data can execute arbitrary transitions.
* If **Agents** (LLMs, neural policies, heuristic schedulers) possess execution authority, hallucinations or prompt injections can directly mutate state or trigger external side effects.
* If **Effectors** can fire without governance certificates, external systems drift out of sync with immutable ledger evidence.

```mermaid
graph TD
    subgraph P1["Observation Plane"]
        Sensors["Physical Sensors / Ingress Gateways / Telemetry"] -->|Calibrated Stimuli| SensorHarness["Sensor Harness"]
        SensorHarness -->|Witnessed Observations Only| WorldStateBuf["WorldState (Attributes & Evidence)"]
    end

    subgraph P2["Proposal Plane"]
        WorldStateBuf -.->|Read State Context| AgentHarness["Agent Harness"]
        Agents["Autonomous Agents / LLMs / Policies"] -->|Candidate Actions| AgentHarness
        AgentHarness -->|Proposals Only (Zero Authority)| ProposalQueue["Candidate Proposals π"]
    end

    subgraph P3["Authority Plane (Governance Kernel)"]
        ProposalQueue -->|Evaluate Preconditions| Kernel["UoW Certifier / OCC Judge"]
        WorldStateBuf -->|Pre-State Hash Check| Kernel
        Quorum["M-of-N Hardware Quorum / Delegations"] -->|Attestations| Kernel
        Kernel -->|CERTIFY(π, St)| Certificate["CertificateResult σ"]
        Certificate -->|COMMIT(σ, St)| Ledger["Immutable Evidence Ledger (WAL)"]
    end

    subgraph P4["Execution Plane (Effectors)"]
        Certificate -->|Verified Certificate Required| EffectorHarness["Effector Harness"]
        EffectorHarness -->|Certified Effects Only| Actuators["Actuators / APIs / Sagas / SMS"]
    end
```

---

## 2. Plane Definitions & Boundary Rules

### 2.1 The Observation Plane: Sensors $\longrightarrow$ Observations Only
* **Rule**: Sensors report *what is observed*, never *what should be done*.
* **Primitive**: `SensorObservation`
  $$O = (\text{sensor\_id}, \text{causal\_epoch}, \text{modality}, \text{reading}, \text{confidence}, \text{witness\_sig})$$
* **Non-authority invariant**: An observation cannot alter execution cursors, grant leases, or directly mutate protected state keys. Observations enter `WorldState.attributes` under designated namespaces (e.g. `obs.telemetry.*`, `obs.hardware.*`, `obs.carrier.*`).

### 2.2 The Proposal Plane: Agents $\longrightarrow$ Proposals Only
* **Rule**: Agents generate *candidate state transitions*, with strictly zero authority to commit them.
* **Primitive**: `AgentProposal`
  $$\pi = (\text{agent\_id}, H_{\text{pre}}, \text{target\_uow}, \text{route\_index}, \text{proposed\_state}, \text{reasoning\_trace})$$
* **Zero-authority invariant**: Any agent (neural network, LLM, distributed subagent, human operator) produces candidates $P_\theta(S_t) \to \pi_t$. If an agent attempts to forge state hashes or bypass guards, the certifier rejects the proposal with `ERR_ROUTE_DIVERGENCE` or `ERR_STALE_PRE_STATE`.

### 2.3 The Authority Plane: Governance $\longrightarrow$ Authorization & Certification
* **Rule**: The kernel independently validates candidates against deterministic contracts.
* **Primitive**: `CertificateResult`
  $$\sigma = \text{CERTIFY}(\pi_t, S_t)$$
* **Certification Invariants**:
  1. $\pi_t.H_{\text{pre}} == S_t.\text{state\_hash}$ (OCC sequence and state freshness)
  2. $\text{Guard.evaluate}(S_t) == \text{True}$ (Precondition satisfaction)
  3. $\pi_t.\text{proposed\_state} == \text{Route.apply\_mutations}(S_t)$ (Deterministic recomputation)
  4. $\text{AuthorityLevel}(\text{Actor}) \ge \text{MinRequired}(\text{Operation})$ (Policy access control)
* Upon certification, $\text{COMMIT}(\sigma_t, S_t) \to S_{t+1}$ atomically advances sequence and appends an immutable witness record to the `EvidenceLedger`.

### 2.4 The Execution Plane: Effectors $\longrightarrow$ Certified Effects Only
* **Rule**: Actuators and external side-effects fire only upon presenting a valid, tamper-free `CertificateResult`.
* **Primitive**: `EffectorIntent` bound to `CertificateResult`
* **Fail-Closed Invariant**: If an effector receives an intent without a certified hash matching the current ledger state, execution is aborted under `ERR_CERTIFICATE_INVALID`.
* **Sagas & Rollbacks**: If an external system fails after certification, a compensating UoW is scheduled to reconcile the divergence.

---

## 3. Threat Model & Failure Mitigation

| Attack / Hazard Vector | Vulnerable Plane | Architectural Defense |
|---|---|---|
| **Prompt Injection / Jailbreak** | Proposal Plane (Agent) | Agent cannot execute. Governed kernel checks strict preconditions over `WorldState`. Injected commands fail route guard validation. |
| **Hallucinated State Mutation** | Proposal Plane (Agent) | Certifier independently recomputes deterministic mutations. Divergent states fail under `ERR_ROUTE_DIVERGENCE`. |
| **Spoofed Sensor Telemetry** | Observation Plane (Sensor) | Raw sensor input is categorized as `UNVERIFIED_CLAIM`. Critical mutations require multi-sensor quorum or cryptographic witness signatures. |
| **Replay / Out-of-Order Packets** | All Planes | Pre-state hash chaining ($H_{\text{pre}}$) and monotonically increasing causal sequences cause duplicate/stale packets to fail closed under `ERR_STALE_PRE_STATE`. |
| **Unauthorized External Effect** | Execution Plane (Effector) | Effectors verify HMAC receipt bindings against certified evidence before dispatching real-world actuators or API calls. |
