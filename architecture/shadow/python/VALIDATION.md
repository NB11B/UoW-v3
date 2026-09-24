# R4 Validation Record

## Passing reconstructed families

U1-U10, U11, U12, U13, U14, U14-B, Q1, and U15.1-U15.4 portable are passing on the shadow reconstruction workflow.

## Distributed-authority first attempt

Runs 43/44 failed during test collection, before any authority assertion.

Cause:
qualification.distributed_authority.authority imports uow.contracts.
Importing uow initializes uow.proposer.quorum_sequencer, which imports
qualification.distributed_authority.authority again.

This is the runtime -> qualification dependency inversion already identified in R1.

## Layering correction

The shadow portable distributed-authority reconstruction now defines its own:
- AuthorityVote semantic object;
- QuorumCertificate semantic object;
- vote grouping / threshold QC formation;
- deterministic faultable network fabric;
- independent authority replicas.

These are reconstructed from the R2 semantic/attestation model and current qualified behavior, not imported from qualification packaging.

State application remains:
QC verification -> distributed quorum authorization profile -> minimal shadow AuthorizedTransition -> independent evidence lineage.

This correction is architecturally preferable to working around the import cycle because it tests the intended language-neutral boundary directly.
