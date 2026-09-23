# Attestation Taxonomy — Draft

The repository contains many objects called certificate, vote, receipt, or evidence. They share structure but not authority semantics.

R2 defines a common family without flattening the subtypes.

## Common Attestation fields

attestation_id
attestation_kind
issuer_identity
subject_identity
contract_or_policy_identity
causal_context
decision_or_claim
evidence_profile
proof/signature reference

## ConformanceCertificate

Claim: this candidate satisfies / does not satisfy the specified contract under the specified context.

Examples:
- core deterministic certificate;
- proposer judge certificate;
- graph replacement certificate where used as conformance.

A ConformanceCertificate does not automatically grant mutation authority.

## AuthorityVote

Claim by one qualified authority participant: I authorize / reject this exact candidate under this exact causal context.

A vote MUST bind:
- voter identity;
- candidate identity;
- context;
- decision.

## QuorumAuthorization

Threshold aggregate over distinct qualified authority votes.

It MUST preserve:
- threshold;
- voter distinctness;
- voter qualification;
- candidate/context equality;
- signature/proof validity.

A raw count of duplicate votes is insufficient.

## DelegationGrant

Transfers a bounded subset of authority/work scope from issuer to delegate.

Invariant: Scope_child subset-of Scope_parent.

It MUST include expiry/freshness or causal scope where required.

## ExternalReceipt

Observation/attestation that an external action occurred or produced a result.

It MUST bind to:
- effect identity;
- idempotency identity;
- expected external source/signer where required;
- response payload identity.

An ExternalReceipt is evidence about external reality, not authority to rewrite internal history arbitrarily.

## Evidence observation

Certified learning feedback and telemetry may be evidence but do not automatically belong in the authority hierarchy.

Examples:
- AdaptationObservation;
- execution telemetry.

They may train proposal systems while preserving zero mutation authority.

## Open question

Whether all attestations should share one wire envelope is an implementation/interoperability question for R5, not an R2 semantic requirement.
