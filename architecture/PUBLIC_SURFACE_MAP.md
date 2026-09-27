# Public Surface and Architectural Layer Map

Status: software-candidate freeze view.

The top-level `uow` package is intentionally retained as a compatibility facade. It currently exports **200 symbols**, pinned exactly in `architecture/public_api_manifest.yaml`. Export status is a compatibility fact, not a claim that a symbol belongs to the axiomatic kernel.

## Current hierarchy

- **Semantic/core:** ontology, state, contracts, engine, application spine, authority protocols, conformance registry/adapters, transaction/OCC semantics, orchestration state/materialization, resource requirement/state, effect descriptor/certification, proposer protocol/types/judge/identity/observations, and composition contract/graph/projection/actor/binding/history/substitution/delegation/mutation semantics.
- **Implementations:** orchestration runtime, resource runtime, proposer orchestration runtime, effects runner/saga machinery, composition runtime/endurance machinery, and distributed host/fabric/convergence machinery.
- **Realizations:** deterministic/WAL/quorum commit, self-hosted/resource/heuristic/stochastic/fallback scheduling, portable/graph adaptation, network wire transport, distributed delegation, and quorum-authorized runtime mutation coordination.
- **Compatibility paths:** historical modules re-export relocated objects and retain no duplicate relocated implementation logic.

## Resolved inversions

The runtime no longer depends on qualification code for quorum authority. `QuorumCommitSequencer` depends on the semantic `QuorumAuthorityProvider` protocol. Historical runtime/proposer/composition paths are compatibility surfaces over the relocated implementations and realizations.

## Non-collapsible boundaries

`Proposal != Authorization`; `Conformance != Authorization`; `InternalCommit != ExternalEffect`; application closure is distinct from authority-formation closure; schema version, sequence, epoch, generation, and history head remain distinct; discovery is distinct from qualification; portable evidence is distinct from physical evidence.

## Qualified architecture beyond the frozen facade

The consolidated architecture now includes recursive system-as-actor composition and qualified development lines for semantic mediation, machine-readable design/policy state, polyglot/runtime-substrate conformance, and governed lifecycle semantics. These layers may advance independently of the compatibility facade and do not become top-level public API unless explicitly promoted.

### Bounded Semantic Mediation Subsystem (`uow.semantic`)

- **Surface status:** Qualified namespaced surface exporting 49 symbols via `uow.semantic.__all__`.
- **Top-level status:** Intentionally not flattened into the frozen top-level facade (`src/uow/__init__.py`), strictly preserving the 200-symbol baseline.
- **Invariants upheld:**
  - $\beta_D = 0$ (Deterministic primacy: probabilistic output cannot overwrite deterministic state).
  - $U_{\text{system}} = 0.0\%$ (Probabilistic mistakes intercepted before UoW preparation).
  - $\text{resolved}_t \cap F_{P, t+1} = \emptyset$ (Residual frontier isolation).
  - $\text{ClarificationContext} \neq \text{WorldState}$ (Zero direct execution authority).
  - $\text{parse}(\text{render}(I_B)) \equiv I_B$ ($\epsilon_{\text{egress-drift}} = 0.0$; deterministic fallback on drift).
- **Realization isolation:** Heavy neural model backends (Transformers / PyTorch / PEFT) are isolated behind lazy imports in `uow.semantic.adapters.huggingface`.

## Forward-compatibility rule

The candidate does not declare Python enums, dataclasses, class names, module paths, qualification harnesses, or research terminology to be the permanent universal ontology. Future ontology evolution must preserve versioning, authority, migration lineage, compatibility/rejection rules, reconstruction of prior semantics, and the invariant separation between proposal, certification, and authoritative commit.
