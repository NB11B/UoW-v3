# Requirement <-> Capability Unification Falsification Matrix

## Research question

Can apparently separate legality systems be represented as typed specializations of:

[
\operatorname{Capabilities}(R,S) \models \operatorname{Requirements}(U)
]

without losing domain-specific correctness?

A successful common ontology must preserve specialized predicates. It must not reduce all checks to untyped key/value matching.

## Candidate common structure

A requirement has:
- semantic kind;
- subject/work identity;
- required value or predicate;
- scope;
- causal context;
- evidence level;
- failure behavior.

A capability has:
- semantic kind;
- actor/realization/state source;
- offered value or predicate;
- qualification/evidence;
- availability/freshness context.

A matcher returns a typed conformance result and evidence.

## Matrix

| Domain | Existing requirement | Existing capability/context | Current validator | Proposed common relation | Falsification test | Status |
|---|---|---|---|---|---|---|
| Resource capacity | `ResourceRequirement` | `ResourceState.available` | `can_accommodate` | quantitative capacity >= demand | demand exceeds one dimension while others pass | STRONG CANDIDATE |
| Resource consumable budget | energy/cost demand | remaining budget | `can_accommodate` | consumable capability >= required budget | lease capacity fits but cost/energy fails | STRONG CANDIDATE |
| Actor functional capability | `required_capabilities` | `ActorDescriptor.capabilities` | `validate_binding` | required set subset offered set | actor lacks exactly one capability | STRONG CANDIDATE |
| Actor authority | `required_authority_class` | qualified actor authority | `validate_binding` / fabric qualification | ordered authority lattice satisfies minimum | self-advertised authority without trust root | STRONG CANDIDATE with qualification dimension |
| Actor liveness | bound actor required now | availability + valid lease | `validate_binding` | capability must be fresh/available | descriptor valid but lease expired | STRONG CANDIDATE with causal freshness |
| Dependency readiness | task prerequisites | completed authoritative set | proposer judge / orchestration state | prerequisite set subset completed set | task exists but dependency incomplete | STRONG CANDIDATE |
| OCC read freshness | read versions | current variable versions | `validate_occ` | state compatibility predicate | stale read only | STRONG CANDIDATE but relational |
| OCC write exclusivity | write versions/couplings | current versions/couplings | `validate_occ` | non-conflict predicate | hidden coupling changed without direct key change | STRONG CANDIDATE but relational |
| Temporal deadline | max duration/deadline | graph critical path / causal epoch | semantic projection | measured time <= bound | all other obligations pass but critical path exceeds bound | STRONG CANDIDATE |
| Evidence requirement | provenance/hash-chain/evidence level | node/effect/authority evidence | semantic projection / receipt verification | offered evidence >= required evidence | correct output but missing provenance | STRONG CANDIDATE |
| Failure semantics | rollback/compensate/fail-closed | realization failure behavior | semantic projection / saga/effect logic | realization failure contract refines required failure contract | output correct but realization allows partial commit | STRONG CANDIDATE |
| Semantic output | required outputs | graph emitted outputs | semantic projection | offered postconditions cover required postconditions | graph omits one required output | STRONG CANDIDATE |
| Causal ordering | predecessor -> successor | graph reachability | semantic projection | realization order satisfies causal constraint | reversed path with same final output | STRONG CANDIDATE |
| Quorum threshold | minimum independent authority votes | distinct valid votes | QC verification | qualified authority cardinality >= threshold | duplicate voter identities meet raw count | STRONG CANDIDATE with distinctness predicate |
| Delegation authority | child requested scope | parent authority scope | `validate_delegation` | child scope subset parent scope | delegate one permission parent lacks | STRONG CANDIDATE |
| External receipt authenticity | expected effect/idempotency/signer | observed receipt | effect certification | receipt evidence satisfies effect observation requirement | valid-looking receipt bound to wrong effect/key | CANDIDATE, external boundary |
| Idempotency | stable work/effect identity | prior committed identity | effects/convergence/delegation logic | duplicate realization maps to existing authoritative result | same semantic work with altered idempotency identity | CANDIDATE, not universal requirement |

## Falsification criteria for unification

The common model fails if any of the following occur:

1. **Loss of type semantics:** a numeric resource requirement can be accidentally satisfied by a string/set capability with matching label.
2. **Loss of relational semantics:** OCC hidden coupling cannot be represented without bypassing the common matcher.
3. **Loss of qualification:** self-advertised authority satisfies the same relation as trusted authority.
4. **Loss of causal freshness:** expired/stale capability satisfies a timeless requirement.
5. **Loss of failure semantics:** matching only pre-execution capability ignores rollback/compensation requirements.
6. **Loss of evidence provenance:** correct values satisfy requirements despite insufficient evidence level.
7. **Over-generalization cost:** common abstraction requires more special-case branching than current typed validators.

## Proposed language-neutral shape

Do not implement yet. A potential typed model is:

```text
Requirement<T> {
  kind
  predicate(T offered, Context c) -> Conformance
  evidence_requirement
  freshness_requirement
  failure_requirement
}

Capability<T> {
  kind
  value: T
  evidence
  freshness
  source
}
```

The important feature is the typed predicate, not the object syntax.

## Experimental plan

Shadow adapters should wrap existing validators first:
- resource adapter delegates to `can_accommodate`;
- actor adapter delegates to `validate_binding`;
- OCC adapter delegates to `validate_occ`;
- projection adapters delegate to current semantic projection checks.

Only after matched positive and negative controls produce identical decisions should shared logic be extracted.

This makes unification an empirical equivalence exercise rather than a rewrite.
