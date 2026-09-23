# UoW Closure Falsification Matrix

## Research question

Can higher-order runtime/meta-runtime operations be expressed through the same minimal UoW algebra without loss of capability?

[
M \subseteq U ; ?
]

A positive result requires more than wrapping an operation in a `UoW` object. The lowered form must preserve authority separation, causal binding, failure semantics, evidence, negative controls, and the experiment's original result.

## Test method

For each candidate operation:

1. define its invariant semantic contract;
2. express its current native/meta representation;
3. build a shadow UoW lowering without removing current code;
4. run matched positive and negative controls against both paths;
5. compare authoritative result and required evidence;
6. reject closure if the UoW lowering needs a privileged side channel unavailable to ordinary UoWs.

## Matrix

| Candidate operation | Current representation | Proposed UoW expression | Required invariants | Falsification vector | Closure status |
|---|---|---|---|---|---|
| Scheduler dispatch | `SchedulerMaterializer` -> UoW | already lowered | A1-A7 as applicable | bypass materialization certification | **SUPPORTED** |
| Task completion | `CompletionMaterializer` -> UoW | already lowered | A1-A7 | forged completion of inactive task | **SUPPORTED** |
| Resource-aware dispatch | resource materializer -> UoW | already lowered | A1-A7 + S1 | resource over-allocation / forged requirement | **SUPPORTED** |
| Effect intent/result state | `EffectRunner` creates UoWs | internal state portions already lowered | A1-A7 + S3/S5 | external call succeeds but internal receipt not committed | **PARTIAL** — external invocation remains boundary |
| Saga state progression | UoW state updates + external compensation | lower state transitions; retain external-effect boundary | A1-A7 + S5 | compensation failure | **PARTIAL** |
| Actor rebinding | direct validated `active_binding` replacement | candidate `U_rebind` changes binding meta-state | A0-A7 + S1/S2 | bind unqualified actor / expired lease / authority deficit | UNTESTED |
| Graph substitution | `GraphReplacementProposal/Certificate` and runtime mutation | `U_substitute_graph` over runtime meta-state | A0-A7 | stale graph, cyclic graph, semantic projection mismatch | UNTESTED |
| Delegation issuance | `DelegationCertificate` + node dispatch | `U_delegate` creating child-work relation and attenuated authority | A0-A7 + S3/S4 | authority inflation / stale child / expired grant | UNTESTED |
| Delegation retry/recovery | bespoke delegation state | UoW transition over delegation lineage | A1-A7 + S3/S4 | duplicate non-idempotent commit | UNTESTED |
| History reconciliation | `AuthoritativeHistory` + cluster reconciliation | UoW representing canonical-history adoption | A1-A7 + S2 | non-prefix divergent replica / minority history | UNTESTED |
| Runtime mutation QC application | `RuntimeMutationQC` + coordinator / host node | `U_apply_runtime_mutation` whose authority evidence is QC | A0-A7 + S1/S2 | self-sign, insufficient quorum, stale head, tampered graph | UNTESTED |
| Model generation promotion | NPU lifecycle manager | UoW transition of model-generation meta-state | A1-A7 | failed health check / corrupt staging model | UNTESTED |
| Model feedback/update | proposer-private state + certified observations | likely split: feedback ingestion UoW; parameter update remains non-authoritative realization state | A2/A3/A6/A7 | forged feedback / stale observation | UNTESTED |
| Actor lease grant/reap | `DistributedActorFabric` | UoW over actor-fabric authority state | A1-A7 + S1/S2 | self-announced authority, expired lease | UNTESTED |
| Quorum vote assembly | mutation/distributed authority primitives | likely attestation protocol, not necessarily state-transition UoW | A2-A7 | duplicate voter / invalid signature / threshold deficit | **OPEN META-LAYER CANDIDATE** |
| External invocation | `ExternalClientProtocol.invoke` | deliberately not reducible to internal state transition | S3/S5 | crash after invocation before receipt commit | **EXPECTED NON-CLOSURE BOUNDARY** |

## Decisive interpretations

### Closure succeeds

Closure is supported only when the ordinary UoW path reproduces:
- accepted behavior;
- rejection behavior;
- authoritative state;
- causal identity;
- evidence/lineage;
- failure/recovery semantics.

### Closure fails constructively

A failure is useful if it reveals a true meta-layer primitive. Likely candidates include:
- multi-party attestation assembly;
- external physical effects;
- possibly transport itself.

The goal is not to force every operation into UoW syntax. The goal is to determine experimentally which operations are genuinely closed under UoW semantics.

## Initial prediction

The evidence currently suggests three classes:

1. **Already closed:** scheduling, completion, resource state, internal effect/saga state.
2. **Plausibly closable:** graph substitution, rebinding, delegation, model promotion, lease lifecycle, history adoption.
3. **Likely boundary/meta primitives:** external invocation and cryptographic multi-party attestation formation.

No implementation decision should be made until shadow tests falsify or support these predictions.
