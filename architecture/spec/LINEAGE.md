# Evidence and Lineage Semantics — Draft

## Core law

AuthoritativeTransition => Evidence.

Authority-relevant mutation must leave enough evidence to determine:
- what was proposed;
- against which causal context;
- what conformance/authorization allowed it;
- what changed;
- what lineage preceded it.

## EvidenceEntry

Minimum semantic fields:

entry_id
event_kind
subject_id
causal_references
pre_context_identity
post_context_identity_or_outcome
proposal_reference
conformance_reference
authorization_reference
evidence_profile
issuer/source

Not every field is mandatory for every event; event schemas define requirements.

## Lineage topology

The semantic model requires causal traceability, not one universal storage topology.

Valid realizations may include:
- linear evidence chain;
- write-ahead log;
- model parent-generation chain;
- topology mutation lineage;
- distributed canonical history;
- delegation ancestry.

A realization requiring total ordering MUST declare it.

## Integrity

Where cryptographic integrity is required, lineage evidence MUST make deletion, insertion, reordering, subject substitution, and causal-context substitution detectable under the declared evidence profile.

## Recovery

A durable realization MUST define how authoritative state and lineage are reconstructed after failure.

Recovery evidence MUST distinguish:
- valid prefix/catch-up;
- torn/incomplete tail;
- stale state;
- non-prefix divergence.

## Historical evidence

Evidence profile is part of claim scope.

A new semantic implementation does not retroactively upgrade old portable evidence to physical evidence, and changing wire/hash semantics may require new physical qualification.
