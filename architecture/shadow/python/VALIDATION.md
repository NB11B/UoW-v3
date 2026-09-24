# R4 Validation Record

## Through A2.7

Shadow runs 55/56 pass A2.6 and A2.7 in addition to the prior reconstructed stack.

A2.6 is preserved as retained realization capability:
- wire authentication/tamper rejection;
- duplication/idempotency;
- reordering/asymmetric partition;
- WAL crash/restart;
- idempotency across restart;
- clock-skew independence.

A2.7 preserves vote/QC formation while replacing mutation application with the minimal shadow authority transition.

## A2.8 capstone now under test

The reconstructed runtime does not instantiate canonical EnduranceAdaptiveRuntime and does not call PhysicalHostNode.apply_mutation_qc.

It preserves the original experiment's:
- ParentContract / SemanticProjection criteria;
- RuntimeObjectiveFunction;
- ContinuousPerturbationTrace;
- AntiThrashingHysteresis;
- RuntimeMutationProposal and signed vote/QC formation;
- Fixed B0 and rule-based B1 controls;
- TopologyLineage;
- optional DurableWAL persistence.

The authority-changing step is reconstructed:

proposal
-> independent mutation votes
-> RuntimeMutationQC
-> exact QC/context/candidate verification
-> minimal distributed-quorum authorization
-> shadow AuthorizedTransition
-> topology lineage + authoritative history.

The 40-step seed-42 test requires exact two-decimal parity with the original reported costs:
B0 8299.78
B1 5934.51
A2 5907.99

The test also retains poisoning, hysteresis, duplicate protection, lineage, semantic projection, and WAL replay controls.
