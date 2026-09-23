# R2 Language-Neutral Specification Acceptance Checklist

R2 is specification work only. It does not authorize runtime refactoring.

## Semantic coverage

- [x] Authoritative state family defined.
- [x] TransitionContract and IntentContract kept distinct.
- [x] Typed requirements/capabilities defined.
- [x] Realization and Binding defined.
- [x] Proposal defined as zero-authority candidate.
- [x] ConformanceResult separated from Authorization.
- [x] Attestation taxonomy defined.
- [x] AuthorizedTransition defined.
- [x] ExternalEffect preserved as separate boundary.
- [x] Evidence/Lineage model defined.
- [x] Schema version separated from causal coordinates.

## Versioned schema candidates

- [x] state.v0.1
- [x] contract.v0.1
- [x] proposal.v0.1
- [x] conformance.v0.1
- [x] attestation.v0.1
- [x] evidence.v0.1
- [x] realization_binding.v0.1
- [x] external_effect.v0.1
- [x] requirement_capability.v0.1

## Implementation mappings

- [x] Python current baseline mapping.
- [x] Embedded C++ current baseline mapping.
- [x] Python/C++ semantic comparison.
- [x] Cross-language conformance levels defined.
- [x] Canonicalization profile concept defined.

## Open research questions intentionally unresolved

- [ ] Can IntentContract always lower to TransitionContract?
- [ ] Can graph substitution lower to ordinary UoW?
- [ ] Can actor rebinding lower to ordinary UoW?
- [ ] Can delegation lower to ordinary UoW without authority leakage?
- [ ] Can runtime mutation QC application lower to ordinary UoW?
- [ ] Is quorum attestation formation itself a meta-layer primitive?
- [ ] Which cross-language authority objects require L4/L5 identity equality?

These questions belong to R3/R4 experiments, not to R2 specification fiat.

## R2 exit rule

R2 is complete when:
1. the semantic model is versioned;
2. current Python and C++ implementations can be mapped without semantic contradiction;
3. every object required by R3 shadow experiments has a draft schema;
4. no unresolved question is being silently answered by schema design;
5. no source runtime/API/deletion has occurred.

R2 completion authorizes R3 shadow implementation only on the research branch.
