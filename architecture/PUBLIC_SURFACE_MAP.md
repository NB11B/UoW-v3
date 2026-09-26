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

## Forward-compatibility rule

The candidate does not declare Python enums, dataclasses, class names, module paths, qualification harnesses, or research terminology to be the permanent universal ontology. Future ontology evolution must preserve versioning, authority, migration lineage, compatibility/rejection rules, reconstruction of prior semantics, and the invariant separation between proposal, certification, and authoritative commit.
