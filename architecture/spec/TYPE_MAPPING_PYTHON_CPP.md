# Python / Embedded C++ Semantic Type Mapping

## Scope

This mapping compares current canonical Python core types with the existing embedded C++ qualification implementation.

It is not a claim that every Python/A2 object already has a C++ equivalent. The C++ implementation currently covers a narrower authority-kernel subset.

## Core mapping

| Semantic object | Python | Embedded C++ | Current conformance interpretation |
|---|---|---|---|
| Authoritative state | WorldState | State | L0/L1 strongly represented; byte identity differs |
| Work/transition program | UoW + Contract/Route | Program + Instruction | L0 semantic mapping for Minsky qualification |
| Proposal | Proposal | Proposal | Same authority role: non-authoritative candidate |
| Conformance certificate | CertificateResult | Certificate | Same independent-recomputation role |
| Authorized commit result | commit return state/evidence | StepResult | Same semantic state/evidence boundary |
| Evidence entry | EvidenceRecord | EvidenceRecord | Same causal chain role |
| Evidence lineage store | EvidenceLedger | EvidenceLedger | Same append/verify/root role |
| Local timing observation | Timing / external local timing tests | LocalClock | Local clock does not grant authority |

## State field mapping

### Python WorldState

- attributes
- cursor
- status
- sequence
- state_hash

### C++ State

- r0
- r1
- pc
- sequence
- halted

Interpretation:

The C++ fields r0/r1/pc/halted are a domain-specific realization of Python's more generic semantic payload/cursor/status.

The shared semantic coordinate is sequence-like causal progression, but its exact update semantics must be compared per experiment rather than assumed identical from field name alone.

## Proposal mapping

### Python core Proposal

- uow_id
- pre_state_hash
- selected_route_index
- proposed_state
- selected_successor
- halted

### C++ Proposal

- pre_state_hash
- proposal_hash
- proposed
- selected_pc
- halted
- proposer_clock (observational only)

Shared semantics:
- bind to a pre-state;
- propose one deterministic successor;
- expose route/control choice;
- carry zero authority.

Difference:
- C++ carries proposal_hash directly;
- Python core certificate hash is built from canonical proposal semantics rather than a Proposal-owned hash field.

R2 therefore treats "proposal identity" as semantic, not tied to where an implementation stores the digest.

## Certificate mapping

### Python CertificateResult

Binds:
- UoW identity;
- pre-state;
- proposed-state identity;
- selected route;
- successor;
- halt decision;
- acceptance/rejection reason.

### C++ Certificate

Stores:
- valid flag;
- rejection reason;
- certificate hash.

The C++ certificate hash is computed over the proposal identity and decision/reason.

Therefore both implement ConformanceCertificate semantics, but they do not currently expose the same wire payload shape.

## Evidence mapping

Both implementations record:
- causal step/order;
- pre-state identity;
- post-state identity;
- certificate/conformance identity;
- previous evidence link;
- current record identity.

Python additionally records semantic work classification and successor pointer.

C++ additionally records proposal hash directly.

R2 conclusion:
- L2 evidence-semantic conformance is plausible and testable.
- L4/L5 canonical-byte/hash equality is not currently established.

## Reject-reason mapping candidates

| Semantic invariant | Python examples | C++ reason |
|---|---|---|
| stale pre-state | PRE_STATE_HASH_MISMATCH | STALE_PRE_STATE |
| proposed-state divergence | STATE_DIVERGENCE | STATE_DIVERGENCE |
| route/control divergence | ROUTE_DIVERGENCE / successor divergence | ROUTE_DIVERGENCE |
| halt divergence | HALT_DIVERGENCE | HALT_DIVERGENCE |
| proposal identity corruption | certificate/proposal binding checks | PROPOSAL_HASH_DIVERGENCE |

Exact strings are not required for L1; invariant class equivalence is.

## Objects currently Python-only in canonical main

No equivalent embedded C++ semantic mapping is yet claimed for:
- generic resource requirements/leases;
- external effects/sagas;
- adaptive model identity/observations;
- A2 ParentContract;
- RealizationGraph;
- ActorDescriptor / ActorBinding;
- DelegationCertificate;
- AuthoritativeHistory;
- RuntimeMutationProposal / RuntimeMutationQC;
- A2.8 endurance controls.

These become later cross-language candidates only if a concrete implementation is created.

## R3 implication

The first shadow implementation should target only the shared authority-kernel subset:

State -> Proposal -> Conformance -> AuthorizedTransition -> Evidence.

That is the highest-confidence cross-language semantic core already demonstrated by two implementations.
