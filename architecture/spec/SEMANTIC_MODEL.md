# Semantic Object Model — Draft

## 1. SemanticContract

A SemanticContract declares what must remain true independent of a particular implementation.

Common semantic fields:

contract_id
contract_schema
semantic_kind
requirements
failure_requirements
evidence_requirements
temporal_requirements

Two currently distinct forms are retained.

### TransitionContract

Represents deterministic state-transition work.

Corresponds to the native UoW concepts:
- identity / semantic classification;
- guarded route selection;
- state mutation;
- successor selection;
- lifecycle/boundary/evidence/timing descriptors.

Semantic relation:

TransitionContract(S_t) => S'_t+1 before authority.

### IntentContract

Represents a higher-level invariant intent that may admit several realizations.

Corresponds to A2 parent semantics:
- required outputs/postconditions;
- dependency/causal constraints;
- authority obligations;
- evidence obligations;
- temporal constraints;
- resource/safety constraints;
- failure semantics.

Semantic relation:

Realization satisfies IntentContract.

OPEN: whether IntentContract can itself always be expressed as a native TransitionContract.

## 2. AuthoritativeState

AuthoritativeState is the state accepted by the authority boundary at a causal position.

Minimum semantics:

state_identity
schema
semantic_payload
causal_coordinate
status

A proposal, observation, model state, actor descriptor, graph, or telemetry record is not authoritative merely because it is present.

Typed facets MAY project portions of state:

S -> projection_i -> S_i

Examples:
- orchestration facet;
- resource facet;
- effect facet.

A projection MUST NOT silently become a second independent authoritative state unless a contract explicitly defines a distributed-authority realization.

## 3. RequirementSet

RequirementSet contains typed predicates a realization/binding/context must satisfy.

Requirements are not restricted to scalar key/value pairs.

Examples:
- functional capabilities;
- quantitative resources;
- authority threshold;
- dependency readiness;
- OCC compatibility;
- temporal bound;
- evidence level;
- failure behavior;
- output/postcondition;
- causal order.

## 4. CapabilitySet

CapabilitySet describes what a realization, actor, authority, or current state can actually provide.

Capabilities may be:
- static;
- qualified;
- leased;
- time/freshness bounded;
- quantitative;
- relational.

Self-advertisement MUST NOT be sufficient for trusted authority capability.

## 5. Realization

A Realization describes one valid way to satisfy a SemanticContract.

It may describe:
- an algorithm;
- a graph;
- a hardware path;
- a scheduler;
- a persistence strategy;
- an authority strategy;
- a model/proposer strategy.

Valid(Realization, Contract) iff Capabilities(Realization, Context) satisfy Requirements(Contract), plus any contract-specific conformance predicates.

## 6. Binding

A Binding maps logical roles/nodes/requirements to concrete actors or substrates.

Minimum semantics:

binding_identity
realization_identity
role_to_actor
causal_context

A binding MUST be independently validated for capabilities, availability/freshness, and authority qualification.

## 7. Proposal

A Proposal is a non-authoritative candidate for execution or mutation.

Minimum semantics:

proposal_identity
proposer_identity
subject_contract
precondition_context
candidate_payload
causal_coordinate
optional predicted metrics

Invariant: Proposal != Authorization.

Proposal metadata not used for conformance MAY remain non-authority-bearing.

## 8. ConformanceResult

A ConformanceResult is the deterministic or otherwise contract-authorized evaluation of a candidate.

Minimum semantics:

subject_identity
contract_identity
context_identity
decision
violations / reason classes
conformance_evidence

Conformance MUST bind to the exact candidate and causal context it evaluated.

## 9. Attestation

An Attestation is evidence from an identified source concerning a candidate, context, authorization, delegation, or external observation.

Attestation taxonomy is defined separately.

## 10. AuthorizedTransition

An AuthorizedTransition is the authoritative application of a valid candidate to authoritative state/meta-state.

(S_t, Proposal, Conformance, Authorization) -> S_t+1

It MUST:
- be causally bound;
- be atomic with respect to its declared authority boundary;
- produce lineage/evidence;
- obey declared failure semantics.

## 11. ExternalEffect

An ExternalEffect is a requested/observed action outside authoritative internal state.

Safe governance pattern:

IntentCommit -> ExternalInvocation -> Observation -> ReceiptConformance -> ResultCommit

The external invocation itself is not assumed reversible by internal rollback.

## 12. EvidenceEntry

An EvidenceEntry records an authority-relevant event.

Minimum semantic content:

entry_identity
event_kind
subject_identity
causal_parent/reference
before_context
after_context or outcome
authority/conformance references
evidence_profile

Storage MAY be a linear hash chain, WAL, distributed history, model ancestry, topology lineage, or another realization satisfying the lineage semantics.

## 13. Lineage

Lineage is the causal relation among authority-relevant evidence entries.

Minimum law: Transition => Evidence.

Every authority decision MUST be traceable to the causal context for which it was valid.

A single globally linear history is not assumed by the semantic model; particular authority realizations may require one.
