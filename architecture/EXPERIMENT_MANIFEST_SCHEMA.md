# Experiment Reconstruction Manifest Schema

Every preserved experiment should eventually have a machine-readable manifest.

The manifest describes semantics, not a particular test runner.

## Required fields

```yaml
experiment:
  id: U12
  name: transactional-concurrency
  lineage:
    source: current|archive
    commit: <sha>

requires:
  axioms: []
  structural_laws: []
  capabilities: []

realizations:
  <semantic role>: <realization id>

negative_controls:
  - id: <control>
    expected_rejection: <reason or invariant>

evidence:
  minimum_level: SIMULATED|PORTABLE|PHYSICAL
  required_components: []
  artifacts: []

assertions:
  - <machine-checkable semantic assertion>

reconstruction:
  status: UNMAPPED|MAPPED|RECONSTRUCTED|BLOCKED
  implementation_targets: []
```

## Reconstruction rule

An experiment is reconstructed only when:
1. every required invariant has a mapped implementation;
2. every required realization exists or has an explicitly qualified substitute;
3. every negative control can still be forced through the actual boundary;
4. every assertion passes;
5. evidence level is not silently downgraded.

## Cross-language extension

A manifest may declare several implementation targets:

```yaml
reconstruction:
  implementation_targets:
    - python
    - cpp
    - rust
```

Semantic conformance and byte/wire conformance are separate requirements.

```yaml
cross_language:
  semantic_conformance: required
  canonical_byte_conformance: optional|required
```
