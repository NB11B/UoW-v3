# R3 Shadow Minimal Implementation Plan

## Purpose

Implement the R2 semantic model beside the existing runtime without changing current production behavior.

The shadow layer exists to answer:

Can the recovered minimal semantic architecture reproduce current decisions and evidence before any refactor?

## Location

Proposed research-only location:

architecture/shadow/python/

The shadow implementation is not imported by src/uow and is not part of the public API.

## Stage R3.0 — semantic data types

Implement shadow representations for:
- AuthoritativeStateRef
- SemanticContractRef
- Requirement / Capability
- ProposalEnvelope
- ConformanceResult
- Attestation variants
- EvidenceEntry
- RealizationRef
- BindingRef
- ExternalEffectRef

These initially wrap or reference existing objects. They do not replace them.

## Stage R3.1 — adapter conformance

Create adapters around existing validators:
- core certify
- validate_occ
- verify_requirement_binding / ResourceState.can_accommodate
- validate_binding
- project_semantics / check_conformance
- validate_delegation
- verify_mutation_vote / verify_mutation_qc
- verify_effect_receipt_binding

The shadow matcher must reproduce existing decisions.

No validator logic is extracted yet.

## Stage R3.2 — closure shadow operations

Implement non-authoritative shadow lowerings for:
- actor rebinding
- graph substitution
- delegation issuance
- delegation retry/recovery state
- runtime mutation QC application
- actor lease lifecycle
- model generation promotion

Each shadow operation is compared with the current path using architecture/conformance/closure_vectors.yaml.

## Stage R3.3 — requirement/capability shadow matcher

Implement typed matcher kinds:
- set inclusion
- ordered lattice
- quantitative minimum/maximum
- relational compatibility adapter
- qualified capability
- fresh capability
- K-of-N quorum
- conditional / one-of

First implementation delegates specialized predicates to current validators.

## Stage R3.4 — first minimal authority kernel

Only after adapters match, implement the highest-confidence shared kernel:

AuthoritativeState
  -> Proposal
  -> Conformance
  -> Authorization
  -> AuthorizedTransition
  -> Evidence

Compare against:
- Python core;
- embedded C++ semantic vectors.

## Constraints

1. No src/uow imports from architecture/shadow.
2. No current runtime code removed or changed for R3.0-R3.3.
3. Shadow objects may reference current objects but not mutate them.
4. Every shadow decision must identify the current validator/oracle used.
5. Differences are findings, not bugs to normalize away automatically.
6. No physical evidence claim is upgraded by shadow parity.

## Exit criterion

R3 is successful enough to enter R4 when:
- shadow schemas instantiate all required experiment inputs;
- matched requirement/capability vectors agree with current validators;
- initial closure vectors produce either equivalence or explicit constructive non-closure;
- the minimal authority kernel passes semantic parity against the canonical Python path;
- failures/open meta-primitives are documented rather than hidden.
