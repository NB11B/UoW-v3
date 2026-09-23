# Typed Requirement / Capability Model — Draft

## Core relation

Capabilities(R,S) satisfy Requirements(U).

This is a typed conformance relation, not generic dictionary matching.

## Requirement

Conceptual shape:

Requirement<T>
- requirement_id
- kind
- predicate(offered: T, context) -> ConformanceResult
- evidence_requirement
- freshness_requirement
- failure_requirement

## Capability

Conceptual shape:

Capability<T>
- capability_id
- kind
- offered_value: T
- source_identity
- qualification
- freshness
- evidence

## Required specialization classes

### Set inclusion

Used for:
- actor functional capabilities;
- dependency completion sets;
- delegated permission scopes.

Required subset-of Offered.

### Ordered lattice / threshold

Used for:
- authority class;
- evidence level.

OfferedLevel must be at least RequiredLevel.

The ordering MUST be defined by the semantic profile, not by arbitrary string comparison.

### Quantitative bound

Used for:
- CPU/RAM/GPU/NPU;
- energy/cost;
- temporal budget;
- quorum threshold.

Available >= Required, or Measured <= Maximum.

### Relational compatibility

Used for:
- OCC read/write hazards;
- hidden coupling;
- causal graph ordering;
- distinct-voter quorum rules.

These cannot be reduced to independent per-field comparisons.

### Qualified capability

Used for:
- trusted authority;
- physical evidence substrate;
- signed external receipts.

A self-declared value is insufficient.

### Fresh capability

Used for:
- actor leases;
- state/graph generation;
- history head;
- proposal freshness.

A valid capability outside its causal/time scope MUST fail conformance.

## Conformance composition

A realization satisfies a contract only when every mandatory requirement is satisfied, unless the contract explicitly declares alternatives such as one-of / quorum / fallback sets.

## Alternatives and quorum

The model MUST support:
- ALL requirements;
- ANY/one-of realizations;
- K-of-N authority;
- optional requirements;
- conditional requirements.

## Failure/evidence are requirements

Failure behavior and evidence level are not post-hoc metadata.

A graph that produces the correct output but permits partial commit under a required rollback contract does not conform.

A portable result cannot satisfy a physical evidence requirement merely because outputs match.

## Preservation rule

Initial shadow implementations MUST wrap existing validators rather than replace them.

The common model is accepted only if matched vectors reproduce all current positive/negative decisions without weakening specialized semantics.
