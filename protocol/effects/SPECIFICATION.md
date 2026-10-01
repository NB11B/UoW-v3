# Protocol Specification: External Effects & Sagas

## 1. Effect Decoupling

State transitions in the UoW core are purely mathematical and deterministic.
Interactions with the external world (I/O, network calls, hardware actuation, payment transactions) are governed by the Effects plane:

1. **Effect Intent (`EffectDescriptor`)**: Declares intent to execute an external side-effect, tagged with a deterministic `idempotency_key`.
2. **Receipt Binding (`EffectReceipt`)**: External execution yields an immutable receipt bound cryptographically to the executing UoW and evidence root.
3. **Saga Orchestration (`SagaCoordinator`)**: Multi-step external transactions register compensation actions for atomic rollback upon failure.

## 2. Idempotency Invariant

Executing an effect with an already-observed `idempotency_key` and matching payload MUST replay the prior receipt without re-executing external side-effects.
Executing an effect with an already-observed key and *conflicting* payload MUST be rejected with `IDEMPOTENCY_PAYLOAD_CONFLICT`.
