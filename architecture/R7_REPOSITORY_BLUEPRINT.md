# R7 Repository Architecture Blueprint

Status: structural blueprint only. No production moves or deletions are authorized.

## Goal

Make the repository itself express the validated UoW architecture:

`Specification -> Capabilities -> Realizations -> Implementations -> Experiments -> Qualification`

while preserving historical evidence and allowing multiple languages and substrates side by side.

## Proposed repository form

```text
UoW/
|-- specification/
|   |-- ontology/
|   |-- contracts/
|   |-- state/
|   |-- identity/
|   |-- requirements/
|   |-- conformance/
|   |-- authority/
|   |-- transition/
|   |-- effects/
|   |-- evidence/
|   `-- wire/
|-- implementations/
|   |-- python/
|   |-- cpp/
|   `-- embedded/
|-- realizations/
|   |-- commit/
|   |-- scheduling/
|   |-- authority/
|   |-- persistence/
|   |-- networking/
|   |-- effects/
|   |-- concurrency/
|   |-- acceleration/
|   `-- adaptation/
|-- experiments/
|   |-- manifests/
|   |-- universality/
|   |-- self-hosting/
|   |-- concurrency/
|   |-- resources/
|   |-- proposer/
|   |-- goal-synthesis/
|   |-- external-effects/
|   |-- adaptation/
|   |-- distributed-authority/
|   `-- adaptive-composition/
|-- qualification/
|   |-- portable/
|   |-- physical/
|   |-- negative-controls/
|   `-- evidence/
|-- conformance/
|   |-- vectors/
|   |-- cross-language/
|   `-- profiles/
`-- archive/
    `-- immutable-research-lineage/
```

Exact names remain provisional; the semantic boundaries are the validated result.

## Governing rules

1. Semantic level before language: Python/C++/embedded code implements shared contracts.
2. Realizations remain plural where durability, authority, substrate, failure, performance, or evidence differs.
3. Experiments remain compositions of invariants, capabilities, realizations, controls, evidence, and assertions.
4. Qualification is downstream: runtime/specification code must not import qualification implementations.
5. Portable reconstruction never substitutes for physical evidence.
6. Existing public aliases remain through compatibility shims until an explicit API migration.

## Validated seams

### Application seam
`Proposal -> Conformance -> Authorization -> AuthorizedTransition -> Evidence`

### Conformance seam
Typed domain predicates share an invocation interface but retain specialized validators.

### Authority seam
Runtime depends on an authority-provider semantic protocol; portable, physical, and qualification implementations are realizations.

### External-effect seam
`ExternalEffect != InternalTransition` remains a first-class boundary.

## Example current-to-target semantics

| Current item | Target semantic placement |
|---|---|
| `WorldState` | specification/state + Python implementation |
| native `UoW` contract | specification/contracts/transition |
| A2 `ParentContract` | specification/contracts/intent |
| `validate_occ` | conformance realization: concurrency |
| `validate_binding` | conformance realization: actor binding |
| `DeterministicSequencer` | realization/commit/deterministic |
| `WALSequencer` | realization/commit/wal |
| `QuorumCommitSequencer` | realization/commit/quorum |
| `EffectRunner` | implementation/effects + external-effect boundary |
| `AdaptiveGraphProposer` | realization/adaptation |
| `RuntimeMutationQC` | authority attestation + Python implementation |
| ESP32/STM32 firmware | embedded implementation + physical authority realization |
| B0/B1/A2.8 controls | experiments/adaptive-composition |

## Migration stages

- R7.0: machine-readable current -> target mapping, no moves.
- R7.1: additive parallel package skeleton, no production imports change.
- R7.2: semantic facade exposing validated application/conformance/authority seams.
- R7.3: dual-layout reconstruction parity.
- R7.4: public API compatibility verification.
- R7.5: physical requalification boundary analysis.
- R7.6: cutover eligibility only after all experiment manifests reconstruct.

## Acceptance

The new organization must preserve or expand the demonstrated capability set, reconstruct every experiment, preserve evidence level, and avoid unsupported public API breaks.