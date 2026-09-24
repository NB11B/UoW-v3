# R7 Frozen-Oracle Gate Map

R7 cutover is now constrained by three qualified reference layers plus one conceptual frontier:

1. A2 portable reconstructed experiment chain.
2. A3 adaptive compute efficiency.
3. Policy Orchestrator P1-P5.
4. A4 ontology adaptation — conceptual/unqualified only.

## Structural consequence

The P1-P5 oracle makes **policy** a first-class semantic concept in the target repository.

The target specification therefore contains distinct surfaces for:

- ontology;
- contracts;
- state;
- requirements;
- conformance;
- policy;
- authority;
- transition;
- effects;
- evidence;
- wire/identity profiles.

Policy is not reducible to either:
- a proposer;
- a scheduler;
- a device binding;
- an authority certificate.

It is the qualified, versioned mapping between requirements/world context and permitted realization behavior.

## Cutover rule

A production move is not eligible merely because R4 portable experiments reconstruct.

It must also show that the target layout can represent every A3 and P1-P5 gate assigned in `experiments/reference-oracles/gate_map.yaml`.

A4 does not add a passed gate. It adds a prohibition against freezing today's implementation vocabulary into the cross-language ontology.

## Evidence discipline

P1-P5 is downstream of A3.

Therefore:
- inherited A3 artifacts satisfy shared evidence dependencies;
- they are not counted twice as independent evidence;
- P1-P5-specific policy lifecycle/authority/recovery evidence remains separately required.
