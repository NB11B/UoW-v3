# Canonical Authority Model: Identity, Authentication & Authority Separation

## 1. Core Invariant

The UoW architecture strictly distinguishes three distinct concepts that are often conflated in monolithic frameworks:

$$\boxed{\text{Identity} \neq \text{Authentication} \neq \text{Authority}}$$

1. **Identity ($\text{ActorID}$)**: Who the participant *claims* to be (e.g. phone number `+15550199`, email address, account ID).
2. **Authentication ($\text{AuthN}$)**: Cryptographic or challenge-response verification that the claimant actually controls the claimed identity (e.g. mTLS, HMAC signature, OTP code, Ed25519 signature).
3. **Authority ($\text{AuthZ}$)**: Explicit, bounded privilege to initiate or commit a specific state mutation under given constraints ($\text{Scope}$, $\text{Lease}$, $\text{MaxAmount}$, $\text{QuorumQC}$).

---

## 2. Ingress Classification Matrix

Every incoming invocation envelope classifies identity and authority into four discrete confidence levels:

| Level | Classification | Identity Proof | Example Ingress Transports | Permitted Operations |
|---|---|---|---|---|
| **L0** | `UNVERIFIED_CLAIM` | Raw claim string (unauthenticated) | SMS inbound text, CLI script, unauthenticated webhook | Read-only status queries, public telemetry, informational UoWs |
| **L1** | `AUTHENTICATED` | Cryptographic signature or verified session | Signed HTTP/REST, mTLS, authenticated API key | Bounded mutations within user's individual domain |
| **L2** | `DELEGATED` | Signed delegation certificate ($\text{Delegator} \to \text{Delegatee}$) | Autonomous agent, scheduled orchestrator | Scoped mutations conforming to delegation limits |
| **L3** | `QUORUM_CERTIFIED` | Threshold signature ($M$-of-$N$ hardware nodes) | Node A (ESP32) + Node B (STM32) + Node C (HTTP) | Critical policy changes, firmware updates, root ledger mutation |

---

## 3. The SMS Test Vector

SMS provides a rigorous testbed for this tripartite separation:

```text
"STATUS 8831" from +1-555-0199
  -> Claim: Actor=+15550199
  -> Auth Level: UNVERIFIED_CLAIM
  -> Required Authority: Read-Only
  -> Evaluation: PERMITTED

"TRANSFER $50,000 TO ACC-4421" from +1-555-0199
  -> Claim: Actor=+15550199
  -> Auth Level: UNVERIFIED_CLAIM
  -> Required Authority: High-Privilege Mutation
  -> Evaluation: REJECTED (ERR_AUTHORITY_DENIED: Step-up authentication required)
```

No mutation may execute on the basis of a caller ID claim alone. High-privilege SMS operations require an out-of-band or two-phase step-up challenge token included in `authority_context.tokens`.

---

## 4. Concurrency & Delivery Hazards

Transports characterized by unreliable networks (SMS, messaging queues, webhooks) must explicitly satisfy:
* **Idempotency Key**: Generated from causal input hash or client token; duplicates replay the committed evidence record rather than re-executing mutations.
* **Correlation ID**: Traces causal flow through multi-step sagas.
* **Replay Protection**: Pre-state hash validation ($\text{pre\_state\_hash} == \text{state.state\_hash}$) guarantees that out-of-order delivery fails closed rather than corrupting sequence.
