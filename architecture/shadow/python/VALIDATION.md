# R4 Validation Record

## U1-U10
Shadow runs 23 and 24: PASS.

## U11
Shadow runs 25 and 26: PASS.

## U12
Commit 799e294 — shadow runs 27 and 28: PASS.

Preserved:
- actual parallel worker preparation;
- OCC disjoint compatibility;
- read/write, write/write, and hidden-coupling hazards;
- atomic reject/no dirty second mutation;
- timing entropy invariance;
- deterministic evidence replay.

Architectural result:
- a transaction can remain causally valid after the whole state hash changes when OCC proves its typed read/write/coupling snapshot is still compatible;
- the reduced architecture therefore needs typed causal contexts, not only one global state-hash freshness predicate.

## U13 next

Resource-aware orchestration reconstruction:
- retain current resource requirement and materialization semantics as oracles;
- exclude run_resource_orchestration and DeterministicSequencer;
- apply scheduler/domain/completion UoWs through minimal shadow authority;
- preserve leased vs consumable distinction;
- preserve over-allocation and forged-requirement controls;
- preserve alternate scheduling policies as distinct valid realizations.
