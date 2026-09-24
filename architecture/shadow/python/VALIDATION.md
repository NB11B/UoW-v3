# R4 Validation Record

## Passing through A2.5

Shadow runs 53/54 pass the entire reconstructed stack through portable distributed authority and A2.0-A2.5.

A notable layering result is now demonstrated: the reconstructed portable authority protocol does not import qualification.distributed_authority. Vote/QC semantics are represented directly in the research architecture.

## A2.6

A2.6 is treated as retained realization capability, not something to collapse into the semantic kernel.

The reconstruction tests preserve:
- signed wire verification and tamper rejection;
- packet duplication plus idempotent N_commit=1;
- reorder exposure and asymmetric partitions;
- WAL fsync-backed history;
- crash/restart replay;
- delegation/task idempotency across restart;
- local wall-clock skew with generation semantics unchanged.

The claim remains PORTABLE; these tests do not upgrade it to physical evidence.

## A2.7

RuntimeMutationProposal / authority vote / RuntimeMutationQC formation remain the attestation protocol.

The authoritative topology application path is reconstructed as:

verified RuntimeMutationQC
-> exact graph/binding/context hash verification
-> distributed-quorum authorization profile
-> minimal shadow AuthorizedTransition
-> evidence

The canonical QuorumMutationCoordinator.apply_mutation and PhysicalHostNode.apply_mutation_qc paths are excluded from the reconstructed application test.
