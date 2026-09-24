# R6 Reduction Eligibility Exit Record

Control baseline: `main@f4dc767322233cd3bd9afc6c1b7af45a3987111d`.

Latest shadow runs 75/76: PASS. Latest suite: **157 passed in 5.86s**.

## Validated K3 prototypes

### Common authority application spine

The reconstructed runtime now uses one research-only application spine:

`UoW -> Proposal -> Conformance -> Authorization -> AuthorizedTransition -> Evidence`

It preserves two execution contexts: `OWNED` for cursor-owned work and `DETACHED` for certified control-plane bookkeeping such as Q1 effect/saga state.

### Qualification-independent authority provider

The shadow quorum layer now depends on the semantic operations `collect_votes`, `form_authorization`, and `apply_authorization`, rather than importing qualification implementations.

### Typed conformance registry

Nine specialized domains now share one invocation interface while retaining their original validators: resource capacity, resource binding, OCC, actor binding, semantic projection, delegation, external receipts, mutation votes, and mutation QC.

## Measured reduction opportunity

- proposal formation appears in 11 source modules;
- core certification in 7;
- transaction descriptor construction in 6;
- sequencer commit in 5 high-level modules;
- materialization certification in 4;
- actor-binding validation in 5;
- semantic projection in 4.

The full proposal/certify/transaction/commit orchestration is independently present in orchestration/runtime, proposer/engine, resources/runtime, effects/runner, and effects/saga.

## Eligibility result

- K0 retain axiomatic: state, contracts, proposal, conformance, authorization, transition, evidence, external-effect boundary.
- K1 retain realizations/evidence: deterministic/WAL/quorum commit, lineage stores, A2.6 network/durability, baselines, adversarial controls, U14-B, U12 threaded realization, physical implementations, compatibility aliases.
- K2 consolidate interfaces/schema only: identity metadata, serialization/schema generation, lineage families.
- K3 validated shadow-refactor eligible: application spine, authority-provider protocol, typed conformance registry.
- K4 delete eligible: **none**.

## Conclusion

R6 supports interface and control-flow consolidation, not feature elimination. R7 may begin as an additive structural migration with no production file moves or deletions until the reconstructed suite passes against the parallel organization.