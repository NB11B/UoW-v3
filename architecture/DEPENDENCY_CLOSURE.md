# Dependency and Closure Map

## Current semantic dependency hypothesis

```text
Ontology O
   |
   v
Work Contract U
   |
   +--> Requirements Q -------------------+
   |                                      |
   v                                      v
Authoritative State S                Realization R
                                          |
                                          v
                                      Binding B
                                          |
                        +-----------------+
                        v
                    Proposal P
                        |
                        v
                  Conformance C
                        |
                        v
                    Authority A
                        |
                        v
              Authorized Transition Delta
                   /             \
                  v               v
          State S(t+1)       External Effect F
                  \               /
                   +-------> Evidence E
```

## Current source mapping

- `ontology.py`: semantic work classification.
- `state.py`: canonical authoritative state.
- `contracts.py`: native work/transition contract.
- `engine.py`: core proposal, certification, commit, evidence.
- `transactions/`: footprints, OCC conformance, commit realizations.
- `orchestration/`: state projection and higher-order operation -> UoW materialization.
- `resources/`: requirement/capability specialization and scheduling realizations.
- `effects/`: external effect boundary, receipts, reconciliation, compensation.
- `proposer/`: non-authoritative candidate generation and certified feedback.
- `composition/`: parent requirements, realization graphs, actors, bindings, projection, distributed history, governed mutation, adaptation.

## Demonstrated partial closure

Higher-order operations already lower to ordinary UoWs in:
- scheduler materialization;
- completion materialization;
- resource-aware dispatch/completion;
- effect intent/result state transitions;
- saga state transitions.

This supports the hypothesis:

[
\text{derived runtime operation} \rightarrow U_{operation}
]

## Open closure question

A2 operations are still represented in a parallel meta-ontology:

- graph substitution;
- actor rebinding;
- delegation;
- distributed history;
- quorum-certified runtime mutation.

The central falsification question is:

[
\boxed{M \subseteq U\;?}
]

where `M` is meta-runtime mutation.

If yes, UoW may be closed over its runtime. If no, a distinct Meta-UoW layer may be necessary.

## Requirement / capability unification question

Test whether the following are specializations of one relation:

[
Capabilities(R,S) \models Requirements(U)
]

Candidates:
- resource capacity;
- actor capability;
- authority requirement;
- dependency readiness;
- OCC compatibility;
- timing;
- evidence level;
- failure semantics.

## Known dependency issue

`src/uow/proposer/quorum_sequencer.py` depends on `qualification.distributed_authority.authority`.

This is a derived-runtime -> qualification dependency inversion and should be treated as evidence of a missing authority realization protocol/specification. Do not refactor it until the preservation ledger identifies every distributed-authority capability it carries.
