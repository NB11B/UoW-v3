# UoW Language-Neutral Semantic Specification — Draft R2

Status: research draft.

This directory does not replace the Python API. It describes the smallest semantic objects and relations currently implied by the UoW experiment history.

The specification is representation-independent. Python classes, C++ structs, JSON, SHA-256, HMAC, OpenVINO, sockets, WAL files, and MCU protocols are implementations or profiles unless explicitly stated otherwise.

## Design constraints

1. Preserve the primitive native UoW transition algebra.
2. Preserve A2's separation of semantic intent from realization and binding.
3. Preserve proposal != authority.
4. Preserve Q1's external-effect boundary.
5. Preserve causal freshness and evidence lineage.
6. Allow multiple languages and substrates to implement the same semantics.
7. Do not collapse semantically distinct certificate/authority types merely because they share fields.
8. Do not require byte-identical serialization unless a boundary declares that conformance level.
9. Keep higher-order closure an empirical question until R3/R4 tests it.

## Semantic object families

SemanticContract
  - TransitionContract
  - IntentContract

AuthoritativeState

RequirementSet <-> CapabilitySet

Realization
Binding
Proposal
ConformanceResult

Attestation
  - ConformanceCertificate
  - AuthorityVote
  - QuorumAuthorization
  - DelegationGrant
  - ExternalReceipt

AuthorizedTransition
ExternalEffect
EvidenceEntry
Lineage

## Core relation

Contract -> Requirements -> Realization -> Binding -> Proposal -> Conformance -> Authority -> Transition -> Evidence

Adaptation may select or learn over Realization and Binding, but does not receive mutation authority.

## Contract layers remain distinct in R2

The canonical native UoW and A2 ParentContract are not forcibly merged.

R2 represents both beneath a common SemanticContract concept:

- TransitionContract: deterministic state-transition semantics, corresponding to the native UoW core.
- IntentContract: realization-invariant semantic obligations, corresponding to A2 parent intent.

R3/R4 closure tests will determine whether these can safely collapse further.

## External effects remain first-class

InternalTransition != ExternalEffect

An external action may be governed by UoW intent/receipt transitions, but the physical action itself is not modeled as an ordinary reversible internal state mutation.

## Normative vocabulary

In these draft documents:
- MUST identifies a candidate invariant required by existing experiments.
- MAY identifies a valid realization choice.
- OPEN identifies an unresolved research question.

These terms are provisional until reconstruction confirms them.
