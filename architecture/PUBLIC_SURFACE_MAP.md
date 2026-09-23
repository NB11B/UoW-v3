# Public Surface and Architectural Layer Map

Baseline: `main@f4dc767322233cd3bd9afc6c1b7af45a3987111d`.

## Observation

The filesystem has meaningful subsystem boundaries, but the top-level `uow` public API re-exports nearly all layers:

```text
primitive kernel
+ orchestration
+ transactions
+ resources
+ effects
+ proposer/adaptation
+ distributed quorum
+ A2 composition
+ A2 physical host/network
+ A2 endurance controls
```

This was useful during rapid research integration, but the public surface does not currently encode the recovered architectural hierarchy.

## Current package surfaces

### `uow`

Exports:
- primitive ontology/state/contracts/engine;
- transaction and persistence realizations;
- orchestration/materialization;
- resources and scheduling policies;
- external effects and sagas;
- proposer/adaptation interfaces and implementations;
- quorum commit implementation;
- complete A2 composition surface, including experimental/runtime/qualification-oriented types.

Architectural interpretation:

[
Public(uow) supset Kernel cup Derived cup Realizations cup A2
]

This is not evidence that all exported symbols are axiomatic.

### `uow.transactions`

Relatively coherent capability surface:
- transaction descriptors;
- OCC;
- commit sequencer protocol;
- deterministic and WAL commit realizations.

Potential future architectural split:
- semantic transaction/conformance contract;
- commit realizations.

### `uow.orchestration`

Contains:
- orchestration state projection;
- materialization/closure protocol;
- scheduler/completion realizations;
- orchestration execution helpers.

This package already reflects the closure architecture better than the top-level API.

### `uow.resources`

Contains both:
- semantic resource requirement/capability structures;
- scheduling realization policies;
- resource-aware runtime materializers.

Potential future split is driven by requirement/capability experiments, not file aesthetics.

### `uow.effects`

Contains:
- external-effect contracts;
- receipt/authentication conformance;
- external client realization;
- saga compensation.

The external-effect boundary should remain visible in any future organization because Q1 establishes that external effect != internal commit.

### `uow.proposer`

Contains:
- zero-authority proposer protocol;
- proposal/certificate data;
- deterministic judge;
- stochastic/heuristic/adaptive implementations;
- deterministic fallback;
- quorum commit realization.

The quorum sequencer's dependency on `qualification.distributed_authority` is the major layer inversion.

`TFWRProposer` is exported through a backwards-compatibility alias module. That makes `proposer/learned.py` ineligible for deletion without an API compatibility decision.

### `uow.composition`

Exports essentially the full A2 research/runtime stack:
- parent contract;
- graph/projection;
- actors/bindings;
- adaptive policy;
- substitution;
- runtime;
- fabric;
- delegation;
- convergence;
- wire;
- host durability;
- quorum runtime mutation;
- endurance controls/baselines.

Architectural interpretation:

A2 currently combines at least four conceptual categories:
1. semantic specification;
2. realization/binding;
3. distributed protocols/authority;
4. experiment/control instrumentation.

A later repository reorganization should separate these only after reconstruction proves the boundaries.

## Preservation constraints on future API reorganization

1. Do not infer axiomatic status from top-level export status.
2. Existing public aliases require compatibility treatment even if implementation is redundant.
3. Experiment-only/control realizations such as B0/B1 may move organizationally but must remain reconstructable.
4. Physical/portable qualification types may be separated from semantic specs only if experiment manifests retain their evidence linkage.
5. Any breaking public API restructure belongs in R7, after R4/R5 reconstruction and cross-language conformance.

## Target principle

Eventually:

```text
uow spec / semantic kernel
        |
        +-- derived capabilities
        |
        +-- realization interfaces
              |
              +-- Python realizations
              +-- C++/embedded realizations
              +-- hardware integrations
```

The exact Python import surface is deliberately not designed yet.
